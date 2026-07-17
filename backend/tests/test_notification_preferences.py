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
async def test_default_preferences_all_enabled(client):
    ceo_h = await _ceo_headers(client)
    resp = await client.get("/api/v1/notifications/preferences", headers=ceo_h)
    assert resp.status_code == 200
    assert resp.json() == {}


@pytest.mark.asyncio
async def test_disabled_type_suppresses_notification(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    e1_h = _h(e1)

    resp = await client.patch("/api/v1/notifications/preferences", headers=e1_h,
                              json={"type": "task_assigned", "enabled": False})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"task_assigned": False}

    pid = (await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P"})).json()["id"]
    tid = (await client.post("/api/v1/tasks", headers=ceo_h,
                             json={"project_id": pid, "title": "T"})).json()["id"]
    await client.post(f"/api/v1/tasks/{tid}/assignees", headers=ceo_h,
                      json={"user_id": e1["user"]["id"]})

    notifs = await client.get("/api/v1/notifications", headers=e1_h)
    assert notifs.json() == []


@pytest.mark.asyncio
async def test_other_types_still_enabled_after_disabling_one(client):
    ceo_h, e1_h, tid = await _task_assigned_to_employee(client)
    await client.patch("/api/v1/notifications/preferences", headers=e1_h,
                       json={"type": "task_assigned", "enabled": False})

    await client.post(f"/api/v1/tasks/{tid}/updates", headers=ceo_h,
                      json={"content": "cap nhat", "percent": 10})

    notifs = (await client.get("/api/v1/notifications", headers=e1_h)).json()
    assert any(n["type"] == "task_update" for n in notifs)


@pytest.mark.asyncio
async def test_preference_is_per_user(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    e2 = await _invite_and_join(client, ceo_h, "employee", "e2@a.vn", m1["user"]["id"])
    e1_h, e2_h = _h(e1), _h(e2)

    await client.patch("/api/v1/notifications/preferences", headers=e1_h,
                       json={"type": "task_assigned", "enabled": False})

    pid = (await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P"})).json()["id"]
    tid = (await client.post("/api/v1/tasks", headers=ceo_h,
                             json={"project_id": pid, "title": "T"})).json()["id"]
    await client.post(f"/api/v1/tasks/{tid}/assignees", headers=ceo_h,
                      json={"user_id": e1["user"]["id"]})
    await client.post(f"/api/v1/tasks/{tid}/assignees", headers=ceo_h,
                      json={"user_id": e2["user"]["id"]})

    assert (await client.get("/api/v1/notifications", headers=e1_h)).json() == []
    e2_notifs = (await client.get("/api/v1/notifications", headers=e2_h)).json()
    assert any(n["type"] == "task_assigned" for n in e2_notifs)


@pytest.mark.asyncio
async def test_re_enabling_type_restores_notifications(client):
    ceo_h, e1_h, tid = await _task_assigned_to_employee(client)
    await client.patch("/api/v1/notifications/preferences", headers=e1_h,
                       json={"type": "task_update", "enabled": False})
    resp = await client.patch("/api/v1/notifications/preferences", headers=e1_h,
                              json={"type": "task_update", "enabled": True})
    assert resp.json() == {"task_update": True}

    await client.post(f"/api/v1/tasks/{tid}/updates", headers=ceo_h,
                      json={"content": "cap nhat", "percent": 20})
    notifs = (await client.get("/api/v1/notifications", headers=e1_h)).json()
    assert any(n["type"] == "task_update" for n in notifs)
