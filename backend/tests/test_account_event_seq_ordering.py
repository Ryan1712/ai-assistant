"""Bug thật (cùng họ với fix seq của Message/TaskUpdate/TaskComment,
docs/superpowers/plans/2026-08-08-stable-message-ordering.md): audit_service.
list_audit_events sort AccountEvent CHỈ theo created_at.desc(), KHÔNG có
tie-break — khi 2 event ghi gần như đồng thời (created_at trùng, ví dụ
offboard_user ghi "Nghỉ việc" rồi "Khóa tài khoản" liên tiếp), thứ tự trả về
phụ thuộc thứ tự vật lý bất định của DB, có thể đảo ngược. Tái hiện bằng
test_offboard_shows_two_ordered_entries_in_timeline (test_audit_service.py)
— PASS khi chạy riêng, FAIL khi chạy chung full suite (timing khác)."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import AccountEvent


@pytest.mark.asyncio
async def test_account_event_seq_auto_increments_even_with_same_created_at(db_session):
    ws, target, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    same_ts = datetime.now(timezone.utc)
    e1 = AccountEvent(workspace_id=ws, target_user_id=target, actor_id=actor,
                      event_type="offboard", detail="Nghỉ việc", created_at=same_ts)
    db_session.add(e1)
    await db_session.flush()
    e2 = AccountEvent(workspace_id=ws, target_user_id=target, actor_id=actor,
                      event_type="lock", detail="Khóa tài khoản", created_at=same_ts)
    db_session.add(e2)
    await db_session.commit()

    rows = (await db_session.execute(
        select(AccountEvent).where(AccountEvent.workspace_id == ws)
        .order_by(AccountEvent.created_at.desc(), AccountEvent.seq.desc())
    )).scalars().all()
    # desc + tie-break seq.desc() -> event GHI SAU cùng ("Khóa tài khoản") lên trước,
    # đúng thứ tự thời gian thực (mới nhất trước) mà audit_service kỳ vọng.
    assert [r.detail for r in rows] == ["Khóa tài khoản", "Nghỉ việc"]
