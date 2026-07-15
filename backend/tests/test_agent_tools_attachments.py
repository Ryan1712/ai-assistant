import pytest

from app.agent.tools import TOOLS, call_tool
from app.models import Project, Role, Task, User, Workspace
from app.services import attachment_service


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db.add(project)
    await db.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="T", created_by=ceo.id)
    db.add(task)
    await db.commit()
    return ws, ceo, task


def test_list_task_attachments_tool_registered_and_not_sensitive():
    spec = TOOLS["list_task_attachments"]
    assert spec.sensitive is False


@pytest.mark.asyncio
async def test_list_task_attachments_returns_uploaded_files(db_session, storage_dir):
    ws, ceo, task = await _world(db_session)
    await attachment_service.create_attachment(
        db_session, ceo, task.id, filename="a.pdf", data=b"noi dung")

    got = await call_tool(db_session, ceo, "list_task_attachments", {"task_id": str(task.id)})
    assert len(got["attachments"]) == 1
    assert got["attachments"][0]["original_filename"] == "a.pdf"
