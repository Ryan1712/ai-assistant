import pytest
from sqlalchemy import select

from app.models import Directive, DirectiveStatus, Project, Role, Task, User, Workspace


@pytest.mark.asyncio
async def test_directive_roundtrip_defaults(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    duy = User(workspace_id=ws.id, email="d@a.vn", password_hash="x", full_name="Duy",
              role=Role.employee)
    db_session.add_all([ceo, duy])
    await db_session.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="T", created_by=ceo.id)
    db_session.add(task)
    await db_session.flush()

    d = Directive(workspace_id=ws.id, created_by=ceo.id, recipient_id=duy.id, task_id=task.id,
                 verbatim_text="bao Duy xong deadline nhe")
    db_session.add(d)
    await db_session.commit()

    found = (await db_session.execute(select(Directive))).scalar_one()
    assert found.status == DirectiveStatus.sent
    assert found.structured_summary == ""
    assert found.deadline is None
    assert found.response_text is None
    assert found.remind_count == 0
    assert found.escalated_at is None
    assert found.acked_at is None
