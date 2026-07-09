import pytest

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
