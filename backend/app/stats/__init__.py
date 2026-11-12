"""Модуль stats: только чистые детерминированные функции.

Никакого ввода-вывода, БД, времени «сейчас» и глобального RNG: все входы явные,
случайность только из переданного seed. Повторный вызов с теми же аргументами
даёт те же числа.
"""

from app.stats.assignment import assign_groups, hmac_unit
from app.stats.cohort import CohortRule, Customer, select_cohort
from app.stats.estimate import EffectResult, Outcome, Status, estimate_effect
from app.stats.mde import mde_two_proportions
from app.stats.strata import stratum_of

__all__ = [
    "CohortRule",
    "Customer",
    "EffectResult",
    "Outcome",
    "Status",
    "assign_groups",
    "estimate_effect",
    "hmac_unit",
    "mde_two_proportions",
    "select_cohort",
    "stratum_of",
]
