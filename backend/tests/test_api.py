"""Сквозные тесты API: импорт → эксперимент → регистрация → закрытие → расчёт."""

import hashlib
from datetime import UTC, date, datetime, timedelta

import numpy as np

from app.storage import get_storage

AS_OF = date(2026, 10, 1)
REGISTER_AT = datetime(2026, 10, 3, 9, 0, tzinfo=UTC)
PROTOCOL = {
    "hypothesis": "Звонок тренера возвращает ушедших клиентов",
    "action": "Тренер звонит и предлагает бесплатное занятие",
    "as_of": AS_OF.isoformat(),
    "control_share": "0.5",
    "window_days": 30,
    "cost_rub": "20000.00",
}


def _csvs(n=400, seed=5):
    rng = np.random.default_rng(seed)
    cust = ["customer_id;first_paid_at;subscription_ends_at;branch"]
    pay = ["payment_id;customer_id;paid_at;amount;operation"]
    vis = ["customer_id;visited_at"]
    for i in range(n):
        cid = f"c{i:04d}"
        last = AS_OF - timedelta(days=int(rng.integers(35, 170)))
        first = last - timedelta(days=int(rng.integers(60, 600)))
        cust.append(f"{cid};{first};{last};Центр")
        pay.append(f"p{i}-0;{cid};{first};3 000,00;payment")
        vis.append(f"{cid};{last}")
        if rng.random() < 0.08:  # часть вернулась после среза
            pay.append(f"p{i}-1;{cid};{AS_OF + timedelta(days=int(rng.integers(1, 30)))};3000;payment")
    # платежи выгружены за всё окно замера
    pay.append(f"tail;active;{AS_OF + timedelta(days=32)};1500;payment")
    return ["\n".join(x).encode() for x in (cust, pay, vis)]


def _upload(client, h, kind, data, name="f.csv"):
    return client.post("/api/v1/imports", headers=h, data={"kind": kind},
                       files={"file": (name, data, "text/csv")})


def _setup_experiment(client, h, title="Звонки ушедшим", protocol=PROTOCOL):
    for kind, data in zip(("customers", "payments", "visits"), _csvs(), strict=True):
        r = _upload(client, h, kind, data)
        assert r.status_code in (200, 201) and r.json()["status"] == "accepted", r.text
    r = client.post("/api/v1/experiments", headers=h, json={"title": title, "protocol": protocol})
    assert r.status_code == 201, r.text
    assert r.json()["seed"] is None  # зерно появляется только при регистрации
    return r.json()["id"]


def _register(client, h, eid, clock_at):
    clock_at(REGISTER_AT)
    r = client.post(f"/api/v1/experiments/{eid}/register", headers=h)
    clock_at(datetime(2026, 11, 5, 9, 0, tzinfo=UTC))
    return r


# --- импорт ------------------------------------------------------------------------------

def test_import_needs_owner_consent(client, world):
    h = world["h"]["owner"]
    cid = client.get("/api/v1/consents", headers=h).json()[0]["id"]
    assert client.post("/api/v1/consents", headers=world["h"]["executor"],
                       json={"text_version": "x"}).status_code == 403
    client.post(f"/api/v1/consents/{cid}/revoke", headers=h)
    r = _upload(client, h, "visits", b"customer_id;visited_at\nc1;2026-01-01\n")
    assert r.status_code == 409 and r.json() == {"detail": "Нужно согласие собственника", "code": "consent_required"}


def test_import_quality_report_sha_and_duplicate(client, world):
    h = world["h"]["owner"]
    data = (b"payment_id;customer_id;paid_at;amount\np1;c1;2026-09-01;100\np1;c1;2026-09-01;100\n"
            + b"".join(f"p{i};c{i % 2 + 1};2026-09-0{i};50\n".encode() for i in range(2, 7)))
    r = _upload(client, h, "payments", data)
    assert r.status_code == 201
    body = r.json()
    assert body["sha256"] == hashlib.sha256(data).hexdigest()
    assert body["quality_report"]["duplicates"] == 1
    assert body["quality_report"]["orphan_customers"] == 2  # клиенты созданы из платежей
    assert get_storage().get(f"{world['business'].id}/{body['id']}/{body['sha256']}.csv") == data
    again = _upload(client, h, "payments", data)
    assert again.status_code == 200 and again.json()["duplicate_of"] == body["id"]


