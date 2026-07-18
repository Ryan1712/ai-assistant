"""voice note: title + duration + transcript_status

Revision ID: f0a1b2c3d4e5
Revises: d1a99ee98bb8
Create Date: 2026-07-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f0a1b2c3d4e5'
down_revision: Union[str, Sequence[str], None] = 'd1a99ee98bb8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('voice_notes', sa.Column('title', sa.String(255), nullable=True))
    op.add_column('voice_notes', sa.Column('duration_seconds', sa.Float(), nullable=True))
    op.add_column('voice_notes', sa.Column('transcript_status', sa.String(16),
                                           nullable=False, server_default='pending'))


def downgrade() -> None:
    op.drop_column('voice_notes', 'transcript_status')
    op.drop_column('voice_notes', 'duration_seconds')
    op.drop_column('voice_notes', 'title')
