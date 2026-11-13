"""Модели данных (спецификация, раздел 4).

Принципы:
* в базе нет ФИО, телефонов и email клиентов, только внешний customer_id;
* деньги — целые копейки (BigInteger);
* audit_log, assignment, experiment_result — только INSERT (триггеры в миграциях),
  протокол эксперимента неизменяем после регистрации (триггер).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Boolean,
    CheckConstraint,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Role(str, enum.Enum):
    admin = "admin"  # методист платформы: видит всё, ведёт журнал
    owner = "owner"  # собственник бизнеса: протокол, регистрация, результат
    executor = "executor"  # исполнитель (тренер, администратор): только тестовая группа


class ExperimentStatus(str, enum.Enum):
    draft = "draft"
    registered = "registered"
    closed = "closed"


class ImportKind(str, enum.Enum):
    customers = "customers"
    payments = "payments"
    visits = "visits"
    obligations = "obligations"


class PaymentOperation(str, enum.Enum):
    payment = "payment"
    refund = "refund"


class ObligationKind(str, enum.Enum):
    subscription = "subscription"
    package = "package"
    prepayment = "prepayment"
    debt = "debt"


class ObligationStatus(str, enum.Enum):
    active = "active"
    frozen = "frozen"
    closed = "closed"
    cancelled = "cancelled"


class ConsentKind(str, enum.Enum):
    csv_upload = "csv_upload"


class ImportStatus(str, enum.Enum):
    accepted = "accepted"
    rejected = "rejected"


class Business(Base):
    __tablename__ = "business"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), server_default="Europe/Moscow", default="Europe/Moscow")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    """Сотрудник бизнеса или платформы (не клиент клуба)."""

    __tablename__ = "app_user"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    business_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("business.id"))
    login: Mapped[str] = mapped_column(String(200), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[Role] = mapped_column(Enum(Role, name="role"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DataConsent(Base):
    """Согласие собственника на обработку данных. Одно действующее на (business_id, kind)."""

    __tablename__ = "data_consent"
    __table_args__ = (
        Index("uq_consent_active", "business_id", "kind", unique=True, postgresql_where=text("revoked_at IS NULL")),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id"), index=True)
    kind: Mapped[ConsentKind] = mapped_column(Enum(ConsentKind, name="consent_kind"))
    text_version: Mapped[str] = mapped_column(String(50))
    granted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportFile(Base):
    __tablename__ = "import_file"
    __table_args__ = (
        Index("uq_import_accepted_sha", "business_id", "sha256", unique=True,
              postgresql_where=text("status = 'accepted'")),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id"), index=True)
    kind: Mapped[ImportKind] = mapped_column(Enum(ImportKind, name="import_kind"))
    filename: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    storage_key: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[ImportStatus] = mapped_column(Enum(ImportStatus, name="import_status"))
    quality_report: Mapped[dict] = mapped_column(JSONB)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Customer(Base):
    """Псевдонимный клиент: только внешний идентификатор и агрегаты."""

    __tablename__ = "customer"
    __table_args__ = (UniqueConstraint("business_id", "external_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(100))
    branch: Mapped[str | None] = mapped_column(String(100))
    first_paid_at: Mapped[date | None] = mapped_column(Date)
    subscription_ends_at: Mapped[date | None] = mapped_column(Date)
    frozen_until: Mapped[date | None] = mapped_column(Date)
    import_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_file.id"))


class Payment(Base):
    __tablename__ = "payment"
    __table_args__ = (
        UniqueConstraint("business_id", "external_id"),
        CheckConstraint("amount_kopecks > 0", name="ck_payment_amount_positive"),
        Index("ix_payment_business_customer_paid", "business_id", "customer_external_id", "paid_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(100))
    customer_external_id: Mapped[str] = mapped_column(String(100), index=True)
    paid_at: Mapped[date] = mapped_column(Date)
    amount_kopecks: Mapped[int] = mapped_column(BigInteger)
    operation: Mapped[PaymentOperation] = mapped_column(
        Enum(PaymentOperation, name="payment_operation"), server_default="payment", default=PaymentOperation.payment
    )
    method: Mapped[str | None] = mapped_column(String(20))
    branch: Mapped[str | None] = mapped_column(String(100))
    import_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_file.id"))


class Visit(Base):
    __tablename__ = "visit"
    __table_args__ = (
        UniqueConstraint("business_id", "customer_external_id", "visited_at", "branch",
                         name="uq_visit_key", postgresql_nulls_not_distinct=True),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id"), index=True)
    customer_external_id: Mapped[str] = mapped_column(String(100), index=True)
    visited_at: Mapped[date] = mapped_column(Date)
    branch: Mapped[str | None] = mapped_column(String(100))
    import_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_file.id"))


class Obligation(Base):
    """Реестр обязательств: абонементы, пакеты, предоплаты, долги (раздел 4.2)."""

    __tablename__ = "obligation"
    __table_args__ = (UniqueConstraint("business_id", "external_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(100))
    customer_external_id: Mapped[str] = mapped_column(String(100), index=True)
    kind: Mapped[ObligationKind] = mapped_column(Enum(ObligationKind, name="obligation_kind"))
    starts_at: Mapped[date] = mapped_column(Date)
    ends_at: Mapped[date | None] = mapped_column(Date)
    visits_total: Mapped[int | None] = mapped_column(Integer)
    visits_used: Mapped[int | None] = mapped_column(Integer)
    amount_kopecks: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[ObligationStatus] = mapped_column(Enum(ObligationStatus, name="obligation_status"))
    frozen_from: Mapped[date | None] = mapped_column(Date)
    frozen_until: Mapped[date | None] = mapped_column(Date)
    branch: Mapped[str | None] = mapped_column(String(100))
    import_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_file.id"))


class Experiment(Base):
    __tablename__ = "experiment"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[ExperimentStatus] = mapped_column(
        Enum(ExperimentStatus, name="experiment_status"), default=ExperimentStatus.draft
    )
    # Протокол: правило когорты, доля контроля, окно замера, стоимость C, действие.
    protocol: Mapped[dict] = mapped_column(JSONB)
    protocol_hash: Mapped[str | None] = mapped_column(String(64))
    seed: Mapped[str | None] = mapped_column(String(64))  # создаётся при регистрации
    control_share: Mapped[float] = mapped_column(Numeric(4, 3))
    data_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # собственник при закрытии подтверждает: выгрузка оплат полная по эту дату включительно
    data_complete_through: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Assignment(Base):
    __tablename__ = "assignment"
    experiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiment.id"), primary_key=True)
    customer_external_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    stratum: Mapped[str] = mapped_column(String(50))
    group: Mapped[str] = mapped_column("grp", String(10))


class ExperimentResult(Base):
    """Версии результата: первая — основная (по ней сертификат), пересчёт с другими цифрами — новая версия с причиной."""

    __tablename__ = "experiment_result"
    __table_args__ = (UniqueConstraint("experiment_id", "version", name="uq_experiment_result_version"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    experiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiment.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    result_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, server_default="1", default=1)
    reason: Mapped[str | None] = mapped_column(Text)
    computed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """Журнал: только INSERT. hash = sha256(prev_hash + canonical_json(запись))."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    business_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSONB)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)
    seq: Mapped[int] = mapped_column(Integer, unique=True)
