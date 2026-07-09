import pytest

from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


async def _task_with_two_employees(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    e2 = await _invite_and_join(client, ceo_h, "employee", "e2@a.vn", m1["user"]["id"])
    pid = (await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P"})).json()["id"]
    tid = (await client.post("/api/v1/tasks", headers=ceo_h,
                             json={"project_id": pid, "title": "T"})).json()["id"]
    for u in (e1, e2):
        await client.post(f"/api/v1/tasks/{tid}/assignees", headers=ceo_h,
                          json={"user_id": u["user"]["id"]})
    return ceo_h, e1, e2, tid


@pytest.mark.asyncio
async def test_two_employees_same_task_can_discuss(client):
    ceo_h, e1, e2, tid = await _task_with_two_employees(client)
    assert (await client.post(f"/api/v1/tasks/{tid}/comments", headers=_h(e1),
                              json={"content": "phan cua toi xong"})).status_code == 201
    lst = await client.get(f"/api/v1/tasks/{tid}/comments", headers=_h(e2))
    assert lst.status_code == 200
    assert lst.json()[0]["content"] == "phan cua toi xong"
    assert (await client.post(f"/api/v1/tasks/{tid}/comments", headers=_h(e2),
                              json={"content": "ok toi tiep"})).status_code == 201


@pytest.mark.asyncio
async def test_outsider_cannot_see_comments(client):
    ceo_h, e1, e2, tid = await _task_with_two_employees(client)
    m2 = await _invite_and_join(client, ceo_h, "manager", "m2@a.vn")
    assert (await client.get(f"/api/v1/tasks/{tid}/comments", headers=_h(m2))).status_code == 404
    assert (await client.post(f"/api/v1/tasks/{tid}/comments", headers=_h(m2),
                              json={"content": "x"})).status_code == 404
