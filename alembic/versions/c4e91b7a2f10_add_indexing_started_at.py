"""add indexing_started_at for P13 watchdog

Revision ID: c4e91b7a2f10
Revises: a8f3c2d91e04
Create Date: 2026-07-14 11:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e91b7a2f10"
down_revision: Union[str, Sequence[str], None] = "a8f3c2d91e04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pipeline_runs",
        sa.Column("indexing_started_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pipeline_runs", "indexing_started_at")
