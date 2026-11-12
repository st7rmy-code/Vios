import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.deps import check_business, require
from app.models import Customer, ImportFile, ImportKind, ImportStatus, Payment, Role, User, Visit
from app.schemas import ImportOut
from app.services import audit
from app.services.csv_import import parse_csv
from app.storage import get_storage

router = APIRouter(prefix="/imports", tags=["imports"])


def _business_for(user: User, business_id: uuid.UUID | None) -> uuid.UUID:
    bid = business_id or user.business_id
    if bid is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Укажите бизнес")
    check_business(user, bid)
    return bid


@router.post("", response_model=ImportOut, status_code=201, operation_id="uploadImport")
async def upload(
    kind: ImportKind = Form(...),
    file: UploadFile = File(...),
    business_id: uuid.UUID | None = Form(None),
    db: Session = Depends(get_session),
    user: User = Depends(require(Role.admin, Role.owner)),
) -> ImportFile:
    bid = _business_for(user, business_id)
    data = await file.read(get_settings().max_upload_bytes + 1)
    if len(data) > get_settings().max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Файл больше допустимого размера")
    parsed = parse_csv(data, kind)
    report = parsed.report
    dup = db.execute(
        select(ImportFile.id).where(ImportFile.business_id == bid, ImportFile.sha256 == parsed.sha256,
                                    ImportFile.status == ImportStatus.accepted)
    ).first()
    report["same_file_imported_before"] = dup is not None

    imp = ImportFile(
        business_id=bid, kind=kind, filename=(file.filename or "upload.csv")[:300], sha256=parsed.sha256,
        size_bytes=parsed.size_bytes, status=ImportStatus.accepted if parsed.accepted else ImportStatus.rejected,
        quality_report=report, uploaded_by=user.id,
    )
    db.add(imp)
    db.flush()
    if parsed.accepted:
        # исходник храним только у принятых файлов: в отклонённых могут быть ПДн
        imp.storage_key = f"{bid}/{imp.id}/{parsed.sha256}.csv"
        get_storage().put(imp.storage_key, data)
        _persist_rows(db, bid, imp.id, kind, parsed.rows)
    audit.append(db, action="import.accepted" if parsed.accepted else "import.rejected", entity_type="import",
                 entity_id=str(imp.id), business_id=bid, actor_id=user.id,
                 payload={"kind": kind.value, "sha256": parsed.sha256, "rows_valid": report["rows_valid"],
                          "rows_total": report["rows_total"], "pii_columns": sorted(report["pii_columns"])})
    db.commit()
    return imp


def _persist_rows(db: Session, bid: uuid.UUID, import_id: uuid.UUID, kind: ImportKind, rows: list[dict]) -> None:
    if kind is ImportKind.customers:
        stmt = insert(Customer).values([
            {"id": uuid.uuid4(), "business_id": bid, "external_id": r["customer_id"], "branch": r.get("branch"),
             "first_paid_at": r["first_paid_at"], "subscription_ends_at": r.get("subscription_ends_at"),
             "import_id": import_id} for r in rows
        ])
        stmt = stmt.on_conflict_do_update(
            index_elements=["business_id", "external_id"],
            set_={"branch": stmt.excluded.branch, "first_paid_at": stmt.excluded.first_paid_at,
                  "subscription_ends_at": stmt.excluded.subscription_ends_at, "import_id": stmt.excluded.import_id},
        )
        db.execute(stmt)
    elif kind is ImportKind.payments:
        for chunk in range(0, len(rows), 5000):
            db.execute(insert(Payment).values([
                {"id": uuid.uuid4(), "business_id": bid, "external_id": r["payment_id"],
                 "customer_external_id": r["customer_id"], "paid_at": r["paid_at"],
                 "amount_kopecks": r["amount"], "import_id": import_id} for r in rows[chunk:chunk + 5000]
            ]).on_conflict_do_nothing(index_elements=["business_id", "external_id"]))
    else:
        for chunk in range(0, len(rows), 5000):
            db.execute(insert(Visit).values([
                {"id": uuid.uuid4(), "business_id": bid, "customer_external_id": r["customer_id"],
                 "visited_at": r["visited_at"], "import_id": import_id} for r in rows[chunk:chunk + 5000]
            ]))


@router.get("", response_model=list[ImportOut], operation_id="listImports")
def list_imports(business_id: uuid.UUID | None = None, db: Session = Depends(get_session),
                 user: User = Depends(require(Role.admin, Role.owner))) -> list[ImportFile]:
    bid = _business_for(user, business_id)
    return list(db.execute(select(ImportFile).where(ImportFile.business_id == bid)
                           .order_by(ImportFile.created_at.desc())).scalars())


@router.get("/{import_id}", response_model=ImportOut, operation_id="getImport")
def get_import(import_id: uuid.UUID, db: Session = Depends(get_session),
               user: User = Depends(require(Role.admin, Role.owner))) -> ImportFile:
    imp = db.get(ImportFile, import_id)
    if imp is None:
        raise HTTPException(404, "Не найдено")
    check_business(user, imp.business_id)
    return imp
