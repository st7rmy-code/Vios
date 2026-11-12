import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import check_business, require
from app.models import AuditLog, Role, User
from app.schemas import AuditOut, ChainOut
from app.services.audit import verify_chain

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditOut], operation_id="listAudit")
def list_audit(business_id: uuid.UUID | None = None, limit: int = Query(100, le=1000), before_seq: int | None = None,
               db: Session = Depends(get_session), user: User = Depends(require(Role.admin, Role.owner))):
    q = select(AuditLog).order_by(AuditLog.seq.desc()).limit(limit)
    bid = business_id or user.business_id
    if user.role is not Role.admin or bid is not None:
        check_business(user, bid)
        q = q.where(AuditLog.business_id == bid)
    if before_seq is not None:
        q = q.where(AuditLog.seq < before_seq)
    return list(db.execute(q).scalars())


@router.get("/verify", response_model=ChainOut, operation_id="verifyAudit")
def verify(db: Session = Depends(get_session), _: User = Depends(require(Role.admin, Role.owner))) -> ChainOut:
    c = verify_chain(db)
    return ChainOut(ok=c.ok, checked=c.checked, broken_at_seq=c.broken_at_seq, reason=c.reason)
