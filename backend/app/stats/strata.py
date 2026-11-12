"""Страты.

ДОПУЩЕНИЕ: страта = стаж клиента × сколько он заплатил за всё время.
Делим внутри страты, чтобы группы были сбалансированы по этим признакам.
"""

from __future__ import annotations

from app.stats.cohort import CohortRule, Customer

TENURE_EDGES_DAYS = (90, 365)  # <3 мес, 3–12 мес, >12 мес
PAID_EDGES_KOPECKS = (1_000_000, 3_000_000)  # <10 тыс. ₽, 10–30 тыс. ₽, >30 тыс. ₽


def _bucket(value: int, edges: tuple[int, ...]) -> int:
    for i, edge in enumerate(edges):
        if value < edge:
            return i
    return len(edges)


def stratum_of(c: Customer, rule: CohortRule) -> str:
    tenure = (rule.as_of - c.first_paid_at).days if c.first_paid_at else 0
    t = _bucket(tenure, TENURE_EDGES_DAYS)
    p = _bucket(c.total_paid_kopecks, PAID_EDGES_KOPECKS)
    return f"t{t}-p{p}"
