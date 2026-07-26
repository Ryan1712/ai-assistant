import pytest

from tests.conftest import _ceo_headers, _invite_and_join


@pytest.mark.asyncio
async def test_add_employee_route_name_only(client):
    headers = await _ceo_headers(client)
    resp = await client.post("/api/v1/employees", headers=headers,
                             json={"full_name": "Duy Linh"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["full_name"] == "Duy Linh"
    assert body["email"] is None
    assert "role" not in body
    assert "activation_code" not in body


@pytest.mark.asyncio
async def test_add_employee_route_with_email(client):
    headers = await _ceo_headers(client)
    resp = await client.post("/api/v1/employees", headers=headers,
                             json={"full_name": "Nam", "email": "nam@a.vn"})
    assert resp.status_code == 201
    assert resp.json()["email"] == "nam@a.vn"


@pytest.mark.asyncio
async def test_add_employee_route_non_ceo_403(client):
    headers = await _ceo_headers(client)
    mgr = await _invite_and_join(client, headers, "manager", "m1@a.vn")
    mgr_headers = {"Authorization": f"Bearer {mgr['access_token']}"}
    resp = await client.post("/api/v1/employees", headers=mgr_headers,
                             json={"full_name": "X"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_old_invites_route_gone(client):
    headers = await _ceo_headers(client)
    resp = await client.post("/api/v1/invites", headers=headers,
                             json={"full_name": "X", "email": "x@a.vn",
                                   "role": "manager", "manager_id": None})
    assert resp.status_code == 404
