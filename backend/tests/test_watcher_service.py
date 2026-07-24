"""Watcher — morning brief 07:00 giờ VN (spec AI upgrade §10.2).

Cron chạy mỗi phút (giống check_report_schedules/check_task_deadlines) nhưng
hàm service tự guard: chỉ thực sự gửi brief đúng phút 07:00 VN, và dedup theo
NGÀY qua Notification đã có sẵn (type="morning_brief") — không thêm cột/bảng
mới cho việc này.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.models import Notification, Role, User, UserStatus, Workspace
from app.services import watcher_service

# 00:00 UTC = 07:00 VN (UTC+7)
SEVEN_AM_VN = datetime(2026, 7, 25, 0, 0, tzinfo=timezone.utc)


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    manager = User(workspace_id=ws.id, email="m@a.vn", password_hash="x", full_name="M",
                   role=Role.manager)
    locked_ceo = User(workspace_id=ws.id, email="c2@a.vn", password_hash="x", full_name="C2",
                      role=Role.ceo, status=UserStatus.locked)
    db.add_all([ceo, manager, locked_ceo])
    await db.flush()
    await db.commit()
    return ws, ceo, manager, locked_ceo


def _llm():
    return FakeLLMClient(turns=[[
        TextDelta(text="Hôm nay ổn, không có gì đáng lo."),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])


@pytest.mark.asyncio
async def test_sends_brief_only_at_seven_am_vn(db_session):
    ws, ceo, manager, locked_ceo = await _world(db_session)
    llm = _llm()

    not_seven = SEVEN_AM_VN.replace(hour=1)  # 08:00 VN, không phải 07:00
    count = await watcher_service.send_morning_briefs(db_session, llm, now=not_seven)

    assert count == 0
    assert (await db_session.execute(select(Notification))).scalars().all() == []


@pytest.mark.asyncio
async def test_sends_brief_to_active_ceo_only(db_session):
    ws, ceo, manager, locked_ceo = await _world(db_session)
    llm = _llm()

    count = await watcher_service.send_morning_briefs(db_session, llm, now=SEVEN_AM_VN)

    assert count == 1
    notifs = (await db_session.execute(select(Notification))).scalars().all()
    assert len(notifs) == 1
    assert notifs[0].recipient_id == ceo.id
    assert notifs[0].type == "morning_brief"
    assert notifs[0].payload["summary"] == "Hôm nay ổn, không có gì đáng lo."


@pytest.mark.asyncio
async def test_does_not_send_twice_same_day(db_session):
    ws, ceo, manager, locked_ceo = await _world(db_session)

    first = await watcher_service.send_morning_briefs(db_session, _llm(), now=SEVEN_AM_VN)
    assert first == 1

    second = await watcher_service.send_morning_briefs(db_session, _llm(), now=SEVEN_AM_VN)
    assert second == 0
    assert len((await db_session.execute(select(Notification))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_sends_again_next_day(db_session):
    ws, ceo, manager, locked_ceo = await _world(db_session)
    await watcher_service.send_morning_briefs(db_session, _llm(), now=SEVEN_AM_VN)

    next_day = SEVEN_AM_VN + timedelta(days=1)
    count = await watcher_service.send_morning_briefs(db_session, _llm(), now=next_day)

    assert count == 1
    assert len((await db_session.execute(select(Notification))).scalars().all()) == 2


@pytest.mark.asyncio
async def test_one_ceo_failure_does_not_block_others(db_session, monkeypatch):
    ws, ceo, manager, locked_ceo = await _world(db_session)
    ceo2 = User(workspace_id=ws.id, email="c3@a.vn", password_hash="x", full_name="C3",
               role=Role.ceo)
    db_session.add(ceo2)
    await db_session.commit()

    from app.services import dashboard_service

    calls = {"n": 0}
    real = dashboard_service.today_dashboard

    async def flaky(db, actor, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return await real(db, actor, **kwargs)
    monkeypatch.setattr(dashboard_service, "today_dashboard", flaky)

    count = await watcher_service.send_morning_briefs(db_session, _llm(), now=SEVEN_AM_VN)

    assert count == 1  # 1 trong 2 CEO vẫn nhận được brief dù CEO kia lỗi
