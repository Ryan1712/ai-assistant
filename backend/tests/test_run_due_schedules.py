import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Notification, Project, Report, Role, User, Workspace, WorkspacePlan
from app.services import report_schedule_service as svc

NOW = datetime(2026, 7, 13, 8, 0, tzinfo=timezone.utc)

_seq = iter(range(2000))


async def _setup(db):
    n = next(_seq)
    ws = Workspace(name=f"W{n}", plan=WorkspacePlan.advanced)
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email=f"c{n}@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    await db.commit()
    return ws, ceo


@pytest.mark.asyncio
async def test_due_schedule_generates_report_and_notifies(db_session, storage_dir):
    ws, ceo = await _setup(db_session)
    sched = await svc.create_schedule(db_session, ceo, weekday=None, hour=8, minute=0)
    sched.next_run_at = NOW - timedelta(minutes=1)  # ép tới hạn
    await db_session.commit()

    results = await svc.run_due_schedules(db_session, now=NOW)

    assert len(results) == 1
    assert results[0]["schedule_id"] == str(sched.id)
    report = await db_session.get(Report, uuid.UUID(results[0]["report_id"]))
    assert report is not None and report.workspace_id == ws.id

    notifs = (await db_session.execute(select(Notification).where(
        Notification.recipient_id == ceo.id))).scalars().all()
    assert len(notifs) == 1
    assert notifs[0].type == "scheduled_report"
    assert notifs[0].payload["report_id"] == results[0]["report_id"]

    await db_session.refresh(sched)
    # SQLite không giữ tzinfo khi đọc lại — so sánh naive.
    assert sched.last_run_at == NOW.replace(tzinfo=None)
    # NOW = 08:00 UTC = 15:00 VN (thứ Hai) → 8h VN đã qua trong ngày → 8h VN ngày mai
    # = 01:00 UTC ngày mai (NOW + 17h, vì lệch UTC-7 cộng thêm 1 ngày).
    assert sched.next_run_at == (NOW + timedelta(hours=17)).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_future_schedule_does_not_run(db_session, storage_dir):
    ws, ceo = await _setup(db_session)
    sched = await svc.create_schedule(db_session, ceo, weekday=None, hour=8, minute=0)
    sched.next_run_at = NOW + timedelta(hours=1)
    await db_session.commit()

    results = await svc.run_due_schedules(db_session, now=NOW)

    assert results == []
    count = (await db_session.execute(select(Report))).scalars().all()
    assert count == []


@pytest.mark.asyncio
async def test_inactive_schedule_does_not_run_even_if_due(db_session, storage_dir):
    ws, ceo = await _setup(db_session)
    sched = await svc.create_schedule(db_session, ceo, weekday=None, hour=8, minute=0)
    sched.next_run_at = NOW - timedelta(minutes=1)
    sched.active = False
    await db_session.commit()

    results = await svc.run_due_schedules(db_session, now=NOW)

    assert results == []


@pytest.mark.asyncio
async def test_mot_lich_hong_khong_chan_lich_khac(db_session, storage_dir):
    # schedule1: creator bị hạ role xuống employee sau khi tạo lịch (require_ceo sẽ 403)
    ws1, ceo1 = await _setup(db_session)
    sched1 = await svc.create_schedule(db_session, ceo1, weekday=None, hour=8)
    sched1.next_run_at = NOW - timedelta(minutes=1)
    ceo1.role = Role.employee
    await db_session.commit()

    # schedule2: creator vẫn là CEO (workspace khác, độc lập)
    ws2, ceo2 = await _setup(db_session)
    sched2 = await svc.create_schedule(db_session, ceo2, weekday=None, hour=8)
    sched2.next_run_at = NOW - timedelta(minutes=1)
    await db_session.commit()

    results = await svc.run_due_schedules(db_session, now=NOW)

    # Không raise; schedule2 vẫn ra báo cáo
    assert len(results) == 1
    assert results[0]["schedule_id"] == str(sched2.id)

    # schedule1 vẫn được advance next_run_at để không retry mỗi phút mãi mãi
    await db_session.refresh(sched1)
    assert sched1.next_run_at > NOW.replace(tzinfo=None)
    assert sched1.last_run_at == NOW.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_commit_advance_fail_mot_lan_khong_chan_ca_tick(db_session, storage_dir, monkeypatch):
    """Commit cuối (advance next_run_at, flush luôn Notification pending từ notify())
    fail 1 lần vì lý do không liên quan (vd lỗi DB tạm thời) — không được lan ra ngoài
    vòng lặp: schedule đang lỗi phải tự retry-commit riêng field advance, và schedule
    tới sau nó trong cùng tick vẫn phải chạy bình thường."""
    ws1, ceo1 = await _setup(db_session)
    sched1 = await svc.create_schedule(db_session, ceo1, weekday=None, hour=8)
    sched1.next_run_at = NOW - timedelta(minutes=1)
    await db_session.commit()

    ws2, ceo2 = await _setup(db_session)
    sched2 = await svc.create_schedule(db_session, ceo2, weekday=None, hour=8)
    sched2.next_run_at = NOW - timedelta(minutes=1)
    await db_session.commit()

    real_commit = db_session.commit
    real_notify = svc.notify
    state = {"arm_next_commit": False, "already_failed": False}

    async def flaky_commit():
        if state["arm_next_commit"] and not state["already_failed"]:
            state["arm_next_commit"] = False
            state["already_failed"] = True
            raise RuntimeError("simulated transient commit failure")
        await real_commit()

    async def notify_then_arm(*args, **kwargs):
        # notify() chỉ db.add(Notification), không tự commit — commit KẾ TIẾP sau
        # notify() chính là bước advance+commit cuối vòng lặp mà ta muốn fail thử.
        out = await real_notify(*args, **kwargs)
        state["arm_next_commit"] = True
        return out

    monkeypatch.setattr(db_session, "commit", flaky_commit)
    monkeypatch.setattr(svc, "notify", notify_then_arm)

    results = await svc.run_due_schedules(db_session, now=NOW)

    assert state["already_failed"] is True  # xác nhận kịch bản lỗi thực sự xảy ra
    # Không raise; cả 2 schedule đều ra báo cáo dù 1 lần commit advance bị lỗi giữa chừng
    assert {r["schedule_id"] for r in results} == {str(sched1.id), str(sched2.id)}

    # next_run_at của CẢ HAI đều được advance — kể cả schedule bị fail-commit-rồi-retry
    await db_session.refresh(sched1)
    await db_session.refresh(sched2)
    assert sched1.next_run_at > NOW.replace(tzinfo=None)
    assert sched2.next_run_at > NOW.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_two_due_schedules_in_different_workspaces_both_run(db_session, storage_dir):
    ws1, ceo1 = await _setup(db_session)
    ws2, ceo2 = await _setup(db_session)
    s1 = await svc.create_schedule(db_session, ceo1, weekday=None, hour=8)
    s2 = await svc.create_schedule(db_session, ceo2, weekday=None, hour=8)
    s1.next_run_at = NOW - timedelta(minutes=1)
    s2.next_run_at = NOW - timedelta(minutes=1)
    await db_session.commit()

    results = await svc.run_due_schedules(db_session, now=NOW)

    assert {r["schedule_id"] for r in results} == {str(s1.id), str(s2.id)}
    reports = {r.workspace_id for r in
              (await db_session.execute(select(Report))).scalars().all()}
    assert reports == {ws1.id, ws2.id}
