import uuid

import pytest

from app.agent.tools import TOOLS, call_tool
from app.models import Project, Role, Task, TaskStatus, User, Workspace


async def _ceo(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    return ws, ceo


@pytest.mark.asyncio
async def test_generate_report_tool_success(db_session, storage_dir):
    ws, ceo = await _ceo(db_session)
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    db_session.add(Task(workspace_id=ws.id, project_id=project.id, title="T",
                        status=TaskStatus.done, created_by=ceo.id))
    await db_session.commit()

    result = await call_tool(db_session, ceo, "generate_report", {})
    assert "error" not in result
    assert result["row_count"] == 1
    assert result["summary"]["done"] == 1
    assert uuid.UUID(result["report_id"])  # id hợp lệ


@pytest.mark.asyncio
async def test_generate_report_tool_with_status_filter(db_session, storage_dir):
    ws, ceo = await _ceo(db_session)
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    db_session.add(Task(workspace_id=ws.id, project_id=project.id, title="T",
                        status=TaskStatus.todo, created_by=ceo.id))
    await db_session.commit()

    result = await call_tool(db_session, ceo, "generate_report", {"status": "done"})
    assert result["row_count"] == 0
    assert result["filters_applied"]["status"] == "done"


@pytest.mark.asyncio
async def test_generate_report_tool_forbidden_for_employee(db_session, storage_dir):
    ws, ceo = await _ceo(db_session)
    emp = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
              role=Role.employee)
    db_session.add(emp)
    await db_session.flush()
    result = await call_tool(db_session, emp, "generate_report", {})
    assert result == {"error": "forbidden", "message": "Bạn không có quyền làm điều này."}


@pytest.mark.asyncio
async def test_generate_report_tool_unknown_project_not_found(db_session, storage_dir):
    ws, ceo = await _ceo(db_session)
    result = await call_tool(db_session, ceo, "generate_report",
                             {"project_id": str(uuid.uuid4())})
    assert result["error"] == "not_found"


def test_generate_report_registered_as_22nd_tool_not_sensitive():
    assert "generate_report" in TOOLS
    assert TOOLS["generate_report"].sensitive is False
    assert len(TOOLS) == 47  # +get/set_notification_preference (2026-07-17)
