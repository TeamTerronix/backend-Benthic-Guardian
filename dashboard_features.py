"""Persistent dashboard alerts and per-user settings APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import DashboardSettings, SystemAlert, User, UserNetworkGroup, UserRole

router = APIRouter(prefix="/api", tags=["dashboard"])


class AlertOut(BaseModel):
    id: int
    type: str
    status: str
    sensor_id: Optional[int]
    sensor_uid: Optional[str]
    network_group_id: Optional[str]
    message: str
    temperature: Optional[float]
    risk_level: Optional[int]
    assigned_to_id: Optional[int]
    assigned_to_email: Optional[str]
    acknowledged_by_email: Optional[str]
    acknowledged_at: Optional[datetime]
    resolved_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]


class AlertUpdate(BaseModel):
    status: Optional[Literal["open", "acknowledged", "resolved"]] = None
    assigned_to_id: Optional[int] = None
    notes: Optional[str] = Field(default=None, max_length=4000)


class AlertOperatorOut(BaseModel):
    id: int
    email: str


class DashboardSettingsPayload(BaseModel):
    unit: Literal["celsius", "fahrenheit"] = "celsius"
    theme: Literal["dark", "light"] = "dark"
    refresh_interval_sec: int = Field(default=300, ge=30, le=86400)
    threshold_warning_c: float = Field(default=28.0, ge=-5, le=50)
    threshold_critical_c: float = Field(default=29.0, ge=-5, le=50)

    @model_validator(mode="after")
    def critical_above_warning(self):
        if self.threshold_critical_c <= self.threshold_warning_c:
            raise ValueError("Critical threshold must be above warning threshold")
        return self


class DashboardSettingsOut(DashboardSettingsPayload):
    updated_at: Optional[datetime] = None


def _network_ids(db: Session, user: User) -> list[str]:
    if user.role == UserRole.admin:
        return []
    rows = (
        db.query(UserNetworkGroup.network_group_id)
        .filter(UserNetworkGroup.user_id == user.id)
        .all()
    )
    return [row[0] for row in rows if row and row[0]]


def _visible_alert_query(db: Session, user: User):
    query = db.query(SystemAlert)
    if user.role != UserRole.admin:
        network_ids = _network_ids(db, user)
        if not network_ids:
            return query.filter(SystemAlert.id == -1)
        query = query.filter(SystemAlert.network_group_id.in_(network_ids))
    return query


def _visible_operator_query(db: Session, user: User):
    query = db.query(User)
    if user.role == UserRole.admin:
        return query
    network_ids = _network_ids(db, user)
    if not network_ids:
        return query.filter(User.id == -1)
    return (
        query.join(UserNetworkGroup, UserNetworkGroup.user_id == User.id)
        .filter(UserNetworkGroup.network_group_id.in_(network_ids))
        .distinct()
    )


def _alert_out(alert: SystemAlert) -> AlertOut:
    return AlertOut(
        id=alert.id,
        type=alert.alert_type,
        status=alert.status,
        sensor_id=alert.sensor_id,
        sensor_uid=alert.sensor.sensor_uid if alert.sensor else None,
        network_group_id=alert.network_group_id,
        message=alert.message,
        temperature=alert.temperature,
        risk_level=alert.risk_level,
        assigned_to_id=alert.assigned_to_id,
        assigned_to_email=alert.assigned_to.email if alert.assigned_to else None,
        acknowledged_by_email=alert.acknowledged_by.email if alert.acknowledged_by else None,
        acknowledged_at=alert.acknowledged_at,
        resolved_at=alert.resolved_at,
        notes=alert.notes,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
    )


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    status_filter: Optional[Literal["open", "acknowledged", "resolved"]] = Query(
        default=None, alias="status"
    ),
    alert_type: Optional[Literal["critical", "warning", "info"]] = Query(
        default=None, alias="type"
    ),
    assigned_to_id: Optional[int] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = _visible_alert_query(db, current_user)
    if status_filter:
        query = query.filter(SystemAlert.status == status_filter)
    if alert_type:
        query = query.filter(SystemAlert.alert_type == alert_type)
    if assigned_to_id is not None:
        query = query.filter(SystemAlert.assigned_to_id == assigned_to_id)
    alerts = query.order_by(SystemAlert.created_at.desc(), SystemAlert.id.desc()).limit(limit).all()
    return [_alert_out(alert) for alert in alerts]


@router.patch("/alerts/{alert_id}", response_model=AlertOut)
def update_alert(
    alert_id: int,
    payload: AlertUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    alert = _visible_alert_query(db, current_user).filter(SystemAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if "assigned_to_id" in payload.model_fields_set:
        if payload.assigned_to_id is not None:
            operator = (
                _visible_operator_query(db, current_user)
                .filter(User.id == payload.assigned_to_id)
                .first()
            )
            if not operator:
                raise HTTPException(status_code=400, detail="Assigned operator is not available")
        alert.assigned_to_id = payload.assigned_to_id

    if "notes" in payload.model_fields_set:
        alert.notes = payload.notes.strip() if payload.notes else None

    if payload.status is not None:
        now = datetime.now(timezone.utc)
        alert.status = payload.status
        if payload.status == "open":
            alert.acknowledged_by_id = None
            alert.acknowledged_at = None
            alert.resolved_at = None
        elif payload.status == "acknowledged":
            alert.acknowledged_by_id = current_user.id
            alert.acknowledged_at = alert.acknowledged_at or now
            alert.resolved_at = None
        else:
            alert.acknowledged_by_id = alert.acknowledged_by_id or current_user.id
            alert.acknowledged_at = alert.acknowledged_at or now
            alert.resolved_at = now

    db.commit()
    db.refresh(alert)
    return _alert_out(alert)


@router.get("/alert-operators", response_model=list[AlertOperatorOut])
def list_alert_operators(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    users = _visible_operator_query(db, current_user).order_by(User.email.asc()).all()
    return [AlertOperatorOut(id=user.id, email=user.email) for user in users]


def _settings_out(settings: DashboardSettings) -> DashboardSettingsOut:
    return DashboardSettingsOut(
        unit=settings.unit,
        theme=settings.theme,
        refresh_interval_sec=settings.refresh_interval_sec,
        threshold_warning_c=settings.threshold_warning_c,
        threshold_critical_c=settings.threshold_critical_c,
        updated_at=settings.updated_at,
    )


@router.get("/settings", response_model=DashboardSettingsOut)
def get_dashboard_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = db.query(DashboardSettings).filter(DashboardSettings.user_id == current_user.id).first()
    if not settings:
        return DashboardSettingsOut()
    return _settings_out(settings)


@router.put("/settings", response_model=DashboardSettingsOut)
def save_dashboard_settings(
    payload: DashboardSettingsPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = db.query(DashboardSettings).filter(DashboardSettings.user_id == current_user.id).first()
    if not settings:
        settings = DashboardSettings(user_id=current_user.id)
        db.add(settings)

    settings.unit = payload.unit
    settings.theme = payload.theme
    settings.refresh_interval_sec = payload.refresh_interval_sec
    settings.threshold_warning_c = payload.threshold_warning_c
    settings.threshold_critical_c = payload.threshold_critical_c
    db.commit()
    db.refresh(settings)
    return _settings_out(settings)

