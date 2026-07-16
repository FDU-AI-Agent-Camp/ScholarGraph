"""add vector_cleanup_queue Wave-2 outbox

Revision ID: a8c91f2e4d10
Revises: f7b24e8d5c33
Create Date: 2026-07-16 12:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8c91f2e4d10"
down_revision: Union[str, Sequence[str], None] = "f7b24e8d5c33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vector_cleanup_queue",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("paper_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("create_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("execute_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_id", "run_id", name="uq_vector_cleanup_paper_run"),
    )
    op.create_index("ix_vector_cleanup_queue_paper_id", "vector_cleanup_queue", ["paper_id"])
    op.create_index("ix_vector_cleanup_queue_execute_at", "vector_cleanup_queue", ["execute_at"])


def downgrade() -> None:
    op.drop_index("ix_vector_cleanup_queue_execute_at", table_name="vector_cleanup_queue")
    op.drop_index("ix_vector_cleanup_queue_paper_id", table_name="vector_cleanup_queue")
    op.drop_table("vector_cleanup_queue")
