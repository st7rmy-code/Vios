"""Импорт CSV: разбор, валидация, отчёт о качестве, блокировка ПДн.

ВРЕМЕННО: контракт ниже — допущение до получения раздела «Данные и импорт».

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
        "required": ["customer_id", "first_paid_at"],
        "optional": ["branch", "subscription_ends_at"],
    },
    ImportKind.payments: {
        "required": ["payment_id", "customer_id", "paid_at", "amount"],
        "optional": ["branch", "method"],
    },
    ImportKind.visits: {
        "required": ["customer_id", "visited_at"],
        "optional": ["branch"],
    },
}
DATE_COLUMNS = {"first_paid_at", "subscription_ends_at", "paid_at", "visited_at"}
MAX_ERRORS_IN_REPORT = 100

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


def parse_csv(data: bytes, kind: ImportKind) -> ParseResult:
    digest = sha256_bytes(data)
    res = ParseResult(kind=kind, sha256=digest, size_bytes=len(data), accepted=False)
    report: dict[str, Any] = {
        "kind": kind.value,
        "sha256": digest,
        "size_bytes": len(data),
        "blocking": [],
        "pii_columns": {},
        "rows_total": 0,
        "rows_valid": 0,
        "rows_invalid": 0,
        "duplicates": 0,
        "errors": [],
        "errors_truncated": False,
        "missing_required_columns": [],
        "unknown_columns": [],
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

    for i, r in enumerate(rows_raw, start=2):  # строка 1 — заголовок
        out: dict[str, Any] = {}
        ok = True
        for col in contract["required"] + contract["optional"]:
            v = (r.get(col) or "").strip()
            if not v:
                if col in contract["required"]:
                    err(i, col, "empty", "пустое обязательное поле")
                    ok = False
                out[col] = None
                continue
            try:
                if col in DATE_COLUMNS:
                    out[col] = parse_date(v)
                elif col == "amount":
                    out[col] = parse_amount_kopecks(v)
                    if out[col] <= 0:
                        raise ValueError("сумма должна быть больше нуля")
                else:
                    if len(v) > 100:
                        raise ValueError("значение длиннее 100 символов")
                    out[col] = v
            except ValueError as e:
                err(i, col, "invalid", str(e))
                ok = False
        if not ok:
            continue
        key = (
            (out["payment_id"],) if kind is ImportKind.payments
            else (out["customer_id"],) if kind is ImportKind.customers
            else (out["customer_id"], out["visited_at"])
        )
        if key in seen_keys:
            report["duplicates"] += 1
            err(i, None, "duplicate", "повтор строки по ключу " + "/".join(map(str, key)))
            continue
        seen_keys.add(key)
        valid.append(out)
        customers.add(out["customer_id"])
        for col in DATE_COLUMNS & out.keys():
            if out[col]:
                dates.append(out[col])
        if kind is ImportKind.payments:
            total_amount += out["amount"]

    report["rows_total"] = len(rows_raw)
    report["rows_valid"] = len(valid)
    report["rows_invalid"] = len(rows_raw) - len(valid)
    report["errors"] = errors[:MAX_ERRORS_IN_REPORT]
    report["errors_truncated"] = len(errors) > MAX_ERRORS_IN_REPORT
    report["customers"] = len(customers)
    report["date_min"] = min(dates).isoformat() if dates else None
    report["date_max"] = max(dates).isoformat() if dates else None
    if kind is ImportKind.payments:
        report["total_amount_kopecks"] = total_amount
    report["valid_share"] = round(len(valid) / len(rows_raw), 4) if rows_raw else 0.0
    if not valid:
        report["blocking"].append("нет ни одной корректной строки")
        return res

    res.accepted = True
    res.rows = valid
    return res
