"""add therapist directory

Revision ID: e3f8c1204a7b
Revises: d2b5a836e4c1
Create Date: 2026-08-31 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3f8c1204a7b'
down_revision: Union[str, None] = 'd2b5a836e4c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'therapists',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('slug', sa.String(length=80), nullable=False),
        sa.Column('full_name', sa.String(length=160), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('bio', sa.Text(), nullable=False),
        sa.Column('photo_url', sa.String(length=400), nullable=True),
        sa.Column('country_code', sa.String(length=2), nullable=False),
        sa.Column('city', sa.String(length=80), nullable=True),
        sa.Column('timezone', sa.String(length=64), nullable=True),
        sa.Column('session_price_min', sa.Float(), nullable=True),
        sa.Column('session_price_max', sa.Float(), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('offers_online', sa.Boolean(), nullable=False),
        sa.Column('offers_in_person', sa.Boolean(), nullable=False),
        sa.Column('accepts_new_clients', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('contact_email', sa.String(length=255), nullable=True),
        sa.Column('website_url', sa.String(length=400), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )
    with op.batch_alter_table('therapists', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_therapists_slug'), ['slug'], unique=True)

    op.create_table(
        'therapist_specializations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('therapist_id', sa.String(length=36), nullable=False),
        sa.Column('value', sa.String(length=48), nullable=False),
        sa.ForeignKeyConstraint(['therapist_id'], ['therapists.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('therapist_id', 'value', name='uq_therapist_specialization'),
    )
    with op.batch_alter_table('therapist_specializations', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_therapist_specializations_therapist_id'),
            ['therapist_id'],
            unique=False,
        )

    op.create_table(
        'therapist_languages',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('therapist_id', sa.String(length=36), nullable=False),
        sa.Column('code', sa.String(length=8), nullable=False),
        sa.ForeignKeyConstraint(['therapist_id'], ['therapists.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('therapist_id', 'code', name='uq_therapist_language'),
    )
    with op.batch_alter_table('therapist_languages', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_therapist_languages_therapist_id'),
            ['therapist_id'],
            unique=False,
        )

    op.create_table(
        'therapist_availability',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('therapist_id', sa.String(length=36), nullable=False),
        sa.Column('weekday', sa.Integer(), nullable=False),
        sa.Column('start_minute', sa.Integer(), nullable=False),
        sa.Column('end_minute', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['therapist_id'], ['therapists.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('therapist_availability', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_therapist_availability_therapist_id'),
            ['therapist_id'],
            unique=False,
        )

    op.create_table(
        'therapist_verifications',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('therapist_id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('license_number', sa.String(length=80), nullable=True),
        sa.Column('license_authority', sa.String(length=160), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verified_by', sa.String(length=80), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['therapist_id'], ['therapists.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('therapist_verifications', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_therapist_verifications_therapist_id'),
            ['therapist_id'],
            unique=False,
        )

    op.create_table(
        'therapist_reports',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('therapist_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['therapist_id'], ['therapists.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('therapist_reports', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_therapist_reports_therapist_id'),
            ['therapist_id'],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_therapist_reports_user_id'), ['user_id'], unique=False
        )


def downgrade() -> None:
    for tbl in (
        'therapist_reports',
        'therapist_verifications',
        'therapist_availability',
        'therapist_languages',
        'therapist_specializations',
        'therapists',
    ):
        op.drop_table(tbl)
