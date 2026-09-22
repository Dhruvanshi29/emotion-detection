"""encrypt reminder text and add email delivery attempts

Revision ID: 4a7b9d0e2f31
Revises: 3f6a8c9d1e20
Create Date: 2026-09-20 21:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4a7b9d0e2f31"
down_revision: Union[str, None] = "3f6a8c9d1e20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("reminders") as batch:
        batch.alter_column("title", existing_type=sa.String(length=120), type_=sa.Text(), existing_nullable=False)
    with op.batch_alter_table("notifications") as batch:
        batch.alter_column("title", existing_type=sa.String(length=160), type_=sa.Text(), existing_nullable=False)
        batch.add_column(sa.Column("delivery_attempts", sa.Integer(), server_default="0", nullable=False))
        batch.add_column(sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("notifications") as batch:
        batch.drop_column("last_attempt_at")
        batch.drop_column("delivery_attempts")
        batch.alter_column("title", existing_type=sa.Text(), type_=sa.String(length=160), existing_nullable=False)
    with op.batch_alter_table("reminders") as batch:
        batch.alter_column("title", existing_type=sa.Text(), type_=sa.String(length=120), existing_nullable=False)
