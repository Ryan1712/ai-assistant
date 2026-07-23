"""invite_user_id_and_pending_status

Revision ID: 7da498fa7411
Revises: de06a77534d4
Create Date: 2026-07-22 23:01:37.085050

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7da498fa7411'
down_revision: Union[str, Sequence[str], None] = 'de06a77534d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Them gia tri enum moi truoc (khong tu dong sinh boi autogenerate - Postgres
    # native ENUM can ALTER TYPE rieng). An toan chay trong transaction vi migration
    # nay khong dung gia tri 'pending' ngay trong cung transaction.
    op.execute("ALTER TYPE userstatus ADD VALUE IF NOT EXISTS 'pending'")
    op.add_column('invites', sa.Column('user_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(None, 'invites', 'users', ['user_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres khong ho tro DROP VALUE cho enum - bo qua o downgrade (chi xoa cot/FK).
    op.drop_constraint(None, 'invites', type_='foreignkey')
    op.drop_column('invites', 'user_id')
