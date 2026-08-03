import uuid

import pytest

from app.models import ChatRequest, Conversation, Message, MessageRole, Role, User, Workspace
from tests.conftest import _ceo_headers


async def _world_with_message(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add(conv)
    await db_session.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="hello", queue_position=1.0)
    db_session.add(req)
    await db_session.flush()
    msg = Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                  role=MessageRole.assistant, content=[{"type": "text", "text": "hi"}])
    db_session.add(msg)
    await db_session.commit()
    return ws, ceo, conv, req, msg


@pytest.mark.asyncio
async def test_message_out_includes_chat_request_id(client, db_session):
    ws, ceo, conv, req, msg = await _world_with_message(db_session)
    from app import security
    from app.models import Role
    token = security.create_access_token(user_id=str(ceo.id), workspace_id=str(ws.id), role=ceo.role)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"/api/v1/conversations/{conv.id}/messages", headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["chat_request_id"] == str(req.id)
