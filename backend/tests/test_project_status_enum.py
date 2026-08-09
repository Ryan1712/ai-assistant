"""Finding #21 (audit 2026-07-26, re-verify 2026-08-08, LOW): Project.status
là str tự do (không Enum như Task.status/Directive.status) -- CEO PATCH
status thành chuỗi bất kỳ (kể cả typo/rỗng) không bị chặn ở request boundary."""
import pytest

from tests.conftest import _ceo_headers


@pytest.mark.asyncio
async def test_patch_project_status_gia_tri_khong_hop_le_tra_422(client):
    ceo_h = await _ceo_headers(client)
    proj = (await client.post("/api/v1/projects", json={"name": "P", "goal": "g"},
                              headers=ceo_h)).json()

    resp = await client.patch(f"/api/v1/projects/{proj['id']}",
                              json={"status": "typo_khong_hop_le"}, headers=ceo_h)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_project_status_gia_tri_hop_le_tra_200(client):
    ceo_h = await _ceo_headers(client)
    proj = (await client.post("/api/v1/projects", json={"name": "P", "goal": "g"},
                              headers=ceo_h)).json()

    resp = await client.patch(f"/api/v1/projects/{proj['id']}",
                              json={"status": "on_hold"}, headers=ceo_h)
    assert resp.status_code == 200
    assert resp.json()["status"] == "on_hold"
