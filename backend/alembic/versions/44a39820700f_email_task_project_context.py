"""email_task_project_context

Revision ID: 44a39820700f
Revises: 3ad3354b9ef2
Create Date: 2026-07-18 16:55:21.074455

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '44a39820700f'
down_revision: Union[str, Sequence[str], None] = '3ad3354b9ef2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("email_messages", sa.Column("task_id", sa.Uuid(), nullable=True))
    op.add_column("email_messages", sa.Column("project_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_email_messages_task_id", "email_messages", "tasks",
                          ["task_id"], ["id"])
    op.create_foreign_key("fk_email_messages_project_id", "email_messages", "projects",
                          ["project_id"], ["id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_email_messages_project_id", "email_messages", type_="foreignkey")
    op.drop_constraint("fk_email_messages_task_id", "email_messages", type_="foreignkey")
    op.drop_column("email_messages", "project_id")
    op.drop_column("email_messages", "task_id")
