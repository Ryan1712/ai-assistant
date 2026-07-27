import uuid

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.models import Conversation, Message, MessageRole
from app.services.conversation_title_service import retitle_pending_conversations


def _fake_title_llm(text="Giao task quy 3 cho Nam"):
    return FakeLLMClient(turns=[[TextDelta(text=text),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)]])


async def _mk_conv_with_reply(db, *, title_locked=False,
                              title="tin nhan dau tien cat 60 ky tu"):
    conv = Conversation(workspace_id=uuid.uuid4(), user_id=uuid.uuid4(),
                        title=title, title_locked=title_locked)
    db.add(conv)
    await db.flush()
    db.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                   role=MessageRole.user, content=[{"type": "text", "text": "giao task cho Nam"}]))
    db.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                   role=MessageRole.assistant, content=[{"type": "text", "text": "Da tao task"}]))
    await db.commit()
    return conv


async def test_retitle_sets_title_and_locks(db_session):
    conv = await _mk_conv_with_reply(db_session)
    llm = _fake_title_llm("Giao task quy 3 cho Nam")

    processed = await retitle_pending_conversations(db_session, llm)

    assert processed == 1
    await db_session.refresh(conv)
    assert conv.title == "Giao task quy 3 cho Nam"
    assert conv.title_locked is True
    assert len(llm.calls) == 1


async def test_retitle_bo_qua_conversation_da_locked(db_session):
    conv = await _mk_conv_with_reply(db_session, title_locked=True)
    llm = _fake_title_llm()

    processed = await retitle_pending_conversations(db_session, llm)

    assert processed == 0
    assert len(llm.calls) == 0
    await db_session.refresh(conv)
    assert conv.title == "tin nhan dau tien cat 60 ky tu"


async def test_retitle_bo_qua_conversation_chua_co_ai_tra_loi(db_session):
    conv = Conversation(workspace_id=uuid.uuid4(), user_id=uuid.uuid4(), title="cho AI tra loi")
    db_session.add(conv)
    await db_session.flush()
    db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                           role=MessageRole.user, content=[{"type": "text", "text": "hoi gi do"}]))
    await db_session.commit()
    llm = _fake_title_llm()

    processed = await retitle_pending_conversations(db_session, llm)

    assert processed == 0
    await db_session.refresh(conv)
    assert conv.title == "cho AI tra loi"


async def test_retitle_gioi_han_batch_size(db_session):
    for _ in range(3):
        await _mk_conv_with_reply(db_session)
    llm = FakeLLMClient(turns=[
        [TextDelta(text=f"Tieu de {i}"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)]
        for i in range(2)
    ])

    processed = await retitle_pending_conversations(db_session, llm, batch_size=2)

    assert processed == 2


async def test_retitle_loi_llm_khong_lock_thu_lai_luot_sau(db_session, monkeypatch):
    conv = await _mk_conv_with_reply(db_session)

    class _BoomLLM:
        model = "fake"
        calls: list = []

        async def stream(self, *, system, messages, tools):
            raise RuntimeError("gateway loi")
            yield  # pragma: no cover - làm hàm thành async generator hợp lệ

    processed = await retitle_pending_conversations(db_session, _BoomLLM())

    assert processed == 0
    await db_session.refresh(conv)
    assert conv.title_locked is False
