from datetime import datetime, timedelta, timezone

from models import Prediction, SensorReading


def _seed_report_rows(db, approved_sensor, now):
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


def test_report_json_download_from_server(client, auth_headers, approved_sensor, db):
    now = datetime.now(timezone.utc)
    _seed_report_rows(db, approved_sensor, now)

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
    assert "attachment" in response.headers.get("content-disposition", "")
    assert "application/json" in response.headers.get("content-type", "")
    payload = response.json()
    assert payload["product"] == "Benthic Guardian"
    assert payload["summary"]["total_readings"] >= 1
    assert payload["summary"]["total_predictions"] >= 1
    assert payload["data"]["sst"][0]["temperature"] == 30.8
    assert payload["data"]["predictions"][0]["risk_score"] == 0.72
    assert payload["metadata"]["product"] == "Benthic Guardian"


def test_report_csv_download_from_server(client, auth_headers, approved_sensor, db):
    now = datetime.now(timezone.utc)
    _seed_report_rows(db, approved_sensor, now)

    response = client.get(
        "/api/report",
        headers=auth_headers,
        params={
            "start": (now - timedelta(days=2)).isoformat(),
            "end": (now + timedelta(days=2)).isoformat(),
            "format": "csv",
            "include_sst": True,
            "include_dhw": False,
            "include_predictions": True,
        },
    )

    assert response.status_code == 200, response.text
    assert "text/csv" in response.headers.get("content-type", "")
    assert "attachment" in response.headers.get("content-disposition", "")
    text = response.content.decode("utf-8-sig")
    assert "Benthic Guardian" in text or "product: Benthic Guardian" in text
    assert "dataset" in text
    assert "sst" in text
    assert "30.8" in text
    assert "SLIOT" not in text


def test_report_pdf_generated_on_server(client, auth_headers, approved_sensor, db):
    now = datetime.now(timezone.utc)
    db.add(
        SensorReading(
            sensor_id=approved_sensor.id,
            timestamp=now - timedelta(hours=2),
            temperature=29.4,
        )
    )
    db.commit()

    response = client.get(
        "/api/report",
        headers=auth_headers,
        params={
            "start": (now - timedelta(days=1)).isoformat(),
            "end": (now + timedelta(days=1)).isoformat(),
            "format": "pdf",
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content[:4] == b"%PDF"
    assert len(response.content) > 1000
    assert b"Benthic Guardian" in response.content
    assert b"SLIOT" not in response.content
