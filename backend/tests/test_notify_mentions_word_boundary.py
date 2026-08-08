"""Finding #14 (audit 2026-07-26, re-verify 2026-08-08, LOW): _notify_mentions
dùng substring check (f"@{full_name.lower()}" in content_lower) không có
word-boundary -- "@Anh Tuấn" chứa "@Anh" nên notify NHẦM cả user "Anh"
(không được nhắc) lẫn "Anh Tuấn" (đúng)."""
import pytest
from sqlalchemy import select

from app.models import Notification, Project, Role, Task, User, Workspace
from app.services import work_service


@pytest.mark.asyncio
async def test_notify_mentions_khong_khop_nham_prefix(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    anh = User(workspace_id=ws.id, email="anh@a.vn", password_hash="x", full_name="Anh",
              role=Role.employee)
    anh_tuan = User(workspace_id=ws.id, email="at@a.vn", password_hash="x",
                    full_name="Anh Tuấn", role=Role.employee)
    db_session.add_all([ceo, anh, anh_tuan])
    await db_session.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="T", created_by=ceo.id)
    db_session.add(task)
    await db_session.commit()

    await work_service._notify_mentions(
        db_session, ceo, task, "@Anh Tuấn ơi check task này")
    await db_session.commit()

    notifs = (await db_session.execute(select(Notification).where(
        Notification.type == "mentioned"))).scalars().all()
    notified_ids = {n.recipient_id for n in notifs}
    # Chỉ Anh Tuấn được notify, KHÔNG phải "Anh"
    assert anh.id not in notified_ids
    assert anh_tuan.id in notified_ids
