import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.services import audit


def _fill(db, n=5):
    for i in range(n):
        audit.append(db, action="test.event", entity_type="test", entity_id=str(i), payload={"i": i, "sum": 1500})
    db.commit()


def test_chain_valid(db):
    _fill(db)
    c = audit.verify_chain(db)
    assert c.ok and c.checked == 5


def test_update_and_delete_are_forbidden(db):
    _fill(db, 1)
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE audit_log SET action = 'x'"))
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM audit_log"))
    db.rollback()


def test_tampering_breaks_chain(db):
    _fill(db)
    # злоумышленник с правами суперпользователя обходит триггер и меняет сумму
    db.execute(text("SET LOCAL session_replication_role = replica"))
    db.execute(text("UPDATE audit_log SET payload = '{\"i\": 2, \"sum\": 1}' WHERE seq = 3"))
    db.commit()
    c = audit.verify_chain(db)
    assert not c.ok and c.broken_at_seq == 3


def test_tampering_with_rehash_breaks_next_link(db):
    _fill(db)
    db.execute(text("SET LOCAL session_replication_role = replica"))
    row = db.execute(text("SELECT * FROM audit_log WHERE seq = 3")).mappings().one()
    from app.models import AuditLog

    fake = db.get(AuditLog, row["id"])
    fake.payload = {"i": 2, "sum": 1}
    fake.hash = audit.compute_hash(fake.prev_hash, audit.record_body(fake))
    db.commit()
    c = audit.verify_chain(db)
    assert not c.ok and c.broken_at_seq == 4
