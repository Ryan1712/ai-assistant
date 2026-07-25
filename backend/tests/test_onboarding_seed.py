import uuid

from app.models import Conversation, Message, MessageRole


async def test_message_co_cot_is_seed_default_false(db_session):
    conv = Conversation(workspace_id=uuid.uuid4(), user_id=uuid.uuid4())
    db_session.add(conv)
    await db_session.flush()
    msg = Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                 role=MessageRole.assistant, content=[{"type": "text", "text": "chao"}])
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    assert msg.is_seed is False
