"""Finding #13 (audit 2026-07-26, re-verify 2026-08-08, LOW): run_due_schedules
không re-check plan_allows(ws, "scheduled_reports") mỗi lần chạy -- workspace
hạ gói sau khi đã tạo lịch vẫn tiếp tục nhận report+notify vô thời hạn."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import (
    Notification, ReportSchedule, Role, User, Workspace, WorkspacePlan,
)
from app.services import report_schedule_service


@pytest.mark.asyncio
async def test_run_due_schedules_tat_lich_khi_workspace_ha_goi(db_session):
    # Workspace TẠO lịch lúc còn gói Advanced, SAU ĐÓ hạ xuống Basic (không còn
    # được phép scheduled_reports) -- lịch cũ vẫn active=True, next_run_at đã tới hạn.
    ws = Workspace(name="A", plan=WorkspacePlan.basic)
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    sched = ReportSchedule(workspace_id=ws.id, created_by=ceo.id, recipient_id=ceo.id,
                           weekday=None, hour=8, minute=0, active=True,
                           next_run_at=now - timedelta(minutes=1))
    db_session.add(sched)
    await db_session.commit()

    results = await report_schedule_service.run_due_schedules(db_session, now=now)

    assert results == []  # không có report nào được tạo
    await db_session.refresh(sched)
    assert sched.active is False  # tự tắt lịch vì workspace không còn đủ gói
    notifs = (await db_session.execute(select(Notification))).scalars().all()
    assert notifs == []
