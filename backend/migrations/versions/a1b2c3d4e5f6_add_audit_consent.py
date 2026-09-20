"""add audit_events + consent_events

Revision ID: a1b2c3d4e5f6
Revises: 12ab34cd56ef
Create Date: 2026-08-31 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '12ab34cd56ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=True),
        sa.Column('category', sa.String(length=24), nullable=False),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('ip', sa.String(length=64), nullable=True),
        sa.Column('user_agent', sa.String(length=255), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_events_user_id', 'audit_events', ['user_id'])
    op.create_index('ix_audit_events_category', 'audit_events', ['category'])
    op.create_index('ix_audit_events_created_at', 'audit_events', ['created_at'])

    op.create_table(
        'consent_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('kind', sa.String(length=24), nullable=False),
        sa.Column('granted', sa.Boolean(), nullable=False),
        sa.Column('source', sa.String(length=24), nullable=False, server_default='settings'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_consent_events_user_id', 'consent_events', ['user_id'])
    op.create_index('ix_consent_events_kind', 'consent_events', ['kind'])
    op.create_index('ix_consent_events_created_at', 'consent_events', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_consent_events_created_at', table_name='consent_events')
    op.drop_index('ix_consent_events_kind', table_name='consent_events')
    op.drop_index('ix_consent_events_user_id', table_name='consent_events')
    op.drop_table('consent_events')
    op.drop_index('ix_audit_events_created_at', table_name='audit_events')
    op.drop_index('ix_audit_events_category', table_name='audit_events')
    op.drop_index('ix_audit_events_user_id', table_name='audit_events')
    op.drop_table('audit_events')
