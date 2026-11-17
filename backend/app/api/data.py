"""Сводка данных бизнеса для кабинета (спецификация, 5.2)."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import business_for, require
from app.errors import ERROR_RESPONSES
from app.models import Customer, ImportFile, ImportKind, ImportStatus, Obligation, Payment, Role, User, Visit
from app.schemas import DataKindSummary, DataSummary

router = APIRouter(prefix="/data", tags=["data"], responses=ERROR_RESPONSES)


@router.get("/summary", response_model=DataSummary, operation_id="getDataSummary")
def summary(business_id: uuid.UUID | None = None, db: Session = Depends(get_session),
            user: User = Depends(require(Role.admin, Role.owner))) -> DataSummary:
    bid = business_for(user, business_id)
    last = dict(db.execute(
        select(ImportFile.kind, func.max(ImportFile.created_at))
        .where(ImportFile.business_id == bid, ImportFile.status == ImportStatus.accepted)
        .group_by(ImportFile.kind)
    ).all())

    def one(model, date_col, kind: ImportKind) -> DataKindSummary:
        q = select(func.count(), func.min(date_col), func.max(date_col)).where(model.business_id == bid)
        n, lo, hi = db.execute(q).one()
        return DataKindSummary(rows=n, date_min=lo, date_max=hi, last_import_at=last.get(kind))

    return DataSummary(
        customers=one(Customer, Customer.first_paid_at, ImportKind.customers),
        payments=one(Payment, Payment.paid_at, ImportKind.payments),
        visits=one(Visit, Visit.visited_at, ImportKind.visits),
        obligations=one(Obligation, Obligation.starts_at, ImportKind.obligations),
    )
