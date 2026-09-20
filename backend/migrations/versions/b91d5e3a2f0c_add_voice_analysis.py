"""add voice_analysis

Revision ID: b91d5e3a2f0c
Revises: 7c2e4a91b3d5
Create Date: 2026-08-31 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b91d5e3a2f0c'
down_revision: Union[str, None] = '7c2e4a91b3d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'voice_analysis',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('source_ref_id', sa.String(length=36), nullable=True),
        sa.Column('transcript', sa.Text(), nullable=False),
        sa.Column('language', sa.String(length=16), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('energy_rms', sa.Float(), nullable=True),
        sa.Column('pause_ratio', sa.Float(), nullable=True),
        sa.Column('speech_rate_wpm', sa.Float(), nullable=True),
        sa.Column('word_count', sa.Integer(), nullable=True),
        sa.Column('features_available', sa.Boolean(), nullable=False),
        sa.Column('stt_provider', sa.String(length=32), nullable=True),
        sa.Column('stt_model', sa.String(length=120), nullable=True),
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
    with op.batch_alter_table('voice_analysis', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_voice_analysis_user_id'), ['user_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_voice_analysis_source_ref_id'),
            ['source_ref_id'],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('voice_analysis', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_voice_analysis_source_ref_id'))
        batch_op.drop_index(batch_op.f('ix_voice_analysis_user_id'))
    op.drop_table('voice_analysis')
