import pytest

from tests.conftest import _ceo_headers, _invite_and_join


@pytest.mark.asyncio
async def test_user_out_includes_manager_id_and_status(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])

    listed = (await client.get("/api/v1/users", headers=ceo_h)).json()
    e1_out = next(u for u in listed if u["email"] == "e1@a.vn")
    assert e1_out["manager_id"] == m1["user"]["id"]
    assert e1_out["status"] == "active"

    ceo_out = next(u for u in listed if u["email"] == "ceo@a.vn")
    assert ceo_out["manager_id"] is None
    assert ceo_out["status"] == "active"

    me = (await client.get("/api/v1/users/me", headers=ceo_h)).json()
    assert "manager_id" in me
    assert "status" in me
