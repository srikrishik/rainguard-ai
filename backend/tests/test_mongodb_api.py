
from datetime import datetime, timezone
from types import SimpleNamespace

from bson import ObjectId
from fastapi.testclient import TestClient
import pytest
from pymongo.errors import DuplicateKeyError

from app import main
from app.database import MongoConnection
from app.gemma_service import GemmaServiceError
from app.repositories import MaintenanceTaskRepository
from app.schemas import GemmaReport
from app.risk_service import assess_asset_risk


class FakeCursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, field, direction):
        return sorted(
            self.documents,
            key=lambda document: document[field],
            reverse=direction < 0,
        )


class FakeCollection:
    def __init__(self):
        self.documents = []

    def insert_one(self, document):
        stored = dict(document)
        stored.setdefault("_id", ObjectId())
        self.documents.append(stored)
        return SimpleNamespace(inserted_id=stored["_id"])

    def find_one(self, query):
        return next(
            (
                document
                for document in self.documents
                if all(document.get(key) == value for key, value in query.items())
            ),
            None,
        )

    def find(self, query):
        return FakeCursor(
            [
                document
                for document in self.documents
                if all(document.get(key) == value for key, value in query.items())
            ]
        )

    def update_one(self, query, updates):
        document = self.find_one(query)
        if document is None:
            return SimpleNamespace(matched_count=0, modified_count=0)

        document.update(updates.get("$set", {}))
        return SimpleNamespace(matched_count=1, modified_count=1)


class FailingCollection(FakeCollection):
    def insert_one(self, document):
        from pymongo.errors import PyMongoError

        raise PyMongoError("database unavailable")


class DuplicateKeyAfterLookupCollection(FakeCollection):
    def __init__(self, existing_document):
        super().__init__()
        self.documents.append(existing_document)
        self.lookup_count = 0

    def find_one(self, query):
        self.lookup_count += 1
        if self.lookup_count == 1:
            return None
        return super().find_one(query)

    def insert_one(self, document):
        raise DuplicateKeyError("duplicate key")


class FakeDatabase:
    def __init__(self):
        self.collections = {
            "societies": FakeCollection(),
            "assets": FakeCollection(),
            "incidents": FakeCollection(),
            "inspections": FakeCollection(),
            "risk_assessments": FakeCollection(),
            "inspection_missions": FakeCollection(),
            "maintenance_tasks": FakeCollection(),
        }

    def __getitem__(self, name):
        return self.collections[name]


class FakeConnection:
    def __init__(self, database, ready=True):
        self.database = database
        self.ready = ready

    def ping(self):
        return self.ready

    def ensure_indexes(self):
        return None


@pytest.fixture(autouse=True)
def disable_real_lifecycle_connection(monkeypatch):
    monkeypatch.setattr(MongoConnection, "connect", lambda self: None)
    monkeypatch.setattr(MongoConnection, "close", lambda self: None)


def test_ready_returns_503_when_database_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        main,
        "_connection",
        lambda request: FakeConnection(FakeDatabase(), ready=False),
    )

    with TestClient(main.app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}


def test_ready_returns_safe_success_when_database_is_available(monkeypatch):
    monkeypatch.setattr(
        main,
        "_connection",
        lambda request: FakeConnection(FakeDatabase()),
    )

    with TestClient(main.app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "service": "rainguard-api"}


def test_health_contract_is_unchanged():
    with TestClient(main.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "rainguard-api"}


def test_asset_can_be_created_and_retrieved(monkeypatch):
    database = FakeDatabase()
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))

    with TestClient(main.app) as client:
        create_response = client.post(
            "/assets",
            json={
                "society_id": "society-1",
                "name": "North stormwater drain",
                "location": "Gate A",
            },
        )
        asset_id = create_response.json()["id"]
        get_response = client.get(f"/assets/{asset_id}")

    assert create_response.status_code == 201
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "North stormwater drain"


