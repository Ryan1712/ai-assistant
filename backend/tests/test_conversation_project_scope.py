"""PO #2 (2026-08-08): gắn project cho conversation đang mở, dùng làm default
project cho create_task khi user không chỉ rõ project khác. Xem
docs/superpowers/specs/2026-08-05-conversation-project-scope-design.md và
docs/superpowers/plans/2026-08-08-conversation-project-scope.md.

Hành vi ON DELETE SET NULL (project bị xóa -> conversation.project_id tự về
NULL) KHÔNG có test tự động ở đây — đã thử bật PRAGMA foreign_keys=ON cho
SQLite (engine test không enforce FK mặc định) nhưng lộ ra 32 test KHÁC trong
suite đang "ăn gian" workspace_id/user_id ngẫu nhiên (không tạo record thật),
sửa hết là việc lớn ngoài phạm vi PO #2 — đã revert. Hành vi SET NULL dựa vào
khai báo SQLAlchemy đúng cú pháp (đã xác nhận bằng migration Alembic áp lên
Postgres dev thật, xem Task 1 plan) + Postgres luôn enforce FK constraint,
không cần test riêng ở tầng model."""
import uuid

import pytest

from app.models import Conversation


async def _mk_conv(db, project_id=None):
    ws, user = uuid.uuid4(), uuid.uuid4()
    conv = Conversation(workspace_id=ws, user_id=user, project_id=project_id)
    db.add(conv)
    await db.flush()
    return conv, ws


@pytest.mark.asyncio
async def test_conversation_project_id_nullable_default_none(db_session):
    conv, _ = await _mk_conv(db_session)
    await db_session.commit()
    assert conv.project_id is None
