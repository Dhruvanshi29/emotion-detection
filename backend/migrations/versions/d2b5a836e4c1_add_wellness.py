"""add wellness_exercises, exercise_sessions, user_goals

Revision ID: d2b5a836e4c1
Revises: c04a7f19d8b2
Create Date: 2026-08-31 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2b5a836e4c1'
down_revision: Union[str, None] = 'c04a7f19d8b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'wellness_exercises',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('slug', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('summary', sa.String(length=400), nullable=False),
        sa.Column('category', sa.String(length=24), nullable=False),
        sa.Column('duration_seconds', sa.Integer(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('target_emotions', sa.JSON(), nullable=True),
        sa.Column('target_goals', sa.JSON(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )
    with op.batch_alter_table('wellness_exercises', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_wellness_exercises_slug'), ['slug'], unique=True
        )

    op.create_table(
        'exercise_sessions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('exercise_id', sa.String(length=36), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['exercise_id'], ['wellness_exercises.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('exercise_sessions', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_exercise_sessions_user_id'), ['user_id'], unique=False
        )

    op.create_table(
        'user_goals',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('priority', sa.Float(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'kind', name='uq_user_goal'),
    )
    with op.batch_alter_table('user_goals', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_user_goals_user_id'), ['user_id'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('user_goals', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_goals_user_id'))
    op.drop_table('user_goals')

    with op.batch_alter_table('exercise_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_exercise_sessions_user_id'))
    op.drop_table('exercise_sessions')

    with op.batch_alter_table('wellness_exercises', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wellness_exercises_slug'))
    op.drop_table('wellness_exercises')
