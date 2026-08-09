"""convert project status to enum

Revision ID: 6b7e1058ae67
Revises: 56409d6c64c5
Create Date: 2026-08-09 00:12:45.443456

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b7e1058ae67'
down_revision: Union[str, Sequence[str], None] = '56409d6c64c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


project_status_enum = sa.Enum(
    'active', 'on_hold', 'completed', 'archived', name='projectstatus',
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    project_status_enum.create(bind, checkfirst=True)
    # Data-fix an toàn: giá trị nào KHÔNG khớp 4 giá trị enum mới (typo/rác
    # dữ liệu cũ) được đưa về 'active' trước khi cast, tránh migration fail
    # giữa chừng. Đã kiểm tra Postgres dev (2026-08-09): chỉ có 'active',
    # không có giá trị lạ -- bước này để an toàn cho môi trường khác (vd
    # staging/prod) có thể có dữ liệu khác.
    op.execute(
        "UPDATE projects SET status = 'active' "
        "WHERE status NOT IN ('active', 'on_hold', 'completed', 'archived')"
    )
    op.alter_column(
        'projects', 'status',
        existing_type=sa.VARCHAR(length=32),
        type_=project_status_enum,
        existing_nullable=False,
        postgresql_using='status::projectstatus',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'projects', 'status',
        existing_type=project_status_enum,
        type_=sa.VARCHAR(length=32),
        existing_nullable=False,
        postgresql_using='status::varchar',
    )
    project_status_enum.drop(op.get_bind(), checkfirst=True)
