"""
database.py
===========
SQLAlchemy engine, session factory, and Base declaration.

Set DATABASE_URL in your environment (or .env file) before importing this module
(or run scripts like provision_prototype.py that load .env first).

Examples:
    SQLite (local dev):
        DATABASE_URL=sqlite:///./sliot.db

    PostgreSQL / RDS:
        DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/sliot

    Supabase (paste URI from Project Settings → Database → Connection string):
        DATABASE_URL=postgresql+psycopg://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
"""

from __future__ import annotations

import os
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


def normalize_database_url(url: str) -> str:
    """Convert generic postgres:// URLs to SQLAlchemy psycopg3 form."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def is_supabase_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host.endswith(".supabase.co") or host.endswith(".pooler.supabase.com")


def engine_connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    if is_supabase_url(url) or url.startswith("postgresql"):
        # Supabase requires TLS; safe for other managed Postgres too.
        return {"sslmode": "require"}
    return {}


def _strip_query_params_for_engine(url: str) -> str:
    """Remove query string from URL (handled via connect_args where needed)."""
    parsed = urlparse(url)
    if not parsed.query:
        return url
    return urlunparse(parsed._replace(query=""))


DATABASE_URL = normalize_database_url(
    os.getenv("DATABASE_URL", "sqlite:///./sliot.db")
)
DATABASE_URL = _strip_query_params_for_engine(DATABASE_URL)

_engine_kwargs: dict = {
    "connect_args": engine_connect_args(DATABASE_URL),
    "pool_pre_ping": True,
}

if DATABASE_URL.startswith("postgresql"):
    _engine_kwargs["pool_recycle"] = int(os.getenv("DB_POOL_RECYCLE_SEC", "300"))

engine = create_engine(DATABASE_URL, **_engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
