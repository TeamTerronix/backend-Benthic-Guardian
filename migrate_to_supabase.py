"""
migrate_to_supabase.py
======================
Create SLIOT tables on Supabase (or any Postgres target) and copy data from a source DB.

Typical flow
------------
1. In Supabase: Project Settings → Database → copy the connection URI (use "Session" or
   "Transaction" pooler; URI-encode special characters in the password).
2. Put the target URL in backend/.env as DATABASE_URL.
3. Run:

       python migrate_to_supabase.py --source sqlite:///./sliot.db

   Or migrate from another Postgres instance:

       python migrate_to_supabase.py --source postgresql+psycopg://user:pass@old-host:5432/sliot

4. Start the API with the same DATABASE_URL in .env.

Requires: target DATABASE_URL must point to Supabase/Postgres (not SQLite).
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

# Load backend/.env before database import (same pattern as provision_prototype.py)
def _load_env_file() -> None:
    env_path = pathlib.Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_load_env_file()

from database import Base, DATABASE_URL, engine_connect_args, normalize_database_url  # noqa: E402
from models import (  # noqa: E402
    NetworkGroup,
    Prediction,
    Sensor,
    SensorReading,
    User,
    UserNetworkGroup,
)

# Insert order respects foreign keys
TABLE_MODELS = [
    NetworkGroup,
    User,
    UserNetworkGroup,
    Sensor,
    SensorReading,
    Prediction,
]


def _make_engine(url: str):
    url = normalize_database_url(url)
    kwargs: dict[str, Any] = {"connect_args": engine_connect_args(url), "pool_pre_ping": True}
    if url.startswith("postgresql"):
        kwargs["pool_recycle"] = 300
    return create_engine(url, **kwargs)


def _row_to_dict(obj) -> dict:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns}


def _reset_postgres_sequences(session: Session) -> None:
    """Align serial sequences after explicit id inserts."""
    for table in ("users", "sensors", "sensor_readings", "predictions"):
        session.execute(
            text(
                f"""
                SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {table}), 1),
                    (SELECT MAX(id) IS NOT NULL FROM {table})
                )
                """
            )
        )


def copy_data(source_url: str, target_url: str, wipe_target: bool) -> None:
    if not target_url.startswith("postgresql"):
        print("ERROR: DATABASE_URL (target) must be PostgreSQL / Supabase.", file=sys.stderr)
        sys.exit(1)

    source_engine = _make_engine(source_url)
    target_engine = _make_engine(target_url)

    print(f"Source: {source_url}")
    print(f"Target: {target_url}")

    # Create schema on target
    Base.metadata.create_all(bind=target_engine)
    print("Target schema created (create_all).")

    SourceSession = sessionmaker(bind=source_engine)
    TargetSession = sessionmaker(bind=target_engine)

    with SourceSession() as src, TargetSession() as tgt:
        if wipe_target:
            print("Wiping target tables (reverse FK order)...")
            for model in reversed(TABLE_MODELS):
                tgt.query(model).delete()
            tgt.commit()

        total = 0
        for model in TABLE_MODELS:
            q = src.query(model)
            if hasattr(model, "id"):
                q = q.order_by(model.id)
            rows = q.all()
            if not rows:
                print(f"  {model.__tablename__}: 0 rows")
                continue
            for row in rows:
                tgt.merge(model(**_row_to_dict(row)))
            tgt.commit()
            print(f"  {model.__tablename__}: {len(rows)} rows")
            total += len(rows)

        if target_url.startswith("postgresql"):
            _reset_postgres_sequences(tgt)
            tgt.commit()

    print(f"Done. Migrated {total} rows total.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate SLIOT data to Supabase/Postgres")
    parser.add_argument(
        "--source",
        default=os.getenv("SOURCE_DATABASE_URL", "sqlite:///./sliot.db"),
        help="Source DB URL (default: sqlite:///./sliot.db or SOURCE_DATABASE_URL)",
    )
    parser.add_argument(
        "--target",
        default=DATABASE_URL,
        help="Target DB URL (default: DATABASE_URL from .env)",
    )
    parser.add_argument(
        "--wipe-target",
        action="store_true",
        help="Delete existing rows on target before copy (schema kept)",
    )
    args = parser.parse_args()

    target = normalize_database_url(args.target)
    if target.startswith("sqlite"):
        print(
            "ERROR: Set DATABASE_URL in backend/.env to your Supabase URI first.",
            file=sys.stderr,
        )
        return 1

    # Quick connectivity check
    tgt_engine = _make_engine(target)
    with tgt_engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("Target connection OK.")

    copy_data(normalize_database_url(args.source), target, args.wipe_target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
