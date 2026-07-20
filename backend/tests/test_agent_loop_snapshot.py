"""Phase 1: loop tiêm snapshot vào system (block động) + invalidate sau write-tool."""
import pytest

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta, ToolUseBlock
from app.agent.loop import resolve_confirmation, run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import ChatRequest, ChatRequestStatus, Message, MessageRole

from tests.test_snapshot_builder import NOW, _world


async def _request(db, ws, ceo, conv=None):
    from app.models import Conversation
    if conv is None:
        conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
        db.add(conv)
        await db.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="hoi tinh hinh", queue_position=1.0)
    db.add(req)
    db.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                   role=MessageRole.user,
                   content=[{"type": "text", "text": req.content}]))
    await db.commit()
    return req


def _system_of(llm: FakeLLMClient, call_idx: int = 0):
    return llm.calls[call_idx]["system"]


@pytest.mark.asyncio
async def test_snapshot_nam_trong_block_dong(db_session):
    ws, ceo, ha, duy, p, tasks = await _world(db_session)
    req = await _request(db_session, ws, ceo)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    system = _system_of(llm)
    assert isinstance(system, list) and len(system) == 2
    assert "Trạng thái công ty" not in system[0]["text"]   # tĩnh không chứa snapshot
    assert "# Trạng thái công ty" in system[1]["text"]
    assert "Marketing Q3" in system[1]["text"]
    # luật grounding nằm ở block tĩnh
    assert "Trạng thái công ty" in system[0]["text"] or "ưu tiên" in system[0]["text"]


@pytest.mark.asyncio
async def test_write_tool_invalidate_snapshot(db_session, fake_snapshot_store):
    ws, ceo, ha, duy, p, tasks = await _world(db_session)
    req = await _request(db_session, ws, ceo)
    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="create_task",
                                            input={"project_id": str(p.id),
                                                   "title": "Task mới"})],
                    stop_reason="tool_use", input_tokens=1, output_tokens=1)],
        [TextDelta(text="đã tạo"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
    ])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())
    assert f"snapshot:{ws.id}" in fake_snapshot_store.deleted


@pytest.mark.asyncio
async def test_read_tool_khong_invalidate(db_session, fake_snapshot_store):
    ws, ceo, *_ = await _world(db_session)
    req = await _request(db_session, ws, ceo)
    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="list_projects", input={})],
                    stop_reason="tool_use", input_tokens=1, output_tokens=1)],
        [TextDelta(text="xong"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
    ])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())
    assert fake_snapshot_store.deleted == []


@pytest.mark.asyncio
async def test_confirm_approved_write_tool_invalidate(db_session, fake_snapshot_store):
    ws, ceo, ha, duy, p, (t1, *_rest) = await _world(db_session)
    req = await _request(db_session, ws, ceo)
    req.status = ChatRequestStatus.awaiting_confirmation
    req.pending_action = {"tool_name": "delete_task",
                          "tool_input": {"task_id": str(t1.id)}, "tool_use_id": "tu1"}
    await db_session.commit()

    await resolve_confirmation(db_session, req, approved=True)
    assert f"snapshot:{ws.id}" in fake_snapshot_store.deleted
