from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models import (
    AccountEvent, Instruction, InstructionVersion, LoginEvent, Project, Role, Skill, SkillKind,
    SkillVersion, Task, TaskStatus, TaskUpdate, User, Workspace,
)
from app.services import audit_service


async def _seed(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="ceo@a.vn", password_hash="x", full_name="Sep",
              role=Role.ceo, is_root=True)
    emp = User(workspace_id=ws.id, email="emp@a.vn", password_hash="x", full_name="Nhan Vien",
              role=Role.employee)
    db.add_all([ceo, emp])
    await db.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db.add(project)
    await db.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="T", created_by=ceo.id)
    instruction = Instruction(workspace_id=ws.id, title="I", created_by=ceo.id)
    skill = Skill(workspace_id=ws.id, name="S", kind=SkillKind.knowledge, created_by=ceo.id)
    db.add_all([task, instruction, skill])
    await db.commit()
    return ws, ceo, emp, task, instruction, skill


@pytest.mark.asyncio
async def test_non_ceo_gets_403(db_session):
    ws, ceo, emp, task, instruction, skill = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await audit_service.list_audit_events(db_session, emp)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_all_five_event_types_present(db_session):
    ws, ceo, emp, task, instruction, skill = await _seed(db_session)
    db_session.add_all([
        TaskUpdate(workspace_id=ws.id, task_id=task.id, author_id=emp.id, percent=50,
                  status=TaskStatus.in_progress),
        LoginEvent(workspace_id=ws.id, user_id=emp.id, device_uuid="d1", device_name="iPhone"),
        InstructionVersion(workspace_id=ws.id, instruction_id=instruction.id, version=1,
                          content="x", created_by=ceo.id),
        SkillVersion(workspace_id=ws.id, skill_id=skill.id, version=1, content="y",
                    created_by=ceo.id),
        AccountEvent(workspace_id=ws.id, target_user_id=emp.id, actor_id=ceo.id,
                    event_type="locked", detail="Khóa tài khoản"),
    ])
    await db_session.commit()

    events = await audit_service.list_audit_events(db_session, ceo)
    types = {e["type"] for e in events}
    assert types == {"task_update", "login", "instruction_edit", "skill_edit", "account_event"}
    assert len(events) == 5


@pytest.mark.asyncio
async def test_task_update_summary_includes_status(db_session):
    ws, ceo, emp, task, instruction, skill = await _seed(db_session)
    db_session.add(TaskUpdate(workspace_id=ws.id, task_id=task.id, author_id=emp.id, percent=70,
                              status=TaskStatus.done))
    await db_session.commit()
    events = await audit_service.list_audit_events(db_session, ceo)
    assert events[0]["summary"] == "Cập nhật task — 70%, done"


@pytest.mark.asyncio
async def test_task_update_summary_without_status(db_session):
    ws, ceo, emp, task, instruction, skill = await _seed(db_session)
    db_session.add(TaskUpdate(workspace_id=ws.id, task_id=task.id, author_id=emp.id, percent=30,
                              status=None))
    await db_session.commit()
    events = await audit_service.list_audit_events(db_session, ceo)
    assert events[0]["summary"] == "Cập nhật task — 30%"


@pytest.mark.asyncio
async def test_actor_and_target_name_resolved(db_session):
    ws, ceo, emp, task, instruction, skill = await _seed(db_session)
    db_session.add(AccountEvent(workspace_id=ws.id, target_user_id=emp.id, actor_id=ceo.id,
                                event_type="locked", detail="Khóa tài khoản"))
    await db_session.commit()
    events = await audit_service.list_audit_events(db_session, ceo)
    assert events[0]["actor_name"] == "Sep"
    assert events[0]["target_name"] == "Nhan Vien"
    assert events[0]["actor_id"] == str(ceo.id)
    assert events[0]["target_user_id"] == str(emp.id)


@pytest.mark.asyncio
async def test_date_filter_excludes_outside_range(db_session):
    ws, ceo, emp, task, instruction, skill = await _seed(db_session)
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    recent = datetime(2026, 6, 1, tzinfo=timezone.utc)
    db_session.add_all([
        LoginEvent(workspace_id=ws.id, user_id=emp.id, device_uuid="old", created_at=old),
        LoginEvent(workspace_id=ws.id, user_id=emp.id, device_uuid="recent", created_at=recent),
    ])
    await db_session.commit()

    events = await audit_service.list_audit_events(db_session, ceo, date_from=date(2026, 5, 1))
    assert len(events) == 1
    assert events[0]["summary"] == "Đăng nhập — recent"


@pytest.mark.asyncio
async def test_sorted_newest_first(db_session):
    ws, ceo, emp, task, instruction, skill = await _seed(db_session)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add_all([
        LoginEvent(workspace_id=ws.id, user_id=emp.id, device_uuid="first", created_at=base),
        LoginEvent(workspace_id=ws.id, user_id=emp.id, device_uuid="second",
                  created_at=base + timedelta(days=1)),
    ])
    await db_session.commit()

    events = await audit_service.list_audit_events(db_session, ceo)
    assert [e["summary"] for e in events] == ["Đăng nhập — second", "Đăng nhập — first"]


@pytest.mark.asyncio
async def test_caps_at_200_most_recent(db_session):
    ws, ceo, emp, task, instruction, skill = await _seed(db_session)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(205):
        db_session.add(LoginEvent(workspace_id=ws.id, user_id=emp.id, device_uuid=f"d{i}",
                                  created_at=base + timedelta(seconds=i)))
    await db_session.commit()

    events = await audit_service.list_audit_events(db_session, ceo)
    assert len(events) == 200
    assert events[0]["summary"] == "Đăng nhập — d204"
    assert events[-1]["summary"] == "Đăng nhập — d5"


@pytest.mark.asyncio
async def test_cross_workspace_isolated(db_session):
    ws, ceo, emp, task, instruction, skill = await _seed(db_session)
    other_ws = Workspace(name="B")
    db_session.add(other_ws)
    await db_session.flush()
    other_ceo = User(workspace_id=other_ws.id, email="other@b.vn", password_hash="x",
                     full_name="Other CEO", role=Role.ceo, is_root=True)
    db_session.add(other_ceo)
    await db_session.flush()
    db_session.add(LoginEvent(workspace_id=other_ws.id, user_id=other_ceo.id, device_uuid="x"))
    db_session.add(LoginEvent(workspace_id=ws.id, user_id=emp.id, device_uuid="y"))
    await db_session.commit()

    events = await audit_service.list_audit_events(db_session, ceo)
    assert len(events) == 1
    assert events[0]["summary"] == "Đăng nhập — y"
