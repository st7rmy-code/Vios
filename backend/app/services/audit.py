"""Журнал действий с хэш-цепочкой.

hash_n = sha256(prev_hash + canonical_json(запись_n)), prev_hash первой записи — 64 нуля.
Таблица защищена триггером от UPDATE/DELETE/TRUNCATE (см. миграцию). Запись
идёт под транзакционной advisory-блокировкой, чтобы цепочка была линейной.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AuditLog

GENESIS = "0" * 64
_LOCK_KEY = 0x5E4E4A  # произвольная константа для pg_advisory_xact_lock


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="microseconds")


def record_body(row: AuditLog) -> dict[str, Any]:
    return {
        "seq": row.seq,
        "occurred_at": _iso(row.occurred_at),
        "business_id": str(row.business_id) if row.business_id else None,
        "actor_id": str(row.actor_id) if row.actor_id else None,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "payload": row.payload,
    }


def compute_hash(prev_hash: str, body: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + canonical_json(body)).encode()).hexdigest()


def append(
    session: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    payload: dict[str, Any] | None = None,
    business_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
) -> AuditLog:
    """Добавляет запись в текущую транзакцию. Коммит — за вызывающим."""
    session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
    last = session.execute(select(AuditLog).order_by(AuditLog.seq.desc()).limit(1)).scalar_one_or_none()
    prev_hash = last.hash if last else GENESIS
    row = AuditLog(
        seq=(last.seq + 1) if last else 1,
        occurred_at=datetime.now(UTC),
        business_id=business_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        # нормализуем payload через JSON, чтобы хэш совпал с тем, что вернёт JSONB
        payload=json.loads(canonical_json(payload or {})),
        prev_hash=prev_hash,
    )
    row.hash = compute_hash(prev_hash, record_body(row))
    session.add(row)
    session.flush()
    return row


@dataclass(frozen=True)
class ChainCheck:
    ok: bool
    checked: int
    broken_at_seq: int | None = None
    reason: str | None = None


def verify_chain(session: Session) -> ChainCheck:
    prev = GENESIS
    expected_seq = 1
    n = 0
    for row in session.execute(select(AuditLog).order_by(AuditLog.seq)).scalars():
        if row.seq != expected_seq:
            return ChainCheck(False, n, row.seq, "пропуск или повтор номера записи")
        if row.prev_hash != prev:
            return ChainCheck(False, n, row.seq, "prev_hash не совпадает с хэшем предыдущей записи")
        if compute_hash(prev, record_body(row)) != row.hash:
            return ChainCheck(False, n, row.seq, "содержимое записи не совпадает с её хэшем")
        prev = row.hash
        expected_seq += 1
        n += 1
    return ChainCheck(True, n)
