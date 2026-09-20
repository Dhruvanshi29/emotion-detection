"""add facial_analysis

Revision ID: c04a7f19d8b2
Revises: b91d5e3a2f0c
Create Date: 2026-08-31 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c04a7f19d8b2'
down_revision: Union[str, None] = 'b91d5e3a2f0c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'facial_analysis',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('source_ref_id', sa.String(length=36), nullable=True),
        sa.Column('sample_count', sa.Integer(), nullable=False),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('faces_detected_ratio', sa.Float(), nullable=True),
        sa.Column('dominant_emotion', sa.String(length=24), nullable=False),
        sa.Column('sentiment', sa.String(length=16), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('scores', sa.JSON(), nullable=True),
        sa.Column('signals', sa.JSON(), nullable=True),
        sa.Column('model_provider', sa.String(length=32), nullable=True),
        sa.Column('model_name', sa.String(length=120), nullable=True),
        sa.Column('emotion_event_id', sa.String(length=36), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('facial_analysis', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_facial_analysis_user_id'), ['user_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_facial_analysis_source_ref_id'),
            ['source_ref_id'],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('facial_analysis', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_facial_analysis_source_ref_id'))
        batch_op.drop_index(batch_op.f('ix_facial_analysis_user_id'))
    op.drop_table('facial_analysis')
