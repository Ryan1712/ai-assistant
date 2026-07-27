import json

import pytest
from sqlalchemy import select

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta, ToolUseBlock
from app.agent.loop import run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import ChatRequest, Conversation, Message, MessageRole, Role, User, Workspace


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


def _make_request(ws, conv, ceo, content="giao viec cho Nam"):
    return ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                       content=content, queue_position=1.0)


@pytest.mark.asyncio
async def test_suggest_replies_ends_turn_without_second_llm_call(db_session):
    ws, ceo, conv = await _world(db_session)
    req = _make_request(ws, conv, ceo)
    db_session.add(req)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    options = ["Nam Nguyen", "Nam Tran"]
    llm = FakeLLMClient(turns=[
        [TextDelta(text="Anh muon giao cho Nam nao?"),
         StreamDone(tool_uses=[ToolUseBlock(id="t1", name="suggest_replies",
                                            input={"options": options})],
                    stop_reason="tool_use", input_tokens=10, output_tokens=5)],
    ])
    pub = FakeEventPublisher()

    await run_agent_loop(db_session, req, llm, pub)

    assert req.status.value == "done"
    assert len(llm.calls) == 1  # KHÔNG gọi LLM lần 2 sau suggest_replies
    event = next(e for _, e in pub.events if e["type"] == "request_done")
    assert event["chat_request_id"] == str(req.id)

    msgs = (await db_session.execute(
        select(Message).where(Message.conversation_id == conv.id)
        .order_by(Message.created_at))).scalars().all()
    tool_result_msg = next(m for m in msgs if m.role == MessageRole.user
                           and m.content and m.content[0].get("type") == "tool_result")
    assert tool_result_msg.content[0]["tool_use_id"] == "t1"
    assistant_msg = next(m for m in msgs if m.role == MessageRole.assistant)
    tool_use_block = next(b for b in assistant_msg.content if b.get("type") == "tool_use")
    assert tool_use_block["name"] == "suggest_replies"
    assert tool_use_block["input"]["options"] == options


@pytest.mark.asyncio
async def test_suggest_replies_publishes_ws_event_with_options(db_session):
    """Fix 1 (whole-branch review): chỉ publish request_done thì FE không có cách
    nào biết options để hiện chip trong phiên chat LIVE (messagesToRows chỉ chạy
    khi load lại lịch sử qua REST). Phải publish thêm 1 event riêng mang options."""
    ws, ceo, conv = await _world(db_session)
    req = _make_request(ws, conv, ceo)
    db_session.add(req)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    options = ["Nam Nguyen", "Nam Tran"]
    llm = FakeLLMClient(turns=[
        [TextDelta(text="Anh muon giao cho Nam nao?"),
         StreamDone(tool_uses=[ToolUseBlock(id="t1", name="suggest_replies",
                                            input={"options": options})],
                    stop_reason="tool_use", input_tokens=10, output_tokens=5)],
    ])
    pub = FakeEventPublisher()

    await run_agent_loop(db_session, req, llm, pub)

    conv_id, event = next((c, e) for c, e in pub.events if e["type"] == "suggest_replies")
    assert conv_id == conv.id
    assert event["chat_request_id"] == str(req.id)
    assert event["options"] == options


@pytest.mark.asyncio
async def test_suggest_replies_with_extra_tool_use_gets_defensive_tool_result(db_session):
    """Fix 4 (whole-branch review): AnthropicLLMClient luôn gửi
    disable_parallel_tool_use=True nên đây không thể xảy ra hôm nay qua path thật, nhưng
    LLM call đi qua gateway bên thứ 3 — nếu gateway lỡ trả về 2 tool_use (suggest_replies
    + tool khác) trong cùng lượt, tool_use "khác" đó KHÔNG được phép mồ côi tool_result,
    nếu không lần gọi Anthropic kế tiếp của conversation sẽ lỗi 400."""
    ws, ceo, conv = await _world(db_session)
    req = _make_request(ws, conv, ceo)
    db_session.add(req)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    options = ["Nam Nguyen", "Nam Tran"]
    llm = FakeLLMClient(turns=[
        [TextDelta(text="Anh muon giao cho Nam nao?"),
         StreamDone(tool_uses=[
             ToolUseBlock(id="t1", name="suggest_replies", input={"options": options}),
             ToolUseBlock(id="t2", name="list_users", input={}),
         ], stop_reason="tool_use", input_tokens=10, output_tokens=5)],
    ])
    pub = FakeEventPublisher()

    await run_agent_loop(db_session, req, llm, pub)

    msgs = (await db_session.execute(
        select(Message).where(Message.conversation_id == conv.id)
        .order_by(Message.created_at))).scalars().all()
    tool_result_msg = next(m for m in msgs if m.role == MessageRole.user
                           and m.content and m.content[0].get("type") == "tool_result")
    by_id = {b["tool_use_id"]: json.loads(b["content"]) for b in tool_result_msg.content}
    assert by_id.keys() == {"t1", "t2"}
    assert by_id["t1"] == {"shown": True}
    assert "error" in by_id["t2"]
