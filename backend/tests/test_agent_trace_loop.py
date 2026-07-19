"""Phase 0 (spec 4.1): run_agent_loop ghi AgentTrace ở mọi đường thoát."""
import pytest
from sqlalchemy import select

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta, ToolUseBlock
from app.agent.loop import _tool_trace_entry, run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    AgentTrace, ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Role, User,
    Workspace,
)


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
    await db.commit()
    return ws, ceo, conv


async def _request(db, ws, conv, ceo, content="xin chao"):
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content=content, queue_position=1.0)
    db.add(req)
    db.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                   role=MessageRole.user, content=[{"type": "text", "text": content}]))
    await db.commit()
    return req


async def _traces(db, req):
    rows = await db.execute(select(AgentTrace).where(
        AgentTrace.chat_request_id == req.id))
    return list(rows.scalars())


@pytest.mark.asyncio
async def test_text_only_ghi_trace_end_turn(db_session):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="chao"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    (trace,) = await _traces(db_session, req)
    assert trace.stop_reason == "end_turn"
    assert trace.iterations == 1
    assert trace.model == "fake"
    assert trace.route == "fast"
    assert trace.tools_called == []
    assert trace.total_latency_ms >= 0
    assert trace.workspace_id == ws.id


@pytest.mark.asyncio
async def test_vong_tool_ghi_ten_va_latency(db_session):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="list_projects", input={})],
                    stop_reason="tool_use", input_tokens=1, output_tokens=1)],
        [TextDelta(text="xong"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
    ])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    (trace,) = await _traces(db_session, req)
    assert trace.iterations == 2
    assert trace.stop_reason == "end_turn"
    assert trace.tools_called[0]["name"] == "list_projects"
    assert isinstance(trace.tools_called[0]["latency_ms"], int)
    assert "projects" in trace.tools_called[0]["output"]


@pytest.mark.asyncio
async def test_sensitive_tool_ghi_awaiting_confirmation(db_session):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo, content="khoa acc")
    llm = FakeLLMClient(turns=[[
        StreamDone(tool_uses=[ToolUseBlock(id="t1", name="lock_user",
                                           input={"target_id": str(ceo.id)})],
                   stop_reason="tool_use", input_tokens=1, output_tokens=1),
    ]])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    (trace,) = await _traces(db_session, req)
    assert trace.stop_reason == "awaiting_confirmation"
    assert trace.tools_called == []  # tool nhạy cảm CHƯA chạy nên không có entry


def test_tool_trace_entry_cat_500_ky_tu():
    entry = _tool_trace_entry("t", {"x": "a" * 2000}, {"y": "b" * 2000}, 7)
    assert entry["name"] == "t"
    assert entry["latency_ms"] == 7
    assert len(entry["input"]) == 500
    assert len(entry["output"]) == 500


@pytest.mark.asyncio
async def test_cancelled_ngay_dau_ghi_trace_iterations_0(db_session):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[])  # không được gọi — hủy trước khi vào vòng lặp

    async def always_cancelled(_id):
        return True

    await run_agent_loop(db_session, req, llm, FakeEventPublisher(),
                         is_cancelled=always_cancelled)

    assert req.status == ChatRequestStatus.cancelled
    assert len(llm.calls) == 0
    (trace,) = await _traces(db_session, req)
    assert trace.stop_reason == "cancelled"
    # check bị hủy xảy ra TRƯỚC khi tăng iteration (đầu vòng while) -> vẫn là 0
    assert trace.iterations == 0


@pytest.mark.asyncio
async def test_max_iterations_ghi_dung_1_trace(db_session, monkeypatch):
    monkeypatch.setattr("app.agent.loop.MAX_ITERATIONS", 2)
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    tool_turn = [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="list_projects", input={})],
                            stop_reason="tool_use", input_tokens=1, output_tokens=1)]
    llm = FakeLLMClient(turns=[tool_turn, tool_turn, tool_turn])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    assert req.status == ChatRequestStatus.failed
    (trace,) = await _traces(db_session, req)
    assert trace.stop_reason == "max_iterations"


@pytest.mark.asyncio
async def test_max_tokens_ghi_nguyen_van_stop_reason(db_session):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="dang tra loi dai..."),
        StreamDone(tool_uses=[], stop_reason="max_tokens", input_tokens=1, output_tokens=1),
    ]])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    assert req.status == ChatRequestStatus.done
    (trace,) = await _traces(db_session, req)
    assert trace.stop_reason == "max_tokens"


@pytest.mark.asyncio
async def test_loi_ha_tang_ghi_trace_error(db_session):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[])  # .stream() được gọi -> pop(0) list rỗng -> IndexError

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    assert req.status == ChatRequestStatus.failed
    (trace,) = await _traces(db_session, req)
    assert trace.stop_reason == "error"


@pytest.mark.asyncio
async def test_loi_ghi_trace_khong_pha_request(db_session, monkeypatch):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="chao"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])

    class _BoomAgentTrace:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr("app.agent.loop.AgentTrace", _BoomAgentTrace)

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    assert req.status == ChatRequestStatus.done
    assert await _traces(db_session, req) == []
