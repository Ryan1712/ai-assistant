"""conversation_title_locked

Revision ID: e84a1d8ad95e
Revises: fd293dc8427b
Create Date: 2026-07-27 16:18:42.072430

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e84a1d8ad95e'
down_revision: Union[str, Sequence[str], None] = 'fd293dc8427b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('conversations',
                  sa.Column('title_locked', sa.Boolean(), nullable=False,
                            server_default=sa.text('false')))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('conversations', 'title_locked')
