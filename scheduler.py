"""
scheduler.py
============
APScheduler background tasks for the SLIOT platform.

  Job 1  (every 6 h)  : pull the last 48 h of readings for every approved
                        sensor, run the PINN forecast, and persist 168-h
                        predictions into the `predictions` table.

  Job 2  (every 24 h) : archive sensor_readings older than 30 days into
                        history_archive.csv, then delete them from the DB
                        to keep the "hot" table small and fast.
"""

import csv
import hashlib
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from database import SessionLocal
from model_paths import MODEL_DIR as _MODEL_DIR_PATH
from models import Prediction, Sensor, SensorReading

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
ARCHIVE_PATH   = os.path.join(os.path.dirname(__file__), "history_archive.csv")
RETENTION_DAYS = 30
_MODEL_DIR     = str(_MODEL_DIR_PATH)

# ── Lazy forecaster loader (avoids importing TF at module import time) ─────────
_forecaster = None


def _get_forecaster():
    global _forecaster
    if _forecaster is None:
        if _MODEL_DIR not in sys.path:
            sys.path.insert(0, _MODEL_DIR)
        from forecaster import get_forecaster  # noqa: PLC0415
        _forecaster = get_forecaster()
    return _forecaster


def _infer_location_from_sensor(sensor: "Sensor") -> str:
    """
    Infer the location name from sensor coordinates or name.
    Falls back to 'hikkaduwa' if unable to determine.
    
    Location coordinates (approximate):
    - Hikkaduwa: 6.12°N, 80.08°E
    - Kalpitiya: 8.25°N, 79.83°E  
    - Passikudha: 7.18°N, 81.22°E
    - Trincomalee: 8.57°N, 81.23°E
    - South East: 5.95°N, 81.22°E
    """
    if sensor.latitude is None or sensor.longitude is None:
        if "kalp" in sensor.sensor_uid.lower():
            return "kalpitiya"
        elif "pass" in sensor.sensor_uid.lower():
            return "passikudha"
        elif "trin" in sensor.sensor_uid.lower():
            return "trinco"
        elif "south" in sensor.sensor_uid.lower() or "east" in sensor.sensor_uid.lower():
            return "south_east"
        else:
            return "hikkaduwa"
    
    lat, lon = sensor.latitude, sensor.longitude
    
    # Simple proximity-based mapping
    locations = {
        "hikkaduwa": (6.12, 80.08),
        "kalpitiya": (8.25, 79.83),
        "passikudha": (7.18, 81.22),
        "trinco": (8.57, 81.23),
        "south_east": (5.95, 81.22),
    }
    
    min_dist = float('inf')
    closest_location = "hikkaduwa"
    
    for loc_name, (loc_lat, loc_lon) in locations.items():
        dist = (lat - loc_lat)**2 + (lon - loc_lon)**2
        if dist < min_dist:
            min_dist = dist
            closest_location = loc_name
    
    return closest_location


# ── Job 1 : 6-hour PINN forecast ──────────────────────────────────────────────

def run_forecast_job() -> None:
    """
    For every approved sensor with coordinates, pull the last 48 h of
    readings, call the PINN forecaster, and replace the existing 168-h
    prediction rows in the database.
    """
    logger.info("[forecast_job] Starting")
    db: Session = SessionLocal()
    try:
        forecaster = _get_forecaster()
        sensors = (
            db.query(Sensor)
            .filter(
                Sensor.is_approved == True,
                Sensor.latitude.isnot(None),
                Sensor.longitude.isnot(None),
            )
            .all()
        )
        logger.info("[forecast_job] %d approved sensors to process", len(sensors))

        for sensor in sensors:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
            raw = (
                db.query(SensorReading)
                .filter(
                    SensorReading.sensor_id == sensor.id,
                    SensorReading.timestamp >= cutoff,
                )
                .order_by(SensorReading.timestamp.asc())
                .all()
            )

            if not raw:
                logger.warning(
                    "[forecast_job] Sensor %s has no readings in last 48 h — skipping",
                    sensor.sensor_uid,
                )
                continue

            readings = [
                {"timestamp": r.timestamp, "temperature": r.temperature}
                for r in raw
            ]

            try:
                location = _infer_location_from_sensor(sensor)
                forecast = forecaster.forecast(
                    lat=sensor.latitude,
                    lon=sensor.longitude,
                    last_readings=readings,
                    location=location,
                )
            except Exception as exc:
                logger.error(
                    "[forecast_job] Forecast failed for sensor %s: %s",
                    sensor.sensor_uid, exc, exc_info=True,
                )
                continue

            # Replace stale predictions for this sensor
            db.query(Prediction).filter(Prediction.sensor_id == sensor.id).delete()
            for item in forecast:
                db.add(
                    Prediction(
                        sensor_id=sensor.id,
                        target_timestamp=item["target_timestamp"],
                        predicted_temp=item["predicted_temp"],
                        risk_level=item["risk_level"],
                        risk_score=item.get("risk_score"),
                        anomaly=item.get("anomaly"),
                        days_stressed=item.get("days_stressed"),
                        warming_rate=item.get("warming_rate"),
                        physics_residual=item["physics_residual"],
                    )
                )

        db.commit()
        logger.info("[forecast_job] Done")

    except Exception as exc:
        db.rollback()
        logger.error("[forecast_job] Fatal error: %s", exc, exc_info=True)
    finally:
        db.close()


