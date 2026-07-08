import pytest

from tests.test_invites import SIGNUP, _ceo_headers, _invite_and_join


async def _team(client):
    """CEO + 2 manager + 2 employee (mỗi manager 1 nhân viên)."""
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    m2 = await _invite_and_join(client, ceo_h, "manager", "m2@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    e2 = await _invite_and_join(client, ceo_h, "employee", "e2@a.vn", m2["user"]["id"])
    def h(x): return {"Authorization": f"Bearer {x['access_token']}"}
    return ceo_h, h(m1), h(e1), h(e2)


@pytest.mark.asyncio
async def test_visibility_matrix(client):
    ceo_h, m1_h, e1_h, _ = await _team(client)

    all_users = (await client.get("/api/v1/users", headers=ceo_h)).json()
    assert len(all_users) == 5  # CEO thấy tất cả

    m1_sees = {u["email"] for u in (await client.get("/api/v1/users", headers=m1_h)).json()}
    assert m1_sees == {"m1@a.vn", "e1@a.vn"}  # manager: mình + nhân viên dưới quyền

    e1_sees = {u["email"] for u in (await client.get("/api/v1/users", headers=e1_h)).json()}
    assert e1_sees == {"e1@a.vn"}  # employee: chỉ mình


@pytest.mark.asyncio
async def test_devices_ceo_only(client):
    ceo_h, m1_h, _, _ = await _team(client)
    users = (await client.get("/api/v1/users", headers=ceo_h)).json()
    target = next(u for u in users if u["email"] == "m1@a.vn")

    ok = await client.get(f"/api/v1/users/{target['id']}/devices", headers=ceo_h)
    assert ok.status_code == 200 and len(ok.json()) >= 1

    denied = await client.get(f"/api/v1/users/{target['id']}/devices", headers=m1_h)
    assert denied.status_code == 403
