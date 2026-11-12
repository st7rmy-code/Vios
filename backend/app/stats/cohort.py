"""Когорта по правилу.

ДОПУЩЕНИЕ (сверить с «Методикой замера»): «ушедший клиент» — у кого на дату
среза нет действующего абонемента и не было посещений `inactive_days` дней,
при этом он хотя бы раз платил и ушёл не раньше, чем `max_inactive_days` назад
(совсем давно ушедших не возвращаем).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class Customer:
    customer_id: str
    first_paid_at: date | None
    last_visit_at: date | None
    subscription_ends_at: date | None
    total_paid_kopecks: int = 0
    branch_id: str | None = None


@dataclass(frozen=True, slots=True)
class CohortRule:
    as_of: date
    inactive_days: int = 30
    max_inactive_days: int = 180
    min_total_paid_kopecks: int = 1


def _last_activity(c: Customer) -> date | None:
    dates = [d for d in (c.last_visit_at, c.subscription_ends_at) if d is not None]
    return max(dates) if dates else None


def in_cohort(c: Customer, rule: CohortRule) -> bool:
    if c.first_paid_at is None or c.total_paid_kopecks < rule.min_total_paid_kopecks:
        return False
    if c.subscription_ends_at is not None and c.subscription_ends_at >= rule.as_of:
        return False
    last = _last_activity(c)
    if last is None:
        return False
    days = (rule.as_of - last).days
    return rule.inactive_days <= days <= rule.max_inactive_days


def select_cohort(customers: list[Customer], rule: CohortRule) -> list[Customer]:
    """Возвращает когорту в стабильном порядке (по customer_id)."""
    picked = [c for c in customers if in_cohort(c, rule)]
    return sorted(picked, key=lambda c: c.customer_id)