def test_assets_can_be_listed_for_dashboard(monkeypatch):
    database, first_id = asset_database()
    database["assets"].documents.append(
        {
            "_id": ObjectId(),
            "created_at": datetime.now(timezone.utc),
            "society_id": "society-1",
            "name": "Gate 2 pump",
            "location": "Gate 2",
        }
    )
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))

    with TestClient(main.app) as client:
        response = client.get("/assets")

    assert response.status_code == 200
    assert {asset["id"] for asset in response.json()} == {
        str(first_id),
        str(database["assets"].documents[1]["_id"]),
    }


def test_asset_rejects_invalid_id_and_missing_asset(monkeypatch):
    monkeypatch.setattr(
        main,
        "_connection",
        lambda request: FakeConnection(FakeDatabase()),
    )

    with TestClient(main.app) as client:
        invalid_response = client.get("/assets/not-an-object-id")
        missing_response = client.get(f"/assets/{ObjectId()}")

    assert invalid_response.status_code == 400
    assert missing_response.status_code == 404


def test_asset_validation_rejects_unknown_fields(monkeypatch):
    monkeypatch.setattr(
        main,
        "_connection",
        lambda request: FakeConnection(FakeDatabase()),
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/assets",
            json={"society_id": "society-1", "name": "Drain", "risk": 0.9},
        )

    assert response.status_code == 422


def test_incident_history_is_returned_newest_first(monkeypatch):
    database = FakeDatabase()
    asset_id = ObjectId()
    database["incidents"].documents.extend(
        [
            {
                "_id": ObjectId(),
                "asset_id": asset_id,
                "occurred_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "summary": "Earlier waterlogging",
            },
            {
                "_id": ObjectId(),
                "asset_id": asset_id,
                "occurred_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
                "summary": "Recent waterlogging",
            },
        ]
    )
    monkeypatch.setattr(
        main,
        "_connection",
        lambda request: FakeConnection(database),
    )

    with TestClient(main.app) as client:
        response = client.get(f"/assets/{asset_id}/incidents")

    assert response.status_code == 200
    assert [item["summary"] for item in response.json()] == [
        "Recent waterlogging",
        "Earlier waterlogging",
    ]


def test_fake_inspection_collection_can_update_and_retrieve_record():
    database = FakeDatabase()
    inspection_id = ObjectId()

    database["inspections"].insert_one(
        {
            "_id": inspection_id,
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
        }
    )

    database["inspections"].update_one(
        {"_id": inspection_id},
        {"$set": {"status": "completed"}},
    )

    inspection = database["inspections"].find_one({"_id": inspection_id})

    assert inspection is not None
    assert inspection["_id"] == inspection_id
    assert inspection["status"] == "completed"


def valid_png() -> bytes:
    return b"\x89PNG\r\n\x1a\nfake-imageIEND"


def make_gemma_report() -> GemmaReport:
    return GemmaReport(
        summary="Visible debris near the drain.",
        observations=[
            {
                "description": "Debris is visible near the drain opening.",
                "concern": "moderate",
            }
        ],
        severity="moderate",
        confidence="medium",
        recommended_actions=["Have maintenance staff inspect the drain."],
        requires_human_review=False,
    )


class FakeGemma:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def analyze_image(self, image_bytes, content_type, asset_context):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def asset_database():
    database = FakeDatabase()
    asset_id = ObjectId()
    database["assets"].documents.append(
        {
            "_id": asset_id,
            "created_at": datetime.now(timezone.utc),
            "society_id": "society-1",
            "name": "North drain",
            "location": "Gate A",
        }
    )
    return database, asset_id


def test_inspection_upload_saves_completed_report(monkeypatch):
    database, asset_id = asset_database()
    gemma = FakeGemma(make_gemma_report())
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))
    monkeypatch.setattr(main, "_gemma_service", lambda request: gemma)

    with TestClient(main.app) as client:
        response = client.post(
            f"/assets/{asset_id}/inspections",
            files={"file": ("drain.png", valid_png(), "image/png")},
        )

    assert response.status_code == 201
    assert response.json()["status"] == "completed"
    assert response.json()["report"]["requires_human_review"] is True
    assert gemma.calls == 1
    stored = database["inspections"].documents[0]
    assert stored["status"] == "completed"
    assert stored["byte_size"] == len(valid_png())
    assert stored["content_type"] == "image/png"
    assert stored["report"]["summary"] == "Visible debris near the drain."


