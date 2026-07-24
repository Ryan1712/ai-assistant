import uuid
from app.models import Conversation


async def test_conversation_co_cot_session_model_defaults(db_session):
    conv = Conversation(workspace_id=uuid.uuid4(), user_id=uuid.uuid4())
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    assert conv.rolling_summary == ""
    assert conv.summary_through_at is None
    assert conv.archived_at is None
