from datetime import datetime, timezone
from types import SimpleNamespace

from bson import ObjectId
from fastapi.testclient import TestClient
import pytest

from app import main
from app.database import MongoConnection


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
        stored = {**document, "_id": ObjectId()}
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


class FakeDatabase:
    def __init__(self):
        self.collections = {
            "societies": FakeCollection(),
            "assets": FakeCollection(),
            "incidents": FakeCollection(),
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


def test_asset_rejects_invalid_id_and_missing_asset(monkeypatch):
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(FakeDatabase()))

    with TestClient(main.app) as client:
        invalid_response = client.get("/assets/not-an-object-id")
        missing_response = client.get(f"/assets/{ObjectId()}")

    assert invalid_response.status_code == 400
    assert missing_response.status_code == 404


def test_asset_validation_rejects_unknown_fields(monkeypatch):
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(FakeDatabase()))

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
    monkeypatch.setattr(main, "_connection", lambda request: FakeConnection(database))

    with TestClient(main.app) as client:
        response = client.get(f"/assets/{asset_id}/incidents")

    assert response.status_code == 200
    assert [item["summary"] for item in response.json()] == [
        "Recent waterlogging",
        "Earlier waterlogging",
    ]