@pytest.mark.parametrize(
    ("filename", "content", "content_type"),
    [
        ("empty.png", b"", "image/png"),
        ("drain.gif", b"GIF89a", "image/gif"),
        ("fake.png", b"not-a-png", "image/png"),
    ],
)
def test_inspection_rejects_invalid_images(monkeypatch, filename, content, content_type):
    database, asset_id = asset_database()
    gemma = FakeGemma(make_gemma_report())
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))
    monkeypatch.setattr(main, "_gemma_service", lambda request: gemma)

    with TestClient(main.app) as client:
        response = client.post(
            f"/assets/{asset_id}/inspections",
            files={"file": (filename, content, content_type)},
        )

    assert response.status_code == 400
    assert gemma.calls == 0
    assert database["inspections"].documents == []


def test_inspection_rejects_oversized_images(monkeypatch):
    database, asset_id = asset_database()
    gemma = FakeGemma(make_gemma_report())
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))
    monkeypatch.setattr(main, "_gemma_service", lambda request: gemma)

    with TestClient(main.app) as client:
        response = client.post(
            f"/assets/{asset_id}/inspections",
            files={
                "file": (
                    "large.png",
                    b"\x89PNG\r\n\x1a\n" + b"x" * (5 * 1024 * 1024),
                    "image/png",
                )
            },
        )

    assert response.status_code == 413
    assert gemma.calls == 0
    assert database["inspections"].documents == []


def test_inspection_rejects_invalid_and_missing_assets(monkeypatch):
    database = FakeDatabase()
    gemma = FakeGemma(make_gemma_report())
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))
    monkeypatch.setattr(main, "_gemma_service", lambda request: gemma)

    with TestClient(main.app) as client:
        invalid = client.post(
            "/assets/not-an-object-id/inspections",
            files={"file": ("drain.png", valid_png(), "image/png")},
        )
        missing = client.post(
            f"/assets/{ObjectId()}/inspections",
            files={"file": ("drain.png", valid_png(), "image/png")},
        )

    assert invalid.status_code == 400
    assert missing.status_code == 404
    assert gemma.calls == 0


def test_provider_failure_keeps_failed_inspection_record(monkeypatch):
    database, asset_id = asset_database()
    gemma = FakeGemma(
        error=GemmaServiceError("provider_timeout", "safe timeout message")
    )
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))
    monkeypatch.setattr(main, "_gemma_service", lambda request: gemma)

    with TestClient(main.app) as client:
        response = client.post(
            f"/assets/{asset_id}/inspections",
            files={"file": ("drain.png", valid_png(), "image/png")},
        )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "image analysis failed",
    }
    assert database["inspections"].documents[0]["status"] == "failed"
    assert database["inspections"].documents[0]["error_code"] == "provider_timeout"


def test_provider_quota_failure_returns_rate_limit_and_persists_failure(monkeypatch):
    database, asset_id = asset_database()
    gemma = FakeGemma(
        error=GemmaServiceError("provider_quota_exceeded", "safe quota message")
    )
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))
    monkeypatch.setattr(main, "_gemma_service", lambda request: gemma)

    with TestClient(main.app) as client:
        response = client.post(
            f"/assets/{asset_id}/inspections",
            files={"file": ("drain.png", valid_png(), "image/png")},
        )

    assert response.status_code == 429
    assert database["inspections"].documents[0]["status"] == "failed"


def test_database_insert_failure_does_not_call_provider(monkeypatch):
    database, asset_id = asset_database()
    database.collections["inspections"] = FailingCollection()
    gemma = FakeGemma(make_gemma_report())
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))
    monkeypatch.setattr(main, "_gemma_service", lambda request: gemma)

    with TestClient(main.app) as client:
        response = client.post(
            f"/assets/{asset_id}/inspections",
            files={"file": ("drain.png", valid_png(), "image/png")},
        )

    assert response.status_code == 503
    assert gemma.calls == 0


