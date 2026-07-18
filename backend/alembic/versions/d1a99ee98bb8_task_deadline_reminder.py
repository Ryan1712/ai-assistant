"""task_deadline_reminder

Revision ID: d1a99ee98bb8
Revises: 44a39820700f
Create Date: 2026-07-18 17:29:16.570060

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1a99ee98bb8'
down_revision: Union[str, Sequence[str], None] = '44a39820700f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("tasks", sa.Column("deadline_reminder_sent_at",
                                     sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("tasks", "deadline_reminder_sent_at")
