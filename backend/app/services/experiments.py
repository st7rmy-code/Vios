"""Жизненный цикл эксперимента (спецификация, 2.1): черновик → регистрация → закрытие → расчёт.

Склейка БД и чистого модуля stats. Все числа считает app.stats; «сегодня» берётся
только из app.clock в часовом поясе бизнеса.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app import clock, stats
from app.errors import ApiError
from app.models import (
    Assignment,
    Business,
    Customer,
    Experiment,
    ExperimentResult,
    ExperimentStatus,
    ImportFile,
    ImportKind,
    ImportStatus,
    Obligation,
    ObligationKind,
    ObligationStatus,
    Payment,
    PaymentOperation,
    User,
    Visit,
)
from app.schemas import Protocol
from app.services import audit
from app.services.audit import canonical_json

AS_OF_MAX_AGE_DAYS = 7


def protocol_hash(protocol: dict, seed: str) -> str:
    return hashlib.sha256(canonical_json({"protocol": protocol, "seed": seed}).encode()).hexdigest()


def cost_kopecks(p: Protocol) -> int:
    return int((p.cost_rub * 100).to_integral_value())


def rule_of(p: Protocol) -> stats.CohortRule:
    return stats.CohortRule(as_of=p.as_of, inactive_days=p.inactive_days, max_inactive_days=p.max_inactive_days)


def business_today(db: Session, business_id: uuid.UUID) -> date:
    b = db.get(Business, business_id)
    return clock.today(b.timezone if b else "Europe/Moscow")


# --- данные на дату среза -------------------------------------------------------------------

def _signed_amount():
    return case((Payment.operation == PaymentOperation.refund, -Payment.amount_kopecks), else_=Payment.amount_kopecks)


def customers_in_registered(db: Session, business_id: uuid.UUID, exclude: uuid.UUID | None = None) -> set[str]:
    q = (
        select(Assignment.customer_external_id)
        .join(Experiment, Experiment.id == Assignment.experiment_id)
        .where(Experiment.business_id == business_id, Experiment.status == ExperimentStatus.registered)
    )
    if exclude is not None:
        q = q.where(Experiment.id != exclude)
    return set(db.execute(q).scalars())


def load_customers(
    db: Session, business_id: uuid.UUID, as_of: date, exclude_experiment: uuid.UUID | None = None
) -> list[stats.Customer]:
    """Клиенты с признаками когорты, все данные с датами ≤ as_of (спецификация, 2.3)."""
    pay_rows = db.execute(
        select(
            Payment.customer_external_id,
            func.sum(_signed_amount()),
            func.min(case((Payment.operation == PaymentOperation.payment, Payment.paid_at))),
            func.max(case((Payment.operation == PaymentOperation.payment, Payment.paid_at))),
        )
        .where(Payment.business_id == business_id, Payment.paid_at <= as_of)
        .group_by(Payment.customer_external_id)
    ).all()
    net_paid = {cid: int(total or 0) for cid, total, _, _ in pay_rows}
    first_paid = {cid: first for cid, _, first, _ in pay_rows}
    last_paid = {cid: last for cid, _, _, last in pay_rows}
    last_visit = dict(
        db.execute(
            select(Visit.customer_external_id, func.max(Visit.visited_at))
            .where(Visit.business_id == business_id, Visit.visited_at <= as_of)
            .group_by(Visit.customer_external_id)
        ).all()
    )

    # Реестр обязательств, если загружен, главнее customers.subscription_ends_at / frozen_until
    obligations: dict[str, list[Obligation]] = {}
    for o in db.execute(
        select(Obligation).where(Obligation.business_id == business_id, Obligation.starts_at <= as_of,
                                 Obligation.kind != ObligationKind.debt)
    ).scalars():
        obligations.setdefault(o.customer_external_id, []).append(o)
    registry_loaded = db.execute(
        select(func.count()).select_from(Obligation).where(Obligation.business_id == business_id)
    ).scalar_one() > 0

    busy = customers_in_registered(db, business_id, exclude=exclude_experiment)

    out = []
    for c in db.execute(select(Customer).where(Customer.business_id == business_id)).scalars():
        cid = c.external_id
        if registry_loaded:
            obs = obligations.get(cid, [])
            active = any(_obligation_active(o, as_of) for o in obs)
            frozen = any(o.frozen_from and o.frozen_until and o.frozen_from <= as_of <= o.frozen_until for o in obs)
            ends = [o.ends_at for o in obs if o.ends_at is not None and o.status is not ObligationStatus.cancelled]
            last_end = max((e for e in ends if e <= as_of), default=None)
        else:
            active = False
            frozen = c.frozen_until is not None and c.frozen_until >= as_of
            last_end = c.subscription_ends_at
        out.append(
            stats.Customer(
                customer_id=cid,
                first_paid_at=first_paid.get(cid) or c.first_paid_at,
                last_visit_at=last_visit.get(cid),
                subscription_ends_at=last_end,
                total_paid_kopecks=net_paid.get(cid, 0),
                branch_id=c.branch,
                active_obligation=active,
                frozen=frozen,
                in_other_experiment=cid in busy,
                last_paid_at=last_paid.get(cid),
            )
        )
    return out


def _obligation_active(o: Obligation, d: date) -> bool:
    if o.status is not ObligationStatus.active or o.starts_at > d:
        return False
    if o.ends_at is not None and o.ends_at < d:
        return False
    if o.kind is ObligationKind.package and o.visits_total is not None:
        return (o.visits_used or 0) < o.visits_total
    return True


def load_outcomes(db: Session, business_id: uuid.UUID, ids: list[str], start: date, end: date) -> list[stats.Outcome]:
    """Исход в окне [start; end] включительно: вернулся = была оплата; выручка = оплаты − возвраты."""
    rows = db.execute(
        select(
            Payment.customer_external_id,
            func.sum(_signed_amount()),
            func.count().filter(Payment.operation == PaymentOperation.payment),
        )
        .where(
            Payment.business_id == business_id,
            Payment.customer_external_id.in_(ids),
            Payment.paid_at >= start,
            Payment.paid_at <= end,
        )
        .group_by(Payment.customer_external_id)
    ).all()
    by_id = {cid: (int(rev or 0), int(n_pay or 0)) for cid, rev, n_pay in rows}
    return [
        stats.Outcome(cid, by_id.get(cid, (0, 0))[1] > 0, by_id.get(cid, (0, 0))[0]) for cid in sorted(ids)
    ]


def baseline_rate(db: Session, business_id: uuid.UUID, p: Protocol, exclude: uuid.UUID | None = None) -> float | None:
    """p0: та же когорта на срез на одно окно раньше, её фактический возврат (спецификация, 2.7)."""
    past = p.model_copy(update={"as_of": p.as_of - timedelta(days=p.window_days)})
    cohort = stats.select_cohort(load_customers(db, business_id, past.as_of, exclude), rule_of(past))
    if not cohort:
        return None
    # история: окно сразу после прошлого среза, той же длины
    outcomes = load_outcomes(db, business_id, [c.customer_id for c in cohort], past.as_of + timedelta(days=1),
                             past.as_of + timedelta(days=p.window_days))
    return sum(o.returned for o in outcomes) / len(cohort)


def clamp_baseline(b: float | None) -> float:
    return min(max(b if b is not None else 0.05, 0.01), 0.99)


def expected_split(n: int, share: Decimal) -> tuple[int, int]:
    from decimal import ROUND_HALF_EVEN

    n_c = int((share * n).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
    return n_c, n - n_c


def preview(db: Session, business_id: uuid.UUID, p: Protocol) -> dict:
    rule = rule_of(p)
    cohort, excluded = stats.cohort_with_exclusions(load_customers(db, business_id, p.as_of), rule)
    n = len(cohort)
    n_c, n_t = expected_split(n, p.control_share)
    base = baseline_rate(db, business_id, p)
    used = clamp_baseline(base)
    mde = stats.mde_two_proportions(used, n_c, n_t, alpha=p.alpha) if n_c and n_t else None
    strata = Counter(stats.assign_strata(cohort, rule).values())
    return {
        "cohort_size": n, "baseline": base, "baseline_used": used, "n_control": n_c, "n_test": n_t,
        "mde": mde, "strata": [{"stratum": s, "n": k} for s, k in sorted(strata.items())],
        "excluded": excluded, "excluded_other_experiments": excluded.get("other_experiment", 0),
    }


# --- жизненный цикл --------------------------------------------------------------------------

def ensure_draft(exp: Experiment) -> None:
    if exp.status is not ExperimentStatus.draft:
        raise ApiError(409, "Протокол зарегистрирован, менять его нельзя", "protocol_locked")


def create(db: Session, user: User, business_id: uuid.UUID, title: str, p: Protocol) -> Experiment:
    exp = Experiment(
        business_id=business_id,
        title=title,
        protocol=p.model_dump(mode="json"),
        seed=None,  # seed появляется только при регистрации (спецификация, 2.5)
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


def delete(db: Session, user: User, exp: Experiment) -> None:
    ensure_draft(exp)
    audit.append(db, action="experiment.deleted", entity_type="experiment", entity_id=str(exp.id),
                 payload={"title": exp.title}, business_id=exp.business_id, actor_id=user.id)
    db.delete(exp)


def data_snapshot(db: Session, business_id: uuid.UUID) -> dict:
    rows = db.execute(
        select(ImportFile.kind, ImportFile.id, ImportFile.sha256)
        .where(ImportFile.business_id == business_id, ImportFile.status == ImportStatus.accepted)
        .order_by(ImportFile.created_at, ImportFile.id)
    ).all()
    snap: dict[str, list[dict]] = {k.value: [] for k in ImportKind}
    for kind, iid, sha in rows:
        snap[kind.value].append({"id": str(iid), "sha256": sha})
    return snap


def register(db: Session, user: User, exp: Experiment) -> Experiment:
    ensure_draft(exp)
    p = Protocol.model_validate(exp.protocol)
    today = business_today(db, exp.business_id)
    if p.as_of > today or p.as_of < today - timedelta(days=AS_OF_MAX_AGE_DAYS):
        raise ApiError(422, f"Дата среза должна быть не позже сегодняшней и не раньше чем за {AS_OF_MAX_AGE_DAYS} "
                            "дней до регистрации", "as_of_out_of_range")
    rule = rule_of(p)
    cohort = stats.select_cohort(load_customers(db, exp.business_id, p.as_of), rule)
    if not cohort:
        raise ApiError(422, "Когорта пустая: проверьте данные и правило", "empty_cohort")

    seed = secrets.token_hex(16)
    strata = stats.assign_strata(cohort, rule)
    groups = stats.assign_groups(strata.items(), seed, p.control_share)
    db.add_all(
        Assignment(experiment_id=exp.id, customer_external_id=cid, stratum=strata[cid], group=g)
        for cid, g in groups.items()
    )
    exp.seed = seed
    exp.protocol_hash = protocol_hash(exp.protocol, seed)
    exp.data_snapshot = data_snapshot(db, exp.business_id)
    exp.status = ExperimentStatus.registered
    exp.registered_at = clock.now()
    assignment_digest = hashlib.sha256(canonical_json(sorted(groups.items())).encode()).hexdigest()
    audit.append(db, action="experiment.registered", entity_type="experiment", entity_id=str(exp.id),
                 payload={"protocol_hash": exp.protocol_hash, "seed": seed, "cohort_size": len(groups),
                          "n_control": sum(g == "control" for g in groups.values()),
                          "assignment_sha256": assignment_digest, "data_snapshot": exp.data_snapshot},
                 business_id=exp.business_id, actor_id=user.id)
    return exp


def window_of(db: Session, exp: Experiment) -> tuple[date, date] | None:
    """Окно замера [первый день; последний день] включительно.

    Начинается в день регистрации по часовому поясу бизнеса: только после регистрации
    исполнитель получает список теста, значит раньше эффекта быть не может. Оплаты между
    датой среза и регистрацией в исход не попадают. Длина окна — window_days дней.
    """
    if exp.registered_at is None:
        return None
    p = Protocol.model_validate(exp.protocol)
    b = db.get(Business, exp.business_id)
    start = exp.registered_at.astimezone(ZoneInfo(b.timezone if b else "Europe/Moscow")).date()
    return start, start + timedelta(days=p.window_days - 1)


def margin_of(p: Protocol) -> float:
    return float(p.margin_pct / 100)


def close(db: Session, user: User, exp: Experiment, data_complete_through: date) -> Experiment:
    """Закрытие: окно прошло, собственник подтвердил полноту выгрузки, и выгрузка оплат
    действительно сделана после конца окна (иначе в ней физически не может быть всех оплат окна).
    """
    if exp.status is not ExperimentStatus.registered:
        raise ApiError(409, "Закрыть можно только зарегистрированный эксперимент", "not_registered")
    _, end = window_of(db, exp)
    today = business_today(db, exp.business_id)
    if today <= end:
        raise ApiError(409, f"Окно замера ещё идёт: закрыть можно с {end + timedelta(days=1):%d.%m.%Y}",
                       "window_not_over")
    if data_complete_through < end or data_complete_through > today:
        raise ApiError(422, f"Подтвердите полноту выгрузки не раньше конца окна ({end:%d.%m.%Y}) и не позже сегодня",
                       "completeness_date_out_of_range")
    b = db.get(Business, exp.business_id)
    tz = ZoneInfo(b.timezone if b else "Europe/Moscow")
    last_upload = db.execute(
        select(func.max(ImportFile.created_at)).where(
            ImportFile.business_id == exp.business_id, ImportFile.kind == ImportKind.payments,
            ImportFile.status == ImportStatus.accepted,
        )
    ).scalar_one_or_none()
    if last_upload is None or last_upload.astimezone(tz).date() <= end:
        have = f"последняя загрузка {last_upload.astimezone(tz):%d.%m.%Y}" if last_upload else "оплаты не загружались"
        raise ApiError(409, f"Загрузите свежую выписку оплат: она должна быть сделана после {end:%d.%m.%Y} ({have})",
                       "payments_not_covering_window")
    exp.status = ExperimentStatus.closed
    exp.closed_at = clock.now()
    exp.data_complete_through = data_complete_through
    audit.append(db, action="experiment.closed", entity_type="experiment", entity_id=str(exp.id),
                 payload={"data_complete_through": data_complete_through.isoformat(),
                          "last_payments_upload_at": last_upload.isoformat()},
                 business_id=exp.business_id, actor_id=user.id)
    return exp


def payment_import_ids(db: Session, business_id: uuid.UUID, ids: list[str], start: date, end: date) -> list[str]:
    rows = db.execute(
        select(Payment.import_id).distinct().where(
            Payment.business_id == business_id, Payment.customer_external_id.in_(ids),
            Payment.paid_at >= start, Payment.paid_at <= end,
        )
    ).scalars()
    return sorted(str(r) for r in rows)


def results_of(db: Session, exp: Experiment) -> list[ExperimentResult]:
    return list(db.execute(select(ExperimentResult).where(ExperimentResult.experiment_id == exp.id)
                           .order_by(ExperimentResult.version)).scalars())


def calculate(db: Session, user: User, exp: Experiment, reason: str | None = None) -> ExperimentResult:
    """Расчёт. Повтор с теми же цифрами возвращает уже сохранённую версию. Если цифры
    изменились (например, исправили данные), нужна причина: появится новая версия,
    а первая остаётся основной и в сертификате.
    """
    if exp.status is not ExperimentStatus.closed:
        raise ApiError(409, "Результат считается после закрытия эксперимента", "not_closed")
    p = Protocol.model_validate(exp.protocol)
    start, end = window_of(db, exp)
    rows = db.execute(
        select(Assignment.customer_external_id, Assignment.group, Assignment.stratum)
        .where(Assignment.experiment_id == exp.id)
    ).all()
    assignment = {cid: g for cid, g, _ in rows}
    strata = {cid: s for cid, _, s in rows}
    outcomes = load_outcomes(db, exp.business_id, list(assignment), start, end)
    base = baseline_rate(db, exp.business_id, p, exclude=exp.id)
    r = stats.estimate_effect(
        assignment, outcomes, seed=exp.seed, cost_kopecks=cost_kopecks(p), baseline_rate=clamp_baseline(base),
        strata=strata, margin=margin_of(p), alpha=p.alpha, min_group_size=p.min_group_size, max_mde=p.max_mde,
    )
    payload = r.to_dict()
    payload["baseline_rate"] = base
    payload["protocol_hash"] = exp.protocol_hash
    payload["window_start"] = start.isoformat()
    payload["window_end"] = end.isoformat()
    payload["data_complete_through"] = exp.data_complete_through.isoformat() if exp.data_complete_through else None
    payload["payment_import_ids"] = payment_import_ids(db, exp.business_id, list(assignment), start, end)
    payload = _json_safe(payload)
    result_hash = hashlib.sha256(canonical_json(payload).encode()).hexdigest()

    previous = results_of(db, exp)
    if previous and previous[-1].result_hash == result_hash:
        return previous[-1]
    if previous and not (reason and reason.strip()):
        raise ApiError(409, "Цифры отличаются от сохранённого результата: укажите причину пересчёта",
                       "reason_required")
    res = ExperimentResult(
        experiment_id=exp.id,
        payload=payload,
        result_hash=result_hash,
        version=len(previous) + 1,
        reason=reason.strip() if previous and reason else None,
        computed_by=user.id,
        computed_at=clock.now(),
    )
    db.add(res)
    db.flush()
    audit.append(db, action="result.calculated" if not previous else "result.recalculated",
                 entity_type="experiment", entity_id=str(exp.id),
                 payload={"result_hash": res.result_hash, "status": payload["status"], "version": res.version,
                          "reason": res.reason},
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
