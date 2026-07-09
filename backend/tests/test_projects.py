import pytest

from tests.conftest import _ceo_headers, _invite_and_join


def _h(joined):
    return {"Authorization": f"Bearer {joined['access_token']}"}


@pytest.mark.asyncio
async def test_ceo_creates_and_patches_project(client):
    ceo_h = await _ceo_headers(client)
    resp = await client.post("/api/v1/projects", headers=ceo_h,
                             json={"name": "Website", "goal": "Ra mat Q4"})
    assert resp.status_code == 201
    pid = resp.json()["id"]
    patch = await client.patch(f"/api/v1/projects/{pid}", headers=ceo_h,
                               json={"status": "paused"})
    assert patch.status_code == 200
    assert patch.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_non_ceo_cannot_create_project(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    resp = await client.post("/api/v1/projects", headers=_h(m1), json={"name": "X"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_project_owner_validated(client):
    import uuid as uuid_mod
    ceo_h = await _ceo_headers(client)
    resp = await client.post("/api/v1/projects", headers=ceo_h,
                             json={"name": "X", "owner_id": str(uuid_mod.uuid4())})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_project_visibility(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    await client.post("/api/v1/projects", headers=ceo_h,
                      json={"name": "P-owned", "owner_id": m1["user"]["id"]})
    await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P-hidden"})

    ceo_sees = {p["name"] for p in (await client.get("/api/v1/projects", headers=ceo_h)).json()}
    assert ceo_sees == {"P-owned", "P-hidden"}
    m1_sees = {p["name"] for p in (await client.get("/api/v1/projects", headers=_h(m1))).json()}
    assert m1_sees == {"P-owned"}
