"""Деление на группы через HMAC-SHA256(seed, customer_id).

Внутри каждой страты клиенты сортируются по HMAC, первые round(n × доля)
уходят в контроль. Результат зависит только от seed и состава страты:
его нельзя подогнать после регистрации, и любой может перепроверить.
"""

from __future__ import annotations

import hashlib
import hmac
from collections import defaultdict
from collections.abc import Iterable
from decimal import ROUND_HALF_EVEN, Decimal

CONTROL = "control"
TEST = "test"


def hmac_hex(seed: str, customer_id: str) -> str:
    return hmac.new(seed.encode(), customer_id.encode(), hashlib.sha256).hexdigest()


def hmac_unit(seed: str, customer_id: str) -> float:
    """Число в [0, 1) из старших 53 бит HMAC: столько точно помещается во float, 1.0 не выпадет."""
    return (int(hmac_hex(seed, customer_id)[:16], 16) >> 11) / 2**53


def assign_groups(
    items: Iterable[tuple[str, str]],
    seed: str,
    control_share: Decimal | float | str,
) -> dict[str, str]:
    """items: пары (customer_id, stratum). Возвращает customer_id → control|test."""
    share = Decimal(str(control_share))
    if not (Decimal(0) < share < Decimal(1)):
        raise ValueError("control_share должна быть строго между 0 и 1")
    by_stratum: dict[str, list[str]] = defaultdict(list)
    seen: set[str] = set()
    for cid, stratum in items:
        if cid in seen:
            raise ValueError(f"повтор customer_id: {cid}")
        seen.add(cid)
        by_stratum[stratum].append(cid)

    result: dict[str, str] = {}
    for stratum in sorted(by_stratum):
        ids = sorted(by_stratum[stratum], key=lambda cid: (hmac_hex(seed, cid), cid))
        n_control = int((share * len(ids)).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
        for i, cid in enumerate(ids):
            result[cid] = CONTROL if i < n_control else TEST
    return result
