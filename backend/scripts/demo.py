"""Демо-данные: бизнес, собственник, исполнитель, CSV, эксперименты на всех стадиях.

    python -m app.cli create-admin admin admin-pass
    python scripts/demo.py admin admin-pass

Скрипт работает в процессе с приложением (TestClient) и пишет в базу из SVERKA_DATABASE_URL.
Так он может «перевести часы» на день регистрации завершённого эксперимента: по правилам
спецификации срез не старше 7 дней, а закрыть можно только после окна замера. На сервер
это не влияет, часы подменяются только внутри скрипта.

Синтетика: 2 000 ушедших клиентов, возврат 5% в контроле и 11% в тесте, C = 20 000 ₽.
"""

import random
import sys
from datetime import UTC, datetime, time, timedelta

from fastapi.testclient import TestClient

from app import clock
from app.main import app

admin_login, admin_pw = sys.argv[1], sys.argv[2]
real_now = clock.now
c = TestClient(app, base_url="http://demo/api/v1")
TODAY = real_now().date()
AS_OF = TODAY - timedelta(days=35)
rnd = random.Random(42)


def at(d):
    clock.now = (lambda: datetime.combine(d, time(9), UTC)) if d else real_now


def ok(r):
    if r.status_code >= 400:
        sys.exit(f"{r.request.method} {r.request.url}: {r.status_code} {r.text}")
    return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else None


def token(login: str, pw: str) -> dict:
    return {"Authorization": f"Bearer {ok(c.post('/auth/token', data={'username': login, 'password': pw}))['access_token']}"}


def upload(h: dict, kind: str, lines: list[str], name: str) -> None:
    r = c.post("/imports", headers=h, data={"kind": kind},
               files={"file": (name, "\n".join(lines).encode(), "text/csv")})
    body = ok(r)
    print(f"{name}: {body['status']}, строк {body['quality_report']['rows_valid']}")


adm = token(admin_login, admin_pw)
biz = ok(c.post("/businesses", headers=adm, json={"name": "Фитнес-клуб «Демо»"}))
ok(c.post("/users", headers=adm, json={"login": "owner", "password": "owner-pass", "role": "owner",
                                       "business_id": biz["id"]}))
own = token("owner", "owner-pass")
ok(c.post("/users", headers=own, json={"login": "coach", "password": "coach-pass", "role": "executor"}))
ok(c.post("/consents", headers=own, json={"text_version": "csv-2026-11"}))

cust = ["customer_id;first_paid_at;subscription_ends_at;branch"]
pay = ["payment_id;customer_id;paid_at;amount;operation;method"]
vis = ["customer_id;visited_at;branch"]
obl = ["obligation_id;customer_id;kind;starts_at;ends_at;amount;status"]
for i in range(2000):
    cid = f"K{i:05d}"
    branch = rnd.choice(["Центр", "Север"])
    last = AS_OF - timedelta(days=rnd.randint(31, 170))
    first = last - timedelta(days=rnd.randint(40, 700))
    cust.append(f"{cid};{first};{last};{branch}")
    pay.append(f"P{i}-0;{cid};{first};{rnd.choice(['3 000,00', '4 500,00', '2 500,00'])};payment;card")
    vis.append(f"{cid};{last};{branch}")
for i in range(2000, 2300):  # активные клиенты: в когорту не попадут
    cid = f"K{i:05d}"
    start = TODAY - timedelta(days=rnd.randint(5, 25))
    pay.append(f"P{i}-0;{cid};{start};3 000,00;payment;cash")
    vis.append(f"{cid};{start};Центр")
    obl.append(f"O{i};{cid};subscription;{start};{start + timedelta(days=30)};3 000,00;active")
pay.append("P2000-r;K02000;" + str(TODAY - timedelta(days=2)) + ";500,00;refund;card")
upload(own, "customers", cust, "clients.csv")
upload(own, "payments", pay, "payments.csv")
upload(own, "visits", vis, "visits.csv")
upload(own, "obligations", obl, "obligations.csv")
upload(own, "customers", ["customer_id;ФИО;Телефон;first_paid_at", "K1;Иванов Иван;+79120000000;2025-01-01"],
       "with_pii.csv")

protocol = {"hypothesis": "Личный звонок тренера возвращает ушедших клиентов",
            "action": "Тренер звонит и предлагает бесплатное пробное занятие",
            "as_of": AS_OF.isoformat(), "control_share": "0.5", "window_days": 30, "cost_rub": "20000.00"}
exp = ok(c.post("/experiments", headers=own, json={"title": "Звонок тренера ушедшим", "protocol": protocol}))
at(AS_OF + timedelta(days=1))
ok(c.post(f"/experiments/{exp['id']}/register", headers=own))
at(None)
groups = ok(c.get(f"/experiments/{exp['id']}/assignments", headers=own))

after = ["payment_id;customer_id;paid_at;amount"]
for a in groups:
    p = 0.11 if a["group"] == "test" else 0.05
    if rnd.random() < p:
        after.append(f"R-{a['customer_id']};{a['customer_id']};{AS_OF + timedelta(days=rnd.randint(1, 30))};3000")
upload(own, "payments", after, "payments_after.csv")
ok(c.post(f"/experiments/{exp['id']}/close", headers=own, json={"data_complete_through": TODAY.isoformat()}))
res = ok(c.post(f"/experiments/{exp['id']}/calculate", headers=own))
print("закрыт:", res["payload"]["status_label"], exp["id"])

running = ok(c.post("/experiments", headers=own, json={
    "title": "Сообщение в MAX с промокодом",
    "protocol": {**protocol, "hypothesis": "Персональное сообщение возвращает часть ушедших",
                 "action": "Сообщение в MAX с промокодом на месяц", "as_of": (TODAY - timedelta(days=3)).isoformat(),
                 "control_share": "0.3", "cost_rub": "3000.00", "inactive_days": 150, "max_inactive_days": 365}}))
r = c.post(f"/experiments/{running['id']}/register", headers=own)
print("идёт:", running["id"], r.status_code)

draft = ok(c.post("/experiments", headers=own, json={
    "title": "Скидка 20% на возврат", "protocol": {**protocol, "as_of": TODAY.isoformat()}}))
print("черновик:", draft["id"])
