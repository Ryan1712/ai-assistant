import pytest

from tests.conftest import _ceo_headers, _invite_and_join


@pytest.mark.asyncio
async def test_employee_cannot_offboard_via_rest(client):
    ceo_h = await _ceo_headers(client)
    mgr = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    emp = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn",
                                 manager_id=mgr["user"]["id"])
    emp_h = {"Authorization": f"Bearer {emp['access_token']}"}

    r = await client.post(f"/api/v1/users/{mgr['user']['id']}/offboard", headers=emp_h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_offboard_without_successor_locks_only(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")

    r = await client.post(f"/api/v1/users/{m1['user']['id']}/offboard", headers=ceo_h, json={})
    assert r.status_code == 200, r.text
    assert r.json() == {"locked": True, "successor_id": None, "tasks_reassigned": 0,
                        "projects_reassigned": 0, "reports_reassigned": 0}

    login = await client.post("/api/v1/auth/login", json={
        "email": "m1@a.vn", "password": "pw123456", "device_uuid": "d", "device_name": "",
    })
    assert login.status_code == 403


@pytest.mark.asyncio
async def test_offboard_with_successor_reassigns_direct_report(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    m2 = await _invite_and_join(client, ceo_h, "manager", "m2@a.vn")
    await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", manager_id=m1["user"]["id"])

    r = await client.post(f"/api/v1/users/{m1['user']['id']}/offboard", headers=ceo_h,
                          json={"successor_id": m2["user"]["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["reports_reassigned"] == 1


@pytest.mark.asyncio
async def test_invalid_successor_returns_422(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")

    r = await client.post(f"/api/v1/users/{m1['user']['id']}/offboard", headers=ceo_h,
                          json={"successor_id": m1["user"]["id"]})
    assert r.status_code == 422
    assert r.json()["detail"] == "invalid_successor"
