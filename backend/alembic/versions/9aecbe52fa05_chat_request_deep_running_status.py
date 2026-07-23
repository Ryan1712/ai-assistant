"""chat_request_deep_running_status

Revision ID: 9aecbe52fa05
Revises: 7da498fa7411
Create Date: 2026-07-23 20:09:57.958021

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9aecbe52fa05'
down_revision: Union[str, Sequence[str], None] = '7da498fa7411'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Gia tri enum moi cho Postgres native ENUM khong tu sinh boi autogenerate -
    # can ALTER TYPE rieng (dung pattern da dung o migration 7da498fa7411).
    op.execute("ALTER TYPE chatrequeststatus ADD VALUE IF NOT EXISTS 'deep_running'")


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres khong ho tro DROP VALUE cho enum - khong co gi de downgrade.
    pass
