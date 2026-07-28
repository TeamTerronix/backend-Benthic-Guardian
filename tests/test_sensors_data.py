"""Sensor list, admin register, and POST /data ingestion."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from models import Sensor, User


def test_sensors_requires_auth(client: TestClient):
    assert client.get("/sensors").status_code == 401


def test_list_sensors_for_user(
    client: TestClient,
    auth_headers: dict[str, str],
    approved_sensor: Sensor,
):
    response = client.get("/sensors", headers=auth_headers)
    assert response.status_code == 200
    uids = [s["sensor_uid"] for s in response.json()]
    assert approved_sensor.sensor_uid in uids


def test_admin_register_sensor(
    client: TestClient,
    admin_headers: dict[str, str],
    regular_user: User,
):
    response = client.post(
        "/admin/register-sensor",
        headers=admin_headers,
        json={
            "sensor_id": "esp32_admin_reg_01",
            "owner_email": regular_user.email,
            "latitude": 6.12,
            "longitude": 80.08,
            "depth": 4.5,
            "network_group_id": "ng_test_user_01",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["sensor_uid"] == "esp32_admin_reg_01"
    assert body["is_approved"] is True
    assert body["owner_id"] == regular_user.id


def test_admin_register_sensor_forbidden_for_user(
    client: TestClient,
    auth_headers: dict[str, str],
    regular_user: User,
):
    response = client.post(
        "/admin/register-sensor",
        headers=auth_headers,
        json={
            "sensor_id": "esp32_blocked",
            "owner_email": regular_user.email,
            "latitude": 6.0,
            "longitude": 80.0,
            "depth": 1.0,
        },
    )
    assert response.status_code == 403


def test_ingest_reading_ok(client: TestClient, approved_sensor: Sensor):
    response = client.post(
        "/data",
        json={
            "sensor_uid": approved_sensor.sensor_uid,
            "temperature": 28.5,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "created"
    assert body["temperature"] == 28.5
    assert body["sensor_id"] == approved_sensor.id


def test_ingest_unknown_sensor(client: TestClient):
    response = client.post(
        "/data",
        json={"sensor_uid": "does_not_exist", "temperature": 27.0},
    )
    assert response.status_code == 404


def test_ingest_unapproved_sensor(client: TestClient, unapproved_sensor: Sensor):
    response = client.post(
        "/data",
        json={"sensor_uid": unapproved_sensor.sensor_uid, "temperature": 27.0},
    )
    assert response.status_code == 403


def test_sensor_readings_history(
    client: TestClient,
    auth_headers: dict[str, str],
    approved_sensor: Sensor,
):
    client.post(
        "/data",
        json={"sensor_uid": approved_sensor.sensor_uid, "temperature": 29.1},
    )
    response = client.get(
        f"/sensors/{approved_sensor.id}/readings",
        headers=auth_headers,
        params={"hours": 24},
    )
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) >= 1
    assert rows[0]["temperature"] == 29.1
