"""методика: дата полноты выгрузки, версии результата

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-13 15:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("experiment", sa.Column("data_complete_through", sa.Date(), nullable=True))
    op.add_column("experiment_result", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.add_column("experiment_result", sa.Column("reason", sa.Text(), nullable=True))
    # Уже сохранённые пересчёты нумеруем по времени. Таблица «только вставка»,
    # поэтому триггер выключаем только на эту нумерацию внутри миграции.
    op.execute("ALTER TABLE experiment_result DISABLE TRIGGER experiment_result_insert_only")
    op.execute("""
        UPDATE experiment_result r SET version = v.n
        FROM (SELECT id, row_number() OVER (PARTITION BY experiment_id ORDER BY computed_at, id) AS n
              FROM experiment_result) v
        WHERE r.id = v.id AND v.n > 1
    """)
    op.execute("ALTER TABLE experiment_result ENABLE TRIGGER experiment_result_insert_only")
    op.create_unique_constraint("uq_experiment_result_version", "experiment_result", ["experiment_id", "version"])


def downgrade() -> None:
    op.drop_constraint("uq_experiment_result_version", "experiment_result", type_="unique")
    op.drop_column("experiment_result", "reason")
    op.drop_column("experiment_result", "version")
    op.drop_column("experiment", "data_complete_through")
