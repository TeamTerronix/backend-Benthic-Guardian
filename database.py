"""
database.py
===========
SQLAlchemy engine, session factory, and Base declaration.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)


def normalize_database_url(url: str) -> str:
    """Convert generic postgres:// URLs to SQLAlchemy psycopg3 form."""
    url = url.strip().strip('"').strip("'")
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def is_supabase_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host.endswith(".supabase.co") or host.endswith(".pooler.supabase.com")


def mask_database_url(url: str) -> str:
    """Hide credentials for logs."""
    try:
        p = urlparse(url)
        host = p.hostname or "?"
        port = f":{p.port}" if p.port else ""
        user = p.username or "?"
        return f"{p.scheme}://{user}:***@{host}{port}{p.path or ''}"
    except Exception:
        return "<invalid DATABASE_URL>"


def engine_connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}

    args: dict = {"sslmode": "require"}

    # Supabase transaction pooler (port 6543): disable prepared statements.
    parsed = urlparse(url)
    if parsed.port == 6543 or "pgbouncer=true" in (parsed.query or "").lower():
        args["prepare_threshold"] = None

    return args


def _strip_query_params_for_engine(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.query:
        return url
    return urlunparse(parsed._replace(query=""))


def _validate_database_url(url: str) -> None:
    if os.getenv("RENDER", "").lower() == "true" and url.startswith("sqlite"):
        raise RuntimeError(
            "DATABASE_URL is not set on Render (defaulting to SQLite). "
            "In Render → Environment, add DATABASE_URL with your Supabase URI "
            "(session pooler, port 5432). The .env file is not included in the Docker image."
        )

    if url.startswith("postgresql"):
        parsed = urlparse(url)
        if not parsed.hostname:
            raise RuntimeError("DATABASE_URL is missing a hostname.")
        if not parsed.username or parsed.password is None:
            raise RuntimeError(
                "DATABASE_URL is missing username or password. "
                "URL-encode special characters in the password (@ → %40, & → %26, ! → %21, + → %2B)."
            )


_raw_url = os.getenv("DATABASE_URL", "sqlite:///./sliot.db")
DATABASE_URL = _strip_query_params_for_engine(normalize_database_url(_raw_url))
_validate_database_url(DATABASE_URL)

_engine_kwargs: dict = {
    "connect_args": engine_connect_args(DATABASE_URL),
    "pool_pre_ping": True,
}

if DATABASE_URL.startswith("postgresql"):
    _engine_kwargs["pool_recycle"] = int(os.getenv("DB_POOL_RECYCLE_SEC", "300"))
    # Keep pool small on PaaS (Render starter).
    _engine_kwargs["pool_size"] = int(os.getenv("DB_POOL_SIZE", "5"))
    _engine_kwargs["max_overflow"] = int(os.getenv("DB_MAX_OVERFLOW", "5"))

engine = create_engine(DATABASE_URL, **_engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

logger.info("Database target: %s", mask_database_url(DATABASE_URL))


def check_database_connection() -> None:
    """Raise if the database is unreachable."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def get_db():
    """FastAPI dependency that yields a DB session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
