import pytest

from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


@pytest.mark.asyncio
async def test_default_plan_is_basic_with_limits(client):
    ceo_h = await _ceo_headers(client)
    r = await client.get("/api/v1/subscription", headers=ceo_h)
    assert r.status_code == 200
    assert r.json()["plan"] == "basic"
    assert r.json()["limits"]["projects"] == 5


@pytest.mark.asyncio
async def test_only_ceo_switches_plan(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    denied = await client.patch("/api/v1/subscription", headers=_h(m1),
                                json={"plan": "advanced"})
    assert denied.status_code == 403
    ok = await client.patch("/api/v1/subscription", headers=ceo_h,
                            json={"plan": "advanced"})
    assert ok.status_code == 200
    assert ok.json()["plan"] == "advanced"
    # advanced: limits không còn (null)
    assert (await client.get("/api/v1/subscription", headers=ceo_h)).json()["limits"] is None


@pytest.mark.asyncio
async def test_basic_project_limit_enforced(client):
    ceo_h = await _ceo_headers(client)
    for i in range(5):
        r = await client.post("/api/v1/projects", headers=ceo_h, json={"name": f"P{i}"})
        assert r.status_code == 201
    sixth = await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P5"})
    assert sixth.status_code == 403
    assert sixth.json()["detail"] == "plan_limit_reached"
    # nâng gói → tạo được
    await client.patch("/api/v1/subscription", headers=ceo_h, json={"plan": "advanced"})
    again = await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P5"})
    assert again.status_code == 201


@pytest.mark.asyncio
async def test_basic_skill_and_member_limits_enforced(client, monkeypatch):
    from app import plans
    monkeypatch.setitem(plans.BASIC_LIMITS, "skills", 1)
    monkeypatch.setitem(plans.BASIC_LIMITS, "members", 2)  # CEO + 1

    ceo_h = await _ceo_headers(client)
    ok = await client.post("/api/v1/skills", headers=ceo_h,
                           json={"name": "S1", "kind": "knowledge", "content": "c"})
    assert ok.status_code == 201
    denied = await client.post("/api/v1/skills", headers=ceo_h,
                               json={"name": "S2", "kind": "knowledge", "content": "c"})
    assert denied.status_code == 403

    await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")  # member thứ 2 OK
    over = await client.post("/api/v1/invites", headers=ceo_h,
                             json={"role": "manager", "manager_id": None})
    assert over.status_code == 403
    assert over.json()["detail"] == "plan_limit_reached"
