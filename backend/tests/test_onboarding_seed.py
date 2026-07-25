import uuid

from sqlalchemy import select

from app.models import Conversation, Message, MessageRole
from app.services import auth_service


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


async def test_signup_workspace_seed_conversation_va_message(db_session):
    user, access, refresh = await auth_service.signup_workspace(
        db_session, workspace_name="Cong ty B", email="ceo2@a.vn",
        password="secret123", full_name="Sep 2",
        device_uuid="dev-onb-1", device_name="",
    )

    convs = (await db_session.execute(select(Conversation).where(
        Conversation.workspace_id == user.workspace_id))).scalars().all()
    assert len(convs) == 1
    assert convs[0].user_id == user.id
    assert convs[0].archived_at is None

    msgs = (await db_session.execute(select(Message).where(
        Message.conversation_id == convs[0].id))).scalars().all()
    assert len(msgs) == 1
    seed = msgs[0]
    assert seed.role == MessageRole.assistant
    assert seed.is_seed is True
    assert seed.chat_request_id is None
    assert seed.content[0]["type"] == "text"
    assert len(seed.content[0]["text"]) > 0


SIGNUP_API = {
    "workspace_name": "Cong ty E", "email": "ceo-e@a.vn", "password": "secret123",
    "full_name": "Sep E", "device_uuid": "dev-onb-2", "device_name": "",
}


async def test_seed_message_co_is_seed_true_qua_api(client):
    resp = await client.post("/api/v1/auth/signup-workspace", json=SIGNUP_API)
    assert resp.status_code == 201, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    active = await client.get("/api/v1/conversations/active", headers=headers)
    conv_id = active.json()["id"]
    msgs = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    assert msgs.status_code == 200
    body = msgs.json()
    assert len(body) == 1
    assert body[0]["is_seed"] is True
