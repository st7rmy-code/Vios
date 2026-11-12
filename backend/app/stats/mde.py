"""MDE: минимальный обнаружимый эффект для разницы двух долей."""

from __future__ import annotations

import math
from statistics import NormalDist


def mde_two_proportions(
    baseline: float,
    n_control: int,
    n_test: int,
    alpha: float = 0.05,
    power: float = 0.8,
) -> float:
    """Абсолютный MDE в долях (0.03 = 3 п.п.), двусторонний тест.

    MDE = (z_{1-α/2} + z_{power}) · sqrt(p(1-p)(1/n_c + 1/n_t)).
    """
    if n_control <= 0 or n_test <= 0:
        return math.inf
    if not 0 < baseline < 1:
        raise ValueError("baseline должна быть в (0, 1)")
    z = NormalDist().inv_cdf(1 - alpha / 2) + NormalDist().inv_cdf(power)
    return z * math.sqrt(baseline * (1 - baseline) * (1 / n_control + 1 / n_test))
