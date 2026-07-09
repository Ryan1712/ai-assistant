import pytest
from sqlalchemy import select

from app.models import (
    Project, Role, Task, TaskAssignee, TaskPriority, TaskStatus, User, Workspace,
)


@pytest.mark.asyncio
async def test_project_task_assignee_roundtrip(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    u = User(workspace_id=ws.id, email="c@a.vn", password_hash="x",
             full_name="C", role=Role.ceo, is_root=True)
    db_session.add(u)
    await db_session.flush()
    p = Project(workspace_id=ws.id, name="P1", created_by=u.id)
    db_session.add(p)
    await db_session.flush()
    t = Task(workspace_id=ws.id, project_id=p.id, title="T1", created_by=u.id)
    db_session.add(t)
    await db_session.flush()
    db_session.add(TaskAssignee(workspace_id=ws.id, task_id=t.id, user_id=u.id))
    await db_session.commit()

    found = (await db_session.execute(select(Task))).scalar_one()
    assert found.status == TaskStatus.todo
    assert found.percent == 0
    assert found.priority == TaskPriority.medium
