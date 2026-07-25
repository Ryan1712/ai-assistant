import uuid

from app.models import (
    Project, Report, Role, Task, TaskAssignee, TaskStatus, User, Workspace,
)
from app.services.onboarding_service import get_coach_flags, render_coach_block


async def _mk_ws_ceo(db):
    ws = Workspace(name="Cong ty C")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c3@a.vn", password_hash="x", full_name="C3",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    return ws, ceo


async def test_workspace_rong_het_ca_4_co_false(db_session):
    ws, ceo = await _mk_ws_ceo(db_session)
    await db_session.commit()
    flags = await get_coach_flags(db_session, ws.id)
    assert flags == {"has_projects": False, "has_tasks": False,
                     "has_members": False, "has_first_report": False}
    assert render_coach_block(flags) is not None


async def test_du_ca_4_moc_tra_none(db_session):
    ws, ceo = await _mk_ws_ceo(db_session)
    other = User(workspace_id=ws.id, email="m3@a.vn", password_hash="x", full_name="M3",
                role=Role.manager)
    db_session.add(other)
    await db_session.flush()
    proj = Project(workspace_id=ws.id, name="Du an X", created_by=ceo.id)
    db_session.add(proj)
    await db_session.flush()
    task = Task(workspace_id=ws.id, project_id=proj.id, title="Task 1",
               status=TaskStatus.todo, created_by=ceo.id)
    db_session.add(task)
    db_session.add(Report(workspace_id=ws.id, requested_by=ceo.id, file_path="x.xlsx"))
    await db_session.commit()

    flags = await get_coach_flags(db_session, ws.id)
    assert flags == {"has_projects": True, "has_tasks": True,
                     "has_members": True, "has_first_report": True}
    assert render_coach_block(flags) is None


async def test_co_project_nhung_chua_co_task(db_session):
    ws, ceo = await _mk_ws_ceo(db_session)
    proj = Project(workspace_id=ws.id, name="Du an rong", created_by=ceo.id)
    db_session.add(proj)
    await db_session.commit()

    flags = await get_coach_flags(db_session, ws.id)
    assert flags["has_projects"] is True
    assert flags["has_tasks"] is False
    block = render_coach_block(flags)
    assert block is not None
    assert "task" in block.lower() or "cong viec" in block.lower() or "công việc" in block
