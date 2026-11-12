"""Журнал (спецификация, 5.4)."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import business_for, require
from app.errors import ERROR_RESPONSES
from app.models import AuditLog, Role, User
from app.schemas import AuditOut, ChainOut
from app.services.audit import verify_chain

router = APIRouter(prefix="/audit", tags=["audit"], responses=ERROR_RESPONSES)


@router.get("", response_model=list[AuditOut], operation_id="listAudit")
def list_audit(business_id: uuid.UUID | None = None, entity_type: str | None = None, entity_id: str | None = None,
               action: str | None = None, limit: int = Query(100, ge=1, le=1000), before_seq: int | None = None,
               db: Session = Depends(get_session), user: User = Depends(require(Role.admin, Role.owner))):
    q = (select(AuditLog, User.login).outerjoin(User, User.id == AuditLog.actor_id)
         .order_by(AuditLog.seq.desc()).limit(limit))
    if not (user.role is Role.admin and business_id is None):
        q = q.where(AuditLog.business_id == business_for(user, business_id))
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    if action:
        q = q.where(AuditLog.action.startswith(action) if action.endswith(".") else AuditLog.action == action)
    if before_seq is not None:
        q = q.where(AuditLog.seq < before_seq)
    out = []
    for row, login in db.execute(q).all():
        item = AuditOut.model_validate(row)
        item.actor_login = login
        out.append(item)
    return out


@router.get("/verify", response_model=ChainOut, operation_id="verifyAudit")
def verify(db: Session = Depends(get_session), _: User = Depends(require(Role.admin, Role.owner))) -> ChainOut:
    c = verify_chain(db)
    return ChainOut(ok=c.ok, checked=c.checked, broken_at_seq=c.broken_at_seq, reason=c.reason, last_hash=c.last_hash)
