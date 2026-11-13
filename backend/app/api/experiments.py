"""Эксперименты (спецификация, 5.3). Права по разделу 1:

* admin, owner — черновик, регистрация, закрытие, расчёт, всё видят;
* executor — только registered/closed своего бизнеса и только тестовая группа;
  контроль, его размер, доля контроля и стоимость C скрыты до closed.
"""

import csv
import io
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import business_for, check_business, current_user, require
from app.errors import ERROR_RESPONSES, ApiError
from app.models import Assignment, AuditLog, Business, Experiment, ExperimentResult, ExperimentStatus, Role, User
from app.schemas import (
    AssignmentOut,
    CertificateOut,
    ExperimentCreate,
    ExperimentOut,
    ExperimentUpdate,
    MdeRequest,
    MdeResponse,
    PreviewOut,
    Protocol,
    ResultOut,
)
from app.services import audit
from app.services import experiments as svc
from app.stats import mde_two_proportions

router = APIRouter(tags=["experiments"], responses=ERROR_RESPONSES)
MANAGERS = (Role.admin, Role.owner)
HIDDEN_FROM_EXECUTOR = ("control_share", "cost_rub")


def _control_visible(user: User, exp: Experiment) -> bool:
    return user.role in MANAGERS or exp.status is ExperimentStatus.closed


def _get(db: Session, user: User, exp_id: uuid.UUID) -> Experiment:
    exp = db.get(Experiment, exp_id)
    if exp is None:
        raise ApiError(404, "Не найдено", "not_found")
    check_business(user, exp.business_id)
    if user.role is Role.executor and exp.status is ExperimentStatus.draft:
        raise ApiError(404, "Не найдено", "not_found")
    return exp


def _out(db: Session, user: User, exp: Experiment) -> ExperimentOut:
    out = ExperimentOut.model_validate(exp)
    counts = dict(db.execute(select(Assignment.group, func.count()).where(Assignment.experiment_id == exp.id)
                             .group_by(Assignment.group)).all())
    if counts:
        out.n_test = counts.get("test", 0)
        out.n_control = counts.get("control", 0)
    if not _control_visible(user, exp):
        out.n_control = None
        out.control_share = None
        # по seed и списку клиентов исполнитель восстановил бы контрольную группу
        out.seed = None
        out.protocol = {k: v for k, v in out.protocol.items() if k not in HIDDEN_FROM_EXECUTOR}
    if user.role is Role.executor:
        out.data_snapshot = None
    return out


@router.post("/stats/mde", response_model=MdeResponse, operation_id="computeMde")
def compute_mde(body: MdeRequest, _: User = Depends(require(*MANAGERS))) -> MdeResponse:
    """Живой MDE для ползунка доли контроля в мастере."""
    mde = mde_two_proportions(min(max(body.baseline, 0.01), 0.99), body.n_control, body.n_test, alpha=body.alpha)
    return MdeResponse(n_control=body.n_control, n_test=body.n_test, mde=None if mde == float("inf") else mde)


@router.post("/experiments/preview", response_model=PreviewOut, operation_id="previewCohort")
def preview_cohort(protocol: Protocol, business_id: uuid.UUID | None = None, db: Session = Depends(get_session),
                   user: User = Depends(require(*MANAGERS))) -> dict:
    return svc.preview(db, business_for(user, business_id), protocol)


@router.post("/experiments", response_model=ExperimentOut, status_code=201, operation_id="createExperiment")
def create(body: ExperimentCreate, db: Session = Depends(get_session),
           user: User = Depends(require(*MANAGERS))) -> ExperimentOut:
    exp = svc.create(db, user, business_for(user, body.business_id), body.title, body.protocol)
    db.commit()
    return _out(db, user, exp)


@router.get("/experiments", response_model=list[ExperimentOut], operation_id="listExperiments")
def list_experiments(business_id: uuid.UUID | None = None, db: Session = Depends(get_session),
                     user: User = Depends(current_user)) -> list[ExperimentOut]:
    q = select(Experiment).order_by(Experiment.created_at.desc())
    if not (user.role is Role.admin and business_id is None):
        q = q.where(Experiment.business_id == business_for(user, business_id))
    if user.role is Role.executor:
        q = q.where(Experiment.status != ExperimentStatus.draft)
    return [_out(db, user, e) for e in db.execute(q).scalars()]


@router.get("/experiments/{exp_id}", response_model=ExperimentOut, operation_id="getExperiment")
def get_experiment(exp_id: uuid.UUID, db: Session = Depends(get_session),
                   user: User = Depends(current_user)) -> ExperimentOut:
    return _out(db, user, _get(db, user, exp_id))


@router.patch("/experiments/{exp_id}", response_model=ExperimentOut, operation_id="updateExperiment")
def update(exp_id: uuid.UUID, body: ExperimentUpdate, db: Session = Depends(get_session),
           user: User = Depends(require(*MANAGERS))) -> ExperimentOut:
    exp = _get(db, user, exp_id)
    svc.update(db, user, exp, body.title, body.protocol)
    db.commit()
    return _out(db, user, exp)


@router.delete("/experiments/{exp_id}", status_code=204, operation_id="deleteExperiment")
def delete(exp_id: uuid.UUID, db: Session = Depends(get_session),
           user: User = Depends(require(*MANAGERS))) -> Response:
    exp = _get(db, user, exp_id)
    svc.delete(db, user, exp)
    db.commit()
    return Response(status_code=204)


