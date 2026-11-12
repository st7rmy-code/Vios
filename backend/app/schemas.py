"""Pydantic v2 схемы API (спецификация, раздел 5)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import ConsentKind, ExperimentStatus, ImportKind, ImportStatus, Role


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    login: str
    role: Role
    business_id: uuid.UUID | None
    is_active: bool = True
    last_login_at: datetime | None = None
    created_at: datetime | None = None


class MeOut(UserOut):
    business_name: str | None = None
    business_timezone: str | None = None


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
    timezone: str = "Europe/Moscow"
    created_at: datetime | None = None


class ConsentCreate(BaseModel):
    kind: ConsentKind = ConsentKind.csv_upload
    text_version: str = Field(min_length=1, max_length=50)
    business_id: uuid.UUID | None = None


class ConsentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    business_id: uuid.UUID
    kind: ConsentKind
    text_version: str
    granted_by: uuid.UUID
    granted_at: datetime
    revoked_at: datetime | None


class DataKindSummary(BaseModel):
    rows: int
    date_min: date | None
    date_max: date | None
    last_import_at: datetime | None


class DataSummary(BaseModel):
    customers: DataKindSummary
    payments: DataKindSummary
    visits: DataKindSummary
    obligations: DataKindSummary


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
    duplicate_of: uuid.UUID | None = None


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
    alpha: float = Field(0.05, ge=0.01, le=0.2)
    # пороги можно только ужесточить (спецификация, 2.2)
    min_group_size: int = Field(100, ge=100)
    max_mde: float = Field(0.10, ge=0.01, le=0.10)

    @model_validator(mode="after")
    def _inactive_range(self) -> "Protocol":
        if self.max_inactive_days <= self.inactive_days:
            raise ValueError("max_inactive_days должен быть больше inactive_days")
        return self


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
    seed: str | None = None
    control_share: Decimal | None
    data_snapshot: dict[str, Any] | None = None
    registered_at: datetime | None
    closed_at: datetime | None
    n_control: int | None = None
    n_test: int | None = None


class AssignmentOut(BaseModel):
    customer_id: str
    group: str
    stratum: str


class MdeRequest(BaseModel):
    baseline: float = Field(0.05, gt=0, lt=1)
    n_control: int = Field(ge=0)
    n_test: int = Field(ge=0)
    alpha: float = Field(0.05, ge=0.01, le=0.2)


class MdeResponse(BaseModel):
    n_control: int
    n_test: int
    mde: float | None


class StratumCount(BaseModel):
    stratum: str
    n: int


class PreviewOut(BaseModel):
    cohort_size: int
    baseline: float | None
    baseline_used: float
    n_control: int
    n_test: int
    mde: float | None
    strata: list[StratumCount]
    excluded: dict[str, int]
    excluded_other_experiments: int


class ResultOut(BaseModel):
    experiment_id: uuid.UUID
    computed_at: datetime
    result_hash: str
    payload: dict[str, Any]


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    seq: int
    actor_login: str | None = None
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
    last_hash: str | None


class CertificateAuditEntry(BaseModel):
    seq: int
    action: str
    occurred_at: datetime
    hash: str


class CertificateOut(BaseModel):
    experiment_id: uuid.UUID
    business_name: str
    title: str
    protocol: dict[str, Any]
    protocol_hash: str | None
    seed: str
    registered_at: datetime | None
    closed_at: datetime | None
    assignment_sha256: str | None
    result: dict[str, Any]
    result_hash: str
    audit: list[CertificateAuditEntry]
