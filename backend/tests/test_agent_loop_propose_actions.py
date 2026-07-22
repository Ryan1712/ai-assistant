import pytest

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


def _make_request(ws, conv, ceo, content="bao Duy xong deadline nhe"):
    return ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                       content=content, queue_position=1.0)


@pytest.mark.asyncio
async def test_valid_proposal_pauses_for_confirmation_without_executing(db_session):
    ws, ceo, conv = await _world(db_session)
    req = _make_request(ws, conv, ceo)
    db_session.add(req)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    actions = [{"tool_name": "create_note", "tool_input": {"content": "nhac Duy deadline"},
               "display_text": "Tạo ghi chú nhắc Duy deadline"}]
    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="propose_actions",
                                            input={"actions": actions, "reasoning": "suy luan tu ngu canh"})],
                    stop_reason="tool_use", input_tokens=12, output_tokens=6)],
    ])
    pub = FakeEventPublisher()

    await run_agent_loop(db_session, req, llm, pub)

    assert req.status.value == "awaiting_confirmation"
    assert req.pending_action["kind"] == "proposal"
    assert req.pending_action["actions"] == actions
    assert req.pending_action["reasoning"] == "suy luan tu ngu canh"
    event = next(e for _, e in pub.events if e["type"] == "confirmation_required")
    assert event["kind"] == "proposal"
    assert event["actions"] == actions
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_invalid_proposal_does_not_pause_gets_error_and_retries(db_session):
    ws, ceo, conv = await _world(db_session)
    req = _make_request(ws, conv, ceo)
    db_session.add(req)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    bad_actions = [{"tool_name": "lock_user", "tool_input": {"target_id": "x"},
                   "display_text": "Khóa tài khoản"}]
    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="propose_actions",
                                            input={"actions": bad_actions, "reasoning": ""})],
                    stop_reason="tool_use", input_tokens=12, output_tokens=6)],
        [TextDelta(text="Xin loi, de toi lam khac."),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=8, output_tokens=4)],
    ])
    pub = FakeEventPublisher()

    await run_agent_loop(db_session, req, llm, pub)

    assert req.status.value == "done"
    assert req.pending_action is None
    assert not any(e["type"] == "confirmation_required" for _, e in pub.events)
    assert len(llm.calls) == 2
    second_call_messages = llm.calls[1]["messages"]
    tool_result_contents = [
        b["content"] for m in second_call_messages for b in m["content"]
        if isinstance(b, dict) and b.get("type") == "tool_result"
    ]
    assert any("lock_user" in c for c in tool_result_contents)
