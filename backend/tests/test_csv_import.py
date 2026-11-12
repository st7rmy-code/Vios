from app.models import ImportKind
from app.services.csv_import import parse_amount_kopecks, parse_csv, sha256_bytes


def _payments(good: int, bad: list[str]) -> bytes:
    rows = ["payment_id;customer_id;paid_at;amount;operation;method"]
    rows += [f"g{i};c{i};2026-09-01;100;payment;card" for i in range(good)]
    return "\n".join(rows + bad).encode()


def test_valid_payments_report():
    data = (
        "payment_id;customer_id;paid_at;amount;operation\n"
        "p1;c1;2026-09-01;3 000,00;\n"
        "p2;c2;05.09.2026;1500.5;payment\n"
        "p5;c2;06.09.2026;500;refund\n"
    ).encode()
    r = parse_csv(data, ImportKind.payments)
    assert r.accepted
    assert r.sha256 == sha256_bytes(data)
    rep = r.report
    assert rep["rows_total"] == 3 and rep["rows_valid"] == 3 and rep["warnings"] == []
    assert rep["total_amount_kopecks"] == 300_000 + 150_050 - 50_000  # оплаты минус возвраты
    assert r.rows[0]["operation"] == "payment"
    assert rep["date_min"] == "2026-09-01" and rep["date_max"] == "2026-09-06"


def test_errors_and_thresholds():
    from datetime import date

    bad = ["p2;c2;05.09.2026;1;payment;card", "p2;c2;05.09.2026;1;payment;card", "p3;c3;2026-13-01;100;;",
           "p4;;2026-09-02;100;;", "p6;c6;2026-09-02;100;gift;", "p7;c7;2030-01-01;100;;"]
    # 6 плохих из 10 → < 80% → отклонён
    r = parse_csv(_payments(4, bad), ImportKind.payments, today=date(2026, 11, 12))
    assert not r.accepted and r.report["valid_share"] == 0.5
    codes = {e["code"] for e in r.report["errors"]}
    assert codes == {"duplicate", "invalid", "empty"}
    assert any(e["message"] == "дата в будущем" for e in r.report["errors"])
    # 1 плохая из 11 → 91% → принят с предупреждением
    r = parse_csv(_payments(10, bad[2:3]), ImportKind.payments)
    assert r.accepted and r.report["warnings"]


def test_visits_same_day_collapse_and_obligations():
    data = b"customer_id;visited_at;branch\nc1;2026-09-01;A\nc1;2026-09-01;A\nc1;2026-09-01;B\n"
    r = parse_csv(data, ImportKind.visits)
    assert r.accepted and len(r.rows) == 2 and r.report["visits_collapsed"] == 1
    ob = (
        "obligation_id;customer_id;kind;starts_at;ends_at;visits_total;visits_used;amount;status\n"
        "o1;c1;package;2026-01-01;2027-01-01;10;3;5000;active\n"
        "o2;c2;debt;2026-01-01;;;;1500;\n"
    ).encode()
    r = parse_csv(ob, ImportKind.obligations)
    assert r.accepted and r.rows[1]["status"] == "active" and r.report["debt_kopecks"] == 150_000


def test_cp1251_and_comma():
    data = "customer_id,branch\nc1,Центр\n".encode("cp1251")
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
    r = parse_csv(b"customer_id\nc1\n", ImportKind.visits)  # нет visited_at
    assert not r.accepted and r.report["missing_required_columns"] == ["visited_at"]


def test_amount_parsing_exact():
    assert parse_amount_kopecks("0,10") == 10
    assert parse_amount_kopecks("1 234,56 ₽") == 123_456
