"""Согласие собственника на обработку данных (спецификация, 1 и 5.2)."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.db import get_session
from app.deps import business_for, check_business, require
from app.errors import ERROR_RESPONSES, ApiError
from app.models import ConsentKind, DataConsent, Role, User
from app.schemas import ConsentCreate, ConsentOut
from app.services import audit

router = APIRouter(prefix="/consents", tags=["consents"], responses=ERROR_RESPONSES)
CONSENT_TEXT_VERSION = "csv-2026-11"


def active_consent(db: Session, business_id: uuid.UUID, kind: ConsentKind) -> DataConsent | None:
    return db.execute(
        select(DataConsent).where(DataConsent.business_id == business_id, DataConsent.kind == kind,
                                  DataConsent.revoked_at.is_(None))
    ).scalar_one_or_none()


@router.get("", response_model=list[ConsentOut], operation_id="listConsents")
def list_consents(business_id: uuid.UUID | None = None, db: Session = Depends(get_session),
                  user: User = Depends(require(Role.admin, Role.owner))) -> list[DataConsent]:
    bid = business_for(user, business_id)
    return list(db.execute(select(DataConsent).where(DataConsent.business_id == bid)
                           .order_by(DataConsent.granted_at.desc())).scalars())


@router.post("", response_model=ConsentOut, status_code=201, operation_id="grantConsent")
def grant(body: ConsentCreate, db: Session = Depends(get_session),
          user: User = Depends(require(Role.owner))) -> DataConsent:
    bid = business_for(user, body.business_id)
    existing = active_consent(db, bid, body.kind)
    if existing:
        return existing
    c = DataConsent(business_id=bid, kind=body.kind, text_version=body.text_version, granted_by=user.id,
                    granted_at=clock.now())
    db.add(c)
    db.flush()
    audit.append(db, action="consent.granted", entity_type="consent", entity_id=str(c.id),
                 payload={"kind": c.kind.value, "text_version": c.text_version}, business_id=bid, actor_id=user.id)
    db.commit()
    return c


@router.post("/{consent_id}/revoke", response_model=ConsentOut, operation_id="revokeConsent")
def revoke(consent_id: uuid.UUID, db: Session = Depends(get_session),
           user: User = Depends(require(Role.owner))) -> DataConsent:
    c = db.get(DataConsent, consent_id)
    if c is None:
        raise ApiError(404, "Не найдено", "not_found")
    check_business(user, c.business_id)
    if c.revoked_at is None:
        c.revoked_at = clock.now()
        audit.append(db, action="consent.revoked", entity_type="consent", entity_id=str(c.id),
                     payload={"kind": c.kind.value}, business_id=c.business_id, actor_id=user.id)
        db.commit()
    return c