# ── Job 2 : 24-hour data archival ──────────────────────────────────────────────

def run_archive_job() -> None:
    """
    Move sensor_readings older than RETENTION_DAYS into history_archive.csv.

    Deletion is disabled by default and requires ENABLE_READING_DELETION=true.
    Before deletion, a row-count and checksum verification is performed against
    the just-appended archive batch.
    """
    logger.info("[archive_job] Starting")
    db: Session = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
        old = (
            db.query(SensorReading)
            .filter(SensorReading.timestamp < cutoff)
            .all()
        )

        if not old:
            logger.info("[archive_job] No readings older than %d days", RETENTION_DAYS)
            return

        expected_count = len(old)
        expected_checksum = _compute_readings_checksum(old)
        archived_at_marker = _write_archive(old)

        verified = _verify_archive_batch(
            archive_path=ARCHIVE_PATH,
            archived_at_marker=archived_at_marker,
            expected_count=expected_count,
            expected_checksum=expected_checksum,
        )
        if not verified:
            raise RuntimeError("Archive verification failed; aborting deletion")

        if not _reading_deletion_enabled():
            logger.warning(
                "[archive_job] Archived %d readings but skipped deletion "
                "(ENABLE_READING_DELETION is false)",
                expected_count,
            )
            return

        ids = [r.id for r in old]
        db.query(SensorReading).filter(
            SensorReading.id.in_(ids)
        ).delete(synchronize_session=False)

        db.commit()
        logger.info(
            "[archive_job] Archived, verified, and deleted %d readings -> %s",
            len(ids), ARCHIVE_PATH,
        )

    except Exception as exc:
        db.rollback()
        logger.error("[archive_job] Fatal error: %s", exc, exc_info=True)
    finally:
        db.close()


def _write_archive(readings: list) -> str:
    """Append rows to history_archive.csv and return this batch marker."""
    fieldnames = ["id", "sensor_id", "timestamp", "temperature", "archived_at"]
    file_exists = os.path.isfile(ARCHIVE_PATH)
    now_iso = datetime.now(timezone.utc).isoformat()

    with open(ARCHIVE_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for r in readings:
            writer.writerow(
                {
                    "id":          r.id,
                    "sensor_id":   r.sensor_id,
                    "timestamp":   r.timestamp.isoformat(),
                    "temperature": r.temperature,
                    "archived_at": now_iso,
                }
            )

    return now_iso


def _reading_deletion_enabled() -> bool:
    """Read deletion toggle from environment (safe default: disabled)."""
    return os.getenv("ENABLE_READING_DELETION", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _reading_checksum_parts(
    reading_id: int,
    sensor_id: int,
    timestamp_iso: str,
    temperature: float,
) -> str:
    return f"{reading_id}|{sensor_id}|{timestamp_iso}|{float(temperature):.6f}"


def _compute_readings_checksum(readings: list[SensorReading]) -> str:
    digest = hashlib.sha256()
    for r in readings:
        digest.update(
            _reading_checksum_parts(
                reading_id=r.id,
                sensor_id=r.sensor_id,
                timestamp_iso=r.timestamp.isoformat(),
                temperature=r.temperature,
            ).encode("utf-8")
        )
    return digest.hexdigest()


def _verify_archive_batch(
    archive_path: str,
    archived_at_marker: str,
    expected_count: int,
    expected_checksum: str,
) -> bool:
    if not os.path.isfile(archive_path):
        logger.error("[archive_job] Archive file not found: %s", archive_path)
        return False

    digest = hashlib.sha256()
    matched_rows = 0

    with open(archive_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("archived_at") != archived_at_marker:
                continue
            matched_rows += 1
            digest.update(
                _reading_checksum_parts(
                    reading_id=int(row["id"]),
                    sensor_id=int(row["sensor_id"]),
                    timestamp_iso=row["timestamp"],
                    temperature=float(row["temperature"]),
                ).encode("utf-8")
            )

    actual_checksum = digest.hexdigest()
    if matched_rows != expected_count:
        logger.error(
            "[archive_job] Verification count mismatch: expected=%d actual=%d",
            expected_count,
            matched_rows,
        )
        return False
    if actual_checksum != expected_checksum:
        logger.error(
            "[archive_job] Verification checksum mismatch: expected=%s actual=%s",
            expected_checksum,
            actual_checksum,
        )
        return False

    return True


# ── Scheduler factory ──────────────────────────────────────────────────────────

def create_scheduler() -> BackgroundScheduler:
    """
    Build and return a configured BackgroundScheduler.
    Call scheduler.start() in the FastAPI lifespan startup handler.
    """
    scheduler = BackgroundScheduler(timezone="UTC")

    scheduler.add_job(
        run_forecast_job,
        trigger=IntervalTrigger(hours=6),
        id="pinn_forecast",
        name="6-hour PINN forecast",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,   # allow 5-min late start
    )

    scheduler.add_job(
        run_archive_job,
        trigger=IntervalTrigger(hours=24),
        id="data_archive",
        name="24-hour data archival",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=600,
    )

    return scheduler
