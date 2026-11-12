"""Pydantic v2 схемы API. ВРЕМЕННО до раздела «API бэкенда»."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import ExperimentStatus, ImportKind, ImportStatus, Role


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    login: str
    role: Role
    business_id: uuid.UUID | None


class UserCreate(BaseModel):
    login: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=8)
    role: Role
    business_id: uuid.UUID | None = None


class BusinessCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class BusinessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str


class ImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    business_id: uuid.UUID
    kind: ImportKind
    filename: str
    sha256: str
    size_bytes: int
    status: ImportStatus
    quality_report: dict[str, Any]
    created_at: datetime


class Protocol(BaseModel):
    """Протокол эксперимента. После регистрации не меняется."""

    model_config = ConfigDict(extra="forbid")
    hypothesis: str = Field(min_length=1, max_length=2000)
    action: str = Field(min_length=1, max_length=2000, description="Что делаем с тестовой группой")
    as_of: date = Field(description="Дата среза когорты")
    inactive_days: int = Field(30, ge=7, le=365)
    max_inactive_days: int = Field(180, ge=14, le=1095)
    control_share: Decimal = Field(Decimal("0.5"), ge=Decimal("0.1"), le=Decimal("0.5"))
    window_days: int = Field(30, ge=7, le=180, description="Окно замера возврата после среза")
    cost_rub: Decimal = Field(ge=0, max_digits=12, decimal_places=2, description="Стоимость действия C, ₽")
    alpha: float = Field(0.05, gt=0, lt=0.2)
    min_group_size: int = Field(100, ge=10)
    max_mde: float = Field(0.10, gt=0, lt=1)


class ExperimentCreate(BaseModel):
    business_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=300)
    protocol: Protocol


class ExperimentUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    protocol: Protocol | None = None


class ExperimentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    business_id: uuid.UUID
    title: str
    status: ExperimentStatus
    protocol: dict[str, Any]
    protocol_hash: str | None
    control_share: Decimal
    registered_at: datetime | None
    closed_at: datetime | None
    n_control: int | None = None
    n_test: int | None = None


class AssignmentOut(BaseModel):
    customer_id: str
    group: str
    stratum: str


class MdeRequest(BaseModel):
    baseline: float = Field(gt=0, lt=1)
    cohort_size: int = Field(ge=0)
    control_share: float = Field(gt=0, lt=1)
    alpha: float = 0.05
    power: float = 0.8


class MdeResponse(BaseModel):
    n_control: int
    n_test: int
    mde: float | None


class PreviewOut(BaseModel):
    cohort_size: int
    baseline: float | None
    n_control: int
    n_test: int
    mde: float | None


class ResultOut(BaseModel):
    experiment_id: uuid.UUID
    computed_at: datetime
    result_hash: str
    payload: dict[str, Any]


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    seq: int
    occurred_at: datetime
    business_id: uuid.UUID | None
    actor_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    payload: dict[str, Any]
    prev_hash: str
    hash: str


class ChainOut(BaseModel):
    ok: bool
    checked: int
    broken_at_seq: int | None
    reason: str | None
