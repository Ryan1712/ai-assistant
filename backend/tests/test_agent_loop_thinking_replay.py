"""Phase 4 (đường sâu, model_smart + extended thinking): run_agent_loop phải
chèn nguyên văn thinking_blocks vào ĐẦU content của Message assistant — hợp
đồng thinking+tool-use của Anthropic (thiếu/sai thứ tự bị từ chối ở lượt sau)."""
import pytest
from sqlalchemy import select

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.loop import run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    ChatRequest, Conversation, Message, MessageRole, Role, User, Workspace,
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
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="danh gia rui ro du an", queue_position=1.0)
    db.add(req)
    db.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                   role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db.commit()
    return ws, ceo, conv, req


@pytest.mark.asyncio
async def test_thinking_block_prepended_before_text_in_assistant_message(db_session):
    ws, ceo, conv, req = await _world(db_session)
    thinking_block = {"type": "thinking", "thinking": "xem xet du lieu...",
                      "signature": "sig123"}
    llm = FakeLLMClient(turns=[[
        TextDelta(text="Ket qua phan tich: on"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=10, output_tokens=5,
                  thinking_blocks=[thinking_block]),
    ]])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    (msg,) = (await db_session.execute(select(Message).where(
        Message.role == MessageRole.assistant))).scalars().all()
    assert msg.content[0] == thinking_block
    assert msg.content[1] == {"type": "text", "text": "Ket qua phan tich: on"}


@pytest.mark.asyncio
async def test_no_thinking_blocks_unchanged_content_shape(db_session):
    """Fast path (khong thinking) khong doi hanh vi cu — content khong co block
    thinking o dau."""
    ws, ceo, conv, req = await _world(db_session)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="chao"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    (msg,) = (await db_session.execute(select(Message).where(
        Message.role == MessageRole.assistant))).scalars().all()
    assert msg.content == [{"type": "text", "text": "chao"}]
