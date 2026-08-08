"""add seq (Integer autoincrement) as new PK for messages/task_updates/task_comments

Doi Primary Key cua 3 bang tu id (UUID) sang seq (Integer, tu tang) -- ly do:
SQLite (dung o test qua Base.metadata.create_all) CHI tu sinh gia tri cho cot
autoincrement khi cot do CHINH LA primary key kieu INTEGER (rowid-alias) --
da xac nhan qua thu nghiem doc lap rang Sequence/Identity/autoincrement tren
cot KHONG PHAI PK deu khong tu sinh gia tri tren SQLite. seq dung lam
tie-break doc lai on dinh thay the id (UUID ngau nhien) trong order_by, tranh
dao lon thu tu message/task_update/task_comment khi created_at trung nhau
(xem docs/superpowers/plans/2026-08-08-stable-message-ordering.md).

id (UUID) VAN la "business key" dung o moi noi trong code/API nhu truoc gio,
chi doi tu PRIMARY KEY sang UNIQUE index -- da grep xac nhan KHONG co FK nao
tham chieu id cua 3 bang nay nen an toan.

Revision ID: ec3f35a015f9
Revises: e84a1d8ad95e
Create Date: 2026-08-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ec3f35a015f9'
down_revision: Union[str, Sequence[str], None] = 'e84a1d8ad95e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLES = ["messages", "task_updates", "task_comments"]


def upgrade() -> None:
    """Upgrade schema."""
    for table in _TABLES:
        # 1. Them cot seq cho phep NULL truoc (bang da co du lieu, chua co
        #    gia tri cho cac dong hien co).
        op.add_column(table, sa.Column('seq', sa.Integer(), nullable=True))

        # 2. Backfill seq theo dung thu tu (created_at, id) hien tai --
        #    best-effort, KHONG khoi phuc duoc thu tu that da mat cho cac
        #    dong created_at trung nhau trong qua khu, nhung cho 1 thu tu ON
        #    DINH tu nay tro di (khong con doi ngau nhien giua cac lan query
        #    nhu id UUID lam tie-break truoc day).
        op.execute(f"""
            WITH ranked AS (
                SELECT id, ROW_NUMBER() OVER (ORDER BY created_at, id) AS rn
                FROM {table}
            )
            UPDATE {table} SET seq = ranked.rn
            FROM ranked WHERE {table}.id = ranked.id
        """)

        # 3. Drop PRIMARY KEY constraint cu tren id (id van UNIQUE, chi khong
        #    con la PK) -- KHONG co FK nao tham chieu id cua bang nay (da
        #    grep xac nhan truoc khi viet migration nay) nen an toan.
        op.drop_constraint(f'{table}_pkey', table, type_='primary')

        # 4. Dat seq lam PRIMARY KEY moi (tu dong tao sequence/identity that
        #    cua Postgres, tu sinh gia tri cho INSERT tu nay tro di).
        op.alter_column(table, 'seq', nullable=False)
        op.create_primary_key(f'{table}_pkey', table, ['seq'])
        op.execute(f"""
            CREATE SEQUENCE IF NOT EXISTS {table}_seq_seq OWNED BY {table}.seq
        """)
        op.execute(f"""
            SELECT setval('{table}_seq_seq',
                          COALESCE((SELECT MAX(seq) FROM {table}), 0) + 1, false)
        """)
        op.execute(f"""
            ALTER TABLE {table} ALTER COLUMN seq SET DEFAULT nextval('{table}_seq_seq')
        """)

        # 5. id: them UNIQUE index thay cho PK constraint vua mat (khop
        #    unique=True, index=True trong model).
        op.create_index(op.f(f'ix_{table}_id'), table, ['id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    for table in reversed(_TABLES):
        op.drop_index(op.f(f'ix_{table}_id'), table_name=table)
        op.execute(f"ALTER TABLE {table} ALTER COLUMN seq DROP DEFAULT")
        op.execute(f"DROP SEQUENCE IF EXISTS {table}_seq_seq")
        op.drop_constraint(f'{table}_pkey', table, type_='primary')
        op.create_primary_key(f'{table}_pkey', table, ['id'])
        op.drop_column(table, 'seq')
