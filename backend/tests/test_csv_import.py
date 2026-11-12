from app.models import ImportKind
from app.services.csv_import import parse_amount_kopecks, parse_csv, sha256_bytes


def test_valid_payments_report():
    data = (
        "payment_id;customer_id;paid_at;amount\n"
        "p1;c1;2026-09-01;3 000,00\n"
        "p2;c2;05.09.2026;1500.5\n"
        "p2;c2;05.09.2026;1500.5\n"
        "p3;c3;2026-13-01;100\n"
        "p4;;2026-09-02;100\n"
    ).encode()
    r = parse_csv(data, ImportKind.payments)
    assert r.accepted
    assert r.sha256 == sha256_bytes(data)
    rep = r.report
    assert rep["rows_total"] == 5 and rep["rows_valid"] == 2 and rep["duplicates"] == 1
    assert rep["total_amount_kopecks"] == 300_000 + 150_050
    assert {e["code"] for e in rep["errors"]} == {"duplicate", "invalid", "empty"}
    assert rep["date_min"] == "2026-09-01" and rep["date_max"] == "2026-09-05"


def test_cp1251_and_comma():
    data = "customer_id,first_paid_at,branch\nc1,2025-01-01,Центр\n".encode("cp1251")
    r = parse_csv(data, ImportKind.customers)
    assert r.accepted and r.report["encoding"] == "cp1251" and r.rows[0]["branch"] == "Центр"


def test_blocks_pii_by_header():
    data = "customer_id;ФИО;Телефон;first_paid_at\nc1;x;y;2025-01-01\n".encode()
    r = parse_csv(data, ImportKind.customers)
    assert not r.accepted and r.rows == []
    assert set(r.report["pii_columns"]) == {"фио", "телефон"}


def test_blocks_pii_by_content_and_never_echoes_values():
    data = (
        "customer_id;first_paid_at;comment\n"
        "c1;2025-01-01;ivan@example.ru\n"
        "+7 (912) 345-67-89;2025-01-01;\n"
        "c3;2025-01-01;Иванов Иван Петрович\n"
    ).encode()
    r = parse_csv(data, ImportKind.customers)
    assert not r.accepted
    assert set(r.report["pii_columns"]) == {"comment", "customer_id"}
    dumped = str(r.report)
    for secret in ("ivan@example.ru", "345-67-89", "Иванов"):
        assert secret not in dumped


def test_missing_columns_blocking():
    r = parse_csv(b"customer_id\nc1\n", ImportKind.visits)
    assert not r.accepted and r.report["missing_required_columns"] == ["visited_at"]


def test_amount_parsing_exact():
    assert parse_amount_kopecks("0,10") == 10
    assert parse_amount_kopecks("1 234,56 ₽") == 123_456
