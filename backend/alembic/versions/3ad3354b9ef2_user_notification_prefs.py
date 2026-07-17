"""user_notification_prefs

Revision ID: 3ad3354b9ef2
Revises: e4af3e9bd478
Create Date: 2026-07-17 16:41:26.444297

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ad3354b9ef2'
down_revision: Union[str, Sequence[str], None] = 'e4af3e9bd478'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("notification_prefs", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "notification_prefs")
