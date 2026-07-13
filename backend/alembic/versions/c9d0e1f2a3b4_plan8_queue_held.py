"""plan8: conversations.queue_held (tiep tuc cong viec, funtional-plan 5.7)

Revision ID: c9d0e1f2a3b4
Revises: b7c8d9e0f1a2
Create Date: 2026-07-13

Viết tay theo pattern các migration trước; schema khớp app/models.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('conversations',
                  sa.Column('queue_held', sa.Boolean(), nullable=False,
                            server_default='false'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('conversations', 'queue_held')
