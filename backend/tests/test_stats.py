from datetime import date

import numpy as np
import pytest

from app.stats import (
    CohortRule,
    Customer,
    Outcome,
    Status,
    assign_groups,
    estimate_effect,
    hmac_unit,
    mde_two_proportions,
    select_cohort,
)
from tests.synthetic import run_business

C = 2_000_000  # 20 000 ₽ в копейках


def test_positive_effect_2000_churned():
    assignment, outcomes = run_business(2000, 0.05, 0.11, sim_seed=1, exp_seed="exp-positive")
    assert len(assignment) == 2000
    r = estimate_effect(assignment, outcomes, seed="exp-positive", cost_kopecks=C)
    assert r.iterations == 5000
    assert r.status is Status.POSITIVE, r
    assert r.uplift_ci[0] > 0
    assert r.net_effect_ci_kopecks[0] > 0
    d = r.to_dict()
    assert d["status"] == "positive" and d["status_label"] == "положительный эффект"
    assert d["revenue_test_kopecks"] > d["revenue_control_kopecks"]


def test_no_effect_in_at_least_90_of_100_simulations():
    not_detected = 0
    for sim in range(100):
        a, o = run_business(2000, 0.05, 0.05, sim_seed=100 + sim, exp_seed=f"null-{sim}")
        r = estimate_effect(a, o, seed=f"null-{sim}", cost_kopecks=C)
        not_detected += r.status is Status.NOT_DETECTED
    assert not_detected >= 90, not_detected


def test_150_customers_insufficient():
    a, o = run_business(150, 0.05, 0.11, sim_seed=3, exp_seed="small")
    r = estimate_effect(a, o, seed="small", cost_kopecks=C)
    assert r.status is Status.INSUFFICIENT
    d = r.to_dict()
    assert d["uplift_ci"] is None and d["net_effect_ci_kopecks"] is None
    import json

    json.dumps(d, allow_nan=False)  # в ответе нет NaN


def test_recalculation_is_identical():
    a, o = run_business(2000, 0.05, 0.11, sim_seed=1, exp_seed="repeat")
    r1 = estimate_effect(a, o, seed="repeat", cost_kopecks=C).to_dict()
    a2, o2 = run_business(2000, 0.05, 0.11, sim_seed=1, exp_seed="repeat")
    r2 = estimate_effect(a2, o2, seed="repeat", cost_kopecks=C).to_dict()
    assert a == a2
    assert r1 == r2


def test_hmac_split_is_deterministic_and_seed_dependent():
    items = [(f"c{i}", "s") for i in range(1000)]
    a1 = assign_groups(items, "seed-1", "0.3")
    assert a1 == assign_groups(list(reversed(items)), "seed-1", "0.3")
    assert sum(v == "control" for v in a1.values()) == 300
    assert a1 != assign_groups(items, "seed-2", "0.3")
    assert 0 <= hmac_unit("seed-1", "c1") < 1


def test_split_is_balanced_within_strata():
    items = [(f"c{i}", f"s{i % 3}") for i in range(999)]
    a = assign_groups(items, "x", "0.5")
    for s in ("s0", "s1", "s2"):
        ctrl = sum(1 for cid, st in items if st == s and a[cid] == "control")
        assert ctrl in (166, 167)


def test_mde_shrinks_with_n():
    assert mde_two_proportions(0.05, 1000, 1000) < mde_two_proportions(0.05, 100, 100)
    assert mde_two_proportions(0.05, 1000, 1000) == pytest.approx(0.0273, abs=0.001)


def test_cohort_rule():
    rule = CohortRule(as_of=date(2026, 10, 1))
    active = Customer("a", date(2025, 1, 1), date(2026, 9, 25), date(2026, 10, 20), 100)
    churned = Customer("b", date(2025, 1, 1), date(2026, 8, 1), date(2026, 8, 1), 100)
    ancient = Customer("c", date(2020, 1, 1), date(2021, 1, 1), date(2021, 1, 1), 100)
    never_paid = Customer("d", None, date(2026, 8, 1), None, 0)
    assert [c.customer_id for c in select_cohort([active, churned, ancient, never_paid], rule)] == ["b"]


