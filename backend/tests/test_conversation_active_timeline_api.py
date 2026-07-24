import uuid
from datetime import datetime, timedelta, timezone

from app.models import Conversation, Message, MessageRole, User
from sqlalchemy import select

from tests.conftest import _ceo_headers


async def test_active_tao_moi_khi_chua_co(client):
    headers = await _ceo_headers(client)
    r = await client.get("/api/v1/conversations/active", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"]
    assert body["archived_at"] is None


async def test_active_tra_lai_cung_conv(client):
    headers = await _ceo_headers(client)
    r1 = await client.get("/api/v1/conversations/active", headers=headers)
    r2 = await client.get("/api/v1/conversations/active", headers=headers)
    assert r1.json()["id"] == r2.json()["id"]  # chua can xoay -> giu nguyen


async def test_active_can_dang_nhap(client):
    r = await client.get("/api/v1/conversations/active")
    assert r.status_code == 401


async def _mk_msgs_for_ceo(client, headers, db_engine_session):
    """Tao 2 conversation cho CEO, moi cai 2 message, thoi gian tang dan."""
    # Lay ceo id qua /me
    me = (await client.get("/api/v1/users/me", headers=headers)).json()
    return me


async def test_timeline_xuyen_conversation_theo_thu_tu(client, db_session):
    headers = await _ceo_headers(client)
    me = (await client.get("/api/v1/users/me", headers=headers)).json()
    ceo_id = uuid.UUID(me["id"])
    # UserOut khong tra workspace_id (chi co trong model DB) -> lay qua db_session.
    ws_id = (await db_session.get(User, ceo_id)).workspace_id
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    c1 = Conversation(workspace_id=ws_id, user_id=ceo_id, created_at=base)
    c2 = Conversation(workspace_id=ws_id, user_id=ceo_id, created_at=base + timedelta(hours=1))
    db_session.add_all([c1, c2])
    await db_session.flush()
    for i, (c, t) in enumerate([(c1, 0), (c1, 1), (c2, 2), (c2, 3)]):
        db_session.add(Message(workspace_id=ws_id, conversation_id=c.id, role=MessageRole.user,
                               content=[{"type": "text", "text": f"m{t}"}],
                               created_at=base + timedelta(minutes=t)))
    await db_session.commit()

    r = await client.get("/api/v1/conversations/timeline?limit=3", headers=headers)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 3
    # newest-first
    texts = [b["text"] for m in rows for b in m["content"] if b.get("type") == "text"]
    assert texts == ["m3", "m2", "m1"]
    assert rows[0]["conversation_id"]

    # trang ke tiep (cu hon rows[-1])
    last = rows[-1]
    r2 = await client.get(
        f"/api/v1/conversations/timeline?limit=3&before_at={last['created_at']}"
        f"&before_id={last['id']}", headers=headers)
    texts2 = [b["text"] for m in r2.json() for b in m["content"] if b.get("type") == "text"]
    assert texts2 == ["m0"]


async def test_timeline_khong_lo_conv_user_khac(client, db_session):
    from tests.conftest import _invite_and_join
    headers = await _ceo_headers(client)
    # nhan vien khac
    other = await _invite_and_join(client, headers, "manager", "m@a.vn")
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    me = (await client.get("/api/v1/users/me", headers=headers)).json()
    # UserOut khong tra workspace_id (chi co trong model DB) -> lay qua db_session.
    ws_id = (await db_session.get(User, uuid.UUID(me["id"]))).workspace_id
    other_id = uuid.UUID(other["user"]["id"] if "user" in other else
                         (await client.get("/api/v1/users/me", headers=other_headers)).json()["id"])
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    c = Conversation(workspace_id=ws_id, user_id=other_id, created_at=base)
    db_session.add(c)
    await db_session.flush()
    db_session.add(Message(workspace_id=ws_id, conversation_id=c.id, role=MessageRole.user,
                           content=[{"type": "text", "text": "bi mat cua nguoi khac"}],
                           created_at=base))
    await db_session.commit()

    r = await client.get("/api/v1/conversations/timeline", headers=headers)
    texts = [b["text"] for m in r.json() for b in m["content"] if b.get("type") == "text"]
    assert "bi mat cua nguoi khac" not in texts
