from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_returns_success() -> None:
    response = client.get("/health")

    assert response.status_code == 200


def test_health_returns_expected_structure() -> None:
    response = client.get("/health")

    assert response.json() == {"status": "ok", "service": "rainguard-api"}


def test_unknown_route_returns_not_found() -> None:
    response = client.get("/not-a-route")

    assert response.status_code == 404


def test_health_allows_configured_frontend_origin() -> None:
    response = client.get(
        "/health",
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
