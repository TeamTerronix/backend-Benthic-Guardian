from __future__ import annotations

from fastapi.testclient import TestClient

from models import Sensor, User


def test_high_temperature_creates_persistent_alert(
    client: TestClient,
    auth_headers: dict[str, str],
    approved_sensor: Sensor,
):
    response = client.post(
        "/data",
        json={"sensor_uid": approved_sensor.sensor_uid, "temperature": 31.4},
    )
    assert response.status_code == 200

    alerts_response = client.get("/api/alerts", headers=auth_headers)
    assert alerts_response.status_code == 200
    alerts = alerts_response.json()
    assert len(alerts) == 1
    assert alerts[0]["sensor_uid"] == approved_sensor.sensor_uid
    assert alerts[0]["status"] == "open"
    assert alerts[0]["temperature"] == 31.4


def test_alert_workflow_is_persisted(
    client: TestClient,
    auth_headers: dict[str, str],
    regular_user: User,
    approved_sensor: Sensor,
):
    client.post(
        "/data",
        json={"sensor_uid": approved_sensor.sensor_uid, "temperature": 32.0},
    )
    alert_id = client.get("/api/alerts", headers=auth_headers).json()[0]["id"]

    acknowledged = client.patch(
        f"/api/alerts/{alert_id}",
        headers=auth_headers,
        json={
            "status": "acknowledged",
            "assigned_to_id": regular_user.id,
            "notes": "Diver inspection scheduled",
        },
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["acknowledged_by_email"] == regular_user.email
    assert acknowledged.json()["assigned_to_email"] == regular_user.email
    assert acknowledged.json()["notes"] == "Diver inspection scheduled"

    resolved = client.patch(
        f"/api/alerts/{alert_id}",
        headers=auth_headers,
        json={"status": "resolved"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["resolved_at"] is not None

    history = client.get("/api/alerts?status=resolved", headers=auth_headers).json()
    assert [item["id"] for item in history] == [alert_id]


def test_alerts_require_auth(client: TestClient):
    assert client.get("/api/alerts").status_code == 401
    assert client.get("/api/alert-operators").status_code == 401


def test_dashboard_settings_round_trip(
    client: TestClient,
    auth_headers: dict[str, str],
):
    defaults = client.get("/api/settings", headers=auth_headers)
    assert defaults.status_code == 200
    assert defaults.json()["refresh_interval_sec"] == 300

    saved = client.put(
        "/api/settings",
        headers=auth_headers,
        json={
            "unit": "fahrenheit",
            "theme": "light",
            "refresh_interval_sec": 900,
            "threshold_warning_c": 28.5,
            "threshold_critical_c": 30.0,
        },
    )
    assert saved.status_code == 200
    assert saved.json()["unit"] == "fahrenheit"

    loaded = client.get("/api/settings", headers=auth_headers)
    assert loaded.json()["theme"] == "light"
    assert loaded.json()["threshold_warning_c"] == 28.5


def test_dashboard_settings_reject_invalid_thresholds(
    client: TestClient,
    auth_headers: dict[str, str],
):
    response = client.put(
        "/api/settings",
        headers=auth_headers,
        json={
            "unit": "celsius",
            "theme": "dark",
            "refresh_interval_sec": 300,
            "threshold_warning_c": 30.0,
            "threshold_critical_c": 29.0,
        },
    )
    assert response.status_code == 422