@router.post("/experiments/{exp_id}/register", response_model=ExperimentOut, operation_id="registerExperiment")
def register(exp_id: uuid.UUID, db: Session = Depends(get_session),
             user: User = Depends(require(*MANAGERS))) -> ExperimentOut:
    exp = _get(db, user, exp_id)
    svc.register(db, user, exp)
    db.commit()
    return _out(db, user, exp)


@router.post("/experiments/{exp_id}/close", response_model=ExperimentOut, operation_id="closeExperiment")
def close(exp_id: uuid.UUID, db: Session = Depends(get_session),
          user: User = Depends(require(*MANAGERS))) -> ExperimentOut:
    exp = _get(db, user, exp_id)
    svc.close(db, user, exp)
    db.commit()
    return _out(db, user, exp)


def _assignments(db: Session, user: User, exp: Experiment, group: str | None) -> list[Assignment]:
    if group == "control" and not _control_visible(user, exp):
        raise ApiError(403, "Контрольная группа откроется после закрытия эксперимента", "control_hidden")
    q = select(Assignment).where(Assignment.experiment_id == exp.id).order_by(Assignment.customer_external_id)
    if group is not None:
        q = q.where(Assignment.group == group)
    elif not _control_visible(user, exp):
        q = q.where(Assignment.group == "test")
    return list(db.execute(q).scalars())


@router.get("/experiments/{exp_id}/assignments", response_model=list[AssignmentOut],
            operation_id="listAssignments")
def assignments(exp_id: uuid.UUID, group: Literal["test", "control"] | None = None,
                db: Session = Depends(get_session), user: User = Depends(current_user)) -> list[AssignmentOut]:
    exp = _get(db, user, exp_id)
    return [AssignmentOut(customer_id=a.customer_external_id, group=a.group, stratum=a.stratum)
            for a in _assignments(db, user, exp, group)]


@router.get("/experiments/{exp_id}/assignments.csv", operation_id="exportAssignments",
            response_class=Response, responses={200: {"content": {"text/csv": {}}}})
def export_assignments(exp_id: uuid.UUID, group: Literal["test", "control"] = "test",
                       db: Session = Depends(get_session), user: User = Depends(current_user)) -> Response:
    exp = _get(db, user, exp_id)
    rows = _assignments(db, user, exp, group)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["customer_id", "group"])
    for a in rows:
        w.writerow([a.customer_external_id, a.group])
    audit.append(db, action="assignments.exported", entity_type="experiment", entity_id=str(exp.id),
                 payload={"group": group, "rows": len(rows)}, business_id=exp.business_id, actor_id=user.id)
    db.commit()
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{group}-{str(exp.id)[:8]}.csv"'})


@router.post("/experiments/{exp_id}/calculate", response_model=ResultOut, operation_id="calculateResult")
def calculate(exp_id: uuid.UUID, db: Session = Depends(get_session),
              user: User = Depends(require(*MANAGERS))) -> ResultOut:
    exp = _get(db, user, exp_id)
    res = svc.calculate(db, user, exp)
    db.commit()
    return ResultOut(experiment_id=exp.id, computed_at=res.computed_at, result_hash=res.result_hash,
                     payload=res.payload)


def _latest_result(db: Session, exp: Experiment) -> ExperimentResult:
    res = db.execute(select(ExperimentResult).where(ExperimentResult.experiment_id == exp.id)
                     .order_by(ExperimentResult.computed_at.desc()).limit(1)).scalar_one_or_none()
    if res is None:
        raise ApiError(404, "Результат ещё не рассчитан", "no_result")
    return res


@router.get("/experiments/{exp_id}/result", response_model=ResultOut, operation_id="getResult")
def get_result(exp_id: uuid.UUID, db: Session = Depends(get_session),
               user: User = Depends(current_user)) -> ResultOut:
    exp = _get(db, user, exp_id)
    if not _control_visible(user, exp):
        raise ApiError(403, "Результат откроется после закрытия эксперимента", "result_hidden")
    res = _latest_result(db, exp)
    return ResultOut(experiment_id=exp.id, computed_at=res.computed_at, result_hash=res.result_hash,
                     payload=res.payload)


@router.get("/experiments/{exp_id}/certificate", response_model=CertificateOut, operation_id="getCertificate")
def certificate(exp_id: uuid.UUID, db: Session = Depends(get_session),
                user: User = Depends(current_user)) -> dict:
    """Данные сертификата: протокол, хэши и записи журнала для проверки."""
    exp = _get(db, user, exp_id)
    if exp.status is not ExperimentStatus.closed:
        raise ApiError(409, "Сертификат выдаётся после закрытия эксперимента", "not_closed")
    res = _latest_result(db, exp)
    log = list(db.execute(select(AuditLog).where(AuditLog.entity_type == "experiment",
                                                 AuditLog.entity_id == str(exp.id)).order_by(AuditLog.seq)).scalars())
    reg = next((r for r in log if r.action == "experiment.registered"), None)
    return {
        "experiment_id": str(exp.id),
        "business_name": db.get(Business, exp.business_id).name,
        "title": exp.title,
        "protocol": exp.protocol,
        "protocol_hash": exp.protocol_hash,
        "seed": exp.seed,
        "registered_at": exp.registered_at,
        "closed_at": exp.closed_at,
        "assignment_sha256": reg.payload.get("assignment_sha256") if reg else None,
        "result": res.payload,
        "result_hash": res.result_hash,
        "audit": [{"seq": r.seq, "action": r.action, "occurred_at": r.occurred_at, "hash": r.hash} for r in log],
    }
