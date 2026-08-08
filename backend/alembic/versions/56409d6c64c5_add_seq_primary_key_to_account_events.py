"""add seq (Integer autoincrement) as new PK for account_events

Bug thật (cùng họ với ec3f35a015f9 — Message/TaskUpdate/TaskComment.seq, xem
docs/superpowers/plans/2026-08-08-stable-message-ordering.md): audit_service.
list_audit_events sort AccountEvent CHỈ theo created_at.desc(), KHÔNG có
tie-break — khi 2 event ghi gần như đồng thời (created_at trùng, vd
offboard_user ghi "Nghỉ việc" rồi "Khóa tài khoản" liên tiếp), thứ tự trả về
phụ thuộc thứ tự vật lý bất định của DB, có thể đảo ngược (bắt qua
test_offboard_shows_two_ordered_entries_in_timeline flaky khi chạy chung full
suite). Đổi PK từ id (UUID) sang seq (Integer, tự tăng thật) — SQLite CHỈ tự
sinh giá trị autoincrement khi cột đó CHÍNH LÀ primary key kiểu INTEGER.

Revision ID: 56409d6c64c5
Revises: 82ed9ec654f0
Create Date: 2026-08-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '56409d6c64c5'
down_revision: Union[str, Sequence[str], None] = '82ed9ec654f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "account_events"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(_TABLE, sa.Column('seq', sa.Integer(), nullable=True))
    op.execute(f"""
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY created_at, id) AS rn
            FROM {_TABLE}
        )
        UPDATE {_TABLE} SET seq = ranked.rn
        FROM ranked WHERE {_TABLE}.id = ranked.id
    """)
    op.drop_constraint(f'{_TABLE}_pkey', _TABLE, type_='primary')
    op.alter_column(_TABLE, 'seq', nullable=False)
    op.create_primary_key(f'{_TABLE}_pkey', _TABLE, ['seq'])
    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {_TABLE}_seq_seq OWNED BY {_TABLE}.seq")
    op.execute(f"""
        SELECT setval('{_TABLE}_seq_seq',
                      COALESCE((SELECT MAX(seq) FROM {_TABLE}), 0) + 1, false)
    """)
    op.execute(f"ALTER TABLE {_TABLE} ALTER COLUMN seq SET DEFAULT nextval('{_TABLE}_seq_seq')")
    op.create_index(op.f(f'ix_{_TABLE}_id'), _TABLE, ['id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f(f'ix_{_TABLE}_id'), table_name=_TABLE)
    op.execute(f"ALTER TABLE {_TABLE} ALTER COLUMN seq DROP DEFAULT")
    op.execute(f"DROP SEQUENCE IF EXISTS {_TABLE}_seq_seq")
    op.drop_constraint(f'{_TABLE}_pkey', _TABLE, type_='primary')
    op.create_primary_key(f'{_TABLE}_pkey', _TABLE, ['id'])
    op.drop_column(_TABLE, 'seq')
