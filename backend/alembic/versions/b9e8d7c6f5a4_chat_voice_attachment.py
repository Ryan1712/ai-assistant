"""chat: dinh kem voice note lam input"""
import sqlalchemy as sa
from alembic import op

revision = "b9e8d7c6f5a4"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_requests", sa.Column(
        "voice_note_id", sa.Uuid(), sa.ForeignKey("voice_notes.id", ondelete="SET NULL"),
        nullable=True))
    op.add_column("messages", sa.Column(
        "voice_note_id", sa.Uuid(), sa.ForeignKey("voice_notes.id", ondelete="SET NULL"),
        nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "voice_note_id")
    op.drop_column("chat_requests", "voice_note_id")
