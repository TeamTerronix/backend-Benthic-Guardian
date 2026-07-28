"""
Shared pytest fixtures.

Must set env vars before importing database/main (engine is created at import time).
"""

from __future__ import annotations

import os

# ── Env before app import ─────────────────────────────────────────────────────
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["DISABLE_SCHEDULER"] = "1"
os.environ["SECRET_KEY"] = "test-secret-key-for-ci-only"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ.pop("RENDER", None)

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import database as database_module
from database import Base, get_db
from models import NetworkGroup, Sensor, User, UserNetworkGroup, UserRole

# Shared in-memory SQLite so all connections see the same schema/data
_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

database_module.engine = _engine
database_module.SessionLocal = TestingSessionLocal

import main as main_module  # noqa: E402
from auth import hash_password  # noqa: E402
from main import app  # noqa: E402

main_module.SessionLocal = TestingSessionLocal


@pytest.fixture(autouse=True)
def _reset_db() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    """HTTP client with DB override; no background PINN after POST /data."""
    monkeypatch.setattr(main_module, "_schedule_forecast_job_after_reading", lambda: None)

    def override_get_db() -> Generator[Session, None, None]:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def user_password() -> str:
    return "test-password-123"


@pytest.fixture
def regular_user(db: Session, user_password: str) -> User:
    user = User(
        email="reef@example.com",
        hashed_password=hash_password(user_password),
        role=UserRole.user,
    )
    db.add(user)
    db.flush()
    ng = NetworkGroup(id="ng_test_user_01", name="Test Network")
    db.add(ng)
    db.add(UserNetworkGroup(user_id=user.id, network_group_id=ng.id))
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_user(db: Session, user_password: str) -> User:
    user = User(
        email="admin@example.com",
        hashed_password=hash_password(user_password),
        role=UserRole.admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_headers(client: TestClient, regular_user: User, user_password: str) -> dict[str, str]:
    response = client.post(
        "/auth/token",
        data={"username": regular_user.email, "password": user_password},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(client: TestClient, admin_user: User, user_password: str) -> dict[str, str]:
    response = client.post(
        "/auth/token",
        data={"username": admin_user.email, "password": user_password},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def approved_sensor(db: Session, regular_user: User) -> Sensor:
    sensor = Sensor(
        sensor_uid="esp32_test_01",
        owner_id=regular_user.id,
        network_group_id="ng_test_user_01",
        latitude=6.12,
        longitude=80.08,
        depth=5.0,
        is_approved=True,
    )
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    return sensor


@pytest.fixture
def unapproved_sensor(db: Session, regular_user: User) -> Sensor:
    sensor = Sensor(
        sensor_uid="esp32_pending_01",
        owner_id=regular_user.id,
        network_group_id="ng_test_user_01",
        latitude=6.12,
        longitude=80.08,
        depth=5.0,
        is_approved=False,
    )
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    return sensor
