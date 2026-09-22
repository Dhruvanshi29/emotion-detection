"""add authenticator mfa

Revision ID: 5b8c0e1f3a42
Revises: 4a7b9d0e2f31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "5b8c0e1f3a42"
down_revision: Union[str, None] = "4a7b9d0e2f31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_enabled", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("users", sa.Column("mfa_secret", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "mfa_secret")
    op.drop_column("users", "mfa_enabled")
