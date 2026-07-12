"""plan7: devices.push_token, email_messages, voice_notes

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-07-12

Viết tay theo pattern các migration trước; schema khớp app/models.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('devices', sa.Column('push_token', sa.String(length=128), nullable=True))
    op.create_table('email_messages',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('sender_id', sa.Uuid(), nullable=False),
    sa.Column('recipient_id', sa.Uuid(), nullable=False),
    sa.Column('subject', sa.String(length=255), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['recipient_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['sender_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_email_messages_recipient_id'), 'email_messages',
                    ['recipient_id'], unique=False)
    op.create_index(op.f('ix_email_messages_sender_id'), 'email_messages',
                    ['sender_id'], unique=False)
    op.create_index(op.f('ix_email_messages_workspace_id'), 'email_messages',
                    ['workspace_id'], unique=False)
    op.create_table('voice_notes',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('author_id', sa.Uuid(), nullable=False),
    sa.Column('file_path', sa.String(length=512), nullable=False),
    sa.Column('transcript', sa.Text(), nullable=False),
    sa.Column('language', sa.String(length=16), nullable=False),
    sa.Column('tags', sa.JSON(), nullable=False),
    sa.Column('task_id', sa.Uuid(), nullable=True),
    sa.Column('project_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_voice_notes_author_id'), 'voice_notes', ['author_id'],
                    unique=False)
    op.create_index(op.f('ix_voice_notes_workspace_id'), 'voice_notes', ['workspace_id'],
                    unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_voice_notes_workspace_id'), table_name='voice_notes')
    op.drop_index(op.f('ix_voice_notes_author_id'), table_name='voice_notes')
    op.drop_table('voice_notes')
    op.drop_index(op.f('ix_email_messages_workspace_id'), table_name='email_messages')
    op.drop_index(op.f('ix_email_messages_sender_id'), table_name='email_messages')
    op.drop_index(op.f('ix_email_messages_recipient_id'), table_name='email_messages')
    op.drop_table('email_messages')
    op.drop_column('devices', 'push_token')
