import pytest

from app.models import Project, Role, Task, TaskAssignee, User, Workspace
from app.services import resolver_service


async def _setup(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="Sếp Eval",
              role=Role.ceo, is_root=True)
    duy = User(workspace_id=ws.id, email="duy@a.vn", password_hash="x", full_name="Duy Phạm",
              role=Role.employee)
    nam1 = User(workspace_id=ws.id, email="nam1@a.vn", password_hash="x", full_name="Nam Nguyễn",
               role=Role.employee)
    nam2 = User(workspace_id=ws.id, email="nam2@a.vn", password_hash="x", full_name="Nam Trần",
               role=Role.employee)
    db.add_all([ceo, duy, nam1, nam2])
    await db.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db.add(project)
    await db.flush()
    await db.commit()
    return ws, ceo, duy, nam1, nam2, project


@pytest.mark.asyncio
async def test_resolve_person_single_match(db_session):
    ws, ceo, duy, nam1, nam2, project = await _setup(db_session)
    result = await resolver_service.resolve_person(db_session, ceo, "Duy")
    assert result["found"] is True
    assert result["match"]["id"] == str(duy.id)


@pytest.mark.asyncio
async def test_resolve_person_ambiguous_two_candidates(db_session):
    ws, ceo, duy, nam1, nam2, project = await _setup(db_session)
    result = await resolver_service.resolve_person(db_session, ceo, "Nam")
    assert result.get("ambiguous") is True
    ids = {c["id"] for c in result["candidates"]}
    assert ids == {str(nam1.id), str(nam2.id)}


@pytest.mark.asyncio
async def test_resolve_person_not_found(db_session):
    ws, ceo, duy, nam1, nam2, project = await _setup(db_session)
    result = await resolver_service.resolve_person(db_session, ceo, "Khong Ton Tai Xyz")
    assert result["found"] is False
    assert result["candidates"] == []


@pytest.mark.asyncio
async def test_resolve_task_by_assignee_single_task(db_session):
    ws, ceo, duy, nam1, nam2, project = await _setup(db_session)
    task = Task(workspace_id=ws.id, project_id=project.id, title="Bao cao thue",
               created_by=ceo.id)
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskAssignee(workspace_id=ws.id, task_id=task.id, user_id=duy.id))
    await db_session.commit()

    result = await resolver_service.resolve_task(db_session, ceo, assignee_id=duy.id)
    assert result["found"] is True
    assert result["match"]["id"] == str(task.id)


@pytest.mark.asyncio
async def test_resolve_task_by_assignee_multiple_tasks_ambiguous(db_session):
    ws, ceo, duy, nam1, nam2, project = await _setup(db_session)
    for title in ["T1", "T2", "T3"]:
        task = Task(workspace_id=ws.id, project_id=project.id, title=title, created_by=ceo.id)
        db_session.add(task)
        await db_session.flush()
        db_session.add(TaskAssignee(workspace_id=ws.id, task_id=task.id, user_id=nam1.id))
    await db_session.commit()

    result = await resolver_service.resolve_task(db_session, ceo, assignee_id=nam1.id)
    assert result.get("ambiguous") is True
    assert len(result["candidates"]) == 3


@pytest.mark.asyncio
async def test_resolve_task_requires_query_or_assignee(db_session):
    ws, ceo, duy, nam1, nam2, project = await _setup(db_session)
    result = await resolver_service.resolve_task(db_session, ceo)
    assert result["error"] == "invalid_input"