def test_get_inspection_success_invalid_id_and_missing(monkeypatch):
    database, asset_id = asset_database()
    inspection_id = ObjectId()
    database["inspections"].documents.append(
        {
            "_id": inspection_id,
            "asset_id": asset_id,
            "status": "completed",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "report": make_gemma_report().model_dump(),
        }
    )
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))

    with TestClient(main.app) as client:
        success = client.get(f"/inspections/{inspection_id}")
        invalid = client.get("/inspections/not-an-object-id")
        missing = client.get(f"/inspections/{ObjectId()}")

    assert success.status_code == 200
    assert success.json()["status"] == "completed"
    assert invalid.status_code == 400
    assert missing.status_code == 404


def test_get_asset_inspections_returns_newest_first(monkeypatch):
    database, asset_id = asset_database()
    older_id = ObjectId()
    newer_id = ObjectId()
    older_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    newer_time = datetime(2026, 1, 2, tzinfo=timezone.utc)
    database["inspections"].documents.extend(
        [
            {
                "_id": older_id,
                "asset_id": asset_id,
                "status": "completed",
                "created_at": older_time,
                "updated_at": older_time,
                "report": make_gemma_report().model_dump(),
            },
            {
                "_id": newer_id,
                "asset_id": asset_id,
                "status": "failed",
                "created_at": newer_time,
                "updated_at": newer_time,
                "error_code": "provider_timeout",
            },
        ]
    )
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))

    with TestClient(main.app) as client:
        response = client.get(f"/assets/{asset_id}/inspections")

    assert response.status_code == 200
    records = response.json()
    assert [record["id"] for record in records] == [str(newer_id), str(older_id)]
    assert records[0]["status"] == "failed"
    assert records[0]["report"] is None
    assert records[0]["error_code"] == "provider_timeout"
    assert records[1]["report"]["summary"] == "Visible debris near the drain."


def test_get_asset_inspections_returns_empty_history(monkeypatch):
    database, asset_id = asset_database()
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))

    with TestClient(main.app) as client:
        response = client.get(f"/assets/{asset_id}/inspections")

    assert response.status_code == 200
    assert response.json() == []


def test_rule_baseline_uses_recent_incidents_and_completed_inspections():
    assessed_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    result = assess_asset_risk(
        str(ObjectId()),
        [
            {
                "occurred_at": datetime(2026, 2, 20, tzinfo=timezone.utc),
            },
            {
                "occurred_at": datetime(2026, 2, 25, tzinfo=timezone.utc),
            },
        ],
        [
            {
                "status": "completed",
                "created_at": datetime(2026, 2, 28, tzinfo=timezone.utc),
                "report": {
                    "severity": "high",
                    "observations": [{"concern": "high"}],
                },
            },
            {
                "status": "failed",
                "created_at": datetime(2026, 2, 28, tzinfo=timezone.utc),
                "report": {"severity": "high"},
            },
        ],
        assessed_at,
    )

    assert result["priority"] == "high"
    assert result["score"] == 10
    assert result["requires_human_review"] is True
    assert any("2 incident(s)" in item for item in result["evidence"])


def test_rule_baseline_applies_timestamp_cutoff_and_missing_data_warning():
    result = assess_asset_risk(
        str(ObjectId()),
        [{"occurred_at": datetime(2026, 1, 1, tzinfo=timezone.utc)}],
        [{"status": "pending", "report": {"severity": "high"}}],
        datetime(2026, 3, 1, tzinfo=timezone.utc),
    )

    assert result["priority"] == "medium"
    assert result["score"] == 0
    assert "No completed inspection evidence is available" in result[
        "data_quality_warnings"
    ]


@pytest.mark.parametrize(
    "created_at",
    [
        datetime(2026, 2, 28, tzinfo=timezone.utc),
        datetime(2026, 2, 28),
    ],
)
def test_rule_baseline_normalizes_inspection_timestamps(created_at):
    result = assess_asset_risk(
        str(ObjectId()),
        [],
        [
            {
                "status": "completed",
                "created_at": created_at,
                "report": {
                    "severity": "moderate",
                    "observations": [],
                },
            }
        ],
        datetime(2026, 3, 1, tzinfo=timezone.utc),
    )

    assert result["priority"] == "medium"
    assert result["score"] == 2
    assert not any(
        "No completed inspection is available within" in warning
        for warning in result["data_quality_warnings"]
    )


