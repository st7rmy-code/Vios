"""Синтетический бизнес для тестов stats."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from app.stats import CohortRule, Customer, Outcome, assign_groups, assign_strata, select_cohort

AS_OF = date(2026, 10, 1)
RULE = CohortRule(as_of=AS_OF)
ABONEMENT_KOPECKS = 300_000  # 3 000 ₽


def make_churned_customers(n: int, rng_seed: int = 7) -> list[Customer]:
    rng = np.random.default_rng(rng_seed)
    out = []
    for i in range(n):
        gone_days = int(rng.integers(30, 181))
        tenure = int(rng.integers(40, 900))
        last = AS_OF - timedelta(days=gone_days)
        out.append(
            Customer(
                customer_id=f"c{i:05d}",
                first_paid_at=last - timedelta(days=tenure),
                last_visit_at=last,
                subscription_ends_at=last,
                total_paid_kopecks=int(rng.integers(3, 60)) * 100_000,
            )
        )
    return out


def run_business(n: int, p_control: float, p_test: float, sim_seed: int, exp_seed: str):
    customers = select_cohort(make_churned_customers(n, rng_seed=sim_seed), RULE)
    assignment = assign_groups(assign_strata(customers, RULE).items(), exp_seed, "0.5")
    rng = np.random.default_rng(10_000 + sim_seed)
    outcomes = []
    for cid in sorted(assignment):
        p = p_control if assignment[cid] == "control" else p_test
        back = bool(rng.random() < p)
        outcomes.append(Outcome(cid, back, ABONEMENT_KOPECKS if back else 0))
    return assignment, outcomes
