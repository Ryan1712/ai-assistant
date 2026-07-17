import pytest

from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


async def _task_assigned_to_employee(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    pid = (await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P"})).json()["id"]
    tid = (await client.post("/api/v1/tasks", headers=ceo_h,
                             json={"project_id": pid, "title": "T"})).json()["id"]
    await client.post(f"/api/v1/tasks/{tid}/assignees", headers=ceo_h,
                      json={"user_id": e1["user"]["id"]})
    return ceo_h, _h(e1), tid


@pytest.mark.asyncio
async def test_recipient_sees_own_notification(client):
    _, e1_h, tid = await _task_assigned_to_employee(client)

    resp = await client.get("/api/v1/notifications", headers=e1_h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    n = body[0]
    assert n["type"] == "task_assigned"
    assert n["payload"]["task_id"] == tid
    assert n["read_at"] is None


@pytest.mark.asyncio
async def test_other_user_does_not_see_notification(client):
    ceo_h, e1_h, _ = await _task_assigned_to_employee(client)

    resp = await client.get("/api/v1/notifications", headers=ceo_h)
    assert resp.json() == []


@pytest.mark.asyncio
async def test_unread_only_filter(client):
    _, e1_h, _ = await _task_assigned_to_employee(client)
    n = (await client.get("/api/v1/notifications", headers=e1_h)).json()[0]

    assert (await client.post(f"/api/v1/notifications/{n['id']}/read",
                              headers=e1_h)).status_code == 204

    all_notifs = await client.get("/api/v1/notifications", headers=e1_h)
    assert all_notifs.json()[0]["read_at"] is not None

    unread = await client.get("/api/v1/notifications?unread_only=true", headers=e1_h)
    assert unread.json() == []


@pytest.mark.asyncio
async def test_mark_all_read(client):
    _, e1_h, _ = await _task_assigned_to_employee(client)

    assert (await client.post("/api/v1/notifications/read-all",
                              headers=e1_h)).status_code == 204

    unread = await client.get("/api/v1/notifications?unread_only=true", headers=e1_h)
    assert unread.json() == []


@pytest.mark.asyncio
async def test_cannot_mark_others_notification_read(client):
    ceo_h, e1_h, _ = await _task_assigned_to_employee(client)
    n = (await client.get("/api/v1/notifications", headers=e1_h)).json()[0]

    resp = await client.post(f"/api/v1/notifications/{n['id']}/read", headers=ceo_h)
    assert resp.status_code == 404
