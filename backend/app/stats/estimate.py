"""Расчёт эффекта по назначенным группам (intention-to-treat) и статусы.

Каждый клиент анализируется в той группе, куда его назначило деление, даже если
действие к нему фактически не применили. Доверительные интервалы — перцентильный
бутстрэп (по умолчанию 5000 повторов) с seed, выведенным из seed эксперимента.

Деньги храним в копейках (int). Итоговые суммы округляются до копеек через
Decimal(ROUND_HALF_EVEN).

Таблица статусов (спецификация, 2.9), проверяется сверху вниз:
  1. в любой группе < min_group_size или MDE > max_mde      → «недостаточно данных»
  2. нижняя граница ДИ прироста возврата > 0 и нижняя граница
     ДИ чистого эффекта в рублях > 0                          → «положительный эффект»
  3. нижняя граница ДИ прироста > 0, а деньги нет            → «эффект есть, окупаемость не доказана»
  4. верхняя граница ДИ прироста < 0                          → «отрицательный эффект»
  5. иначе                                                    → «эффект не обнаружен»
Чистый эффект = (средняя выручка теста − средняя выручка контроля) × n_test − C,
где C — стоимость действия (скидки, звонков, бонусов) в копейках.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum

import numpy as np

from app.stats.assignment import CONTROL, TEST
from app.stats.mde import mde_two_proportions

BOOTSTRAP_ITERATIONS = 5000
_CHUNK = 250
# предел элементов в одной матрице индексов: при n=200 тыс. 250 строк заняли бы ~400 МБ
_MAX_CELLS = 5_000_000


class Status(StrEnum):
    INSUFFICIENT = "insufficient"
    POSITIVE = "positive"
    NOT_PAYING_OFF = "not_paying_off"
    NEGATIVE = "negative"
    NOT_DETECTED = "not_detected"


STATUS_LABEL: dict[Status, str] = {
    Status.INSUFFICIENT: "недостаточно данных",
    Status.POSITIVE: "положительный эффект",
    Status.NOT_PAYING_OFF: "эффект есть, окупаемость не доказана",
    Status.NEGATIVE: "отрицательный эффект",
    Status.NOT_DETECTED: "эффект не обнаружен",
}


@dataclass(frozen=True, slots=True)
class Outcome:
    customer_id: str
    returned: bool
    revenue_kopecks: int = 0


@dataclass(frozen=True, slots=True)
class EffectResult:
    status: Status
    n_control: int
    n_test: int
    rate_control: float
    rate_test: float
    uplift: float
    uplift_ci: tuple[float, float] | None
    mde: float | None
    net_effect_kopecks: int
    net_effect_ci_kopecks: tuple[int, int] | None
    cost_kopecks: int
    iterations: int
    bootstrap_seed: int
    alpha: float = 0.05
    revenue_control_kopecks: int = 0
    revenue_test_kopecks: int = 0
    rate_control_ci: tuple[float, float] | None = None
    rate_test_ci: tuple[float, float] | None = None
    by_stratum: dict[str, dict[str, dict[str, float | int]]] | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["status_label"] = STATUS_LABEL[self.status]
        for k, v in list(d.items()):  # JSON не допускает NaN/inf
            if isinstance(v, float) and not math.isfinite(v):
                d[k] = None
        return d


def bootstrap_seed_from(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(b"bootstrap:" + seed.encode()).digest()[:8], "big")


def _kopecks(x: float) -> int:
    return int(Decimal(repr(float(x))).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def _bootstrap_means(
    rng: np.random.Generator, returned: np.ndarray, revenue: np.ndarray, iterations: int
) -> tuple[np.ndarray, np.ndarray]:
    n = returned.shape[0]
    chunk = max(1, min(_CHUNK, _MAX_CELLS // max(n, 1)))
    rates = np.empty(iterations)
    revs = np.empty(iterations)
    for start in range(0, iterations, chunk):
        size = min(chunk, iterations - start)
        idx = rng.integers(0, n, size=(size, n))
        rates[start : start + size] = returned[idx].mean(axis=1)
        revs[start : start + size] = revenue[idx].mean(axis=1)
    return rates, revs


def estimate_effect(
    assignment: dict[str, str],
    outcomes: list[Outcome],
    *,
    seed: str,
    cost_kopecks: int,
    baseline_rate: float | None = None,
    strata: dict[str, str] | None = None,
    iterations: int = BOOTSTRAP_ITERATIONS,
    alpha: float = 0.05,
    min_group_size: int = 100,
    max_mde: float = 0.10,
) -> EffectResult:
    """Считает эффект. Клиент без исхода считается невернувшимся с выручкой 0.

    Выручка клиента может быть отрицательной (возвраты в окне).
    strata — только для показа разбивки by_stratum, на расчёт не влияет.
    """
    by_id: dict[str, Outcome] = {}
    for o in outcomes:
        if o.customer_id in by_id:
            raise ValueError(f"повтор исхода для customer_id: {o.customer_id}")
        if o.customer_id not in assignment:
            raise ValueError(f"исход для клиента вне деления: {o.customer_id}")
        by_id[o.customer_id] = o
    groups: dict[str, list[Outcome]] = {CONTROL: [], TEST: []}
    for cid in sorted(assignment):
        groups[assignment[cid]].append(by_id.get(cid, Outcome(cid, False, 0)))

    def arrays(g: str) -> tuple[np.ndarray, np.ndarray]:
        rows = groups[g]
        return (
            np.array([1.0 if o.returned else 0.0 for o in rows]),
            np.array([float(o.revenue_kopecks) for o in rows]),
        )

    rc, vc = arrays(CONTROL)
    rt, vt = arrays(TEST)
    n_c, n_t = len(rc), len(rt)
    rate_c = float(rc.mean()) if n_c else 0.0
    rate_t = float(rt.mean()) if n_t else 0.0
    uplift = rate_t - rate_c

    rev_c_total, rev_t_total = int(vc.sum()), int(vt.sum())
    by_stratum = _by_stratum(assignment, by_id, strata) if strata else None

    p0 = baseline_rate if baseline_rate is not None else 0.05
    p0 = min(max(p0, 0.01), 0.99)
    mde = mde_two_proportions(p0, n_c, n_t, alpha=alpha)

    b_seed = bootstrap_seed_from(seed)
    if n_c < min_group_size or n_t < min_group_size or mde > max_mde:
        net = _kopecks(((vt.mean() if n_t else 0) - (vc.mean() if n_c else 0)) * n_t - cost_kopecks)
        return EffectResult(
            Status.INSUFFICIENT, n_c, n_t, rate_c, rate_t, uplift, None,
            mde if math.isfinite(mde) else None, net, None, cost_kopecks, 0, b_seed,
            alpha, rev_c_total, rev_t_total, None, None, by_stratum,
        )

    rng = np.random.Generator(np.random.PCG64(b_seed))
    rate_c_b, rev_c_b = _bootstrap_means(rng, rc, vc, iterations)
    rate_t_b, rev_t_b = _bootstrap_means(rng, rt, vt, iterations)
    uplift_b = rate_t_b - rate_c_b
    net_b = (rev_t_b - rev_c_b) * n_t - cost_kopecks

    lo_q, hi_q = 100 * alpha / 2, 100 * (1 - alpha / 2)
    u_lo, u_hi = (float(x) for x in np.percentile(uplift_b, [lo_q, hi_q]))
    rc_lo, rc_hi = (float(x) for x in np.percentile(rate_c_b, [lo_q, hi_q]))
    rt_lo, rt_hi = (float(x) for x in np.percentile(rate_t_b, [lo_q, hi_q]))
    n_lo, n_hi = (_kopecks(x) for x in np.percentile(net_b, [lo_q, hi_q]))
    net = _kopecks((vt.mean() - vc.mean()) * n_t - cost_kopecks)

    if u_lo > 0 and n_lo > 0:
        status = Status.POSITIVE
    elif u_lo > 0:
        status = Status.NOT_PAYING_OFF
    elif u_hi < 0:
        status = Status.NEGATIVE
    else:
        status = Status.NOT_DETECTED

    return EffectResult(
        status, n_c, n_t, rate_c, rate_t, uplift, (u_lo, u_hi), mde, net, (n_lo, n_hi),
        cost_kopecks, iterations, b_seed, alpha, rev_c_total, rev_t_total,
        (rc_lo, rc_hi), (rt_lo, rt_hi), by_stratum,
    )


def _by_stratum(
    assignment: dict[str, str], by_id: dict[str, Outcome], strata: dict[str, str]
) -> dict[str, dict[str, dict[str, float | int]]]:
    acc: dict[str, dict[str, list[int]]] = {}
    for cid in sorted(assignment):
        s = strata.get(cid, "?")
        g = assignment[cid]
        o = by_id.get(cid)
        cell = acc.setdefault(s, {CONTROL: [0, 0], TEST: [0, 0]})[g]
        cell[0] += 1
        cell[1] += 1 if o and o.returned else 0
    return {
        s: {g: {"n": n, "rate": round(r / n, 6) if n else 0.0} for g, (n, r) in groups.items()}
        for s, groups in sorted(acc.items())
    }
