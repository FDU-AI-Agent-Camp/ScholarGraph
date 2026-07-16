"""add pipeline_generation_id write-guard token

Revision ID: e6a13d9c4b22
Revises: d5f02c8b3a11
Create Date: 2026-07-15 23:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e6a13d9c4b22"
down_revision: Union[str, Sequence[str], None] = "d5f02c8b3a11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pipeline_runs",
        sa.Column("pipeline_generation_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pipeline_runs", "pipeline_generation_id")
