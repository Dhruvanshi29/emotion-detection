"""encrypt sensitive titles and metadata

Revision ID: 6c9d1f2a4b53
Revises: 5b8c0e1f3a42
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "6c9d1f2a4b53"
down_revision: Union[str, None] = "5b8c0e1f3a42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _text(table: str, column: str) -> None:
    op.alter_column(table, column, existing_type=sa.JSON(), type_=sa.Text(), postgresql_using=f"{column}::text")


def upgrade() -> None:
    op.alter_column("conversations", "title", existing_type=sa.String(length=200), type_=sa.Text())
    op.alter_column("journal_entries", "title", existing_type=sa.String(length=200), type_=sa.Text())
    op.alter_column("user_memories", "title", existing_type=sa.String(length=160), type_=sa.Text())
    for table, column in (
        ("risk_assessments", "categories"),
        ("safety_events", "payload"),
        ("journal_entries", "tags"),
        ("journal_analysis", "themes"),
        ("journal_analysis", "key_feelings"),
        ("user_memories", "tags"),
        ("conversation_summaries", "key_points"),
    ):
        _text(table, column)


def downgrade() -> None:
    for table, column in (
        ("risk_assessments", "categories"),
        ("safety_events", "payload"),
        ("journal_entries", "tags"),
        ("journal_analysis", "themes"),
        ("journal_analysis", "key_feelings"),
        ("user_memories", "tags"),
        ("conversation_summaries", "key_points"),
    ):
        op.alter_column(table, column, existing_type=sa.Text(), type_=sa.JSON(), postgresql_using=f"{column}::json")
    op.alter_column("user_memories", "title", existing_type=sa.Text(), type_=sa.String(length=160))
    op.alter_column("journal_entries", "title", existing_type=sa.Text(), type_=sa.String(length=200))
    op.alter_column("conversations", "title", existing_type=sa.Text(), type_=sa.String(length=200))