def test_refunds_reduce_paid_total(client, world):
    h = world["h"]["owner"]
    data = "payment_id;customer_id;paid_at;amount;operation\np1;c1;2026-09-01;3000;payment\n" \
           "r1;c1;2026-09-05;1000;refund\n".encode()
    r = _upload(client, h, "payments", data)
    assert r.json()["quality_report"]["total_amount_kopecks"] == 200_000
    summary = client.get("/api/v1/data/summary", headers=h).json()
    assert summary["customers"]["rows"] == 1


def test_import_with_pii_is_rejected_and_not_stored(client, world):
    h = world["h"]["owner"]
    data = "customer_id;first_paid_at;Телефон\nc1;2025-01-01;+79123456789\n".encode()
    r = _upload(client, h, "customers", data)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "rejected" and "телефон" in body["quality_report"]["pii_columns"]
    assert "+79123456789" not in r.text
    assert not any(body["id"] in k for k in get_storage().objects)


def test_executor_cannot_upload(client, world):
    r = _upload(client, world["h"]["executor"], "visits", b"customer_id;visited_at\nc1;2026-01-01\n")
    assert r.status_code == 403 and r.json()["code"] == "forbidden"


# --- эксперимент -----------------------------------------------------------------------------

def test_protocol_edit_after_registration_conflict(client, world, clock_at):
    h = world["h"]["owner"]
    eid = _setup_experiment(client, h)
    assert client.patch(f"/api/v1/experiments/{eid}", headers=h, json={"title": "Новое имя"}).status_code == 200
    r = _register(client, h, eid, clock_at)
    assert r.status_code == 200, r.text
    assert r.json()["protocol_hash"] and len(r.json()["seed"]) == 32
    changed = {**PROTOCOL, "control_share": "0.3"}
    r = client.patch(f"/api/v1/experiments/{eid}", headers=h, json={"protocol": changed})
    assert r.status_code == 409 and r.json()["code"] == "protocol_locked"
    assert client.post(f"/api/v1/experiments/{eid}/register", headers=h).status_code == 409
    assert client.delete(f"/api/v1/experiments/{eid}", headers=h).status_code == 409


def test_register_needs_fresh_as_of(client, world):
    h = world["h"]["owner"]
    eid = _setup_experiment(client, h)
    r = client.post(f"/api/v1/experiments/{eid}/register", headers=h)  # сегодня 05.11, срез 01.10
    assert r.status_code == 422 and r.json()["code"] == "as_of_out_of_range"


def test_draft_can_be_deleted(client, world):
    h = world["h"]["owner"]
    eid = _setup_experiment(client, h)
    assert client.delete(f"/api/v1/experiments/{eid}", headers=h).status_code == 204
    assert client.get(f"/api/v1/experiments/{eid}", headers=h).status_code == 404