def test_rule_baseline_handles_invalid_inspection_timestamp():
    result = assess_asset_risk(
        str(ObjectId()),
        [],
        [
            {
                "status": "completed",
                "created_at": "not-a-timestamp",
                "report": {"severity": "high", "observations": []},
            }
        ],
        datetime(2026, 3, 1, tzinfo=timezone.utc),
    )

    assert result["priority"] == "medium"
    assert result["score"] == 4
    assert any(
        "No completed inspection is available within" in warning
        for warning in result["data_quality_warnings"]
    )


def test_risk_assessment_is_persisted_and_retrieved(monkeypatch):
    database, asset_id = asset_database()
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))

    with TestClient(main.app) as client:
        created = client.post(f"/assets/{asset_id}/risk-assessments")
        latest = client.get(f"/assets/{asset_id}/risk-assessments/latest")

    assert created.status_code == 201
    assert latest.status_code == 200
    assert latest.json()["id"] == created.json()["id"]
    assert latest.json()["requires_human_review"] is True


def test_risk_assessment_rejects_invalid_missing_and_database_failure(monkeypatch):
    database, asset_id = asset_database()
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))

    with TestClient(main.app) as client:
        invalid = client.post("/assets/not-an-object-id/risk-assessments")
        missing = client.post(
            f"/assets/{ObjectId()}/risk-assessments"
        )

    assert invalid.status_code == 400
    assert missing.status_code == 404

    database.collections["risk_assessments"] = FailingCollection()
    with TestClient(main.app) as client:
        failed = client.post(f"/assets/{asset_id}/risk-assessments")
    assert failed.status_code == 503


def test_rule_baseline_remains_default_when_tabpfn_is_unavailable(monkeypatch):
    database, asset_id = asset_database()
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))

    with TestClient(main.app) as client:
        response = client.post(f"/assets/{asset_id}/risk-assessments")

    assert response.status_code == 201
    assert response.json()["method"] == "rule_based_asset_risk_baseline"
    assert response.json()["method_version"] == "phase-5a-v1"
    assert response.json()["requires_human_review"] is True


