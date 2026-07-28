"""Health and public surface tests."""

from fastapi.testclient import TestClient


def test_health_ok(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["version"] == "1.0.0"
    assert "timestamp" in body


def test_ws_alerts_http_probe(client: TestClient):
    response = client.get("/ws/alerts")
    assert response.status_code == 200
    assert "WebSocket" in response.json()["detail"]
