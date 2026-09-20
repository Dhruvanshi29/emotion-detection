"""add user memories + conversation summaries

Revision ID: 12ab34cd56ef
Revises: f0a1b2c3d4e5
Create Date: 2026-08-31 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '12ab34cd56ef'
down_revision: Union[str, None] = 'f0a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_memories',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('kind', sa.String(length=24), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=24), nullable=False),
        sa.Column('source_ref_id', sa.String(length=36), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('importance', sa.Float(), nullable=False, server_default='0.5'),
        sa.Column('pinned', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('embedding', sa.JSON(), nullable=True),
        sa.Column('embedding_model', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_user_memories_user_id', 'user_memories', ['user_id'])
    op.create_index('ix_user_memories_source_ref_id', 'user_memories', ['source_ref_id'])

    op.create_table(
        'conversation_summaries',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('conversation_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False, server_default=''),
        sa.Column('key_points', sa.JSON(), nullable=True),
        sa.Column('message_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_message_id', sa.String(length=36), nullable=True),
        sa.Column('embedding', sa.JSON(), nullable=True),
        sa.Column('embedding_model', sa.String(length=64), nullable=True),
        sa.Column('provider', sa.String(length=32), nullable=True),
        sa.Column('model', sa.String(length=120), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('conversation_id', name='uq_conversation_summary'),
    )
    op.create_index('ix_conversation_summaries_conversation_id', 'conversation_summaries', ['conversation_id'])
    op.create_index('ix_conversation_summaries_user_id', 'conversation_summaries', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_conversation_summaries_user_id', table_name='conversation_summaries')
    op.drop_index('ix_conversation_summaries_conversation_id', table_name='conversation_summaries')
    op.drop_table('conversation_summaries')
    op.drop_index('ix_user_memories_source_ref_id', table_name='user_memories')
    op.drop_index('ix_user_memories_user_id', table_name='user_memories')
    op.drop_table('user_memories')
