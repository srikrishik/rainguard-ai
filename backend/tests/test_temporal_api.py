from datetime import datetime, timezone
from types import SimpleNamespace

from bson import ObjectId
from fastapi.testclient import TestClient
from temporalio.exceptions import TemporalError, WorkflowAlreadyStartedError

from app import main
from app.config import Settings
from app.database import MongoConnection
from app.temporal_worker import TASK_QUEUE
from test_mongodb_api import FakeConnection, FakeDatabase


def task_record() -> tuple[FakeDatabase, ObjectId]:
    database = FakeDatabase()
    task_id = ObjectId()
    asset_id = ObjectId()
    mission_id = ObjectId()
    database["maintenance_tasks"].documents.append(
        {
            "_id": task_id,
            "asset_id": asset_id,
            "mission_id": mission_id,
            "finding_id": "finding-1",
            "description": "Clear the drain",
            "priority": "high",
            "assignee": "Facilities",
            "due_date": datetime(2026, 10, 23, 5, 19, tzinfo=timezone.utc),
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "completion_notes": None,
            "evidence_refs": [],
        }
    )
    return database, task_id


def configure_request(monkeypatch, database, *, enabled=True):
    monkeypatch.setattr(
        main,
        "_connection",
        lambda request: FakeConnection(database),
    )
    monkeypatch.setattr(
        main,
        "settings",
        Settings(temporal_enabled=enabled),
    )


def test_start_workflow_rejects_invalid_task_id():
    with TestClient(main.app) as client:
        response = client.post("/maintenance-tasks/not-an-object-id/temporal-workflow")

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid task id"


def test_start_workflow_returns_not_found_before_temporal(monkeypatch):
    database = FakeDatabase()
    configure_request(monkeypatch, database)

    with TestClient(main.app) as client:
        response = client.post(
            f"/maintenance-tasks/{ObjectId()}/temporal-workflow"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "maintenance task not found"


def test_start_workflow_returns_503_when_temporal_is_disabled(monkeypatch):
    database, task_id = task_record()
    configure_request(monkeypatch, database, enabled=False)

    with TestClient(main.app) as client:
        response = client.post(f"/maintenance-tasks/{task_id}/temporal-workflow")

    assert response.status_code == 503
    assert response.json()["detail"] == "Temporal workflow service is disabled"


def test_start_workflow_returns_503_when_temporal_is_unavailable(monkeypatch):
    database, task_id = task_record()
    configure_request(monkeypatch, database)

    async def unavailable(settings):
        raise TemporalError("service unavailable")

    monkeypatch.setattr(main, "create_temporal_client", unavailable)

    with TestClient(main.app) as client:
        response = client.post(f"/maintenance-tasks/{task_id}/temporal-workflow")

    assert response.status_code == 503
    assert response.json()["detail"] == "Temporal workflow service unavailable"


def test_start_workflow_returns_202_with_deterministic_id(monkeypatch):
    database, task_id = task_record()
    configure_request(monkeypatch, database)
    calls = []

    class FakeClient:
        async def start_workflow(self, workflow, arg, **kwargs):
            calls.append((workflow, arg, kwargs))
            return SimpleNamespace(id=kwargs["id"])

    async def fake_client(settings):
        return FakeClient()

    monkeypatch.setattr(main, "create_temporal_client", fake_client)

    with TestClient(main.app) as client:
        response = client.post(f"/maintenance-tasks/{task_id}/temporal-workflow")

    assert response.status_code == 202
    assert response.json() == {
        "task_id": str(task_id),
        "workflow_id": f"maintenance-task-{task_id}",
        "status": "started",
    }
    assert calls[0][0] == "maintenance-task-orchestration"
    assert calls[0][2]["task_queue"] == TASK_QUEUE
    assert calls[0][2]["id_reuse_policy"].name == "REJECT_DUPLICATE"
    assert calls[0][1]["due_date"] == "2026-10-23T05:19:00+00:00"


def test_start_workflow_reuses_existing_workflow_id_safely(monkeypatch):
    database, task_id = task_record()
    configure_request(monkeypatch, database)

    class FakeClient:
        async def start_workflow(self, workflow, arg, **kwargs):
            raise WorkflowAlreadyStartedError(
                kwargs["id"], "maintenance-task-orchestration"
            )

    async def fake_client(settings):
        return FakeClient()

    monkeypatch.setattr(main, "create_temporal_client", fake_client)

    with TestClient(main.app) as client:
        response = client.post(f"/maintenance-tasks/{task_id}/temporal-workflow")

    assert response.status_code == 202
    assert response.json()["status"] == "already_started"
