"""employee_no_login

Revision ID: fd293dc8427b
Revises: 1a11430b62b9
Create Date: 2026-07-26 18:30:08.831657

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fd293dc8427b'
down_revision: Union[str, Sequence[str], None] = '1a11430b62b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nhân viên = record chỉ-tên (add_employee, không tài khoản) không còn bắt buộc
    # có email/mật khẩu. Postgres cho phép nhiều NULL trên cột unique nên không xung
    # đột giữa nhiều nhân viên không-email.
    op.alter_column('users', 'email', existing_type=sa.String(255), nullable=True)
    op.alter_column('users', 'password_hash', existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('users', 'password_hash', existing_type=sa.String(255), nullable=False)
    op.alter_column('users', 'email', existing_type=sa.String(255), nullable=False)
