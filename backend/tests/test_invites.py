import pytest

SIGNUP = {
    "workspace_name": "Cong ty A", "email": "ceo@a.vn", "password": "secret123",
    "full_name": "Sep", "device_uuid": "dev-1", "device_name": "",
}


async def _ceo_headers(client):
    resp = await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _invite_and_join(client, headers, role, email, manager_id=None):
    inv = await client.post("/api/v1/invites", headers=headers,
                            json={"role": role, "manager_id": manager_id})
    assert inv.status_code == 201, inv.text
    join = await client.post("/api/v1/auth/signup-invite", json={
        "token": inv.json()["token"], "email": email, "password": "pw123456",
        "full_name": email, "device_uuid": "d-" + email, "device_name": "",
    })
    assert join.status_code == 201, join.text
    return join.json()


@pytest.mark.asyncio
async def test_full_invite_flow(client):
    headers = await _ceo_headers(client)
    mgr = await _invite_and_join(client, headers, "manager", "m1@a.vn")
    emp = await _invite_and_join(client, headers, "employee", "e1@a.vn",
                                 manager_id=mgr["user"]["id"])
    assert emp["user"]["role"] == "employee"


@pytest.mark.asyncio
async def test_employee_invite_requires_manager(client):
    headers = await _ceo_headers(client)
    resp = await client.post("/api/v1/invites", headers=headers,
                             json={"role": "employee", "manager_id": None})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invite_single_use(client):
    headers = await _ceo_headers(client)
    inv = await client.post("/api/v1/invites", headers=headers,
                            json={"role": "manager", "manager_id": None})
    token = inv.json()["token"]
    body = {"token": token, "email": "m2@a.vn", "password": "pw123456",
            "full_name": "M2", "device_uuid": "d", "device_name": ""}
    assert (await client.post("/api/v1/auth/signup-invite", json=body)).status_code == 201
    body["email"] = "m3@a.vn"
    assert (await client.post("/api/v1/auth/signup-invite", json=body)).status_code == 400


@pytest.mark.asyncio
async def test_non_ceo_cannot_invite(client):
    headers = await _ceo_headers(client)
    mgr = await _invite_and_join(client, headers, "manager", "m1@a.vn")
    mgr_headers = {"Authorization": f"Bearer {mgr['access_token']}"}
    resp = await client.post("/api/v1/invites", headers=mgr_headers,
                             json={"role": "employee", "manager_id": None})
    assert resp.status_code == 403
