"""Жизненный цикл эксперимента: черновик → регистрация (деление) → закрытие → расчёт.

Склейка БД и чистого модуля stats. Все числа считает app.stats.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import stats
from app.models import (
    Assignment,
    Customer,
    Experiment,
    ExperimentResult,
    ExperimentStatus,
    Payment,
    User,
    Visit,
)
from app.schemas import Protocol
from app.services import audit
from app.services.audit import canonical_json


def protocol_hash(protocol: dict, seed: str) -> str:
    return hashlib.sha256(canonical_json({"protocol": protocol, "seed": seed}).encode()).hexdigest()


def cost_kopecks(p: Protocol) -> int:
    return int((p.cost_rub * 100).to_integral_value())


def rule_of(p: Protocol) -> stats.CohortRule:
    return stats.CohortRule(as_of=p.as_of, inactive_days=p.inactive_days, max_inactive_days=p.max_inactive_days)


def load_customers(db: Session, business_id: uuid.UUID, as_of: date) -> list[stats.Customer]:
    """Собирает клиентов из импортированных данных, видимых на дату среза."""
    paid = dict(
        db.execute(
            select(Payment.customer_external_id, func.sum(Payment.amount_kopecks))
            .where(Payment.business_id == business_id, Payment.paid_at <= as_of)
            .group_by(Payment.customer_external_id)
        ).all()
    )
    first_paid = dict(
        db.execute(
            select(Payment.customer_external_id, func.min(Payment.paid_at))
            .where(Payment.business_id == business_id, Payment.paid_at <= as_of)
            .group_by(Payment.customer_external_id)
        ).all()
    )
    last_visit = dict(
        db.execute(
            select(Visit.customer_external_id, func.max(Visit.visited_at))
            .where(Visit.business_id == business_id, Visit.visited_at <= as_of)
            .group_by(Visit.customer_external_id)
        ).all()
    )
    out = []
    for c in db.execute(select(Customer).where(Customer.business_id == business_id)).scalars():
        out.append(
            stats.Customer(
                customer_id=c.external_id,
                first_paid_at=first_paid.get(c.external_id) or c.first_paid_at,
                last_visit_at=last_visit.get(c.external_id),
                subscription_ends_at=c.subscription_ends_at,
                total_paid_kopecks=int(paid.get(c.external_id) or 0),
                branch_id=c.branch,
            )
        )
    return out


def baseline_rate(db: Session, business_id: uuid.UUID, p: Protocol) -> float | None:
    """Историческая доля возврата: та же когорта на срез на окно раньше."""
    past = p.model_copy(update={"as_of": p.as_of - timedelta(days=p.window_days)})
    cohort = stats.select_cohort(load_customers(db, business_id, past.as_of), rule_of(past))
    if not cohort:
        return None
    outcomes = load_outcomes(db, business_id, [c.customer_id for c in cohort], past)
    return sum(o.returned for o in outcomes) / len(cohort)


def load_outcomes(db: Session, business_id: uuid.UUID, ids: list[str], p: Protocol) -> list[stats.Outcome]:
    start, end = p.as_of, p.as_of + timedelta(days=p.window_days)
    rows = dict(
        db.execute(
            select(Payment.customer_external_id, func.sum(Payment.amount_kopecks))
            .where(
                Payment.business_id == business_id,
                Payment.customer_external_id.in_(ids),
                Payment.paid_at > start,
                Payment.paid_at <= end,
            )
            .group_by(Payment.customer_external_id)
        ).all()
    )
    return [stats.Outcome(cid, cid in rows, int(rows.get(cid) or 0)) for cid in sorted(ids)]


def preview(db: Session, business_id: uuid.UUID, p: Protocol) -> dict:
    cohort = stats.select_cohort(load_customers(db, business_id, p.as_of), rule_of(p))
    n = len(cohort)
    n_c = int((p.control_share * n).to_integral_value())
    base = baseline_rate(db, business_id, p)
    mde = stats.mde_two_proportions(min(max(base or 0.05, 0.01), 0.99), n_c, n - n_c, alpha=p.alpha) if n else None
    return {"cohort_size": n, "baseline": base, "n_control": n_c, "n_test": n - n_c,
            "mde": None if mde is None or mde == float("inf") else mde}


def ensure_draft(exp: Experiment) -> None:
    if exp.status is not ExperimentStatus.draft:
        raise HTTPException(status.HTTP_409_CONFLICT, "Протокол зарегистрирован, менять его нельзя")


def create(db: Session, user: User, business_id: uuid.UUID, title: str, p: Protocol) -> Experiment:
    exp = Experiment(
        business_id=business_id,
        title=title,
        protocol=p.model_dump(mode="json"),
        seed=secrets.token_hex(16),
        control_share=p.control_share,
        created_by=user.id,
    )
    db.add(exp)
    db.flush()
    audit.append(db, action="experiment.created", entity_type="experiment", entity_id=str(exp.id),
                 payload={"title": title, "protocol": exp.protocol}, business_id=business_id, actor_id=user.id)
    return exp


def update(db: Session, user: User, exp: Experiment, title: str | None, p: Protocol | None) -> Experiment:
    ensure_draft(exp)
    if title is not None:
        exp.title = title
    if p is not None:
        exp.protocol = p.model_dump(mode="json")
        exp.control_share = p.control_share
    audit.append(db, action="experiment.updated", entity_type="experiment", entity_id=str(exp.id),
                 payload={"title": exp.title, "protocol": exp.protocol}, business_id=exp.business_id,
                 actor_id=user.id)
    return exp


def register(db: Session, user: User, exp: Experiment) -> Experiment:
    ensure_draft(exp)
    p = Protocol.model_validate(exp.protocol)
    rule = rule_of(p)
    cohort = stats.select_cohort(load_customers(db, exp.business_id, p.as_of), rule)
    if not cohort:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Когорта пустая: проверьте данные и правило")
    strata = {c.customer_id: stats.stratum_of(c, rule) for c in cohort}
    groups = stats.assign_groups(strata.items(), exp.seed, p.control_share)
    db.add_all(
        Assignment(experiment_id=exp.id, customer_external_id=cid, stratum=strata[cid], group=g)
        for cid, g in groups.items()
    )
    exp.protocol_hash = protocol_hash(exp.protocol, exp.seed)
    exp.status = ExperimentStatus.registered
    exp.registered_at = datetime.now(UTC)
    assignment_digest = hashlib.sha256(
        canonical_json(sorted(groups.items())).encode()
    ).hexdigest()
    audit.append(db, action="experiment.registered", entity_type="experiment", entity_id=str(exp.id),
                 payload={"protocol_hash": exp.protocol_hash, "seed": exp.seed, "cohort_size": len(groups),
                          "n_control": sum(g == stats.assignment.CONTROL for g in groups.values()),
                          "assignment_sha256": assignment_digest},
                 business_id=exp.business_id, actor_id=user.id)
    return exp


def close(db: Session, user: User, exp: Experiment) -> Experiment:
    if exp.status is not ExperimentStatus.registered:
        raise HTTPException(status.HTTP_409_CONFLICT, "Закрыть можно только зарегистрированный эксперимент")
    exp.status = ExperimentStatus.closed
    exp.closed_at = datetime.now(UTC)
    audit.append(db, action="experiment.closed", entity_type="experiment", entity_id=str(exp.id),
                 payload={}, business_id=exp.business_id, actor_id=user.id)
    return exp


def calculate(db: Session, user: User, exp: Experiment) -> ExperimentResult:
    if exp.status is not ExperimentStatus.closed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Результат считается после закрытия эксперимента")
    p = Protocol.model_validate(exp.protocol)
    assignment = dict(
        db.execute(
            select(Assignment.customer_external_id, Assignment.group).where(Assignment.experiment_id == exp.id)
        ).all()
    )
    outcomes = load_outcomes(db, exp.business_id, list(assignment), p)
    base = baseline_rate(db, exp.business_id, p)
    r = stats.estimate_effect(
        assignment, outcomes, seed=exp.seed, cost_kopecks=cost_kopecks(p), baseline_rate=base,
        alpha=p.alpha, min_group_size=p.min_group_size, max_mde=p.max_mde,
    )
    payload = r.to_dict()
    payload["baseline_rate"] = base
    payload["protocol_hash"] = exp.protocol_hash
    payload = _json_safe(payload)
    res = ExperimentResult(
        experiment_id=exp.id,
        payload=payload,
        result_hash=hashlib.sha256(canonical_json(payload).encode()).hexdigest(),
    )
    db.add(res)
    db.flush()
    audit.append(db, action="experiment.calculated", entity_type="experiment", entity_id=str(exp.id),
                 payload={"result_hash": res.result_hash, "status": payload["status"]},
                 business_id=exp.business_id, actor_id=user.id)
    return res


def _json_safe(obj):
    if isinstance(obj, float):
        return None if obj != obj or obj in (float("inf"), float("-inf")) else round(obj, 10)
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    return obj
