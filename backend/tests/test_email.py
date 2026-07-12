import pytest

from app.agent.tools import SENSITIVE_TOOLS, call_tool
from app.services import email_service
from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


@pytest.fixture(autouse=True)
def _reset_mock_email():
    email_service.mock_email_client.sent.clear()
    yield
    email_service.mock_email_client.sent.clear()


async def _world(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    e2 = await _invite_and_join(client, ceo_h, "employee", "e2@a.vn", m1["user"]["id"])
    return ceo_h, m1, e1, e2


@pytest.mark.asyncio
async def test_matrix_employee_to_employee_forbidden(client, db_session):
    ceo_h, m1, e1, e2 = await _world(client)
    from app.models import User
    e1_user = await db_session.get(User, __import__("uuid").UUID(e1["user"]["id"]))
    result = await call_tool(db_session, e1_user, "send_email",
                             {"recipient_id": e2["user"]["id"], "subject": "hi", "body": "x"})
    assert result["error"] == "forbidden"


@pytest.mark.asyncio
async def test_employee_to_ceo_and_manager_ok_and_logged(client, db_session):
    ceo_h, m1, e1, e2 = await _world(client)
    import uuid as uuid_mod
    from app.models import User
    e1_user = await db_session.get(User, uuid_mod.UUID(e1["user"]["id"]))
    ok = await call_tool(db_session, e1_user, "send_email",
                         {"recipient_id": m1["user"]["id"], "subject": "bao cao",
                          "body": "noi dung"})
    assert ok.get("error") is None
    assert len(email_service.mock_email_client.sent) == 1

    # inbox của m1 có mail, sent của e1 có mail
    inbox = await client.get("/api/v1/emails?box=inbox", headers=_h(m1))
    assert [m["subject"] for m in inbox.json()] == ["bao cao"]
    sent = await client.get("/api/v1/emails?box=sent", headers=_h(e1))
    assert len(sent.json()) == 1


@pytest.mark.asyncio
async def test_send_email_is_sensitive_tool(client):
    assert "send_email" in SENSITIVE_TOOLS


@pytest.mark.asyncio
async def test_cross_workspace_recipient_404(client, db_session):
    ceo_h, m1, e1, e2 = await _world(client)
    b = await client.post("/api/v1/auth/signup-workspace", json={
        "workspace_name": "B", "email": "ceo@b.vn", "password": "secret123",
        "full_name": "B", "device_uuid": "db", "device_name": "",
    })
    import uuid as uuid_mod
    from app.models import User
    ceo_a = (await db_session.execute(
        __import__("sqlalchemy").select(User).where(User.email == "ceo@a.vn")
    )).scalar_one()
    result = await call_tool(db_session, ceo_a, "send_email",
                             {"recipient_id": b.json()["user"]["id"], "subject": "s",
                              "body": "b"})
    assert result["error"] == "not_found"
