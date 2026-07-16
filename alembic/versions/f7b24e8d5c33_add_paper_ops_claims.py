"""add paper_ops_claims cluster wipe mutex

Revision ID: f7b24e8d5c33
Revises: e6a13d9c4b22
Create Date: 2026-07-16 00:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7b24e8d5c33"
down_revision: Union[str, Sequence[str], None] = "e6a13d9c4b22"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "paper_ops_claims",
        sa.Column("paper_id", sa.String(length=36), nullable=False),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("owner_token", sa.String(length=64), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("paper_id"),
    )


def downgrade() -> None:
    op.drop_table("paper_ops_claims")
