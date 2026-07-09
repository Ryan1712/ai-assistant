import pytest
from sqlalchemy import select as sa_select

from app.models import SkillUsageLog
from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


@pytest.mark.asyncio
async def test_ceo_creates_skill_with_v1_and_bumps_version(client):
    ceo_h = await _ceo_headers(client)
    r = await client.post("/api/v1/skills", headers=ceo_h,
                          json={"name": "Quy trinh bao cao", "kind": "knowledge",
                                "content": "Buoc 1..."})
    assert r.status_code == 201
    sid = r.json()["id"]
    assert r.json()["latest_version"] == 1
    v2 = await client.post(f"/api/v1/skills/{sid}/versions", headers=ceo_h,
                           json={"content": "Buoc 1 (sua)..."})
    assert v2.status_code == 201
    assert v2.json()["version"] == 2


@pytest.mark.asyncio
async def test_non_ceo_cannot_create_or_version(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    r = await client.post("/api/v1/skills", headers=_h(m1),
                          json={"name": "X", "kind": "knowledge", "content": "c"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_grant_and_list_visibility(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    s = await client.post("/api/v1/skills", headers=ceo_h,
                          json={"name": "S", "kind": "knowledge", "content": "c"})
    sid = s.json()["id"]
    g = await client.post(f"/api/v1/skills/{sid}/grants", headers=ceo_h,
                          json={"user_id": e1["user"]["id"]})
    assert g.status_code == 201
    assert len((await client.get("/api/v1/skills", headers=_h(e1))).json()) == 1
    assert (await client.get("/api/v1/skills", headers=_h(m1))).json() == []
    assert len((await client.get("/api/v1/skills", headers=ceo_h)).json()) == 1


@pytest.mark.asyncio
async def test_grant_cross_workspace_422(client):
    ceo_h = await _ceo_headers(client)
    s = await client.post("/api/v1/skills", headers=ceo_h,
                          json={"name": "S", "kind": "knowledge", "content": "c"})
    b = await client.post("/api/v1/auth/signup-workspace", json={
        "workspace_name": "B", "email": "ceo@b.vn", "password": "secret123",
        "full_name": "B", "device_uuid": "db", "device_name": "",
    })
    r = await client.post(f"/api/v1/skills/{s.json()['id']}/grants", headers=ceo_h,
                          json={"user_id": b.json()["user"]["id"]})
    assert r.status_code == 422


async def _skill_on_task(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    pid = (await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P"})).json()["id"]
    tid = (await client.post("/api/v1/tasks", headers=ceo_h,
                             json={"project_id": pid, "title": "T"})).json()["id"]
    await client.post(f"/api/v1/tasks/{tid}/assignees", headers=ceo_h,
                      json={"user_id": e1["user"]["id"]})
    sid = (await client.post("/api/v1/skills", headers=ceo_h,
                             json={"name": "S", "kind": "knowledge", "task_id": tid,
                                   "content": "huong dan v1"})).json()["id"]
    await client.post(f"/api/v1/skills/{sid}/grants", headers=ceo_h,
                      json={"user_id": e1["user"]["id"]})
    return ceo_h, e1, tid, sid


@pytest.mark.asyncio
async def test_use_skill_composes_two_layers(client, db_session):
    ceo_h, e1, tid, sid = await _skill_on_task(client)
    # e1 cap nhat tien do -> task_state phai song
    await client.post(f"/api/v1/tasks/{tid}/updates", headers=_h(e1),
                      json={"content": "50% roi", "percent": 50, "status": "in_progress"})
    # CEO sua noi dung skill -> version 2
    await client.post(f"/api/v1/skills/{sid}/versions", headers=ceo_h,
                      json={"content": "huong dan v2"})

    used = await client.get(f"/api/v1/skills/{sid}/use", headers=_h(e1))
    assert used.status_code == 200
    data = used.json()
    assert data["version"] == 2
    assert data["content"] == "huong dan v2"
    assert data["task_state"]["percent"] == 50
    assert data["task_state"]["status"] == "in_progress"
    assert data["task_state"]["latest_updates"][0]["content"] == "50% roi"

    log = (await db_session.execute(sa_select(SkillUsageLog))).scalars().all()
    assert len(log) == 1
    assert log[0].version == 2


@pytest.mark.asyncio
async def test_use_skill_requires_grant(client):
    ceo_h, e1, tid, sid = await _skill_on_task(client)
    m2 = await _invite_and_join(client, ceo_h, "manager", "m2@a.vn")
    assert (await client.get(f"/api/v1/skills/{sid}/use", headers=_h(m2))).status_code == 403
    assert (await client.get(f"/api/v1/skills/{sid}/use", headers=ceo_h)).status_code == 200
