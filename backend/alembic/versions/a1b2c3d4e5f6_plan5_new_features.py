"""plan5 new features: instructions, notes, workspace plan + invite_code

Revision ID: a1b2c3d4e5f6
Revises: c4d5e6f70812
Create Date: 2026-07-12

Viết tay (postgres local đang bị project khác chiếm port) theo đúng pattern
autogenerate của các migration trước; schema khớp app/models.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'c4d5e6f70812'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('instructions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_instructions_workspace_id'), 'instructions', ['workspace_id'],
                    unique=False)
    op.create_table('instruction_versions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('instruction_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['instruction_id'], ['instructions.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('instruction_id', 'version', name='uq_instruction_version')
    )
    op.create_index(op.f('ix_instruction_versions_instruction_id'), 'instruction_versions',
                    ['instruction_id'], unique=False)
    op.create_index(op.f('ix_instruction_versions_workspace_id'), 'instruction_versions',
                    ['workspace_id'], unique=False)
    op.create_table('notes',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('author_id', sa.Uuid(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('tags', sa.JSON(), nullable=False),
    sa.Column('note_date', sa.Date(), nullable=False),
    sa.Column('task_id', sa.Uuid(), nullable=True),
    sa.Column('project_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notes_author_id'), 'notes', ['author_id'], unique=False)
    op.create_index(op.f('ix_notes_note_date'), 'notes', ['note_date'], unique=False)
    op.create_index(op.f('ix_notes_workspace_id'), 'notes', ['workspace_id'], unique=False)

    workspaceplan = sa.Enum('basic', 'advanced', name='workspaceplan')
    workspaceplan.create(op.get_bind(), checkfirst=True)
    op.add_column('workspaces', sa.Column('plan', workspaceplan, nullable=False,
                                          server_default='basic'))
    # Cột NOT NULL UNIQUE trên bảng có sẵn dữ liệu: thêm nullable trước, backfill
    # bằng mã ngẫu nhiên, rồi siết NOT NULL.
    op.add_column('workspaces', sa.Column('invite_code', sa.String(length=16), nullable=True))
    from alembic import context
    if not context.is_offline_mode():  # backfill cần SELECT — chỉ chạy online
        conn = op.get_bind()
        rows = conn.execute(
            sa.text("SELECT id FROM workspaces WHERE invite_code IS NULL")).fetchall()
        if rows:
            import secrets
            import string
            alphabet = string.ascii_uppercase + string.digits
            for (ws_id,) in rows:
                code = "".join(secrets.choice(alphabet) for _ in range(8))
                conn.execute(sa.text(
                    "UPDATE workspaces SET invite_code = :code WHERE id = :id"
                ), {"code": code, "id": ws_id})
    op.alter_column('workspaces', 'invite_code', nullable=False)
    op.create_index(op.f('ix_workspaces_invite_code'), 'workspaces', ['invite_code'],
                    unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_workspaces_invite_code'), table_name='workspaces')
    op.drop_column('workspaces', 'invite_code')
    op.drop_column('workspaces', 'plan')
    sa.Enum(name='workspaceplan').drop(op.get_bind(), checkfirst=True)
    op.drop_index(op.f('ix_notes_workspace_id'), table_name='notes')
    op.drop_index(op.f('ix_notes_note_date'), table_name='notes')
    op.drop_index(op.f('ix_notes_author_id'), table_name='notes')
    op.drop_table('notes')
    op.drop_index(op.f('ix_instruction_versions_workspace_id'),
                  table_name='instruction_versions')
    op.drop_index(op.f('ix_instruction_versions_instruction_id'),
                  table_name='instruction_versions')
    op.drop_table('instruction_versions')
    op.drop_index(op.f('ix_instructions_workspace_id'), table_name='instructions')
    op.drop_table('instructions')
