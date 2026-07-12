import pytest

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.loop import run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.agent.tools import SENSITIVE_TOOLS, call_tool
from app.models import ChatRequest, Conversation, Message, MessageRole, Role, User, Workspace
from app.services import instruction_service


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
               role=Role.ceo, is_root=True)
    emp = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
               role=Role.employee)
    db.add_all([ceo, emp])
    await db.flush()
    await db.commit()
    return ws, ceo, emp


@pytest.mark.asyncio
async def test_tools_create_update_list_delete(db_session):
    ws, ceo, emp = await _world(db_session)
    created = await call_tool(db_session, ceo, "create_instruction",
                              {"title": "Quy tac", "content": "v1"})
    assert created["version"] == 1
    iid = created["id"]

    updated = await call_tool(db_session, ceo, "update_instruction",
                              {"instruction_id": iid, "content": "v2"})
    assert updated["version"] == 2

    listed = await call_tool(db_session, ceo, "list_instructions", {})
    assert listed["instructions"][0]["content"] == "v2"

    # employee bị chặn ở service layer
    denied = await call_tool(db_session, emp, "create_instruction",
                             {"title": "X", "content": "y"})
    assert denied["error"] == "forbidden"

    assert "delete_instruction" in SENSITIVE_TOOLS
    deleted = await call_tool(db_session, ceo, "delete_instruction", {"instruction_id": iid})
    assert deleted["deleted"] is True


@pytest.mark.asyncio
async def test_agent_loop_injects_latest_instruction_into_system_prompt(db_session):
    ws, ceo, emp = await _world(db_session)
    ins = await instruction_service.create_instruction(db_session, ceo, "Giong dieu", "phien ban cu")
    await instruction_service.update_instruction(db_session, ceo, ins.id, "luon tra loi kem emoji")

    conv = Conversation(workspace_id=ws.id, user_id=emp.id)
    db_session.add(conv)
    await db_session.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=emp.id,
                      content="hi", queue_position=1.0)
    db_session.add(req)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": "hi"}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[[
        TextDelta(text="chao"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    system = llm.calls[0]["system"]
    assert "luon tra loi kem emoji" in system
    assert "phien ban cu" not in system
