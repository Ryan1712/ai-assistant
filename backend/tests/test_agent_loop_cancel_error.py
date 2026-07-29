import pytest

from app.agent.llm_client import FakeLLMClient, LLMClient, StreamDone, TextDelta, ToolUseBlock
from app.agent.loop import MAX_ITERATIONS, run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Role, User, Workspace,
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
                      content="xin chao", queue_position=1.0)
    db.add(req)
    await db.flush()
    db.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                   role=MessageRole.user, content=[{"type": "text", "text": "xin chao"}]))
    await db.commit()
    return req


@pytest.mark.asyncio
async def test_cancelled_before_first_call_stops_immediately(db_session):
    req = await _world(db_session)
    llm = FakeLLMClient(turns=[])  # không được gọi
    pub = FakeEventPublisher()

    async def always_cancelled(_id):
        return True

    await run_agent_loop(db_session, req, llm, pub, is_cancelled=always_cancelled)

    assert req.status == ChatRequestStatus.cancelled
    assert len(llm.calls) == 0
    assert any(e["status"] == "cancelled" for _, e in pub.events)


@pytest.mark.asyncio
async def test_cancelled_mid_stream_keeps_partial_tokens_and_stops(db_session):
    req = await _world(db_session)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="Dang "), TextDelta(text="lam"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])
    pub = FakeEventPublisher()
    calls = {"n": 0}

    async def cancel_on_third_check(_id):
        # 3 lần check trước khi hủy: (1) đầu while, (2) trước token "Dang ", (3) trước token "lam" -> True
        calls["n"] += 1
        return calls["n"] > 2

    await run_agent_loop(db_session, req, llm, pub, is_cancelled=cancel_on_third_check)

    assert req.status == ChatRequestStatus.cancelled
    tokens = [e for _, e in pub.events if e["type"] == "token"]
    assert len(tokens) == 1
    assert tokens[0]["text"] == "Dang "


@pytest.mark.asyncio
async def test_llm_error_marks_request_failed_without_raising(db_session):
    """req.error KHÔNG BAO GIỜ được chứa nguyên văn str(exc) — exception của SDK
    bên thứ 3 (vd anthropic.APIError) có thể lộ chi tiết nội bộ, và FE hiển thị
    thẳng field này ra màn hình nếu không khớp pattern lỗi đã biết nào (dev report
    thật: người dùng thấy nguyên object lỗi Anthropic trong chat). Chỉ trả mã lỗi
    chung an toàn — chi tiết thật chỉ nằm trong log server."""
    req = await _world(db_session)

    class _RaisingLLMClient(LLMClient):
        async def stream(self, *, system, messages, tools):
            raise RuntimeError("rate_limited_429 kem chi tiet noi bo nhay cam")
            yield  # pragma: no cover - giữ hàm là generator

    pub = FakeEventPublisher()
    await run_agent_loop(db_session, req, _RaisingLLMClient(), pub)

    assert req.status == ChatRequestStatus.failed
    assert req.error == "internal_error"
    assert "rate_limited_429" not in req.error
    failed_event = next(e for _, e in pub.events if e["type"] == "request_failed")
    assert failed_event["error"] == "internal_error"


@pytest.mark.asyncio
async def test_arq_cancellation_marks_request_failed_before_reraising(db_session):
    """arq job_timeout giết job bằng asyncio.CancelledError — BaseException, trước
    đây lọt qua except Exception → request kẹt status=running VĨNH VIỄN, FE không
    nhận được bất kỳ event nào (AI "đứng im" không báo lỗi). Giờ phải best-effort
    mark failed + publish request_failed rồi re-raise cho arq hoàn tất việc hủy."""
    import asyncio

    req = await _world(db_session)

    class _CancelledMidStreamLLMClient(LLMClient):
        async def stream(self, *, system, messages, tools):
            raise asyncio.CancelledError()
            yield  # pragma: no cover - giữ hàm là generator

    pub = FakeEventPublisher()
    with pytest.raises(asyncio.CancelledError):
        await run_agent_loop(db_session, req, _CancelledMidStreamLLMClient(), pub)

    assert req.status == ChatRequestStatus.failed
    assert req.error == "job_cancelled"
    assert any(e["type"] == "request_failed" for _, e in pub.events)


def test_get_llm_client_sets_explicit_timeout():
    """Không set timeout tường minh thì SDK default (~600s) ≥ arq job_timeout 600s
    — stream treo (gateway chết giữa chừng) bị arq giết trước khi SDK kịp raise,
    rơi đúng vào ca CancelledError ở trên. Timeout đọc phải đủ NHỎ so với
    job_timeout để treo biến thành Exception bình thường (mark failed + báo FE)."""
    from app.agent.llm_client import get_llm_client

    get_llm_client.cache_clear()
    try:
        client = get_llm_client()
        timeout = client._client.timeout
        assert timeout.connect == 10.0
        assert timeout.read == 180.0
    finally:
        get_llm_client.cache_clear()


class _AlwaysToolUseLLMClient(LLMClient):
    """Kịch bản model buggy/adversarial: luôn trả tool_use cho tool vô hại
    (list_projects), không bao giờ tới end_turn. Dùng để kiểm tra MAX_ITERATIONS
    chặn vòng lặp vô hạn thay vì để job treo tới khi arq job_timeout giết bằng
    CancelledError (BaseException, lọt qua except Exception)."""

    def __init__(self):
        self.call_count = 0

    async def stream(self, *, system, messages, tools):
        self.call_count += 1
        yield StreamDone(
            tool_uses=[ToolUseBlock(id=f"t{self.call_count}", name="list_projects", input={})],
            stop_reason="tool_use", input_tokens=1, output_tokens=1,
        )


@pytest.mark.asyncio
async def test_runaway_tool_use_loop_terminates_via_max_iterations(db_session):
    req = await _world(db_session)
    llm = _AlwaysToolUseLLMClient()
    pub = FakeEventPublisher()

    await run_agent_loop(db_session, req, llm, pub)

    assert req.status == ChatRequestStatus.failed
    assert req.error == "max_iterations_exceeded"
    assert any(e["type"] == "request_failed" for _, e in pub.events)
    # Không được gọi LLM vô hạn — dừng lại đúng ở ngưỡng MAX_ITERATIONS.
    assert llm.call_count == MAX_ITERATIONS
