import asyncio
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from bson import ObjectId
from temporalio.exceptions import ApplicationError

from app import temporal_workflows
from app.config import Settings
from app.temporal_activities import MaintenanceTaskActivities
from app.temporal_worker import (
    TASK_QUEUE,
    TemporalDisabledError,
    run_worker,
)


def workflow_input() -> dict[str, object]:
    return {
        "asset_id": str(ObjectId()),
        "mission_id": str(ObjectId()),
        "finding_id": "finding-1",
        "description": "Clear the drain",
        "priority": "high",
        "assignee": "Facilities",
        "due_date": None,
        "completion_notes": None,
        "evidence_refs": [],
    }


def test_workflow_executes_only_the_creation_activity(monkeypatch) -> None:
    calls = []
    result = {"task_id": "task-1", "status": "pending"}
    input_data = workflow_input()

    async def fake_execute_activity(name, input, **kwargs):
        calls.append((name, input, kwargs))
        return result

    monkeypatch.setattr(
        temporal_workflows.workflow,
        "execute_activity",
        fake_execute_activity,
    )

    actual = asyncio.run(
        temporal_workflows.MaintenanceTaskWorkflow().run(input_data)
    )

    assert actual == result
    assert calls[0][0] == "create_maintenance_task"
    assert calls[0][1] == input_data
    assert calls[0][2]["start_to_close_timeout"] == timedelta(seconds=30)
    assert calls[0][2]["retry_policy"].maximum_attempts == 3
    assert calls[0][2]["retry_policy"].non_retryable_error_types == (
        "ValidationError",
    )


def test_activity_reuses_repository_idempotency_result(monkeypatch) -> None:
    asset_id = ObjectId()
    mission_id = ObjectId()
    existing_task = {"_id": ObjectId(), "status": "pending"}

    class FakeAssetRepository:
        def __init__(self, database):
            pass

        def get(self, requested_id):
            assert requested_id == asset_id
            return {"_id": asset_id}

    class FakeMissionRepository:
        def __init__(self, database):
            pass

        def get(self, requested_id):
            assert requested_id == mission_id
            return {
                "_id": mission_id,
                "asset_id": asset_id,
                "findings": [{"id": "finding-1", "approved": True}],
            }

    class FakeTaskRepository:
        def __init__(self, database):
            pass

        def create(self, document):
            assert document["mission_id"] == mission_id
            assert document["finding_id"] == "finding-1"
            return existing_task

    monkeypatch.setattr(
        "app.temporal_activities.AssetRepository", FakeAssetRepository
    )
    monkeypatch.setattr(
        "app.temporal_activities.InspectionMissionRepository",
        FakeMissionRepository,
    )
    monkeypatch.setattr(
        "app.temporal_activities.MaintenanceTaskRepository",
        FakeTaskRepository,
    )

    result = MaintenanceTaskActivities(SimpleNamespace()).create_maintenance_task(
        {
            **workflow_input(),
            "asset_id": str(asset_id),
            "mission_id": str(mission_id),
        }
    )

    assert result == {"task_id": str(existing_task["_id"]), "status": "pending"}


def test_activity_marks_invalid_input_non_retryable() -> None:
    with pytest.raises(ApplicationError) as error:
        MaintenanceTaskActivities(SimpleNamespace()).create_maintenance_task(
            {**workflow_input(), "asset_id": "not-an-object-id"}
        )

    assert error.value.non_retryable is True
    assert error.value.type == "ValidationError"


def test_worker_refuses_to_start_when_temporal_is_disabled() -> None:
    with pytest.raises(TemporalDisabledError, match="TEMPORAL_ENABLED=true"):
        asyncio.run(run_worker(Settings(temporal_enabled=False)))


def test_worker_uses_expected_task_queue() -> None:
    assert TASK_QUEUE == "rainguard-maintenance"


def test_worker_registers_sync_activity_with_thread_pool(monkeypatch) -> None:
    captured = {}

    class FakeConnection:
        def __init__(self, settings):
            self.database = SimpleNamespace()

        def connect(self):
            return None

        def close(self):
            captured["connection_closed"] = True

    class FakeClient:
        pass

    class FakeWorker:
        def __init__(self, client, **kwargs):
            captured.update(kwargs)

        async def run(self):
            return None

    async def fake_client(settings):
        return FakeClient()

    monkeypatch.setattr(
        "app.temporal_worker.MongoConnection",
        FakeConnection,
    )
    monkeypatch.setattr(
        "app.temporal_worker.create_temporal_client",
        fake_client,
    )
    monkeypatch.setattr("app.temporal_worker.Worker", FakeWorker)

    asyncio.run(run_worker(Settings(temporal_enabled=True)))

    assert captured["task_queue"] == TASK_QUEUE
    assert captured["workflows"] == [temporal_workflows.MaintenanceTaskWorkflow]
    assert len(captured["activities"]) == 1
    assert captured["activity_executor"]._max_workers == 4
    assert isinstance(captured["activity_executor"], ThreadPoolExecutor)
    assert captured["connection_closed"] is True
