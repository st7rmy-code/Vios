"""Единственный источник «сейчас» для сервисов. Модуль stats его не использует.

В тестах подменяется через monkeypatch app.clock.now.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def now() -> datetime:
    return datetime.now(UTC)


def today(tz: str = "Europe/Moscow") -> date:
    return now().astimezone(ZoneInfo(tz)).date()
