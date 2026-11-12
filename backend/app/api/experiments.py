"""Эксперименты. Права (ВРЕМЕННО, до «Ролей и прав»):

* admin, owner — создают, правят черновик, регистрируют, закрывают, считают;
* executor — видит только зарегистрированные эксперименты своего бизнеса и
  только тестовую группу; контрольную группу и её размер — после closed.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import check_business, current_user, require
from app.models import Assignment, AuditLog, Experiment, ExperimentResult, ExperimentStatus, Role, User
from app.schemas import (
    AssignmentOut,
    ExperimentCreate,
    ExperimentOut,
    ExperimentUpdate,
    MdeRequest,
    MdeResponse,
    PreviewOut,
    Protocol,
    ResultOut,
)
from app.services import experiments as svc
from app.stats import mde_two_proportions

router = APIRouter(tags=["experiments"])
MANAGERS = (Role.admin, Role.owner)


def _control_visible(user: User, exp: Experiment) -> bool:
    return user.role in MANAGERS or exp.status is ExperimentStatus.closed


def _get(db: Session, user: User, exp_id: uuid.UUID) -> Experiment:
    exp = db.get(Experiment, exp_id)
    if exp is None:
        raise HTTPException(404, "Не найдено")
    check_business(user, exp.business_id)
    if user.role is Role.executor and exp.status is ExperimentStatus.draft:
        raise HTTPException(404, "Не найдено")
    return exp


def _out(db: Session, user: User, exp: Experiment) -> ExperimentOut:
    out = ExperimentOut.model_validate(exp)
    counts = dict(db.execute(select(Assignment.group, func.count()).where(Assignment.experiment_id == exp.id)
                             .group_by(Assignment.group)).all())
    if counts:
        out.n_test = counts.get("test", 0)
        out.n_control = counts.get("control", 0) if _control_visible(user, exp) else None
    if not _control_visible(user, exp):
        out.protocol = {k: v for k, v in out.protocol.items() if k != "control_share"}
    return out


@router.post("/stats/mde", response_model=MdeResponse, operation_id="computeMde")
def compute_mde(body: MdeRequest, _: User = Depends(require(*MANAGERS))) -> MdeResponse:
    """Живой MDE для ползунка доли контроля в мастере."""
    n_c = round(body.cohort_size * body.control_share)
    n_t = body.cohort_size - n_c
    mde = mde_two_proportions(body.baseline, n_c, n_t, alpha=body.alpha, power=body.power)
    return MdeResponse(n_control=n_c, n_test=n_t, mde=None if mde == float("inf") else mde)


@router.post("/experiments/preview", response_model=PreviewOut, operation_id="previewCohort")
def preview_cohort(protocol: Protocol, business_id: uuid.UUID | None = None, db: Session = Depends(get_session),
                   user: User = Depends(require(*MANAGERS))) -> dict:
    bid = business_id or user.business_id
    if bid is None:
        raise HTTPException(422, "Укажите бизнес")
    check_business(user, bid)
    return svc.preview(db, bid, protocol)


@router.post("/experiments", response_model=ExperimentOut, status_code=201, operation_id="createExperiment")
def create(body: ExperimentCreate, db: Session = Depends(get_session),
           user: User = Depends(require(*MANAGERS))) -> ExperimentOut:
    bid = body.business_id or user.business_id
    if bid is None:
        raise HTTPException(422, "Укажите бизнес")
    check_business(user, bid)
    exp = svc.create(db, user, bid, body.title, body.protocol)
    db.commit()
    return _out(db, user, exp)


@router.get("/experiments", response_model=list[ExperimentOut], operation_id="listExperiments")
def list_experiments(business_id: uuid.UUID | None = None, db: Session = Depends(get_session),
                     user: User = Depends(current_user)) -> list[ExperimentOut]:
    q = select(Experiment).order_by(Experiment.created_at.desc())
    bid = business_id or user.business_id
    if user.role is not Role.admin or bid is not None:
        if bid is None:
            return []
        check_business(user, bid)
        q = q.where(Experiment.business_id == bid)
    if user.role is Role.executor:
        q = q.where(Experiment.status != ExperimentStatus.draft)
    return [_out(db, user, e) for e in db.execute(q).scalars()]


@router.get("/experiments/{exp_id}", response_model=ExperimentOut, operation_id="getExperiment")
def get_experiment(exp_id: uuid.UUID, db: Session = Depends(get_session),
                   user: User = Depends(current_user)) -> ExperimentOut:
    return _out(db, user, _get(db, user, exp_id))


@router.patch("/experiments/{exp_id}", response_model=ExperimentOut, operation_id="updateExperiment",
              responses={409: {"description": "Протокол уже зарегистрирован"}})
def update(exp_id: uuid.UUID, body: ExperimentUpdate, db: Session = Depends(get_session),
           user: User = Depends(require(*MANAGERS))) -> ExperimentOut:
    exp = _get(db, user, exp_id)
    svc.update(db, user, exp, body.title, body.protocol)
    db.commit()
    return _out(db, user, exp)


@router.post("/experiments/{exp_id}/register", response_model=ExperimentOut, operation_id="registerExperiment",
             responses={409: {"description": "Уже зарегистрирован"}})
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


@router.get("/experiments/{exp_id}/assignments", response_model=list[AssignmentOut],
            operation_id="listAssignments")
def assignments(exp_id: uuid.UUID, group: Literal["test", "control"] | None = None,
                db: Session = Depends(get_session), user: User = Depends(current_user)) -> list[AssignmentOut]:
    exp = _get(db, user, exp_id)
    if group == "control" and not _control_visible(user, exp):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Контрольная группа откроется после закрытия эксперимента")
    q = select(Assignment).where(Assignment.experiment_id == exp.id).order_by(Assignment.customer_external_id)
    if group is not None:
        q = q.where(Assignment.group == group)
    elif not _control_visible(user, exp):
        q = q.where(Assignment.group == "test")
    return [AssignmentOut(customer_id=a.customer_external_id, group=a.group, stratum=a.stratum)
            for a in db.execute(q).scalars()]


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
        raise HTTPException(404, "Результат ещё не рассчитан")
    return res


@router.get("/experiments/{exp_id}/result", response_model=ResultOut, operation_id="getResult")
def get_result(exp_id: uuid.UUID, db: Session = Depends(get_session),
               user: User = Depends(current_user)) -> ResultOut:
    exp = _get(db, user, exp_id)
    if not _control_visible(user, exp):
        raise HTTPException(403, "Результат откроется после закрытия эксперимента")
    res = _latest_result(db, exp)
    return ResultOut(experiment_id=exp.id, computed_at=res.computed_at, result_hash=res.result_hash,
                     payload=res.payload)


@router.get("/experiments/{exp_id}/certificate", operation_id="getCertificate")
def certificate(exp_id: uuid.UUID, db: Session = Depends(get_session),
                user: User = Depends(current_user)) -> dict:
    """Данные сертификата: протокол, хэши и ссылки на записи журнала для проверки."""
    exp = _get(db, user, exp_id)
    if exp.status is not ExperimentStatus.closed:
        raise HTTPException(409, "Сертификат выдаётся после закрытия эксперимента")
    res = _latest_result(db, exp)
    log = db.execute(select(AuditLog).where(AuditLog.entity_type == "experiment",
                                            AuditLog.entity_id == str(exp.id)).order_by(AuditLog.seq)).scalars()
    return {
        "experiment_id": str(exp.id),
        "title": exp.title,
        "protocol": exp.protocol,
        "protocol_hash": exp.protocol_hash,
        "seed": exp.seed,
        "registered_at": exp.registered_at,
        "closed_at": exp.closed_at,
        "result": res.payload,
        "result_hash": res.result_hash,
        "audit": [{"seq": r.seq, "action": r.action, "occurred_at": r.occurred_at, "hash": r.hash} for r in log],
    }
