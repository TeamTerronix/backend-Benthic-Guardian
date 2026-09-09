from datetime import datetime, timedelta, timezone

from models import Prediction, SensorReading


def test_report_generation_returns_summary_data(client, auth_headers, approved_sensor, db):
    now = datetime.now(timezone.utc)
    db.add(
        SensorReading(
            sensor_id=approved_sensor.id,
            timestamp=now - timedelta(hours=1),
            temperature=30.8,
        )
    )
    db.add(
        Prediction(
            sensor_id=approved_sensor.id,
            target_timestamp=now + timedelta(hours=2),
            predicted_temp=31.8,
            risk_level=1,
            risk_score=0.72,
            anomaly=1.4,
            days_stressed=5,
            warming_rate=0.25,
            physics_residual=0.12,
        )
    )
    db.commit()

    response = client.get(
        "/api/report",
        headers=auth_headers,
        params={
            "start": (now - timedelta(days=2)).isoformat(),
            "end": (now + timedelta(days=2)).isoformat(),
            "format": "json",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"]["total_readings"] >= 1
    assert payload["summary"]["total_predictions"] >= 1
    assert payload["risk_summary"]["warning"] >= 1 or payload["risk_summary"]["danger"] >= 0
    assert payload["datasets"]["sst"][0]["temperature"] == 30.8
    assert payload["datasets"]["predictions"][0]["risk_score"] == 0.72
