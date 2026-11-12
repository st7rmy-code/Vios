"""Импорт CSV (спецификация, 3 и 5.2)."""

import uuid

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import clock
from app.config import get_settings
from app.db import get_session
from app.deps import business_for, check_business, require
from app.errors import ERROR_RESPONSES, ApiError
from app.models import (
    Business,
    ConsentKind,
    Customer,
    ExperimentResult,
    Experiment,
    ImportFile,
    ImportKind,
    ImportStatus,
    Obligation,
    Payment,
    Role,
    User,
    Visit,
)
from app.schemas import ImportOut
from app.api.consents import active_consent
from app.services import audit
from app.services.csv_import import parse_csv
from app.storage import get_storage

router = APIRouter(prefix="/imports", tags=["imports"], responses=ERROR_RESPONSES)


@router.post("", response_model=ImportOut, status_code=201, operation_id="uploadImport",
             responses={200: {"model": ImportOut, "description": "Этот файл уже загружен (duplicate_of)"},
                        413: {"description": "Файл больше лимита"}})
async def upload(
    response: Response,
    kind: ImportKind = Form(...),
    file: UploadFile = File(...),
    business_id: uuid.UUID | None = Form(None),
    db: Session = Depends(get_session),
    user: User = Depends(require(Role.admin, Role.owner)),
) -> ImportOut:
    bid = business_for(user, business_id)
    if active_consent(db, bid, ConsentKind.csv_upload) is None:
        raise ApiError(409, "Нужно согласие собственника", "consent_required")
    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise ApiError(413, f"Файл больше {limit // 1024 // 1024} МБ", "file_too_large")

    business = db.get(Business, bid)
    parsed = parse_csv(data, kind, today=clock.today(business.timezone))
    dup = db.execute(
        select(ImportFile).where(ImportFile.business_id == bid, ImportFile.sha256 == parsed.sha256,
                                 ImportFile.status == ImportStatus.accepted)
    ).scalar_one_or_none()
    if dup is not None:
        response.status_code = 200
        out = ImportOut.model_validate(dup)
        out.duplicate_of = dup.id
        return out

    report = parsed.report
    imp = ImportFile(
        business_id=bid, kind=kind, filename=(file.filename or "upload.csv")[:300], sha256=parsed.sha256,
        size_bytes=parsed.size_bytes, status=ImportStatus.accepted if parsed.accepted else ImportStatus.rejected,
        quality_report=report, uploaded_by=user.id,
    )
    db.add(imp)
    db.flush()
    overwritten = 0
    if parsed.accepted:
        # исходник храним только у принятых файлов: в отклонённых могут быть ПДн
        imp.storage_key = f"{bid}/{imp.id}/{parsed.sha256}.csv"
        get_storage().put(imp.storage_key, data)
        report["orphan_customers"], overwritten = _persist_rows(db, bid, imp.id, kind, parsed.rows)
        imp.quality_report = dict(report)  # JSONB: новый объект, чтобы SQLAlchemy увидел изменение
    audit.append(db, action="import.accepted" if parsed.accepted else "import.rejected", entity_type="import",
                 entity_id=str(imp.id), business_id=bid, actor_id=user.id,
                 payload={"kind": kind.value, "sha256": parsed.sha256, "rows_valid": report["rows_valid"],
                          "rows_total": report["rows_total"], "pii_columns": sorted(report["pii_columns"]),
                          "orphan_customers": report.get("orphan_customers", 0)})
    if overwritten:
        has_results = db.execute(
            select(func.count()).select_from(ExperimentResult)
            .join(Experiment, Experiment.id == ExperimentResult.experiment_id)
            .where(Experiment.business_id == bid)
        ).scalar_one()
        if has_results:
            audit.append(db, action="import.overwrote_payments", entity_type="import", entity_id=str(imp.id),
                         business_id=bid, actor_id=user.id, payload={"rows": overwritten})
    db.commit()
    return ImportOut.model_validate(imp)


def _chunks(rows: list[dict], size: int):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def _ensure_customers(db: Session, bid: uuid.UUID, import_id: uuid.UUID, ids: set[str]) -> int:
    """Клиенты из платежей/посещений/обязательств, которых нет в customers, создаются автоматически."""
    created = 0
    for chunk in _chunks(sorted(ids), 5000):
        res = db.execute(
            insert(Customer).values([
                {"id": uuid.uuid4(), "business_id": bid, "external_id": cid, "import_id": import_id} for cid in chunk
            ]).on_conflict_do_nothing(index_elements=["business_id", "external_id"]).returning(Customer.id)
        )
        created += len(res.fetchall())
    return created


