"""add journal_entries journal_analysis

Revision ID: 7c2e4a91b3d5
Revises: 98716852523a
Create Date: 2026-08-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c2e4a91b3d5'
down_revision: Union[str, None] = '98716852523a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'journal_entries',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('mood', sa.Integer(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('journal_entries', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_journal_entries_user_id'), ['user_id'], unique=False
        )

    op.create_table(
        'journal_analysis',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('entry_id', sa.String(length=36), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('themes', sa.JSON(), nullable=True),
        sa.Column('reflection_prompt', sa.Text(), nullable=False),
        sa.Column('key_feelings', sa.JSON(), nullable=True),
        sa.Column('dominant_emotion', sa.String(length=24), nullable=True),
        sa.Column('sentiment', sa.String(length=16), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('provider', sa.String(length=32), nullable=True),
        sa.Column('model', sa.String(length=120), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['entry_id'], ['journal_entries.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('entry_id'),
    )


def downgrade() -> None:
    op.drop_table('journal_analysis')
    with op.batch_alter_table('journal_entries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_journal_entries_user_id'))
    op.drop_table('journal_entries')
