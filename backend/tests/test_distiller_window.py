"""Finding #9 (audit 2026-07-26, re-verify 2026-08-08, HIGH): distiller_service
tính day_start = now_vn.replace(hour=0,...) TẠI THỜI ĐIỂM CRON CHẠY (02:00 VN)
-- tức 00:00 SÁNG NAY, không phải hôm qua. Query created_at >= day_start_utc
chỉ quét TaskUpdate tạo trong khung 00:00-02:00 sáng (2 tiếng), bỏ hoàn toàn
cả ngày làm việc hôm trước -- "bộ nhớ dài hạn" gần như no-op âm thầm."""
from datetime import datetime, timezone

import pytest

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.models import Project, Role, Task, TaskUpdate, User, Workspace
from app.services import distiller_service


def _llm(reply: str):
    return FakeLLMClient(turns=[[
        TextDelta(text=reply),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])


@pytest.mark.asyncio
async def test_distiller_quet_dung_ca_ngay_hom_qua(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="T", created_by=ceo.id)
    db_session.add(task)
    await db_session.flush()

    # now_vn giả lập 02:00 VN hôm nay (UTC+7 -> 19:00 UTC hôm qua)
    now_utc = datetime(2026, 8, 9, 19, 0, 0, tzinfo=timezone.utc)  # = 02:00 2026-08-10 VN
    # Update tạo lúc 10:00 VN HÔM QUA (giờ hành chính) -- PHẢI được quét
    update_hom_qua = TaskUpdate(workspace_id=ws.id, task_id=task.id, author_id=ceo.id,
                                content="cap nhat hom qua",
                                created_at=datetime(2026, 8, 9, 3, 0, 0, tzinfo=timezone.utc))
    db_session.add(update_hom_qua)
    await db_session.commit()

    llm = _llm("Cap nhat hom qua da duoc ghi nhan.")
    count = await distiller_service.distill_workspace_memories(db_session, llm, now=now_utc)

    # Nếu day_start bị tính sai (= hôm nay 00:00 tại thời điểm chạy 02:00), update
    # tạo lúc 10:00 VN hôm qua sẽ bị bỏ hoàn toàn -> không có TaskUpdate nào lọt
    # vào cửa sổ quét -> _extract_facts không được gọi -> count == 0.
    assert count == 1
    assert llm.calls  # LLM phải được gọi vì có update hôm qua trong cửa sổ
