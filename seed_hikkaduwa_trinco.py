"""
seed_hikkaduwa_trinco.py
========================
Seed Supabase (or any DATABASE_URL) with two demo reef networks:

  1) Hikkaduwa — 1 user, 1 network, 5 sensors (offshore west of Hikkaduwa)
  2) Trincomalee — 1 user, 1 network, 6 sensors (offshore east of Trinco)

Also seeds:
  - hourly sensor_readings for the last N hours (default 168 = 7 days)
  - predictions covering the last 7 days + next 7 days (hourly)

Usage (PowerShell):
  cd d:\\sliot2026\\backend
  # Ensure .env has DATABASE_URL pointing at Supabase session pooler
  python seed_hikkaduwa_trinco.py

Optional:
  python seed_hikkaduwa_trinco.py --reading-hours 168 --reset-passwords
"""

from __future__ import annotations

import argparse
import math
import os
import pathlib
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError


def _load_env_file_if_needed() -> None:
    here = pathlib.Path(__file__).resolve().parent
    env_path = here / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and (k not in os.environ):
            os.environ[k] = v


_load_env_file_if_needed()

from auth import hash_password  # noqa: E402
from database import DATABASE_URL, SessionLocal, engine  # noqa: E402
from models import (  # noqa: E402
    Base,
    NetworkGroup,
    Prediction,
    Sensor,
    SensorReading,
    User,
    UserNetworkGroup,
    UserRole,
)

# ── Demo credentials (printed at end) ─────────────────────────────────────────
HIKKA_EMAIL = "hikkaduwa@benthic.local"
HIKKA_PASSWORD = "ReefHikka2026!"
TRINCO_EMAIL = "trinco@benthic.local"
TRINCO_PASSWORD = "ReefTrinco2026!"

# Offshore centers — west of Hikkaduwa coast / east of Trincomalee (open water)
# Small fixed offsets keep nodes in a compact sea cluster (~0.3–0.6 km spacing).
HIKKADUWA_NODES: list[tuple[str, float, float, float]] = [
    # sensor_uid, lat, lon, depth_m
    ("hikka-sea-01", 6.1365, 80.0750, 4.0),
    ("hikka-sea-02", 6.1340, 80.0785, 5.5),
    ("hikka-sea-03", 6.1315, 80.0720, 3.5),
    ("hikka-sea-04", 6.1290, 80.0765, 6.0),
    ("hikka-sea-05", 6.1380, 80.0800, 4.5),
]

TRINCO_NODES: list[tuple[str, float, float, float]] = [
    ("trinco-sea-01", 8.5620, 81.2480, 5.0),
    ("trinco-sea-02", 8.5655, 81.2550, 6.5),
    ("trinco-sea-03", 8.5590, 81.2525, 4.0),
    ("trinco-sea-04", 8.5680, 81.2600, 7.0),
    ("trinco-sea-05", 8.5555, 81.2455, 5.5),
    ("trinco-sea-06", 8.5705, 81.2510, 4.5),
]


def _utc_hour() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(minute=0, second=0, microsecond=0)


