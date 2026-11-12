"""Сквозные тесты API: импорт → эксперимент → регистрация → закрытие → расчёт."""

from datetime import date, timedelta

import numpy as np

from app.storage import get_storage

AS_OF = date(2026, 10, 1)
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
    pay = ["payment_id;customer_id;paid_at;amount"]
    vis = ["customer_id;visited_at"]
    for i in range(n):
        cid = f"c{i:04d}"
        last = AS_OF - timedelta(days=int(rng.integers(35, 170)))
        first = last - timedelta(days=int(rng.integers(60, 600)))
        cust.append(f"{cid};{first};{last};Центр")
        pay.append(f"p{i}-0;{cid};{first};3 000,00")
        vis.append(f"{cid};{last}")
        if rng.random() < 0.08:  # часть вернулась после среза
            pay.append(f"p{i}-1;{cid};{AS_OF + timedelta(days=int(rng.integers(1, 30)))};3000")
    return ["\n".join(x).encode() for x in (cust, pay, vis)]


def _upload(client, h, kind, data, name="f.csv"):
    return client.post("/api/v1/imports", headers=h, data={"kind": kind},
                       files={"file": (name, data, "text/csv")})


def _setup_experiment(client, h):
    for kind, data in zip(("customers", "payments", "visits"), _csvs(), strict=True):
        r = _upload(client, h, kind, data)
        assert r.status_code == 201 and r.json()["status"] == "accepted", r.text
    r = client.post("/api/v1/experiments", headers=h, json={"title": "Звонки ушедшим", "protocol": PROTOCOL})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_import_quality_report_and_sha(client, world):
    h = world["h"]["owner"]
    data = b"payment_id;customer_id;paid_at;amount\np1;c1;2026-09-01;100\np1;c1;2026-09-01;100\n"
    r = _upload(client, h, "payments", data)
    assert r.status_code == 201
    body = r.json()
    import hashlib

    assert body["sha256"] == hashlib.sha256(data).hexdigest()
    assert body["quality_report"]["duplicates"] == 1
    assert get_storage().get(f"{world['business'].id}/{body['id']}/{body['sha256']}.csv") == data
    again = _upload(client, h, "payments", data).json()
    assert again["quality_report"]["same_file_imported_before"] is True


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
    assert r.status_code == 403


def test_protocol_edit_after_registration_conflict(client, world):
    h = world["h"]["owner"]
    eid = _setup_experiment(client, h)
    r = client.patch(f"/api/v1/experiments/{eid}", headers=h, json={"title": "Новое имя"})
    assert r.status_code == 200
    r = client.post(f"/api/v1/experiments/{eid}/register", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["protocol_hash"]
    changed = {**PROTOCOL, "control_share": "0.3"}
    r = client.patch(f"/api/v1/experiments/{eid}", headers=h, json={"protocol": changed})
    assert r.status_code == 409
    assert client.post(f"/api/v1/experiments/{eid}/register", headers=h).status_code == 409


def test_executor_sees_control_only_after_close(client, world):
    owner, ex = world["h"]["owner"], world["h"]["executor"]
    eid = _setup_experiment(client, owner)
    assert client.get(f"/api/v1/experiments/{eid}", headers=ex).status_code == 404  # черновик скрыт
    client.post(f"/api/v1/experiments/{eid}/register", headers=owner)

    r = client.get(f"/api/v1/experiments/{eid}/assignments", headers=ex)
    assert r.status_code == 200 and r.json() and {a["group"] for a in r.json()} == {"test"}
    assert client.get(f"/api/v1/experiments/{eid}/assignments?group=control", headers=ex).status_code == 403
    card = client.get(f"/api/v1/experiments/{eid}", headers=ex).json()
    assert card["n_control"] is None and "control_share" not in card["protocol"]
    assert client.get(f"/api/v1/experiments/{eid}/result", headers=ex).status_code == 403
    assert client.post(f"/api/v1/experiments/{eid}/close", headers=ex).status_code == 403

    client.post(f"/api/v1/experiments/{eid}/close", headers=owner)
    r = client.get(f"/api/v1/experiments/{eid}/assignments?group=control", headers=ex)
    assert r.status_code == 200 and r.json()


def test_full_flow_recalculation_identical_and_certificate(client, world):
    h = world["h"]["owner"]
    eid = _setup_experiment(client, h)
    pre = client.post("/api/v1/experiments/preview", headers=h, json=PROTOCOL).json()
    assert pre["cohort_size"] == 400 and pre["n_control"] == 200
    client.post(f"/api/v1/experiments/{eid}/register", headers=h)
    assert client.post(f"/api/v1/experiments/{eid}/calculate", headers=h).status_code == 409
    client.post(f"/api/v1/experiments/{eid}/close", headers=h)
    r1 = client.post(f"/api/v1/experiments/{eid}/calculate", headers=h).json()
    r2 = client.post(f"/api/v1/experiments/{eid}/calculate", headers=h).json()
    assert r1["payload"] == r2["payload"] and r1["result_hash"] == r2["result_hash"]
    assert r1["payload"]["status"] == "эффект не обнаружен"
    assert r1["payload"]["iterations"] == 5000
    cert = client.get(f"/api/v1/experiments/{eid}/certificate", headers=h).json()
    assert cert["result_hash"] == r1["result_hash"]
    assert [a["action"] for a in cert["audit"]][:2] == ["experiment.created", "experiment.registered"]
    chain = client.get("/api/v1/audit/verify", headers=h).json()
    assert chain["ok"] and chain["checked"] > 5


def test_live_mde(client, world):
    r = client.post("/api/v1/stats/mde", headers=world["h"]["owner"],
                    json={"baseline": 0.05, "cohort_size": 2000, "control_share": 0.5})
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
