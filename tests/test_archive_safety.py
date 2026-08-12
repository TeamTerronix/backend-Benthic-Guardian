from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from models import SensorReading
from scheduler import run_archive_job


def _count_readings(db):
    return db.query(SensorReading).count()


def _old_ts(days: int = 31) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def test_archive_failure_never_deletes_rows(db, approved_sensor, monkeypatch, tmp_path):
    reading = SensorReading(
        sensor_id=approved_sensor.id,
        timestamp=_old_ts(),
        temperature=29.4,
    )
    db.add(reading)
    db.commit()

    monkeypatch.setattr("scheduler.ARCHIVE_PATH", str(tmp_path / "history_archive.csv"))
    monkeypatch.setattr("scheduler._write_archive", lambda rows: (_ for _ in ()).throw(RuntimeError("disk write failed")))
    monkeypatch.setenv("ENABLE_READING_DELETION", "true")

    run_archive_job()

    assert _count_readings(db) == 1


def test_archive_verification_mismatch_never_deletes_rows(db, approved_sensor, monkeypatch, tmp_path):
    reading = SensorReading(
        sensor_id=approved_sensor.id,
        timestamp=_old_ts(),
        temperature=30.1,
    )
    db.add(reading)
    db.commit()

    monkeypatch.setattr("scheduler.ARCHIVE_PATH", str(tmp_path / "history_archive.csv"))
    monkeypatch.setenv("ENABLE_READING_DELETION", "true")
    monkeypatch.setattr("scheduler._verify_archive_batch", lambda **kwargs: False)

    run_archive_job()

    assert _count_readings(db) == 1


def test_archive_with_deletion_disabled_keeps_rows(db, approved_sensor, monkeypatch, tmp_path):
    reading = SensorReading(
        sensor_id=approved_sensor.id,
        timestamp=_old_ts(),
        temperature=28.8,
    )
    db.add(reading)
    db.commit()

    monkeypatch.setattr("scheduler.ARCHIVE_PATH", str(tmp_path / "history_archive.csv"))
    monkeypatch.setenv("ENABLE_READING_DELETION", "false")

    run_archive_job()

    assert _count_readings(db) == 1


def test_archive_with_deletion_enabled_deletes_rows(db, approved_sensor, monkeypatch, tmp_path):
    reading = SensorReading(
        sensor_id=approved_sensor.id,
        timestamp=_old_ts(),
        temperature=31.2,
    )
    db.add(reading)
    db.commit()

    monkeypatch.setenv("ENABLE_READING_DELETION", "true")
    monkeypatch.setattr("scheduler.ARCHIVE_PATH", str(tmp_path / "history_archive.csv"))

    run_archive_job()

    assert _count_readings(db) == 0
