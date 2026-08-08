"""Finding #10 (audit 2026-07-26, re-verify 2026-08-08, MED): guard 'đúng
phút' (hour==7 and minute==0) không catch-up nếu tick bị trễ (worker bận,
restart) -- rớt cả ngày. dedup theo Notification cùng ngày đã có sẵn nên
nới cửa sổ guard không gây double-send."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.models import Notification, Role, User, Workspace
from app.services import watcher_service


def _llm():
    return FakeLLMClient(turns=[[
        TextDelta(text="Hôm nay ổn, không có gì đáng lo."),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])


@pytest.mark.asyncio
async def test_watcher_chay_duoc_khi_tick_tre_vai_phut(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.commit()

    # now_vn = 07:05 (trễ 5 phút so với mốc 07:00) -- PHẢI vẫn chạy được
    # thay vì bị guard chặn hoàn toàn tới 07:00 hôm sau.
    now_utc = datetime(2026, 8, 10, 0, 5, 0, tzinfo=timezone.utc)  # 07:05 VN
    count = await watcher_service.send_morning_briefs(db_session, _llm(), now=now_utc)

    assert count == 1  # không bị early-return vì guard quá chặt
    notifs = (await db_session.execute(select(Notification))).scalars().all()
    assert len(notifs) == 1
    assert notifs[0].recipient_id == ceo.id
