"""add auth action tokens

Revision ID: 3f6a8c9d1e20
Revises: 28c3e41f9a02
Create Date: 2026-09-20 20:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3f6a8c9d1e20"
down_revision: Union[str, None] = "28c3e41f9a02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_action_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_auth_action_tokens_user_id", "auth_action_tokens", ["user_id"])
    op.create_index("ix_auth_action_tokens_purpose", "auth_action_tokens", ["purpose"])
    op.create_index("ix_auth_action_tokens_token_hash", "auth_action_tokens", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_auth_action_tokens_token_hash", table_name="auth_action_tokens")
    op.drop_index("ix_auth_action_tokens_purpose", table_name="auth_action_tokens")
    op.drop_index("ix_auth_action_tokens_user_id", table_name="auth_action_tokens")
    op.drop_table("auth_action_tokens")
