"""Phase 4 (đường sâu §8.2): run_agent_loop nhận override cho các guardrail
(max_iterations/max_tool_calls/max_duration_seconds/max_total_tokens) — job
phân tích nền dùng model_smart+thinking cần trần cao hơn fast path. Không
truyền gì (mặc định None) vẫn dùng đúng hằng số module như cũ (fast path
không đổi hành vi, kể cả khi bị monkeypatch trong test khác)."""
import pytest
from sqlalchemy import select

from app.agent.llm_client import FakeLLMClient, LLMClient, StreamDone, TextDelta, ToolUseBlock
from app.agent.loop import run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import AgentTrace, ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Role, User, Workspace


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
                      content="phan tich sau", queue_position=1.0)
    db.add(req)
    db.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                   role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db.commit()
    return ws, ceo, conv, req


@pytest.mark.asyncio
async def test_deep_route_keeps_deep_running_status_during_loop(db_session):
    """LỖ HỔNG bug queue đường sâu: process_conversation guard chặn queue khi
    request ở deep_running, NHƯNG run_agent_loop ghi đè status=running ngay dòng
    đầu. Nếu route="deep" cũng bị hạ về running thì suốt 800s phân tích, guard
    (chỉ thấy deep_running) không chặn gì → watchdog/tin nhắn mới pickup request
    queued chạy SONG SONG cùng conversation → hỏng lịch sử. Vì vậy khi route=
    "deep", loop phải GIỮ status=deep_running trong lúc chạy."""
    ws, ceo, conv, req = await _world(db_session)

    seen_status = {}

    class _StatusProbeLLM(LLMClient):
        async def stream(self, *, system, messages, tools):
            # Đọc status NGAY TRONG lúc loop đang chạy (giữa 2 lần commit).
            await db_session.refresh(req)
            seen_status["during"] = req.status
            yield TextDelta(text="ket qua")
            yield StreamDone(tool_uses=[], stop_reason="end_turn",
                             input_tokens=1, output_tokens=1)

    await run_agent_loop(db_session, req, _StatusProbeLLM(), FakeEventPublisher(),
                         route="deep")

    assert seen_status["during"] == ChatRequestStatus.deep_running
    await db_session.refresh(req)
    assert req.status == ChatRequestStatus.done  # xong thật vẫn về done


@pytest.mark.asyncio
async def test_fast_route_uses_running_status_during_loop(db_session):
    """Đối chứng: route mặc định (fast) vẫn dùng running như cũ."""
    ws, ceo, conv, req = await _world(db_session)

    seen_status = {}

    class _StatusProbeLLM(LLMClient):
        async def stream(self, *, system, messages, tools):
            await db_session.refresh(req)
            seen_status["during"] = req.status
            yield StreamDone(tool_uses=[], stop_reason="end_turn",
                             input_tokens=1, output_tokens=1)

    await run_agent_loop(db_session, req, _StatusProbeLLM(), FakeEventPublisher())

    assert seen_status["during"] == ChatRequestStatus.running


@pytest.mark.asyncio
async def test_default_max_iterations_still_uses_module_constant(db_session, monkeypatch):
    """Khong truyen max_iterations -> van doc dung hang so module TAI THOI DIEM
    goi (khong bind luc def) - monkeypatch van co hieu luc, hanh vi cu khong doi."""
    monkeypatch.setattr("app.agent.loop.MAX_ITERATIONS", 2)
    ws, ceo, conv, req = await _world(db_session)
    tool_turn = [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="list_projects", input={})],
                            stop_reason="tool_use", input_tokens=1, output_tokens=1)]
    llm = FakeLLMClient(turns=[tool_turn, tool_turn, tool_turn])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    assert req.status == ChatRequestStatus.failed
    (trace,) = (await db_session.execute(select(AgentTrace).where(
        AgentTrace.chat_request_id == req.id))).scalars().all()
    assert trace.stop_reason == "max_iterations"


@pytest.mark.asyncio
async def test_max_iterations_override_takes_priority_over_module_constant(db_session):
    ws, ceo, conv, req = await _world(db_session)
    tool_turn = [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="list_projects", input={})],
                            stop_reason="tool_use", input_tokens=1, output_tokens=1)]
    llm = FakeLLMClient(turns=[tool_turn, tool_turn, tool_turn])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher(), max_iterations=2)

    assert req.status == ChatRequestStatus.failed
    (trace,) = (await db_session.execute(select(AgentTrace).where(
        AgentTrace.chat_request_id == req.id))).scalars().all()
    assert trace.stop_reason == "max_iterations"


@pytest.mark.asyncio
async def test_max_iterations_override_allows_more_than_default(db_session):
    """Nguoc lai: override CAO HON MAX_ITERATIONS mac dinh (25) phai cho phep
    chay het so vong lap do (khong bi chan som boi hang so module)."""
    ws, ceo, conv, req = await _world(db_session)
    tool_turn = [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="list_projects", input={})],
                            stop_reason="tool_use", input_tokens=1, output_tokens=1)]
    end_turn = [StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)]
    turns = [tool_turn] * 30 + [end_turn]
    llm = FakeLLMClient(turns=turns)

    await run_agent_loop(db_session, req, llm, FakeEventPublisher(), max_iterations=40)

    assert req.status == ChatRequestStatus.done
    (trace,) = (await db_session.execute(select(AgentTrace).where(
        AgentTrace.chat_request_id == req.id))).scalars().all()
    assert trace.iterations == 31
