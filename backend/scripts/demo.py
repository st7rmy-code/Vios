"""Демо-данные через HTTP API: бизнес, собственник, исполнитель, CSV, эксперимент с результатом.

    python -m app.cli create-admin admin admin-pass
    python scripts/demo.py http://localhost:8000 admin admin-pass

Синтетика: 2 000 ушедших клиентов, возврат 5% в контроле и 11% в тесте, C = 20 000 ₽.
Оплаты после среза загружаются после регистрации, как в жизни.
"""

import random
import sys
from datetime import date, timedelta

import httpx

base, admin_login, admin_pw = sys.argv[1], sys.argv[2], sys.argv[3]
c = httpx.Client(base_url=f"{base}/api/v1", timeout=120)
AS_OF = date.today() - timedelta(days=35)
rnd = random.Random(42)


def token(login: str, pw: str) -> dict:
    r = c.post("/auth/token", data={"username": login, "password": pw})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def upload(h: dict, kind: str, lines: list[str], name: str) -> None:
    r = c.post("/imports", headers=h, data={"kind": kind},
               files={"file": (name, "\n".join(lines).encode(), "text/csv")})
    r.raise_for_status()
    print(kind, r.json()["status"], r.json()["quality_report"]["rows_valid"])


adm = token(admin_login, admin_pw)
biz = c.post("/businesses", headers=adm, json={"name": "Фитнес-клуб «Демо»"}).json()
c.post("/users", headers=adm, json={"login": "owner", "password": "owner-pass", "role": "owner",
                                    "business_id": biz["id"]}).raise_for_status()
own = token("owner", "owner-pass")
c.post("/users", headers=own, json={"login": "coach", "password": "coach-pass", "role": "executor"}).raise_for_status()

cust, pay, vis = ["customer_id;first_paid_at;subscription_ends_at;branch"], ["payment_id;customer_id;paid_at;amount"], [
    "customer_id;visited_at"]
for i in range(2000):
    cid = f"K{i:05d}"
    last = AS_OF - timedelta(days=rnd.randint(31, 170))
    first = last - timedelta(days=rnd.randint(40, 700))
    cust.append(f"{cid};{first};{last};{rnd.choice(['Центр', 'Север'])}")
    pay.append(f"P{i}-0;{cid};{first};{rnd.choice(['3 000,00', '4 500,00', '2 500,00'])}")
    vis.append(f"{cid};{last}")
upload(own, "customers", cust, "clients.csv")
upload(own, "payments", pay, "payments_before.csv")
upload(own, "visits", vis, "visits.csv")
upload(own, "customers", ["customer_id;ФИО;Телефон;first_paid_at", "K1;Иванов Иван;+79120000000;2025-01-01"], "with_pii.csv")

protocol = {"hypothesis": "Личный звонок тренера возвращает ушедших клиентов",
            "action": "Тренер звонит и предлагает бесплатное пробное занятие",
            "as_of": AS_OF.isoformat(), "control_share": "0.5", "window_days": 30, "cost_rub": "20000.00"}
exp = c.post("/experiments", headers=own, json={"title": "Звонок тренера ушедшим", "protocol": protocol}).json()
c.post(f"/experiments/{exp['id']}/register", headers=own).raise_for_status()
groups = c.get(f"/experiments/{exp['id']}/assignments", headers=own).json()

after = ["payment_id;customer_id;paid_at;amount"]
for a in groups:
    p = 0.11 if a["group"] == "test" else 0.05
    if rnd.random() < p:
        after.append(f"R-{a['customer_id']};{a['customer_id']};{AS_OF + timedelta(days=rnd.randint(1, 30))};3000")
upload(own, "payments", after, "payments_after.csv")
c.post(f"/experiments/{exp['id']}/close", headers=own).raise_for_status()
res = c.post(f"/experiments/{exp['id']}/calculate", headers=own).json()
print("result:", res["payload"]["status"], exp["id"])

draft = c.post("/experiments", headers=own, json={"title": "Скидка 20% на возврат", "protocol": {**protocol, "as_of": date.today().isoformat()}}).json()
print("draft:", draft["id"])