def _persist_rows(db: Session, bid: uuid.UUID, import_id: uuid.UUID, kind: ImportKind,
                  rows: list[dict]) -> tuple[int, int]:
    """Upsert по ключу. Возвращает (создано клиентов-«сирот», перезаписано платежей)."""
    if kind is ImportKind.customers:
        for chunk in _chunks(rows, 5000):
            stmt = insert(Customer).values([
                {"id": uuid.uuid4(), "business_id": bid, "external_id": r["customer_id"], "branch": r.get("branch"),
                 "first_paid_at": r.get("first_paid_at"), "subscription_ends_at": r.get("subscription_ends_at"),
                 "frozen_until": r.get("frozen_until"), "import_id": import_id} for r in chunk
            ])
            db.execute(stmt.on_conflict_do_update(
                index_elements=["business_id", "external_id"],
                set_={c: getattr(stmt.excluded, c) for c in
                      ("branch", "first_paid_at", "subscription_ends_at", "frozen_until", "import_id")},
            ))
        return 0, 0

    orphans = _ensure_customers(db, bid, import_id, {r["customer_id"] for r in rows})
    overwritten = 0
    if kind is ImportKind.payments:
        existing = set(db.execute(select(Payment.external_id).where(
            Payment.business_id == bid, Payment.external_id.in_([r["payment_id"] for r in rows]))).scalars())
        overwritten = len(existing)
        for chunk in _chunks(rows, 5000):
            stmt = insert(Payment).values([
                {"id": uuid.uuid4(), "business_id": bid, "external_id": r["payment_id"],
                 "customer_external_id": r["customer_id"], "paid_at": r["paid_at"], "amount_kopecks": r["amount"],
                 "operation": r["operation"], "method": r.get("method"), "branch": r.get("branch"),
                 "import_id": import_id} for r in chunk
            ])
            db.execute(stmt.on_conflict_do_update(
                index_elements=["business_id", "external_id"],
                set_={c: getattr(stmt.excluded, c) for c in
                      ("customer_external_id", "paid_at", "amount_kopecks", "operation", "method", "branch",
                       "import_id")},
            ))
    elif kind is ImportKind.visits:
        for chunk in _chunks(rows, 5000):
            stmt = insert(Visit).values([
                {"id": uuid.uuid4(), "business_id": bid, "customer_external_id": r["customer_id"],
                 "visited_at": r["visited_at"], "branch": r.get("branch"), "import_id": import_id} for r in chunk
            ])
            db.execute(stmt.on_conflict_do_update(constraint="uq_visit_key", set_={"import_id": stmt.excluded.import_id}))
    else:
        for chunk in _chunks(rows, 3000):
            stmt = insert(Obligation).values([
                {"id": uuid.uuid4(), "business_id": bid, "external_id": r["obligation_id"],
                 "customer_external_id": r["customer_id"], "kind": r["kind"], "starts_at": r["starts_at"],
                 "ends_at": r.get("ends_at"), "visits_total": r.get("visits_total"),
                 "visits_used": r.get("visits_used"), "amount_kopecks": r.get("amount"), "status": r["status"],
                 "frozen_from": r.get("frozen_from"), "frozen_until": r.get("frozen_until"),
                 "branch": r.get("branch"), "import_id": import_id} for r in chunk
            ])
            db.execute(stmt.on_conflict_do_update(
                index_elements=["business_id", "external_id"],
                set_={c: getattr(stmt.excluded, c) for c in
                      ("customer_external_id", "kind", "starts_at", "ends_at", "visits_total", "visits_used",
                       "amount_kopecks", "status", "frozen_from", "frozen_until", "branch", "import_id")},
            ))
    return orphans, overwritten


@router.get("", response_model=list[ImportOut], operation_id="listImports")
def list_imports(business_id: uuid.UUID | None = None, db: Session = Depends(get_session),
                 user: User = Depends(require(Role.admin, Role.owner))) -> list[ImportFile]:
    bid = business_for(user, business_id)
    return list(db.execute(select(ImportFile).where(ImportFile.business_id == bid)
                           .order_by(ImportFile.created_at.desc())).scalars())


@router.get("/{import_id}", response_model=ImportOut, operation_id="getImport")
def get_import(import_id: uuid.UUID, db: Session = Depends(get_session),
               user: User = Depends(require(Role.admin, Role.owner))) -> ImportFile:
    imp = db.get(ImportFile, import_id)
    if imp is None:
        raise ApiError(404, "Не найдено", "not_found")
    check_business(user, imp.business_id)
    return imp
