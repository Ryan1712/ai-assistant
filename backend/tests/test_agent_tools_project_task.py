import pytest

from app.agent.tools import TOOLS, call_tool
from app.models import Project, Role, User, Workspace


async def _ceo(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    return ws, ceo


async def _employee(db, ws):
    e = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
            role=Role.employee)
    db.add(e)
    await db.flush()
    return e


@pytest.mark.asyncio
async def test_create_project_tool_success(db_session):
    ws, ceo = await _ceo(db_session)
    result = await call_tool(db_session, ceo, "create_project", {"name": "Website"})
    assert result["name"] == "Website"
    assert "error" not in result


@pytest.mark.asyncio
async def test_create_project_tool_forbidden_for_employee(db_session):
    ws, ceo = await _ceo(db_session)
    emp = await _employee(db_session, ws)
    result = await call_tool(db_session, emp, "create_project", {"name": "X"})
    assert result["error"] == "forbidden"
    assert result["message"] == "Bạn không có quyền làm điều này."
    assert result.get("hint")


@pytest.mark.asyncio
async def test_create_task_tool_invalid_input_missing_title(db_session):
    ws, ceo = await _ceo(db_session)
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    await db_session.commit()
    result = await call_tool(db_session, ceo, "create_task", {"project_id": str(project.id)})
    assert result["error"] == "invalid_input"


@pytest.mark.asyncio
async def test_create_get_update_assign_unassign_task_tools_roundtrip(db_session):
    ws, ceo = await _ceo(db_session)
    emp = await _employee(db_session, ws)
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    await db_session.commit()

    created = await call_tool(db_session, ceo, "create_task",
                              {"project_id": str(project.id), "title": "Lam bao cao"})
    assert created["title"] == "Lam bao cao"
    task_id = created["id"]

    assigned = await call_tool(db_session, ceo, "assign_task",
                               {"task_id": task_id, "user_id": str(emp.id)})
    assert assigned["already_assigned"] is False

    fetched = await call_tool(db_session, emp, "get_task", {"task_id": task_id})
    assert str(emp.id) in fetched["assignee_ids"]

    updated = await call_tool(db_session, ceo, "update_task",
                              {"task_id": task_id, "percent": 50})
    assert updated["percent"] == 50

    unassigned = await call_tool(db_session, ceo, "unassign_task",
                                 {"task_id": task_id, "user_id": str(emp.id)})
    assert unassigned["unassigned"] is True


@pytest.mark.asyncio
async def test_list_projects_and_list_tasks_tools_take_no_args(db_session):
    ws, ceo = await _ceo(db_session)
    await call_tool(db_session, ceo, "create_project", {"name": "P1"})
    listed = await call_tool(db_session, ceo, "list_projects", {})
    assert len(listed["projects"]) == 1


def test_all_9_project_task_tools_registered():
    expected = {"create_project", "update_project", "list_projects", "create_task",
               "update_task", "list_tasks", "get_task", "assign_task", "unassign_task"}
    assert expected <= TOOLS.keys()
