import uuid

import pytest

from app.agent.tools import call_tool
from app.models import Project, Role, Skill, SkillKind, Task, User, Workspace, WorkspacePlan


async def _empty_ceo(db):
    """Workspace vừa tạo, chưa có project/task/skill/note/ghi âm/thông báo gì cả."""
    ws = Workspace(name="Empty", plan=WorkspacePlan.advanced)
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="ce@a.vn", password_hash="x", full_name="CE",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    await db.commit()
    return ceo


async def _ceo_with_task_and_skill(db):
    """Có 1 project/task/skill nhưng KHÔNG có bình luận/cập nhật/đính kèm/grant nào."""
    ws = Workspace(name="WithTask")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="ct@a.vn", password_hash="x", full_name="CT",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db.add(project)
    await db.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="T", created_by=ceo.id)
    db.add(task)
    await db.flush()
    skill = Skill(workspace_id=ws.id, name="S", kind=SkillKind.profile, created_by=ceo.id)
    db.add(skill)
    await db.flush()
    await db.commit()
    return ceo, task, skill


@pytest.mark.asyncio
async def test_call_tool_unknown_tool_name_returns_not_found_not_keyerror(db_session):
    ceo = await _empty_ceo(db_session)
    result = await call_tool(db_session, ceo, "khong_ton_tai_tool", {})
    assert result["error"] == "not_found"
    assert "hint" in result


@pytest.mark.asyncio
async def test_call_tool_error_includes_hint(db_session):
    ceo = await _empty_ceo(db_session)
    result = await call_tool(db_session, ceo, "get_task", {"task_id": str(uuid.uuid4())})
    assert result["error"] == "not_found"
    assert "hint" in result


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,tool_input,key", [
    ("list_projects", {}, "projects"),
    ("list_tasks", {}, "tasks"),
    ("list_skills", {}, "skills"),
    ("list_reports", {}, "reports"),
    ("list_report_schedules", {}, "schedules"),
    ("list_audit_events", {}, "events"),
    ("list_instructions", {}, "instructions"),
    ("list_notes", {}, "notes"),
    ("list_voice_notes", {}, "voice_notes"),
    ("list_notifications", {}, "notifications"),
])
async def test_list_handler_empty_result_has_explanatory_note(db_session, tool_name, tool_input, key):
    ceo = await _empty_ceo(db_session)
    result = await call_tool(db_session, ceo, tool_name, tool_input)
    assert result[key] == []
    assert result.get("note"), f"{tool_name} trả rỗng nhưng thiếu 'note' giải thích"


@pytest.mark.asyncio
async def test_list_task_updates_empty_has_note(db_session):
    ceo, task, skill = await _ceo_with_task_and_skill(db_session)
    result = await call_tool(db_session, ceo, "list_task_updates", {"task_id": str(task.id)})
    assert result["updates"] == []
    assert result.get("note")


@pytest.mark.asyncio
async def test_list_comments_empty_has_note(db_session):
    ceo, task, skill = await _ceo_with_task_and_skill(db_session)
    result = await call_tool(db_session, ceo, "list_comments", {"task_id": str(task.id)})
    assert result["comments"] == []
    assert result.get("note")


@pytest.mark.asyncio
async def test_list_task_attachments_empty_has_note(db_session):
    ceo, task, skill = await _ceo_with_task_and_skill(db_session)
    result = await call_tool(db_session, ceo, "list_task_attachments", {"task_id": str(task.id)})
    assert result["attachments"] == []
    assert result.get("note")


@pytest.mark.asyncio
async def test_list_skill_grants_empty_has_note(db_session):
    ceo, task, skill = await _ceo_with_task_and_skill(db_session)
    result = await call_tool(db_session, ceo, "list_skill_grants", {"skill_id": str(skill.id)})
    assert result["grants"] == []
    assert result.get("note")


@pytest.mark.asyncio
async def test_search_all_empty_has_single_top_level_note(db_session):
    ceo = await _empty_ceo(db_session)
    result = await call_tool(db_session, ceo, "search", {"q": "khong co gi khop ca"})
    assert all(result[k] == [] for k in ("tasks", "notes", "voice_notes", "users", "skills"))
    assert result.get("note")