def test_executor_sees_test_group_only_until_close(client, world, clock_at):
    owner, ex = world["h"]["owner"], world["h"]["executor"]
    eid = _setup_experiment(client, owner)
    assert client.get(f"/api/v1/experiments/{eid}", headers=ex).status_code == 404  # черновик скрыт
    _register(client, owner, eid, clock_at)

    r = client.get(f"/api/v1/experiments/{eid}/assignments", headers=ex)
    assert r.status_code == 200 and r.json() and {a["group"] for a in r.json()} == {"test"}
    assert client.get(f"/api/v1/experiments/{eid}/assignments?group=control", headers=ex).status_code == 403
    assert client.get(f"/api/v1/experiments/{eid}/assignments.csv?group=control", headers=ex).status_code == 403
    card = client.get(f"/api/v1/experiments/{eid}", headers=ex).json()
    assert card["n_control"] is None and card["control_share"] is None and card["seed"] is None
    assert all(e["seed"] is None for e in client.get("/api/v1/experiments", headers=ex).json())
    assert "control_share" not in card["protocol"] and "cost_rub" not in card["protocol"]
    assert client.get(f"/api/v1/experiments/{eid}/result", headers=ex).status_code == 403
    assert client.post(f"/api/v1/experiments/{eid}/close", headers=ex).status_code == 403

    csv_r = client.get(f"/api/v1/experiments/{eid}/assignments.csv", headers=ex)
    assert csv_r.status_code == 200 and csv_r.text.lstrip("﻿").startswith("customer_id;group")
    log = client.get(f"/api/v1/audit?action=assignments.exported", headers=owner).json()
    assert log and log[0]["actor_login"] == "coach"

    assert client.post(f"/api/v1/experiments/{eid}/close", headers=owner).status_code == 200
    r = client.get(f"/api/v1/experiments/{eid}/assignments?group=control", headers=ex)
    assert r.status_code == 200 and r.json()
    assert client.get(f"/api/v1/experiments/{eid}", headers=ex).json()["protocol"]["cost_rub"] == "20000.00"


