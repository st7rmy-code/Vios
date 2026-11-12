import os

os.environ.setdefault("SVERKA_DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:5432/sverka_test")
os.environ["SVERKA_STORAGE_BACKEND"] = "memory"

from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import get_engine, get_sessionmaker
from app.models import Business, Role, User
from app.security import hash_password

TABLES = ["experiment_result", "assignment", "experiment", "obligation", "visit", "payment", "customer",
          "import_file", "data_consent", "audit_log", "app_user", "business"]
# «Сегодня» в тестах фиксировано: окно замера эксперимента из test_api уже закончилось
TODAY = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="session")
def migrated():
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "migrations"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture
def db(migrated):
    with get_engine().begin() as conn:
        # триггер «только вставка» обходим только здесь, для очистки тестовой базы
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        for t in TABLES:
            conn.execute(text(f"DELETE FROM {t}"))
    with get_sessionmaker()() as s:
        yield s


@pytest.fixture(autouse=True)
def clock_at(monkeypatch):
    """clock_at(datetime) переводит часы сервисов; по умолчанию TODAY."""
    from app import clock

    state = {"now": TODAY}
    monkeypatch.setattr(clock, "now", lambda: state["now"])

    def set_now(dt: datetime) -> None:
        state["now"] = dt

    return set_now


@pytest.fixture
def client(db):
    from app.main import app

    return TestClient(app)


@pytest.fixture
def world(db, client):
    """Бизнес, админ, собственник, исполнитель и токены."""
    b = Business(name="Клуб «Тест»")
    db.add(b)
    db.flush()
    users = {
        "admin": User(login="admin", password_hash=hash_password("admin-pass"), role=Role.admin),
        "owner": User(login="owner", password_hash=hash_password("owner-pass"), role=Role.owner, business_id=b.id),
        "executor": User(login="coach", password_hash=hash_password("coach-pass"), role=Role.executor,
                         business_id=b.id),
    }
    db.add_all(users.values())
    db.commit()
    pw = {"admin": "admin-pass", "owner": "owner-pass", "executor": "coach-pass"}
    headers = {}
    for k, u in users.items():
        r = client.post("/api/v1/auth/token", data={"username": u.login, "password": pw[k]})
        assert r.status_code == 200, r.text
        headers[k] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post("/api/v1/consents", headers=headers["owner"], json={"text_version": "csv-2026-11"})
    assert r.status_code == 201, r.text
    return {"business": b, "users": users, "h": headers}