def test_inspection_mission_finding_approval_and_task_lifecycle(monkeypatch):
    database, asset_id = asset_database()
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))

    with TestClient(main.app) as client:
        mission_response = client.post(f"/assets/{asset_id}/inspection-missions")
        mission = mission_response.json()
        assert mission_response.status_code == 201
        assert len(mission["checklist"]) == 6

        finding_response = client.post(
            f"/inspection-missions/{mission['id']}/findings",
            json={
                "checklist_item_id": "debris-obstruction",
                "description": "Leaves obstruct the drain opening.",
                "evidence_refs": ["inspection-photo-1"],
            },
        )
        finding = finding_response.json()["findings"][0]
        assert finding_response.status_code == 201
        assert finding["approved"] is False

        rejected = client.post(
            "/maintenance-tasks",
            json={
                "asset_id": str(asset_id),
                "mission_id": mission["id"],
                "finding_id": finding["id"],
                "description": finding["description"],
                "priority": "high",
            },
        )
        assert rejected.status_code == 409

        approved_response = client.post(
            f"/inspection-missions/{mission['id']}/findings/{finding['id']}/approve"
        )
        assert approved_response.status_code == 200
        assert approved_response.json()["findings"][0]["approved"] is True

        task_response = client.post(
            "/maintenance-tasks",
            json={
                "asset_id": str(asset_id),
                "mission_id": mission["id"],
                "finding_id": finding["id"],
                "description": finding["description"],
                "priority": "high",
                "assignee": "Maintenance team",
                "evidence_refs": ["inspection-photo-1"],
            },
        )
        task = task_response.json()
        assert task_response.status_code == 201
        assert task["status"] == "pending"
        persisted_tasks = client.get(f"/assets/{asset_id}/maintenance-tasks")
        assert persisted_tasks.status_code == 200
        assert persisted_tasks.json()[0]["id"] == task["id"]
        assert persisted_tasks.json()[0]["status"] == "pending"

        duplicate = client.post(
            "/maintenance-tasks",
            json={
                "asset_id": str(asset_id),
                "mission_id": mission["id"],
                "finding_id": finding["id"],
                "description": finding["description"],
                "priority": "high",
            },
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["id"] == task["id"]
        assert len(database["maintenance_tasks"].documents) == 1
        legacy_reinspection = client.post(
            f"/maintenance-tasks/{task['id']}/reinspection",
            json={"notes": "Follow-up without a due date."},
        )
        assert legacy_reinspection.status_code == 200
        assert legacy_reinspection.json()["reinspection_due_at"] is None

        started = client.patch(
            f"/maintenance-tasks/{task['id']}",
            json={"status": "in_progress"},
        )
        completed = client.patch(
            f"/maintenance-tasks/{task['id']}",
            json={
                "status": "completed",
                "completion_notes": "Cleared leaves and flushed the opening.",
                "evidence_refs": ["after-photo-reference"],
            },
        )
        reinspection = client.post(
            f"/maintenance-tasks/{task['id']}/reinspection",
            json={
                "notes": "Verify flow after the next heavy rain.",
                "reinspection_due_at": "2026-10-20T04:30:00+00:00",
            },
        )
        listed = client.get(f"/assets/{asset_id}/maintenance-tasks")
        dashboard = client.get("/maintenance-tasks")
        rescheduled = client.post(
            f"/maintenance-tasks/{task['id']}/reinspection",
            json={
                "reinspection_due_at": "2026-10-22T06:45:00+00:00",
            },
        )
        refreshed = client.get(f"/assets/{asset_id}/maintenance-tasks")

    assert started.status_code == 200
    assert completed.status_code == 200
    assert completed.json()["completion_notes"] == "Cleared leaves and flushed the opening."
    assert reinspection.status_code == 200
    assert reinspection.json()["reinspection_status"] == "scheduled"
    assert reinspection.json()["reinspection_due_at"] == "2026-10-20T04:30:00Z"
    assert reinspection.json()["status"] == "completed"
    assert listed.status_code == 200 and len(listed.json()) == 1
    assert listed.json()[0]["reinspection_due_at"] == "2026-10-20T04:30:00Z"
    assert dashboard.status_code == 200 and len(dashboard.json()) == 1

    assert rescheduled.status_code == 200
    assert rescheduled.json()["reinspection_due_at"] == "2026-10-22T06:45:00Z"
    assert rescheduled.json()["status"] == "completed"
    assert refreshed.json()[0]["reinspection_due_at"] == "2026-10-22T06:45:00Z"

    india_rescheduled = client.post(
        f"/maintenance-tasks/{task['id']}/reinspection",
        json={
            "reinspection_due_at": "2026-10-17T17:05:00+05:30",
        },
    )
    india_refreshed = client.get(f"/assets/{asset_id}/maintenance-tasks")

    assert india_rescheduled.status_code == 200
    assert india_rescheduled.json()["reinspection_due_at"] == "2026-10-17T11:35:00Z"
    assert india_rescheduled.json()["status"] == "completed"
    assert india_refreshed.json()[0]["reinspection_due_at"] == "2026-10-17T11:35:00Z"


def test_mission_and_task_validation_and_missing_ids(monkeypatch):
    database, asset_id = asset_database()
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))

    with TestClient(main.app) as client:
        invalid_mission = client.get("/inspection-missions/not-an-id")
        mission_response = client.post(f"/assets/{asset_id}/inspection-missions")
        mission_id = mission_response.json()["id"]
        invalid_finding = client.post(
            f"/inspection-missions/{mission_id}/findings",
            json={
                "checklist_item_id": "unknown",
                "description": "Invalid checklist item",
            },
        )
        missing_task = client.get("/maintenance-tasks/not-an-id")
        missing_asset_mission = client.post(
            f"/assets/{ObjectId()}/inspection-missions"
        )

    assert invalid_mission.status_code == 400
    assert invalid_finding.status_code == 422
    assert missing_task.status_code == 400
    assert missing_asset_mission.status_code == 404


