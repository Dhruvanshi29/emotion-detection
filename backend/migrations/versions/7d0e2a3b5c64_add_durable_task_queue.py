"""add durable task queue

Revision ID: 7d0e2a3b5c64
Revises: 6c9d1f2a4b53
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "7d0e2a3b5c64"
down_revision: Union[str, None] = "6c9d1f2a4b53"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_task_jobs_dedupe_key"),
    )
    op.create_index("ix_task_jobs_kind", "task_jobs", ["kind"])
    op.create_index("ix_task_jobs_status", "task_jobs", ["status"])
    op.create_index("ix_task_jobs_available_at", "task_jobs", ["available_at"])


def downgrade() -> None:
    op.drop_index("ix_task_jobs_available_at", table_name="task_jobs")
    op.drop_index("ix_task_jobs_status", table_name="task_jobs")
    op.drop_index("ix_task_jobs_kind", table_name="task_jobs")
    op.drop_table("task_jobs")
