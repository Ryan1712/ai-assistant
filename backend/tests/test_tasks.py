import uuid as uuid_mod

import pytest
from sqlalchemy import select

from app.models import Notification
from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


async def _project(client, ceo_h, **kw):
    resp = await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P", **kw})
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_ceo_creates_task_and_assigns(client, db_session):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    pid = await _project(client, ceo_h)

    t = await client.post("/api/v1/tasks", headers=ceo_h,
                          json={"project_id": pid, "title": "Lam bao cao"})
    assert t.status_code == 201
    tid = t.json()["id"]

    a = await client.post(f"/api/v1/tasks/{tid}/assignees", headers=ceo_h,
                          json={"user_id": e1["user"]["id"]})
    assert a.status_code == 201
    # idempotent
    a2 = await client.post(f"/api/v1/tasks/{tid}/assignees", headers=ceo_h,
                           json={"user_id": e1["user"]["id"]})
    assert a2.status_code == 200
    # notification cho người được gán
    notes = (await db_session.execute(select(Notification).where(
        Notification.type == "task_assigned"))).scalars().all()
    assert len(notes) == 1
    assert str(notes[0].recipient_id) == e1["user"]["id"]

    detail = await client.get(f"/api/v1/tasks/{tid}", headers=_h(e1))
    assert detail.status_code == 200
    assert e1["user"]["id"] in detail.json()["assignee_ids"]


@pytest.mark.asyncio
async def test_non_ceo_cannot_create_or_assign(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    pid = await _project(client, ceo_h)
    r = await client.post("/api/v1/tasks", headers=_h(m1),
                          json={"project_id": pid, "title": "X"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_task_visibility_404_outside_scope(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    pid = await _project(client, ceo_h)
    t = await client.post("/api/v1/tasks", headers=ceo_h,
                          json={"project_id": pid, "title": "T"})
    tid = t.json()["id"]
    # e1 chưa được gán -> không thấy
    assert (await client.get(f"/api/v1/tasks/{tid}", headers=_h(e1))).status_code == 404
    assert (await client.get("/api/v1/tasks", headers=_h(e1))).json() == []


@pytest.mark.asyncio
async def test_assign_cross_workspace_user_422(client):
    ceo_h = await _ceo_headers(client)
    pid = await _project(client, ceo_h)
    t = await client.post("/api/v1/tasks", headers=ceo_h,
                          json={"project_id": pid, "title": "T"})
    tid = t.json()["id"]
    b = await client.post("/api/v1/auth/signup-workspace", json={
        "workspace_name": "B", "email": "ceo@b.vn", "password": "secret123",
        "full_name": "B", "device_uuid": "db", "device_name": "",
    })
    r = await client.post(f"/api/v1/tasks/{tid}/assignees", headers=ceo_h,
                          json={"user_id": b.json()["user"]["id"]})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_ceo_patches_task(client):
    ceo_h = await _ceo_headers(client)
    pid = await _project(client, ceo_h)
    t = await client.post("/api/v1/tasks", headers=ceo_h,
                          json={"project_id": pid, "title": "T"})
    tid = t.json()["id"]

    patch = await client.patch(f"/api/v1/tasks/{tid}", headers=ceo_h,
                               json={"title": "T2", "priority": "high"})
    assert patch.status_code == 200
    body = patch.json()
    assert body["title"] == "T2"
    assert body["priority"] == "high"


@pytest.mark.asyncio
async def test_patch_task_explicit_null_ignored(client):
    ceo_h = await _ceo_headers(client)
    pid = await _project(client, ceo_h)
    t = await client.post("/api/v1/tasks", headers=ceo_h,
                          json={"project_id": pid, "title": "T"})
    tid = t.json()["id"]
    before_status = t.json()["status"]

    patch = await client.patch(f"/api/v1/tasks/{tid}", headers=ceo_h,
                               json={"status": None})
    assert patch.status_code == 200
    assert patch.json()["status"] == before_status


@pytest.mark.asyncio
async def test_patch_task_404_missing_or_cross_workspace(client):
    ceo_h = await _ceo_headers(client)
    pid = await _project(client, ceo_h)
    t = await client.post("/api/v1/tasks", headers=ceo_h,
                          json={"project_id": pid, "title": "T"})
    tid = t.json()["id"]

    # nonexistent task_id
    missing = await client.patch(f"/api/v1/tasks/{uuid_mod.uuid4()}", headers=ceo_h,
                                 json={"title": "X"})
    assert missing.status_code == 404

    # cross-workspace: CEO of workspace B cannot patch workspace A's task
    b = await client.post("/api/v1/auth/signup-workspace", json={
        "workspace_name": "B", "email": "ceo2@b.vn", "password": "secret123",
        "full_name": "B", "device_uuid": "db2", "device_name": "",
    })
    b_h = {"Authorization": f"Bearer {b.json()['access_token']}"}
    cross = await client.patch(f"/api/v1/tasks/{tid}", headers=b_h, json={"title": "X"})
    assert cross.status_code == 404
