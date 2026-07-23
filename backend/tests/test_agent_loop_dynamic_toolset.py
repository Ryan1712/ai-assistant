"""Phase 4 (Router §6.4/§8.1): run_agent_loop lọc toolset theo tool_names khi
Router chắc route; None (mặc định) vẫn nạp full toolset như trước — không đổi
hành vi hiện có."""
import pytest

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.loop import _tool_specs_for_api, run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.agent.tools import TOOLS
from app.models import ChatRequest, Conversation, Message, MessageRole, Role, User, Workspace


def test_tool_specs_for_api_none_returns_full_toolset():
    specs = _tool_specs_for_api(None)
    assert len(specs) == len(TOOLS)


def test_tool_specs_for_api_filters_to_given_names():
    names = {"get_task", "search"}
    specs = _tool_specs_for_api(names)
    assert {s["name"] for s in specs} == names


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db.add(conv)
    await db.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="tinh trang hom nay", queue_position=1.0)
    db.add(req)
    db.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                   role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db.commit()
    return ws, ceo, conv, req


@pytest.mark.asyncio
async def test_run_agent_loop_passes_filtered_toolset_to_llm(db_session):
    ws, ceo, conv, req = await _world(db_session)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])
    names = {"get_today_dashboard", "get_directive_status"}

    await run_agent_loop(db_session, req, llm, FakeEventPublisher(), tool_names=names)

    assert {t["name"] for t in llm.calls[0]["tools"]} == names


@pytest.mark.asyncio
async def test_run_agent_loop_default_tool_names_none_keeps_full_toolset(db_session):
    ws, ceo, conv, req = await _world(db_session)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    assert len(llm.calls[0]["tools"]) == len(TOOLS)
