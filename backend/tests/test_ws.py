import pytest

from app import security
from app.api.ws import WebSocketAuthError, authorize_ws, stream_events
from app.models import Conversation, Role, User, Workspace


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


@pytest.mark.asyncio
async def test_authorize_ws_accepts_owner_token(db_session):
    ws, ceo, conv = await _world(db_session)
    token = security.create_access_token(user_id=str(ceo.id), workspace_id=str(ws.id),
                                         role=ceo.role.value)
    result = await authorize_ws(db_session, token, conv.id)
    assert result.id == conv.id


@pytest.mark.asyncio
async def test_authorize_ws_rejects_invalid_token(db_session):
    ws, ceo, conv = await _world(db_session)
    with pytest.raises(WebSocketAuthError):
        await authorize_ws(db_session, "not-a-real-token", conv.id)


@pytest.mark.asyncio
async def test_authorize_ws_rejects_conversation_of_another_user(db_session):
    ws, ceo, conv = await _world(db_session)
    other = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
                role=Role.employee)
    db_session.add(other)
    await db_session.flush()
    await db_session.commit()
    token = security.create_access_token(user_id=str(other.id), workspace_id=str(ws.id),
                                         role=other.role.value)
    with pytest.raises(WebSocketAuthError):
        await authorize_ws(db_session, token, conv.id)  # conv thuộc ceo, không phải other


@pytest.mark.asyncio
async def test_stream_events_forwards_every_event_in_order():
    async def fake_subscription():
        yield {"type": "token", "text": "a"}
        yield {"type": "request_done"}

    sent = []

    async def fake_send_json(event):
        sent.append(event)

    await stream_events(fake_send_json, fake_subscription())

    assert sent == [{"type": "token", "text": "a"}, {"type": "request_done"}]
