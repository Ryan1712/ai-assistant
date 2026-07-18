import pytest

from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


@pytest.mark.asyncio
async def test_ceo_crud_instruction(client):
    ceo_h = await _ceo_headers(client)
    r = await client.post("/api/v1/instructions", headers=ceo_h,
                          json={"title": "Giong dieu", "content": "Ngan gon"})
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    assert r.json()["version"] == 1

    up = await client.patch(f"/api/v1/instructions/{iid}", headers=ceo_h,
                            json={"content": "Ngan gon, than thien"})
    assert up.status_code == 200
    assert up.json()["version"] == 2

    listed = await client.get("/api/v1/instructions", headers=ceo_h)
    assert listed.status_code == 200
    assert listed.json()[0]["content"] == "Ngan gon, than thien"

    dele = await client.delete(f"/api/v1/instructions/{iid}", headers=ceo_h)
    assert dele.status_code == 204
    assert (await client.get("/api/v1/instructions", headers=ceo_h)).json() == []


@pytest.mark.asyncio
async def test_non_ceo_forbidden(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    r = await client.post("/api/v1/instructions", headers=_h(m1),
                          json={"title": "X", "content": "y"})
    assert r.status_code == 403
    assert (await client.get("/api/v1/instructions", headers=_h(m1))).status_code == 403


@pytest.mark.asyncio
async def test_basic_plan_instruction_limit_enforced(client):
    ceo_h = await _ceo_headers(client)
    for i in range(10):
        r = await client.post("/api/v1/instructions", headers=ceo_h,
                              json={"title": f"T{i}", "content": "x"})
        assert r.status_code == 201
    over = await client.post("/api/v1/instructions", headers=ceo_h,
                             json={"title": "T10", "content": "x"})
    assert over.status_code == 403
    assert over.json()["detail"] == "plan_limit_reached"

    await client.patch("/api/v1/subscription", headers=ceo_h, json={"plan": "advanced"})
    ok = await client.post("/api/v1/instructions", headers=ceo_h,
                           json={"title": "T11", "content": "x"})
    assert ok.status_code == 201
