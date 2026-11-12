"""Импорт CSV: разбор, валидация, отчёт о качестве, блокировка ПДн (спецификация, раздел 3).

Чистая часть (parse_csv) не трогает БД и хранилище: на вход байты, на выход
строки и отчёт. Файл с ФИО, телефонами или email отклоняется целиком, в отчёт
попадают только имена колонок и причина, сами значения — никогда.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

from app.models import ImportKind

CONTRACT: dict[ImportKind, dict[str, list[str]]] = {
    ImportKind.customers: {
        "required": ["customer_id"],
        "optional": ["branch", "first_paid_at", "subscription_ends_at", "frozen_until"],
    },
    ImportKind.payments: {
        "required": ["payment_id", "customer_id", "paid_at", "amount"],
        "optional": ["operation", "method", "branch"],
    },
    ImportKind.visits: {
        "required": ["customer_id", "visited_at"],
        "optional": ["branch"],
    },
    ImportKind.obligations: {
        "required": ["obligation_id", "customer_id", "kind", "starts_at"],
        "optional": ["ends_at", "visits_total", "visits_used", "amount", "status", "frozen_from", "frozen_until",
                     "branch"],
    },
}
DATE_COLUMNS = {"first_paid_at", "subscription_ends_at", "frozen_until", "paid_at", "visited_at", "starts_at",
                "ends_at", "frozen_from"}
# Даты, которые по смыслу могут быть в будущем (срок абонемента, заморозки)
FUTURE_OK = {"subscription_ends_at", "frozen_until", "ends_at", "frozen_from", "starts_at"}
INT_COLUMNS = {"visits_total", "visits_used"}
ENUMS: dict[str, tuple[str, ...]] = {
    "operation": ("payment", "refund"),
    "method": ("cash", "card", "transfer", "online", "other"),
    "kind": ("subscription", "package", "prepayment", "debt"),
    "status": ("active", "frozen", "closed", "cancelled"),
}
DEFAULTS = {"operation": "payment", "status": "active"}
KEY: dict[ImportKind, tuple[str, ...]] = {
    ImportKind.customers: ("customer_id",),
    ImportKind.payments: ("payment_id",),
    ImportKind.visits: ("customer_id", "visited_at", "branch"),
    ImportKind.obligations: ("obligation_id",),
}
MAX_ERRORS_IN_REPORT = 100
MAX_ROWS = 500_000
REJECT_BELOW = 0.80
WARN_BELOW = 0.95

_PII_HEADER = re.compile(
    r"(фио|фамил|имя|отчеств|клиент_?имя|name|phone|телефон|^тел|mobile|моб|e-?mail|почт|mail|паспорт|snils|снилс|адрес|address|birth|рожд)",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[A-Za-zА-Яа-я]{2,}")
_PHONE = re.compile(r"^\s*(\+7|8|7)?[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}\s*$")
_FULL_NAME = re.compile(r"^[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?(?:\s+[А-ЯЁ][а-яё]+){1,2}$")


@dataclass
class ParseResult:
    kind: ImportKind
    sha256: str
    size_bytes: int
    accepted: bool
    rows: list[dict[str, Any]] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode(data: bytes) -> tuple[str, str]:
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise ValueError("не удалось определить кодировку (ожидается UTF-8 или Windows-1251)")


def _norm_header(h: str) -> str:
    return h.strip().lower().replace(" ", "_")


def parse_date(v: str) -> date:
    v = v.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return date.fromisoformat(v)
    m = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", v)
    if m:
        return date(int(m[3]), int(m[2]), int(m[1]))
    raise ValueError("дата должна быть ГГГГ-ММ-ДД или ДД.ММ.ГГГГ")


def parse_amount_kopecks(v: str) -> int:
    """'1 500,50' / '1500.5' / '1500' → копейки. Без float."""
    s = v.strip().replace(" ", "").replace(" ", "").replace("₽", "").replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation as e:
        raise ValueError("сумма не число") from e
    if d != d.quantize(Decimal("0.01")):
        raise ValueError("больше двух знаков после запятой")
    return int((d * 100).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def detect_pii_columns(headers: list[str], sample_rows: list[dict[str, str]]) -> dict[str, str]:
    """Колонка → причина. Проверяем и заголовки, и содержимое (до 500 строк)."""
    found: dict[str, str] = {}
    for h in headers:
        if _PII_HEADER.search(h):
            found[h] = "название колонки похоже на персональные данные"
    for h in headers:
        if h in found:
            continue
        for row in sample_rows:
            val = (row.get(h) or "").strip()
            if not val:
                continue
            if _EMAIL.search(val):
                found[h] = "в значениях есть email"
            elif _PHONE.match(val) and len(re.sub(r"\D", "", val)) in (10, 11):
                found[h] = "в значениях есть номера телефонов"
            elif _FULL_NAME.match(val):
                found[h] = "в значениях есть ФИО"
            if h in found:
                break
    return found


def parse_csv(data: bytes, kind: ImportKind, today: date | None = None) -> ParseResult:
    """today — дата «сегодня» бизнеса для проверки дат в будущем (None — не проверять)."""
    digest = sha256_bytes(data)
    res = ParseResult(kind=kind, sha256=digest, size_bytes=len(data), accepted=False)
    report: dict[str, Any] = {
        "kind": kind.value,
        "sha256": digest,
        "size_bytes": len(data),
        "blocking": [],
        "warnings": [],
        "pii_columns": {},
        "rows_total": 0,
        "rows_valid": 0,
        "rows_invalid": 0,
        "duplicates": 0,
        "errors": [],
        "errors_truncated": False,
        "missing_required_columns": [],
        "unknown_columns": [],
        "orphan_customers": 0,
    }
    res.report = report

    try:
        text, encoding = _decode(data)
    except ValueError as e:
        report["blocking"].append(str(e))
        return res
    report["encoding"] = encoding
    if not text.strip():
        report["blocking"].append("файл пустой")
        return res

    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";"
    report["delimiter"] = delimiter
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    raw_headers = reader.fieldnames or []
    headers = [_norm_header(h) for h in raw_headers]
    rows_raw = [{_norm_header(k): (v or "") for k, v in r.items() if k is not None} for r in reader]
    if len(rows_raw) > MAX_ROWS:
        report["rows_total"] = len(rows_raw)
        report["blocking"].append(f"больше {MAX_ROWS:,} строк в одном файле, разбейте его на части".replace(",", " "))
        return res

    pii = detect_pii_columns(headers, rows_raw[:500])
    if pii:
        report["pii_columns"] = pii
        report["blocking"].append(
            "Файл содержит персональные данные клиентов. Удалите колонки "
            + ", ".join(f"«{c}»" for c in pii)
            + " и загрузите снова. Нужен только идентификатор клиента."
        )
        report["rows_total"] = len(rows_raw)
        return res  # строки не возвращаем и не сохраняем

    contract = CONTRACT[kind]
    missing = [c for c in contract["required"] if c not in headers]
    report["missing_required_columns"] = missing
    report["unknown_columns"] = [h for h in headers if h not in contract["required"] + contract["optional"]]
    if missing:
        report["blocking"].append("нет обязательных колонок: " + ", ".join(missing))
        return res

    errors: list[dict[str, Any]] = []
    seen_keys: set[tuple] = set()
    valid: list[dict[str, Any]] = []
    dates: list[date] = []
    total_amount = 0
    customers: set[str] = set()

    def err(line: int, column: str | None, code: str, message: str) -> None:
        errors.append({"line": line, "column": column, "code": code, "message": message})

    collapsed = 0
    debt_total = 0
    for i, r in enumerate(rows_raw, start=2):  # строка 1 — заголовок
        out: dict[str, Any] = {}
        ok = True
        for col in contract["required"] + contract["optional"]:
            v = (r.get(col) or "").strip()
            if not v:
                if col in contract["required"]:
                    err(i, col, "empty", "пустое обязательное поле")
                    ok = False
                out[col] = DEFAULTS.get(col) if col in ENUMS else None
                continue
            try:
                if col in DATE_COLUMNS:
                    out[col] = parse_date(v)
                    if today is not None and col not in FUTURE_OK and out[col] > today:
                        raise ValueError("дата в будущем")
                elif col == "amount":
                    out[col] = parse_amount_kopecks(v)
                    if out[col] <= 0:
                        raise ValueError("сумма должна быть больше нуля")
                elif col in INT_COLUMNS:
                    if not v.isdigit():
                        raise ValueError("ожидается целое число ≥ 0")
                    out[col] = int(v)
                elif col in ENUMS:
                    lv = v.lower()
                    if lv not in ENUMS[col]:
                        raise ValueError("допустимо: " + ", ".join(ENUMS[col]))
                    out[col] = lv
                else:
                    if len(v) > 100:
                        raise ValueError("значение длиннее 100 символов")
                    out[col] = v
            except ValueError as e:
                err(i, col, "invalid", str(e))
                ok = False
        if ok and kind is ImportKind.obligations:
            if out.get("ends_at") and out["ends_at"] < out["starts_at"]:
                err(i, "ends_at", "invalid", "конец раньше начала")
                ok = False
            elif out.get("frozen_from") and out.get("frozen_until") and out["frozen_until"] < out["frozen_from"]:
                err(i, "frozen_until", "invalid", "конец заморозки раньше начала")
                ok = False
        if not ok:
            continue
        key = tuple(out.get(k) for k in KEY[kind])
        if key in seen_keys:
            if kind is ImportKind.visits:  # несколько посещений в день схлопываются в одно
                collapsed += 1
                continue
            report["duplicates"] += 1
            err(i, None, "duplicate", "повтор строки по ключу " + "/".join(str(k) for k in key if k is not None))
            continue
        seen_keys.add(key)
        valid.append(out)
        customers.add(out["customer_id"])
        for col in DATE_COLUMNS & out.keys():
            if out[col] and col not in FUTURE_OK:
                dates.append(out[col])
        if kind is ImportKind.obligations and out["kind"] == "debt" and out.get("amount"):
            debt_total += out["amount"]
        if kind is ImportKind.payments:
            total_amount += out["amount"] if out["operation"] == "payment" else -out["amount"]

    report["rows_total"] = len(rows_raw)
    n_ok = len(valid) + collapsed
    report["rows_valid"] = n_ok
    report["rows_invalid"] = len(rows_raw) - n_ok
    if kind is ImportKind.visits:
        report["visits_collapsed"] = collapsed
    if kind is ImportKind.obligations:
        report["debt_kopecks"] = debt_total
    report["errors"] = errors[:MAX_ERRORS_IN_REPORT]
    report["errors_truncated"] = len(errors) > MAX_ERRORS_IN_REPORT
    report["customers"] = len(customers)
    report["date_min"] = min(dates).isoformat() if dates else None
    report["date_max"] = max(dates).isoformat() if dates else None
    if kind is ImportKind.payments:
        report["total_amount_kopecks"] = total_amount
    share = n_ok / len(rows_raw) if rows_raw else 0.0
    report["valid_share"] = round(share, 4)
    if not valid:
        report["blocking"].append("нет ни одной корректной строки")
        return res
    if share < REJECT_BELOW:
        report["blocking"].append(
            f"корректных строк {share:.0%}, нужно не меньше {REJECT_BELOW:.0%}: исправьте ошибки и загрузите снова"
        )
        return res
    if share < WARN_BELOW:
        report["warnings"].append(f"корректных строк {share:.0%}: строки с ошибками пропущены")

    res.accepted = True
    res.rows = valid
    return res
