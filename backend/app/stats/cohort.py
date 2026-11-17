"""Когорта «ушедший клиент» (спецификация, раздел 2.3).

Клиент входит в когорту на дату среза, если:
1. была хотя бы одна оплата до среза и оплаты минус возвраты > 0;
2. нет действующего обязательства на срез (абонемент/пакет/предоплата);
3. не в заморозке;
4. от последней активности (посещение, оплата или конец последнего обязательства)
   до среза прошло от inactive_days до max_inactive_days дней включительно;
5. не состоит в другом зарегистрированном эксперименте этого бизнеса.

Признаки 2, 3, 5 вычисляет сервис по данным на дату среза; здесь только правило.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class Customer:
    customer_id: str
    first_paid_at: date | None
    last_visit_at: date | None
    # конец последнего обязательства (реестр) или subscription_ends_at из customers
    subscription_ends_at: date | None
    total_paid_kopecks: int = 0  # оплаты минус возвраты до среза
    branch_id: str | None = None
    active_obligation: bool = False
    frozen: bool = False
    in_other_experiment: bool = False
    # последняя оплата до среза: недавно заплативший клиент не «ушедший», даже без визитов
    last_paid_at: date | None = None


@dataclass(frozen=True, slots=True)
class CohortRule:
    as_of: date
    inactive_days: int = 30
    max_inactive_days: int = 180
    min_total_paid_kopecks: int = 1


def _last_activity(c: Customer) -> date | None:
    dates = [d for d in (c.last_visit_at, c.subscription_ends_at, c.last_paid_at) if d is not None]
    return max(dates) if dates else None


def exclusion_reason(c: Customer, rule: CohortRule) -> str | None:
    """None — клиент в когорте, иначе код причины исключения."""
    if c.first_paid_at is None or c.total_paid_kopecks < rule.min_total_paid_kopecks:
        return "no_payments"
    if c.active_obligation or (c.subscription_ends_at is not None and c.subscription_ends_at >= rule.as_of):
        return "active_obligation"
    if c.frozen:
        return "frozen"
    last = _last_activity(c)
    if last is None:
        return "no_activity"
    days = (rule.as_of - last).days
    if days < rule.inactive_days:
        return "recently_active"
    if days > rule.max_inactive_days:
        return "gone_too_long"
    if c.in_other_experiment:
        return "other_experiment"
    return None


def in_cohort(c: Customer, rule: CohortRule) -> bool:
    return exclusion_reason(c, rule) is None


def select_cohort(customers: list[Customer], rule: CohortRule) -> list[Customer]:
    """Возвращает когорту в стабильном порядке (по customer_id)."""
    return sorted((c for c in customers if in_cohort(c, rule)), key=lambda c: c.customer_id)


def cohort_with_exclusions(customers: list[Customer], rule: CohortRule) -> tuple[list[Customer], dict[str, int]]:
    picked: list[Customer] = []
    excluded: Counter[str] = Counter()
    for c in customers:
        reason = exclusion_reason(c, rule)
        if reason is None:
            picked.append(c)
        else:
            excluded[reason] += 1
    return sorted(picked, key=lambda c: c.customer_id), dict(sorted(excluded.items()))
