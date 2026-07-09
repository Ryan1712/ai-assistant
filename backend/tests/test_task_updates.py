import pytest
from sqlalchemy import select

from app.models import Notification, Task
from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


async def _setup(client):
    """CEO + m1 + e1(m1) + e2(m2); task gán e1."""
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    m2 = await _invite_and_join(client, ceo_h, "manager", "m2@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    e2 = await _invite_and_join(client, ceo_h, "employee", "e2@a.vn", m2["user"]["id"])
    pid = (await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P"})).json()["id"]
    tid = (await client.post("/api/v1/tasks", headers=ceo_h,
                             json={"project_id": pid, "title": "T"})).json()["id"]
    await client.post(f"/api/v1/tasks/{tid}/assignees", headers=ceo_h,
                      json={"user_id": e1["user"]["id"]})
    return ceo_h, m1, m2, e1, e2, tid


@pytest.mark.asyncio
async def test_assignee_updates_and_task_syncs(client, db_session):
    ceo_h, m1, m2, e1, e2, tid = await _setup(client)
    r = await client.post(f"/api/v1/tasks/{tid}/updates", headers=_h(e1),
                          json={"content": "da xong 50%", "percent": 50,
                                "status": "in_progress"})
    assert r.status_code == 201
    task = (await db_session.execute(select(Task))).scalar_one()
    assert task.percent == 50
    assert task.status.value == "in_progress"


@pytest.mark.asyncio
async def test_update_notifications_fanout(client, db_session):
    ceo_h, m1, m2, e1, e2, tid = await _setup(client)
    await client.post(f"/api/v1/tasks/{tid}/updates", headers=_h(e1),
                      json={"content": "update", "percent": 10})
    notes = (await db_session.execute(select(Notification).where(
        Notification.type == "task_update"))).scalars().all()
    recipients = {str(n.recipient_id) for n in notes}
    # manager cua tac gia + CEO goc (tac gia e1 la assignee duy nhat -> khong tu nhan)
    assert m1["user"]["id"] in recipients
    assert e1["user"]["id"] not in recipients
    assert len(recipients) == 2  # m1 + root CEO


@pytest.mark.asyncio
async def test_manager_updates_subordinate_task(client):
    ceo_h, m1, m2, e1, e2, tid = await _setup(client)
    assert (await client.post(f"/api/v1/tasks/{tid}/updates", headers=_h(m1),
                              json={"percent": 60})).status_code == 201


@pytest.mark.asyncio
async def test_unrelated_users_denied(client):
    ceo_h, m1, m2, e1, e2, tid = await _setup(client)
    # e2 khong thay task -> 404
    assert (await client.post(f"/api/v1/tasks/{tid}/updates", headers=_h(e2),
                              json={"percent": 1})).status_code == 404
    # m2 khong thay task (khong duoc gan, khong owner) -> 404
    assert (await client.get(f"/api/v1/tasks/{tid}/updates", headers=_h(m2))).status_code == 404


@pytest.mark.asyncio
async def test_list_updates_newest_first(client):
    ceo_h, m1, m2, e1, e2, tid = await _setup(client)
    await client.post(f"/api/v1/tasks/{tid}/updates", headers=_h(e1), json={"content": "1"})
    await client.post(f"/api/v1/tasks/{tid}/updates", headers=_h(e1), json={"content": "2"})
    lst = (await client.get(f"/api/v1/tasks/{tid}/updates", headers=_h(e1))).json()
    assert [u["content"] for u in lst] == ["2", "1"]