def test_cohort_exclusions():
    from app.stats import cohort_with_exclusions

    rule = CohortRule(as_of=date(2026, 10, 1))
    base = dict(first_paid_at=date(2025, 1, 1), last_visit_at=date(2026, 8, 1),
                subscription_ends_at=date(2026, 8, 1), total_paid_kopecks=100)
    ok = Customer("ok", **base)
    frozen = Customer("fz", **base, frozen=True)
    package = Customer("pk", **base, active_obligation=True)
    busy = Customer("ox", **base, in_other_experiment=True)
    refunded = Customer("rf", **{**base, "total_paid_kopecks": 0})
    cohort, excluded = cohort_with_exclusions([ok, frozen, package, busy, refunded], rule)
    assert [c.customer_id for c in cohort] == ["ok"]
    assert excluded == {"active_obligation": 1, "frozen": 1, "no_payments": 1, "other_experiment": 1}


def test_strata_branch_and_small_merge():
    from app.stats import assign_strata

    rule = CohortRule(as_of=date(2026, 10, 1))
    cs = []
    for i in range(60):  # крупная страта в «Центре»
        cs.append(Customer(f"a{i}", date(2025, 1, 1), None, date(2026, 8, 1), 500_000, "Центр"))
    for i in range(5):  # крошечные страты в «Севере»
        cs.append(Customer(f"b{i}", date(2026, 7, 1), None, date(2026, 8, 1), 5_000_000, "Север"))
    for i in range(25):
        cs.append(Customer(f"c{i}", date(2025, 1, 1), None, date(2026, 8, 1), 500_000, "Север"))
    st = assign_strata(cs, rule)
    assert st["a0"] == "bЦентр-t2-p0"
    assert st["c0"] == "bСевер-t2-p0"
    assert st["b0"] == "small"  # «Север-small» из 5 < 20 → общая small

    single = assign_strata([Customer(f"x{i}", date(2025, 1, 1), None, None, 100, "Центр") for i in range(30)], rule)
    assert set(single.values()) == {"t2-p0"}  # один филиал — признак не используется


def test_recent_payment_counts_as_activity():
    rule = CohortRule(as_of=date(2026, 6, 1), inactive_days=30)
    gone = Customer("c1", date(2025, 1, 1), date(2026, 3, 1), None, total_paid_kopecks=100)
    paid_recently = Customer("c2", date(2025, 1, 1), date(2026, 3, 1), None, total_paid_kopecks=100,
                             last_paid_at=date(2026, 5, 20))
    assert [c.customer_id for c in select_cohort([gone, paid_recently], rule)] == ["c1"]


def test_outcomes_must_match_assignment():
    a = {"c1": "control", "c2": "test"}
    with pytest.raises(ValueError, match="повтор"):
        estimate_effect(a, [Outcome("c1", True, 1), Outcome("c1", False, 0)], seed="s", cost_kopecks=0)
    with pytest.raises(ValueError, match="вне деления"):
        estimate_effect(a, [Outcome("c3", True, 1)], seed="s", cost_kopecks=0)


def test_margin_scales_money_not_returns():
    a, o = run_business(2000, 0.05, 0.11, sim_seed=1, exp_seed="m")
    full = estimate_effect(a, o, seed="m", cost_kopecks=0)
    half = estimate_effect(a, o, seed="m", cost_kopecks=0, margin=0.5)
    assert half.uplift == full.uplift and half.uplift_ci == full.uplift_ci
    assert abs(half.net_effect_kopecks - full.net_effect_kopecks / 2) <= 1
    # выручка в отчёте остаётся выручкой
    assert half.revenue_test_kopecks == full.revenue_test_kopecks
    with pytest.raises(ValueError):
        estimate_effect(a, o, seed="m", cost_kopecks=0, margin=0)


def test_stratified_estimate_corrects_imbalance():
    # Две страты с разным базовым возвратом и разной долей контроля внутри страты.
    # Наивная разница средних даёт ложный «эффект», стратифицированная — около нуля.
    a, o, s = {}, [], {}
    rng = np.random.default_rng(3)
    for stratum, p, n_c, n_t in (("hi", 0.30, 300, 100), ("lo", 0.02, 100, 300)):
        for g, n in (("control", n_c), ("test", n_t)):
            for i in range(n):
                cid = f"{stratum}-{g}-{i}"
                a[cid], s[cid] = g, stratum
                back = bool(rng.random() < p)
                o.append(Outcome(cid, back, 300_000 if back else 0))
    naive = estimate_effect(a, o, seed="st", cost_kopecks=0)
    strat = estimate_effect(a, o, seed="st", cost_kopecks=0, strata=s)
    assert naive.uplift < -0.08  # ложный отрицательный эффект от перекоса
    assert abs(strat.uplift) < 0.05
    assert strat.status is not Status.NEGATIVE
    again = estimate_effect(a, o, seed="st", cost_kopecks=0, strata=s)
    assert again.to_dict() == strat.to_dict()
