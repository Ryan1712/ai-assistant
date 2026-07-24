from tests.conftest import _ceo_headers


async def test_active_tao_moi_khi_chua_co(client):
    headers = await _ceo_headers(client)
    r = await client.get("/api/v1/conversations/active", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"]
    assert body["archived_at"] is None


async def test_active_tra_lai_cung_conv(client):
    headers = await _ceo_headers(client)
    r1 = await client.get("/api/v1/conversations/active", headers=headers)
    r2 = await client.get("/api/v1/conversations/active", headers=headers)
    assert r1.json()["id"] == r2.json()["id"]  # chua can xoay -> giu nguyen


async def test_active_can_dang_nhap(client):
    r = await client.get("/api/v1/conversations/active")
    assert r.status_code == 401
