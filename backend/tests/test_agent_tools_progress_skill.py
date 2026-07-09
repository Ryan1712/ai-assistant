import pytest

from app.agent.tools import TOOLS, call_tool
from app.models import Project, Role, Task, User, Workspace


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    emp = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
              role=Role.employee)
    db.add(emp)
    await db.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db.add(project)
    await db.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="T", created_by=ceo.id)
    db.add(task)
    await db.flush()
    await db.commit()
    return ws, ceo, emp, task


@pytest.mark.asyncio
async def test_add_task_update_and_list_task_updates_tools(db_session):
    ws, ceo, emp, task = await _world(db_session)
    result = await call_tool(db_session, ceo, "add_task_update",
                             {"task_id": str(task.id), "content": "50%", "percent": 50})
    assert result["percent"] == 50

    listed = await call_tool(db_session, ceo, "list_task_updates", {"task_id": str(task.id)})
    assert len(listed["updates"]) == 1
    assert listed["updates"][0]["content"] == "50%"


@pytest.mark.asyncio
async def test_add_comment_and_list_comments_tools(db_session):
    ws, ceo, emp, task = await _world(db_session)
    result = await call_tool(db_session, ceo, "add_comment",
                             {"task_id": str(task.id), "content": "Nho deadline"})
    assert result["content"] == "Nho deadline"

    listed = await call_tool(db_session, ceo, "list_comments", {"task_id": str(task.id)})
    assert len(listed["comments"]) == 1


@pytest.mark.asyncio
async def test_skill_lifecycle_via_tools(db_session):
    ws, ceo, emp, task = await _world(db_session)
    created = await call_tool(db_session, ceo, "create_skill", {
        "name": "Skill A", "kind": "knowledge", "task_id": str(task.id), "content": "boi canh v1",
    })
    assert created["latest_version"] == 1
    skill_id = created["id"]

    versioned = await call_tool(db_session, ceo, "add_skill_version",
                                {"skill_id": skill_id, "content": "boi canh v2"})
    assert versioned["version"] == 2

    granted = await call_tool(db_session, ceo, "grant_skill",
                              {"skill_id": skill_id, "user_id": str(emp.id)})
    assert granted["already_granted"] is False

    listed = await call_tool(db_session, emp, "list_skills", {})
    assert len(listed["skills"]) == 1

    used = await call_tool(db_session, emp, "use_skill", {"skill_id": skill_id})
    assert used["version"] == 2
    assert used["task_state"]["id"] == str(task.id)


@pytest.mark.asyncio
async def test_use_skill_tool_forbidden_when_not_granted(db_session):
    ws, ceo, emp, task = await _world(db_session)
    created = await call_tool(db_session, ceo, "create_skill", {
        "name": "Skill B", "kind": "knowledge", "content": "boi canh",
    })
    result = await call_tool(db_session, emp, "use_skill", {"skill_id": created["id"]})
    assert result["error"] == "forbidden"


def test_all_9_progress_comment_skill_tools_registered():
    expected = {"add_task_update", "list_task_updates", "add_comment", "list_comments",
               "create_skill", "add_skill_version", "grant_skill", "list_skills", "use_skill"}
    assert expected <= TOOLS.keys()
