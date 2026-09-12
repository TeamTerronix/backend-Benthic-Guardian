"""Tests for /api/model-performance evaluation."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from models import Prediction, SensorReading


def test_pinn_model_performance_scores_pairs(client, auth_headers, approved_sensor, db):
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    # Past hour with both reading and prediction
    ts = now - timedelta(hours=3)
    db.add(
        SensorReading(
            sensor_id=approved_sensor.id,
            timestamp=ts,
            temperature=29.0,
        )
    )
    db.add(
        Prediction(
            sensor_id=approved_sensor.id,
            target_timestamp=ts,
            predicted_temp=30.0,
            risk_level=1,
            risk_score=0.4,
            anomaly=1.0,
            days_stressed=1,
            warming_rate=0.1,
            physics_residual=0.02,
        )
    )
    # Second pair for R²
    ts2 = now - timedelta(hours=2)
    db.add(
        SensorReading(
            sensor_id=approved_sensor.id,
            timestamp=ts2,
            temperature=28.5,
        )
    )
    db.add(
        Prediction(
            sensor_id=approved_sensor.id,
            target_timestamp=ts2,
            predicted_temp=28.0,
            risk_level=0,
            risk_score=0.1,
            anomaly=0.2,
            days_stressed=0,
            warming_rate=0.05,
            physics_residual=0.01,
        )
    )
    db.commit()

    response = client.get(
        "/api/model-performance",
        headers=auth_headers,
        params={"model": "PINN"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model"] == "PINN"
    assert body["n_pairs"] == 2
    assert body["mae"] is not None and body["mae"] > 0
    assert body["rmse"] is not None
    assert body["physics_loss"] is not None
    assert body["r2"] is not None


def test_lstm_model_performance_uses_forecaster(
    client, auth_headers, approved_sensor, db, monkeypatch
):
    now = datetime.now(timezone.utc)
    as_of = now - timedelta(days=8)
    # Daily readings aligned to LSTM horizons from as_of
    for day_offset, temp in [(1, 29.0), (3, 29.5), (7, 30.0)]:
        db.add(
            SensorReading(
                sensor_id=approved_sensor.id,
                timestamp=as_of + timedelta(days=day_offset, hours=12),
                temperature=temp,
            )
        )
    db.commit()

    fake = MagicMock()
    fake.forecast.return_value = [
        {
            "model": "ann_lstm_L60",
            "location": "hikkaduwa",
            "issue_time": as_of.isoformat(),
            "horizon_days": d,
            "target_date": (as_of + timedelta(days=d)).date().isoformat(),
            "predicted_temp": 29.0 + d * 0.1,
            "sst_pred": 29.0 + d * 0.1,
            "dhw_pred": 0.5,
            "sst_issue": 28.8,
            "dhw_issue": 0.4,
            "sst_persist": 28.8,
            "baseline_month_sst": 27.5,
            "anomaly": 1.7,
            "risk_score": 0.2,
            "risk_level": 0,
            "risk_name": "healthy",
        }
        for d in (1, 3, 7)
    ]

    import sys
    import types

    fake_mod = types.ModuleType("lstm_forecaster")
    fake_mod.get_lstm_forecaster = lambda: fake
    monkeypatch.setitem(sys.modules, "lstm_forecaster", fake_mod)

    response = client.get(
        "/api/model-performance",
        headers=auth_headers,
        params={"model": "LSTM"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model"] == "LSTM"
    assert body["physics_loss"] is None
    assert body["n_pairs"] >= 2
    assert body["mae"] is not None


def test_model_performance_requires_auth(client):
    assert client.get("/api/model-performance").status_code == 401
