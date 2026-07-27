import pytest
from fastapi import HTTPException

from app.agent.tools import TOOLS, call_tool
from app.models import Role, User, Workspace, WorkspacePlan


async def _ceo(db, plan=WorkspacePlan.advanced):
    ws = Workspace(name="A", plan=plan)
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    await db.commit()
    return ws, ceo


def test_report_schedule_tools_registered_and_not_sensitive():
    for name in ("create_report_schedule", "list_report_schedules",
                 "delete_report_schedule"):
        assert name in TOOLS
        assert TOOLS[name].sensitive is False
    assert len(TOOLS) == 63  # +suggest_replies (thẻ bấm chọn nhanh) +create_directive +get_directive_status (Phase 3) +get_project_health +get_progress_stats (feedback fast-track) +semantic_search +list_memories +forget_memory (Phase 6) +add_example (Phase 6)


@pytest.mark.asyncio
async def test_create_report_schedule_tool_rejects_out_of_range_weekday(db_session):
    """LLM rất dễ sinh weekday=7 (nhầm quy ước 1..7 hoặc 0=Chủ Nhật). Không chặn
    thì compute_next_run chạy `while weekday()!=7` vô hạn → treo worker. Tool phải
    trả invalid_input (như schema API ge=0,le=6) để model tự sửa, không nổ/treo."""
    ws, ceo = await _ceo(db_session)
    res = await call_tool(db_session, ceo, "create_report_schedule",
                          {"weekday": 7, "hour": 8, "minute": 0})
    assert res["error"] == "invalid_input"


@pytest.mark.asyncio
async def test_create_report_schedule_tool_rejects_out_of_range_hour(db_session):
    ws, ceo = await _ceo(db_session)
    res = await call_tool(db_session, ceo, "create_report_schedule",
                          {"weekday": 0, "hour": 24, "minute": 0})
    assert res["error"] == "invalid_input"
    res2 = await call_tool(db_session, ceo, "create_report_schedule",
                           {"weekday": 0, "hour": 8, "minute": 60})
    assert res2["error"] == "invalid_input"


@pytest.mark.asyncio
async def test_create_list_delete_report_schedule_tools(db_session):
    ws, ceo = await _ceo(db_session)

    created = await call_tool(db_session, ceo, "create_report_schedule",
                              {"weekday": 0, "hour": 8, "minute": 0})
    assert created["weekday"] == 0 and created["hour"] == 8
    assert created["recipient_id"] == str(ceo.id)

    listed = await call_tool(db_session, ceo, "list_report_schedules", {})
    assert len(listed["schedules"]) == 1
    assert listed["schedules"][0]["id"] == created["id"]

    deleted = await call_tool(db_session, ceo, "delete_report_schedule",
                              {"schedule_id": created["id"]})
    assert deleted["deleted"] is True

    listed2 = await call_tool(db_session, ceo, "list_report_schedules", {})
    assert listed2["schedules"] == []


@pytest.mark.asyncio
async def test_create_report_schedule_tool_wraps_basic_plan_error(db_session):
    ws, ceo = await _ceo(db_session, plan=WorkspacePlan.basic)

    result = await call_tool(db_session, ceo, "create_report_schedule",
                             {"weekday": None, "hour": 8})
    assert result["error"] == "forbidden"  # 403 advanced_plan_required
