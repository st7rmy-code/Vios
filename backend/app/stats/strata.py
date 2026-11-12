"""Страты (спецификация, раздел 2.4): филиал × стаж × сумма оплат.

Филиал используется, только если в когорте больше одного непустого филиала.
Страта меньше SMALL_STRATUM клиентов сливается с другими малыми того же филиала
в «<филиал>-small»; если и там меньше порога — в общую «small».
"""

from __future__ import annotations

from collections import defaultdict

from app.stats.cohort import CohortRule, Customer

TENURE_EDGES_DAYS = (90, 365)  # <90, 90–364, ≥365
PAID_EDGES_KOPECKS = (1_000_000, 3_000_000)  # <10 тыс. ₽, 10–29 999,99 ₽, ≥30 тыс. ₽
SMALL_STRATUM = 20


def _bucket(value: int, edges: tuple[int, ...]) -> int:
    for i, edge in enumerate(edges):
        if value < edge:
            return i
    return len(edges)


def stratum_of(c: Customer, rule: CohortRule, use_branch: bool = False) -> str:
    tenure = (rule.as_of - c.first_paid_at).days if c.first_paid_at else 0
    base = f"t{_bucket(tenure, TENURE_EDGES_DAYS)}-p{_bucket(c.total_paid_kopecks, PAID_EDGES_KOPECKS)}"
    return f"b{c.branch_id or ''}-{base}" if use_branch else base


def assign_strata(cohort: list[Customer], rule: CohortRule) -> dict[str, str]:
    """customer_id → итоговая страта с учётом слияния малых."""
    branches = {c.branch_id for c in cohort if c.branch_id}
    use_branch = len(branches) > 1
    raw = {c.customer_id: stratum_of(c, rule, use_branch) for c in cohort}
    branch_of = {c.customer_id: (c.branch_id or "") for c in cohort}

    sizes: dict[str, int] = defaultdict(int)
    for s in raw.values():
        sizes[s] += 1

    merged = {}
    for cid, s in raw.items():
        if sizes[s] >= SMALL_STRATUM:
            merged[cid] = s
        else:
            merged[cid] = f"b{branch_of[cid]}-small" if use_branch else "small"

    if use_branch:
        small_sizes: dict[str, int] = defaultdict(int)
        for s in merged.values():
            if s.endswith("-small"):
                small_sizes[s] += 1
        for cid, s in merged.items():
            if s.endswith("-small") and small_sizes[s] < SMALL_STRATUM:
                merged[cid] = "small"
    return merged
