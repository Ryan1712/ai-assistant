import pytest

from tests.conftest import _ceo_headers, _invite_and_join


@pytest.mark.asyncio
async def test_employee_cannot_change_role_via_rest(client):
    ceo_h = await _ceo_headers(client)
    mgr = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    emp = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn",
                                 manager_id=mgr["user"]["id"])
    emp_h = {"Authorization": f"Bearer {emp['access_token']}"}

    r = await client.post(f"/api/v1/users/{mgr['user']['id']}/change-role", headers=emp_h,
                          json={"new_role": "employee"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_change_manager_only_via_rest(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    m2 = await _invite_and_join(client, ceo_h, "manager", "m2@a.vn")
    emp = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn",
                                 manager_id=m1["user"]["id"])

    r = await client.post(f"/api/v1/users/{emp['user']['id']}/change-role", headers=ceo_h,
                          json={"new_manager_id": m2["user"]["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["manager_id"] == m2["user"]["id"]


@pytest.mark.asyncio
async def test_promote_employee_to_manager_via_rest(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    emp = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn",
                                 manager_id=m1["user"]["id"])

    r = await client.post(f"/api/v1/users/{emp['user']['id']}/change-role", headers=ceo_h,
                          json={"new_role": "manager"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "manager"


@pytest.mark.asyncio
async def test_demote_manager_with_dependents_requires_successor_via_rest(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    m2 = await _invite_and_join(client, ceo_h, "manager", "m2@a.vn")
    await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", manager_id=m1["user"]["id"])

    r = await client.post(f"/api/v1/users/{m1['user']['id']}/change-role", headers=ceo_h,
                          json={"new_role": "employee", "new_manager_id": m2["user"]["id"]})
    assert r.status_code == 422
    assert r.json()["detail"] == "successor_required"
