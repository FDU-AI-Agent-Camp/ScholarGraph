"""add pipeline ephemeral state columns

Revision ID: a8f3c2d91e04
Revises: 17bad1e1a105
Create Date: 2026-07-13 13:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8f3c2d91e04"
down_revision: Union[str, Sequence[str], None] = "17bad1e1a105"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pipeline_runs",
        sa.Column("active_rag_run_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "pipeline_runs",
        sa.Column("preview_graph", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pipeline_runs", "preview_graph")
    op.drop_column("pipeline_runs", "active_rag_run_id")
