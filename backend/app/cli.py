"""Команды обслуживания.

    python -m app.cli create-admin <login> <password>   первый администратор
    python -m app.cli anchor-audit                      суточный якорь журнала в S3
"""

import sys

from app.db import get_sessionmaker
from app.models import Role, User
from app.security import hash_password
from app.services import audit


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "anchor-audit":
        from app.services.anchor import write_anchor

        with get_sessionmaker()() as db:
            print(write_anchor(db))
        return
    if len(sys.argv) != 4 or sys.argv[1] != "create-admin":
        sys.exit("usage: python -m app.cli create-admin <login> <password> | anchor-audit")
    with get_sessionmaker()() as db:
        u = User(login=sys.argv[2], password_hash=hash_password(sys.argv[3]), role=Role.admin)
        db.add(u)
        db.flush()
        audit.append(db, action="user.created", entity_type="user", entity_id=str(u.id),
                     payload={"login": u.login, "role": "admin"}, actor_id=None)
        db.commit()
    print("ok")


if __name__ == "__main__":
    main()
