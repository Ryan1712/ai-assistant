"""Phase 0 (spec AI upgrade 4.1): bảng agent_traces."""
from sqlalchemy import select

from app.models import AgentTrace, ChatRequest, Conversation, Role, User, Workspace


async def test_agent_trace_luu_va_doc_lai(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
               role=Role.ceo)
    db_session.add(ceo)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add(conv)
    await db_session.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="hi", queue_position=1.0)
    db_session.add(req)
    await db_session.flush()

    db_session.add(AgentTrace(
        workspace_id=ws.id, chat_request_id=req.id, model="fake",
        iterations=2, stop_reason="end_turn",
        tools_called=[{"name": "list_tasks", "latency_ms": 5,
                       "input": "{}", "output": "{\"tasks\": []}"}],
        total_latency_ms=123))
    await db_session.commit()

    row = (await db_session.execute(select(AgentTrace).where(
        AgentTrace.chat_request_id == req.id))).scalar_one()
    assert row.route == "fast"
    assert row.model == "fake"
    assert row.iterations == 2
    assert row.tools_called[0]["name"] == "list_tasks"
    assert row.total_latency_ms == 123
    assert row.created_at is not None
