"""add indexing_heartbeat for P13 anti-false-kill watchdog

Revision ID: d5f02c8b3a11
Revises: c4e91b7a2f10
Create Date: 2026-07-14 11:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5f02c8b3a11"
down_revision: Union[str, Sequence[str], None] = "c4e91b7a2f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pipeline_runs",
        sa.Column("indexing_heartbeat", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pipeline_runs", "indexing_heartbeat")
