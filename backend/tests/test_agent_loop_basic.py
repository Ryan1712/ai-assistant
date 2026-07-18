import pytest
from sqlalchemy import select

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta, ToolUseBlock
from app.agent.loop import run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    ChatRequest, Conversation, Message, MessageRole, Project, Role, User, UserStatus, Workspace,
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


def _make_request(ws, conv, ceo, content="xin chao"):
    return ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                       content=content, queue_position=1.0)


@pytest.mark.asyncio
async def test_text_only_response_completes_request(db_session):
    ws, ceo, conv = await _world(db_session)
    req = _make_request(ws, conv, ceo)
    db_session.add(req)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[[
        TextDelta(text="Chao "), TextDelta(text="ban"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=10, output_tokens=3),
    ]])
    pub = FakeEventPublisher()

    await run_agent_loop(db_session, req, llm, pub)

    assert req.status.value == "done"
    assert req.result_summary == "Chao ban"
    tokens = [e for _, e in pub.events if e["type"] == "token"]
    assert [t["text"] for t in tokens] == ["Chao ", "ban"]
    assert any(e["type"] == "request_done" for _, e in pub.events)


@pytest.mark.asyncio
async def test_max_tokens_stop_reason_appends_cut_note(db_session):
    """Trả lời bị cắt vì chạm trần output (stop_reason=max_tokens) phải nói thẳng
    cho người dùng thay vì im lặng như thể đã trả lời xong."""
    ws, ceo, conv = await _world(db_session)
    req = _make_request(ws, conv, ceo)
    db_session.add(req)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[[
        TextDelta(text="Day la mot cau tra loi dai"),
        StreamDone(tool_uses=[], stop_reason="max_tokens", input_tokens=10, output_tokens=8192),
    ]])
    pub = FakeEventPublisher()

    await run_agent_loop(db_session, req, llm, pub)

    assert req.status.value == "done"
    assert "chạm giới hạn độ dài" in req.result_summary
    tokens = [e for _, e in pub.events if e["type"] == "token"]
    assert "chạm giới hạn độ dài" in tokens[-1]["text"]


@pytest.mark.asyncio
async def test_system_prompt_contains_actor_identity_and_date(db_session):
    """Smoke test LLM thật 2026-07-13: agent hỏi 'cần user ID của bạn' vì system
    prompt không nói người dùng là ai — danh tính phải từ JWT/actor, model không
    được phép hỏi."""
    ws, ceo, conv = await _world(db_session)
    req = _make_request(ws, conv, ceo, content="giao task cho chính tôi")
    db_session.add(req)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[[
        TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    system = llm.calls[0]["system"]
    assert ceo.full_name in system
    assert str(ceo.id) in system
    assert "ceo" in system  # vai trò
    from datetime import datetime, timezone

    from app.tz import VN_TZ
    now_vn = datetime.now(timezone.utc).astimezone(VN_TZ)
    assert now_vn.strftime("%Y-%m-%d") in system  # ngày hôm nay theo giờ VN


@pytest.mark.asyncio
async def test_empty_model_response_does_not_store_empty_message(db_session):
    """Smoke test LLM thật 2026-07-13: model (qua gateway) có thể trả về lượt rỗng —
    nếu lưu Message content=[] thì mọi lần gọi API sau của conversation fail 400
    (Anthropic cấm content rỗng)."""
    ws, ceo, conv = await _world(db_session)
    req = _make_request(ws, conv, ceo)
    db_session.add(req)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[[
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=0),
    ]])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    assert req.status.value == "done"
    assistants = (await db_session.execute(select(Message).where(
        Message.role == MessageRole.assistant))).scalars().all()
    assert assistants == []  # không lưu message rỗng


@pytest.mark.asyncio
async def test_history_skips_messages_with_empty_content(db_session):
    """Tự chữa conversation đã dính message rỗng từ trước khi có guard."""
    ws, ceo, conv = await _world(db_session)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=None,
                           role=MessageRole.assistant, content=[]))  # message rỗng cũ
    req = _make_request(ws, conv, ceo)
    db_session.add(req)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[[
        TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    history = llm.calls[0]["messages"]
    assert all(m["content"] for m in history)  # không còn content rỗng gửi lên API


@pytest.mark.asyncio
async def test_non_sensitive_tool_executes_and_loop_continues(db_session):
    ws, ceo, conv = await _world(db_session)
    req = _make_request(ws, conv, ceo, content="tao project Website")
    db_session.add(req)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="create_project",
                                            input={"name": "Website"})],
                    stop_reason="tool_use", input_tokens=20, output_tokens=8)],
        [TextDelta(text="Da tao xong."),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=15, output_tokens=4)],
    ])
    pub = FakeEventPublisher()

    await run_agent_loop(db_session, req, llm, pub)

    assert req.status.value == "done"
    project = (await db_session.execute(select(Project))).scalar_one()
    assert project.name == "Website"
    assert len(llm.calls) == 2
    running = [e for _, e in pub.events if e["type"] == "tool_running"]
    assert running == [{"type": "tool_running", "chat_request_id": str(req.id),
                        "tool_name": "create_project"}]


@pytest.mark.asyncio
async def test_sensitive_tool_pauses_for_confirmation_without_executing(db_session):
    ws, ceo, conv = await _world(db_session)
    target = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
                 role=Role.employee)
    db_session.add(target)
    await db_session.flush()
    req = _make_request(ws, conv, ceo, content="khoa tai khoan e@a.vn")
    db_session.add(req)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="lock_user",
                                            input={"target_id": str(target.id)})],
                    stop_reason="tool_use", input_tokens=12, output_tokens=6)],
    ])
    pub = FakeEventPublisher()

    await run_agent_loop(db_session, req, llm, pub)

    assert req.status.value == "awaiting_confirmation"
    assert req.pending_action["tool_name"] == "lock_user"
    await db_session.refresh(target)
    assert target.status == UserStatus.active
    assert any(e["type"] == "confirmation_required" for _, e in pub.events)
    assert len(llm.calls) == 1