def test_close_reasons(client, world, clock_at):
    h = world["h"]["owner"]
    eid = _setup_experiment(client, h)
    assert client.post(f"/api/v1/experiments/{eid}/close", headers=h).json()["code"] == "not_registered"
    _register(client, h, eid, clock_at)
    clock_at(datetime(2026, 10, 20, tzinfo=UTC))
    r = client.post(f"/api/v1/experiments/{eid}/close", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "window_not_over" and "31.10.2026" in r.json()["detail"]


def test_close_needs_payments_covering_window(client, world, clock_at):
    h = world["h"]["owner"]
    cust, pay, vis = _csvs()
    pay = b"\n".join(line for line in pay.split(b"\n") if not line.startswith(b"tail"))
    for kind, data in (("customers", cust), ("payments", pay), ("visits", vis)):
        _upload(client, h, kind, data)
    eid = client.post("/api/v1/experiments", headers=h, json={"title": "t", "protocol": PROTOCOL}).json()["id"]
    _register(client, h, eid, clock_at)
    r = client.post(f"/api/v1/experiments/{eid}/close", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "payments_not_covering_window"


def test_customer_in_registered_experiment_is_excluded(client, world, clock_at):
    h = world["h"]["owner"]
    eid = _setup_experiment(client, h)
    _register(client, h, eid, clock_at)
    pre = client.post("/api/v1/experiments/preview", headers=h, json=PROTOCOL).json()
    assert pre["cohort_size"] == 0 and pre["excluded_other_experiments"] == 400


def test_full_flow_recalculation_identical_and_certificate(client, world, clock_at):
    h = world["h"]["owner"]
    eid = _setup_experiment(client, h)
    pre = client.post("/api/v1/experiments/preview", headers=h, json=PROTOCOL).json()
    assert pre["cohort_size"] == 400 and pre["n_control"] == 200 and pre["strata"]
    _register(client, h, eid, clock_at)
    assert client.post(f"/api/v1/experiments/{eid}/calculate", headers=h).json()["code"] == "not_closed"
    assert client.get(f"/api/v1/experiments/{eid}/result", headers=h).status_code == 404
    client.post(f"/api/v1/experiments/{eid}/close", headers=h)
    r1 = client.post(f"/api/v1/experiments/{eid}/calculate", headers=h).json()
    r2 = client.post(f"/api/v1/experiments/{eid}/calculate", headers=h).json()
    assert r1["payload"] == r2["payload"] and r1["result_hash"] == r2["result_hash"]
    # зерно случайное при регистрации: без эффекта статус чаще всего not_detected (проверено в test_stats)
    from app.stats import STATUS_LABEL

    assert r1["payload"]["status_label"] == STATUS_LABEL[r1["payload"]["status"]]
    assert r1["payload"]["status"] != "insufficient"
    assert r1["payload"]["iterations"] == 5000
    cert = client.get(f"/api/v1/experiments/{eid}/certificate", headers=h).json()
    assert cert["result_hash"] == r1["result_hash"] and cert["business_name"] == "Клуб «Тест»"
    assert len(cert["assignment_sha256"]) == 64
    assert [a["action"] for a in cert["audit"]][:2] == ["experiment.created", "experiment.registered"]
    chain = client.get("/api/v1/audit/verify", headers=h).json()
    assert chain["ok"] and chain["checked"] > 5 and len(chain["last_hash"]) == 64


def test_live_mde(client, world):
    r = client.post("/api/v1/stats/mde", headers=world["h"]["owner"],
                    json={"baseline": 0.05, "n_control": 1000, "n_test": 1000})
    assert r.status_code == 200 and abs(r.json()["mde"] - 0.0273) < 0.001


def test_other_business_is_hidden(client, world, db):
    from app.models import Business, Role, User
    from app.security import hash_password

    b2 = Business(name="Чужой клуб")
    db.add(b2)
    db.flush()
    db.add(User(login="owner2", password_hash=hash_password("owner2-pass"), role=Role.owner, business_id=b2.id))
    db.commit()
    tok = client.post("/api/v1/auth/token", data={"username": "owner2", "password": "owner2-pass"}).json()
    eid = _setup_experiment(client, world["h"]["owner"])
    r = client.get(f"/api/v1/experiments/{eid}", headers={"Authorization": f"Bearer {tok['access_token']}"})
    assert r.status_code == 404


# --- команда и журнал --------------------------------------------------------------------------

def test_owner_manages_executors_and_failed_login_is_logged(client, world):
    h = world["h"]["owner"]
    r = client.post("/api/v1/users", headers=h, json={"login": "coach2", "password": "coach2-pass",
                                                       "role": "owner"})
    assert r.status_code == 403
    r = client.post("/api/v1/users", headers=h, json={"login": "coach2", "password": "coach2-pass",
                                                       "role": "executor"})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    assert client.post("/api/v1/users", headers=h, json={"login": "coach2", "password": "coach2-pass",
                                                          "role": "executor"}).json()["code"] == "login_taken"
    assert client.post(f"/api/v1/users/{uid}/deactivate", headers=h).status_code == 200
    r = client.post("/api/v1/auth/token", data={"username": "coach2", "password": "coach2-pass"})
    assert r.status_code == 401
    log = client.get("/api/v1/audit?action=auth.", headers=world["h"]["admin"]).json()
    assert any(e["action"] == "auth.login_failed" for e in log)


def test_me(client, world):
    me = client.get("/api/v1/auth/me", headers=world["h"]["owner"]).json()
    assert me["role"] == "owner" and me["business_name"] == "Клуб «Тест»"
    assert client.get("/api/v1/auth/me").json()["code"] == "unauthorized"


def test_db_blocks_tampering_after_registration(client, world, clock_at, db):
    import pytest
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    h = world["h"]["owner"]
    eid = _setup_experiment(client, h)
    _register(client, h, eid, clock_at)
    for sql in (f"UPDATE experiment SET protocol = '{{}}' WHERE id = '{eid}'",
                f"UPDATE experiment SET seed = 'x' WHERE id = '{eid}'",
                f"UPDATE assignment SET \"group\" = 'test' WHERE experiment_id = '{eid}'",
                f"DELETE FROM assignment WHERE experiment_id = '{eid}'",
                f"DELETE FROM experiment WHERE id = '{eid}'"):
        with pytest.raises(DBAPIError):
            db.execute(text(sql))
        db.rollback()


def test_audit_anchor_written_to_storage(client, world, db):
    import json

    from app.services.anchor import write_anchor

    a = write_anchor(db)
    assert a["key"] == "audit-anchors/2026-11-05.json"
    stored = json.loads(get_storage().get(a["key"]))
    assert stored["hash"] == client.get("/api/v1/audit/verify", headers=world["h"]["owner"]).json()["last_hash"]