def _get_or_create_user(
    db,
    *,
    email: str,
    password: str,
    reset_password: bool,
) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user:
        if reset_password:
            user.hashed_password = hash_password(password)
            user.role = UserRole.user
            db.commit()
            db.refresh(user)
        return user
    user = User(
        email=email,
        hashed_password=hash_password(password),
        role=UserRole.user,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _get_or_create_network(db, *, ngid: str, name: str) -> NetworkGroup:
    ng = db.query(NetworkGroup).filter(NetworkGroup.id == ngid).first()
    if ng:
        if name and ng.name != name:
            ng.name = name
            db.commit()
            db.refresh(ng)
        return ng
    ng = NetworkGroup(id=ngid, name=name)
    db.add(ng)
    db.commit()
    db.refresh(ng)
    return ng


def _ensure_membership(db, *, user_id: int, network_group_id: str) -> None:
    exists = (
        db.query(UserNetworkGroup)
        .filter(
            UserNetworkGroup.user_id == user_id,
            UserNetworkGroup.network_group_id == network_group_id,
        )
        .first()
    )
    if exists:
        return
    db.add(UserNetworkGroup(user_id=user_id, network_group_id=network_group_id))
    db.commit()


def _get_or_create_sensor(
    db,
    *,
    sensor_uid: str,
    owner_id: int,
    network_group_id: str,
    latitude: float,
    longitude: float,
    depth: float,
) -> Sensor:
    sensor = db.query(Sensor).filter(Sensor.sensor_uid == sensor_uid).first()
    if sensor:
        sensor.owner_id = owner_id
        sensor.network_group_id = network_group_id
        sensor.latitude = latitude
        sensor.longitude = longitude
        sensor.depth = depth
        sensor.is_approved = True
        db.commit()
        db.refresh(sensor)
        return sensor

    sensor = Sensor(
        sensor_uid=sensor_uid,
        owner_id=owner_id,
        network_group_id=network_group_id,
        latitude=latitude,
        longitude=longitude,
        depth=depth,
        is_approved=True,
    )
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    return sensor


def _upsert_reading(db, *, sensor_id: int, ts: datetime, temperature: float) -> None:
    exists = (
        db.query(SensorReading)
        .filter(SensorReading.sensor_id == sensor_id, SensorReading.timestamp == ts)
        .first()
    )
    if exists:
        exists.temperature = temperature
        db.commit()
        return
    db.add(SensorReading(sensor_id=sensor_id, timestamp=ts, temperature=temperature))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


def _risk_for_temp(temp: float) -> tuple[int, float]:
    if temp >= 31.0:
        return 2, min(1.0, 0.7 + (temp - 31.0) * 0.15)
    if temp >= 30.0:
        return 1, min(1.0, 0.3 + (temp - 30.0) * 0.4)
    return 0, max(0.0, (temp - 29.0) * 0.1)


def _replace_predictions_window(
    db,
    *,
    sensor_id: int,
    base_temp: float,
    start_ts: datetime,
    hours: int,
) -> None:
    """Replace predictions for this sensor over [start_ts, start_ts + hours)."""
    end_ts = start_ts + timedelta(hours=hours)
    db.query(Prediction).filter(
        Prediction.sensor_id == sensor_id,
        Prediction.target_timestamp >= start_ts,
        Prediction.target_timestamp < end_ts,
    ).delete(synchronize_session=False)

    for h in range(hours):
        ts = start_ts + timedelta(hours=h)
        # Offset from "now-ish" for a slow warming drift across the window
        age_h = (ts - start_ts).total_seconds() / 3600.0
        drift = 0.015 * (age_h / 24.0)
        wave = 0.55 * math.sin((2 * math.pi * (ts.hour)) / 24.0)
        noise = random.uniform(-0.08, 0.08)
        temp = base_temp + drift + wave + noise
        risk_level, risk_score = _risk_for_temp(temp)
        anomaly = max(0.0, temp - 28.5)

        db.add(
            Prediction(
                sensor_id=sensor_id,
                target_timestamp=ts,
                predicted_temp=float(round(temp, 3)),
                risk_level=risk_level,
                risk_score=float(round(risk_score, 4)),
                anomaly=float(round(anomaly, 3)),
                days_stressed=int(max(0, (temp - 29.5) * 2)),
                warming_rate=float(round(0.02 + random.uniform(-0.01, 0.02), 4)),
                physics_residual=float(round(random.uniform(0.0, 0.04), 6)),
            )
        )
    db.commit()


def _seed_site(
    db,
    *,
    email: str,
    password: str,
    network_id: str,
    network_name: str,
    nodes: list[tuple[str, float, float, float]],
    reading_hours: int,
    reset_password: bool,
) -> tuple[User, list[Sensor]]:
    user = _get_or_create_user(
        db, email=email, password=password, reset_password=reset_password
    )
    ng = _get_or_create_network(db, ngid=network_id, name=network_name)
    _ensure_membership(db, user_id=user.id, network_group_id=ng.id)

    sensors: list[Sensor] = []
    now = _utc_hour()
    hist_start = now - timedelta(hours=reading_hours)

    for uid, lat, lon, depth in nodes:
        sensor = _get_or_create_sensor(
            db,
            sensor_uid=uid,
            owner_id=user.id,
            network_group_id=ng.id,
            latitude=lat,
            longitude=lon,
            depth=depth,
        )
        sensors.append(sensor)

        base = random.uniform(28.4, 30.2)
        for h in range(reading_hours + 1):
            ts = hist_start + timedelta(hours=h)
            wave = 0.65 * math.sin((2 * math.pi * ts.hour) / 24.0)
            temp = base + wave + random.uniform(-0.12, 0.12)
            _upsert_reading(
                db,
                sensor_id=sensor.id,
                ts=ts,
                temperature=float(round(temp, 3)),
            )

        # Predictions: past 7 days + next 7 days (336 hours total)
        pred_start = now - timedelta(days=7)
        _replace_predictions_window(
            db,
            sensor_id=sensor.id,
            base_temp=base,
            start_ts=pred_start,
            hours=24 * 14,
        )

    return user, sensors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed Hikkaduwa (5) + Trincomalee (6) demo networks into DATABASE_URL"
    )
    parser.add_argument(
        "--reading-hours",
        type=int,
        default=168,
        help="Hours of past sensor_readings to seed (default 168 = 7 days)",
    )
    parser.add_argument(
        "--reset-passwords",
        action="store_true",
        help="If users already exist, reset passwords to the demo values",
    )
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    print(f"Database: {DATABASE_URL}")
    if "sqlite" in DATABASE_URL.lower():
        print(
            "WARNING: DATABASE_URL looks like SQLite. "
            "Set Supabase URI in backend/.env to seed production data."
        )

    random.seed(42)
    db = SessionLocal()
    try:
        hikka_user, hikka_sensors = _seed_site(
            db,
            email=HIKKA_EMAIL,
            password=HIKKA_PASSWORD,
            network_id="ng_hikkaduwa_sea_01",
            network_name="Hikkaduwa Reef Network",
            nodes=HIKKADUWA_NODES,
            reading_hours=args.reading_hours,
            reset_password=args.reset_passwords,
        )
        trinco_user, trinco_sensors = _seed_site(
            db,
            email=TRINCO_EMAIL,
            password=TRINCO_PASSWORD,
            network_id="ng_trinco_sea_01",
            network_name="Trincomalee Sea Network",
            nodes=TRINCO_NODES,
            reading_hours=args.reading_hours,
            reset_password=args.reset_passwords,
        )

        print()
        print("Seed complete.")
        print()
        print("=== Login credentials (email = username) ===")
        print(f"  Hikkaduwa  email: {HIKKA_EMAIL}")
        print(f"             password: {HIKKA_PASSWORD}")
        print(f"             network: ng_hikkaduwa_sea_01  ({len(hikka_sensors)} nodes)")
        print(f"  Trincomalee email: {TRINCO_EMAIL}")
        print(f"             password: {TRINCO_PASSWORD}")
        print(f"             network: ng_trinco_sea_01  ({len(trinco_sensors)} nodes)")
        print()
        print(f"User ids: hikka={hikka_user.id}, trinco={trinco_user.id}")
        print(
            f"Data: {args.reading_hours}h readings + "
            "14 days of hourly predictions (past 7 + next 7) per sensor."
        )
        print("If an existing user could not log in, re-run with --reset-passwords")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
