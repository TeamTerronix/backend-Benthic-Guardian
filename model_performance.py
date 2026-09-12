"""
model_performance.py
====================
Compute live evaluation metrics for PINN / ANN-LSTM / Ensemble forecasts.

PINN  — pair past ``predictions`` rows with ``sensor_readings`` (hourly match).
LSTM  — re-issue forecast from an ``as_of`` date in the past and compare to
        daily mean readings at the matching reef site.
Ensemble — average PINN + LSTM error metrics; physics loss from PINN only.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np
from sqlalchemy.orm import Session

from models import Prediction, Sensor, SensorReading, User, UserRole
from scheduler import _infer_location_from_sensor

logger = logging.getLogger(__name__)

HOUR = timedelta(hours=1)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _floor_hour(dt: datetime) -> datetime:
    dt = _to_utc(dt)
    return dt.replace(minute=0, second=0, microsecond=0)


def _day_key(dt: datetime) -> str:
    return _to_utc(dt).strftime("%Y-%m-%d")


def _metrics_from_pairs(actual: list[float], predicted: list[float]) -> dict[str, Any]:
    if len(actual) < 2 or len(actual) != len(predicted):
        return {
            "mae": None,
            "rmse": None,
            "r2": None,
            "n_pairs": len(actual),
        }
    y = np.asarray(actual, dtype=float)
    yhat = np.asarray(predicted, dtype=float)
    err = yhat - y
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))
    ss_res = float(np.sum(err**2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = None if ss_tot < 1e-12 else float(1.0 - ss_res / ss_tot)
    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "r2": None if r2 is None else round(r2, 4),
        "n_pairs": int(len(actual)),
    }


def _user_network_ids(db: Session, user: User) -> list[str]:
    if user.role == UserRole.admin:
        return []
    from models import UserNetworkGroup  # noqa: PLC0415

    rows = (
        db.query(UserNetworkGroup.network_group_id)
        .filter(UserNetworkGroup.user_id == user.id)
        .all()
    )
    return [r[0] for r in rows if r and r[0]]


def _scoped_sensors(db: Session, user: User) -> list[Sensor]:
    q = db.query(Sensor).filter(
        Sensor.is_approved == True,  # noqa: E712
        Sensor.latitude.isnot(None),
        Sensor.longitude.isnot(None),
    )
    if user.role != UserRole.admin:
        network_ids = _user_network_ids(db, user)
        if not network_ids:
            return []
        q = q.filter(Sensor.network_group_id.in_(network_ids))
    return q.all()


def evaluate_pinn(db: Session, user: User, *, lookback_days: int = 14) -> dict[str, Any]:
    """Score PINN predictions against observed readings."""
    sensors = _scoped_sensors(db, user)
    if not sensors:
        return {
            "model": "PINN",
            "mae": None,
            "rmse": None,
            "r2": None,
            "physics_loss": None,
            "n_pairs": 0,
            "message": "No approved sensors in scope.",
        }

    sensor_ids = [s.id for s in sensors]
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=lookback_days)

    preds = (
        db.query(Prediction)
        .filter(
            Prediction.sensor_id.in_(sensor_ids),
            Prediction.target_timestamp >= start,
            Prediction.target_timestamp <= now + HOUR,
        )
        .all()
    )
    readings = (
        db.query(SensorReading)
        .filter(
            SensorReading.sensor_id.in_(sensor_ids),
            SensorReading.timestamp >= start - HOUR,
            SensorReading.timestamp <= now + HOUR,
        )
        .all()
    )

    reading_map: dict[tuple[int, datetime], float] = {}
    for r in readings:
        key = (r.sensor_id, _floor_hour(r.timestamp))
        # Keep first sample in that hour
        reading_map.setdefault(key, float(r.temperature))

    actual: list[float] = []
    predicted: list[float] = []
    residuals: list[float] = []

    for p in preds:
        key = (p.sensor_id, _floor_hour(p.target_timestamp))
        if key not in reading_map:
            continue
        # Only score when the target hour has already been observed
        if _floor_hour(p.target_timestamp) > _floor_hour(now):
            continue
        actual.append(reading_map[key])
        predicted.append(float(p.predicted_temp))
        if p.physics_residual is not None:
            residuals.append(abs(float(p.physics_residual)))

    stats = _metrics_from_pairs(actual, predicted)
    physics_loss = round(float(np.mean(residuals)), 6) if residuals else None

    message = None
    if stats["n_pairs"] == 0:
        message = (
            "No overlapping past prediction/reading pairs yet. "
            "Metrics appear after forecasts and observations share the same hours."
        )

    return {
        "model": "PINN",
        "mae": stats["mae"],
        "rmse": stats["rmse"],
        "r2": stats["r2"],
        "physics_loss": physics_loss,
        "n_pairs": stats["n_pairs"],
        "message": message,
    }


def evaluate_lstm(
    db: Session,
    user: User,
    *,
    as_of_days_ago: int = 8,
) -> dict[str, Any]:
    """
    Score ANN-LSTM by issuing a forecast from ``as_of_days_ago`` and comparing
    +1/+3/+7 day SST to daily mean sensor temperatures at that reef site.
    """
    sensors = _scoped_sensors(db, user)
    if not sensors:
        return {
            "model": "LSTM",
            "mae": None,
            "rmse": None,
            "r2": None,
            "physics_loss": None,
            "n_pairs": 0,
            "message": "No approved sensors in scope.",
        }

    # Prefer the most common inferred location among scoped sensors
    loc_counts: dict[str, int] = {}
    loc_sensors: dict[str, list[Sensor]] = {}
    for s in sensors:
        loc = _infer_location_from_sensor(s)
        loc_counts[loc] = loc_counts.get(loc, 0) + 1
        loc_sensors.setdefault(loc, []).append(s)
    location = max(loc_counts, key=loc_counts.get)

    as_of = datetime.now(timezone.utc) - timedelta(days=as_of_days_ago)
    try:
        import sys
        from model_paths import MODEL_DIR

        model_dir = str(MODEL_DIR)
        if model_dir not in sys.path:
            sys.path.insert(0, model_dir)
        from lstm_forecaster import get_lstm_forecaster  # noqa: PLC0415

        rows = get_lstm_forecaster().forecast(location=location, as_of=as_of)
    except Exception as exc:
        logger.warning("LSTM evaluation forecast failed: %s", exc)
        return {
            "model": "LSTM",
            "mae": None,
            "rmse": None,
            "r2": None,
            "physics_loss": None,
            "n_pairs": 0,
            "message": f"LSTM evaluation unavailable: {exc}",
        }

    site_ids = [s.id for s in loc_sensors[location]]
    day_temps: dict[str, list[float]] = {}
    window_start = as_of - timedelta(days=1)
    window_end = as_of + timedelta(days=10)
    readings = (
        db.query(SensorReading)
        .filter(
            SensorReading.sensor_id.in_(site_ids),
            SensorReading.timestamp >= window_start,
            SensorReading.timestamp <= window_end,
        )
        .all()
    )
    for r in readings:
        day_temps.setdefault(_day_key(r.timestamp), []).append(float(r.temperature))

    actual: list[float] = []
    predicted: list[float] = []
    for row in rows:
        day = str(row.get("target_date") or "")[:10]
        if day not in day_temps:
            continue
        actual.append(float(np.mean(day_temps[day])))
        predicted.append(float(row["predicted_temp"]))

    stats = _metrics_from_pairs(actual, predicted)
    message = None
    if stats["n_pairs"] == 0:
        message = (
            f"No observed daily temperatures to score LSTM ({location}) "
            f"horizons from as_of={as_of.date()}."
        )
    elif stats["n_pairs"] < 2:
        message = "Only one LSTM horizon had observations; R² needs ≥2 pairs."

    return {
        "model": "LSTM",
        "mae": stats["mae"],
        "rmse": stats["rmse"],
        "r2": stats["r2"],
        "physics_loss": None,  # data-driven model — no PDE residual
        "n_pairs": stats["n_pairs"],
        "location": location,
        "message": message,
    }


def evaluate_ensemble(db: Session, user: User) -> dict[str, Any]:
    pinn = evaluate_pinn(db, user)
    lstm = evaluate_lstm(db, user)

    def _avg(a: Optional[float], b: Optional[float]) -> Optional[float]:
        vals = [v for v in (a, b) if v is not None and not (isinstance(v, float) and math.isnan(v))]
        if not vals:
            return None
        return round(sum(vals) / len(vals), 4)

    n_pairs = int(pinn.get("n_pairs") or 0) + int(lstm.get("n_pairs") or 0)
    message_parts = [m for m in (pinn.get("message"), lstm.get("message")) if m]
    return {
        "model": "Ensemble",
        "mae": _avg(pinn.get("mae"), lstm.get("mae")),
        "rmse": _avg(pinn.get("rmse"), lstm.get("rmse")),
        "r2": _avg(pinn.get("r2"), lstm.get("r2")),
        "physics_loss": pinn.get("physics_loss"),
        "n_pairs": n_pairs,
        "components": {"PINN": pinn, "LSTM": lstm},
        "message": " | ".join(message_parts) if message_parts else None,
    }


def evaluate_model(db: Session, user: User, model: str) -> dict[str, Any]:
    key = (model or "PINN").strip().upper()
    if key == "LSTM":
        return evaluate_lstm(db, user)
    if key == "ENSEMBLE":
        return evaluate_ensemble(db, user)
    return evaluate_pinn(db, user)
