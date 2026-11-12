"""Суточный якорь журнала (спецификация, 4.3): последний hash пишется в S3.

Запуск раз в сутки: python -m app.cli anchor-audit (cron/k8s CronJob).
Перезапись всей цепочки суперпользователем БД видна по расхождению с якорем.
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.config import get_settings
from app.models import AuditLog
from app.storage import get_storage


def write_anchor(db: Session) -> dict:
    last = db.execute(select(AuditLog).order_by(AuditLog.seq.desc()).limit(1)).scalar_one_or_none()
    now = clock.now()
    anchor = {"seq": last.seq if last else 0, "hash": last.hash if last else None, "written_at": now.isoformat()}
    key = f"{get_settings().audit_anchor_prefix}/{now:%Y-%m-%d}.json"
    get_storage().put(key, json.dumps(anchor, ensure_ascii=False).encode())
    return {"key": key, **anchor}