def test_reinspection_rejects_invalid_or_timezone_naive_due_dates(monkeypatch):
    database, asset_id = asset_database()
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))

    with TestClient(main.app) as client:
        mission = client.post(f"/assets/{asset_id}/inspection-missions").json()
        finding = client.post(
            f"/inspection-missions/{mission['id']}/findings",
            json={
                "checklist_item_id": "debris-obstruction",
                "description": "Leaves obstruct the drain opening.",
            },
        ).json()["findings"][0]
        client.post(
            f"/inspection-missions/{mission['id']}/findings/{finding['id']}/approve"
        )
        task = client.post(
            "/maintenance-tasks",
            json={
                "asset_id": str(asset_id),
                "mission_id": mission["id"],
                "finding_id": finding["id"],
                "description": finding["description"],
                "priority": "medium",
            },
        ).json()
        naive = client.post(
            f"/maintenance-tasks/{task['id']}/reinspection",
            json={"reinspection_due_at": "2026-10-20T10:00:00"},
        )
        malformed = client.post(
            f"/maintenance-tasks/{task['id']}/reinspection",
            json={"reinspection_due_at": "not-a-timestamp"},
        )

    assert naive.status_code == 422
    assert malformed.status_code == 422


def test_reinspection_response_normalizes_legacy_mongodb_timestamps(monkeypatch):
    database, asset_id = asset_database()
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))

    with TestClient(main.app) as client:
        mission = client.post(f"/assets/{asset_id}/inspection-missions").json()
        finding = client.post(
            f"/inspection-missions/{mission['id']}/findings",
            json={
                "checklist_item_id": "debris-obstruction",
                "description": "Leaves obstruct the drain opening.",
            },
        ).json()["findings"][0]
        client.post(
            f"/inspection-missions/{mission['id']}/findings/{finding['id']}/approve"
        )
        task = client.post(
            "/maintenance-tasks",
            json={
                "asset_id": str(asset_id),
                "mission_id": mission["id"],
                "finding_id": finding["id"],
                "description": finding["description"],
                "priority": "medium",
            },
        ).json()
        stored_task = database["maintenance_tasks"].documents[0]

        missing = client.get(f"/maintenance-tasks/{task['id']}")
        stored_task["reinspection_due_at"] = datetime(2026, 10, 23, 5, 19)
        naive = client.get(f"/maintenance-tasks/{task['id']}")
        stored_task["reinspection_due_at"] = "legacy-invalid-timestamp"
        invalid = client.get(f"/maintenance-tasks/{task['id']}")

    assert missing.status_code == 200
    assert missing.json()["reinspection_due_at"] is None
    assert naive.status_code == 200
    assert naive.json()["reinspection_due_at"] == "2026-10-23T05:19:00Z"
    assert naive.json()["status"] == "pending"
    assert invalid.status_code == 200
    assert invalid.json()["reinspection_due_at"] is None


def test_maintenance_task_repository_reuses_task_after_duplicate_key():
    mission_id = ObjectId()
    finding_id = "finding-1"
    existing = {
        "_id": ObjectId(),
        "mission_id": mission_id,
        "finding_id": finding_id,
        "status": "pending",
    }
    database = FakeDatabase()
    database.collections["maintenance_tasks"] = DuplicateKeyAfterLookupCollection(
        existing
    )
    repository = MaintenanceTaskRepository(database)

    result = repository.create(
        {
            "_id": ObjectId(),
            "mission_id": mission_id,
            "finding_id": finding_id,
            "status": "pending",
        }
    )

    assert result == existing
    assert result["_id"] == existing["_id"]
    assert len(database["maintenance_tasks"].documents) == 1


def test_task_database_failure_returns_safe_error(monkeypatch):
    database, asset_id = asset_database()
    database.collections["inspection_missions"] = FailingCollection()
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))

    with TestClient(main.app) as client:
        response = client.post(f"/assets/{asset_id}/inspection-missions")

    assert response.status_code == 503
