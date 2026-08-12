import uuid

import pytest

from app import security
from tests.conftest import _ceo_headers


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


async def _ceo_with_headers(client):
    """Trả (headers, workspace_id) cho CEO vừa signup.

    GAP đã biết: UserOut (app/schemas.py) không có field workspace_id, nên
    KHÔNG thể lấy workspace_id qua GET /api/v1/users/me (sẽ KeyError). Thay
    vào đó decode thẳng JWT access_token bằng app.security.decode_access_token
    — payload chứa claim "ws" (xem app/security.py create_access_token, không
    phải "workspace_id").
    """
    headers = await _ceo_headers(client)
    payload = security.decode_access_token(headers["Authorization"].removeprefix("Bearer "))
    ws_id = payload["ws"]
    return headers, ws_id


@pytest.mark.asyncio
async def test_ceo_crud_and_publish_flow(client, storage_dir, monkeypatch):
    ceo_h, ws_id = await _ceo_with_headers(client)

    r = await client.post("/api/v1/public-reports", headers=ceo_h,
                          data={"title": "Q3", "description": "desc"},
                          files={"file": ("q3.pdf", b"%PDF-x", "application/pdf")})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert r.json()["status"] == "draft"

    upd = await client.patch(f"/api/v1/public-reports/{rid}", headers=ceo_h,
                             json={"title": "Q3 updated"})
    assert upd.status_code == 200
    assert upd.json()["title"] == "Q3 updated"

    pub = await client.post(f"/api/v1/public-reports/{rid}/publish", headers=ceo_h)
    assert pub.status_code == 200
    assert pub.json()["status"] == "published"

    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "public_app_bundle_ids", "com.9learning.app")
    monkeypatch.setattr(get_settings(), "public_report_workspace_id", ws_id)

    listed = await client.get("/api/v1/public-reports",
                              headers={"X-App-Bundle-Id": "com.9learning.app"})
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    detail = await client.get(f"/api/v1/public-reports/{rid}",
                              headers={"X-App-Bundle-Id": "com.9learning.app"})
    assert detail.status_code == 200

    content = await client.get(f"/api/v1/public-reports/{rid}/content",
                               headers={"X-App-Bundle-Id": "com.9learning.app"})
    assert content.status_code == 200
    assert content.content == b"%PDF-x"

    unpub = await client.post(f"/api/v1/public-reports/{rid}/unpublish", headers=ceo_h)
    assert unpub.json()["status"] == "draft"
    listed_after = await client.get("/api/v1/public-reports",
                                    headers={"X-App-Bundle-Id": "com.9learning.app"})
    assert listed_after.json() == []

    dele = await client.delete(f"/api/v1/public-reports/{rid}", headers=ceo_h)
    assert dele.status_code == 204


@pytest.mark.asyncio
async def test_bundle_id_disabled_by_default_401(client, storage_dir):
    r = await client.get("/api/v1/public-reports",
                         headers={"X-App-Bundle-Id": "com.9learning.app"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_non_ceo_cannot_write(client, storage_dir):
    from tests.conftest import _invite_and_join
    ceo_h, ws_id = await _ceo_with_headers(client)
    manager = await _invite_and_join(client, ceo_h, "manager", "m@a.vn")
    m_h = _h(manager)
    r = await client.post("/api/v1/public-reports", headers=m_h,
                          data={"title": "X"},
                          files={"file": ("a.pdf", b"x", "application/pdf")})
    assert r.status_code == 403

    # Non-CEO cũng không được PATCH/publish/unpublish/DELETE report có thật (do CEO tạo).
    created = await client.post("/api/v1/public-reports", headers=ceo_h,
                                data={"title": "Real report"},
                                files={"file": ("r.pdf", b"x", "application/pdf")})
    assert created.status_code == 201, created.text
    rid = created.json()["id"]

    patch_r = await client.patch(f"/api/v1/public-reports/{rid}", headers=m_h,
                                 json={"title": "Hacked"})
    assert patch_r.status_code == 403

    publish_r = await client.post(f"/api/v1/public-reports/{rid}/publish", headers=m_h)
    assert publish_r.status_code == 403

    unpublish_r = await client.post(f"/api/v1/public-reports/{rid}/unpublish", headers=m_h)
    assert unpublish_r.status_code == 403

    delete_r = await client.delete(f"/api/v1/public-reports/{rid}", headers=m_h)
    assert delete_r.status_code == 403


@pytest.mark.asyncio
async def test_bundle_id_never_leaks_draft(client, storage_dir, monkeypatch):
    ceo_h, ws_id = await _ceo_with_headers(client)
    r = await client.post("/api/v1/public-reports", headers=ceo_h,
                          data={"title": "Draft only"},
                          files={"file": ("d.pdf", b"x", "application/pdf")})
    rid = r.json()["id"]

    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "public_app_bundle_ids", "com.9learning.app")
    monkeypatch.setattr(get_settings(), "public_report_workspace_id", ws_id)

    detail = await client.get(f"/api/v1/public-reports/{rid}",
                              headers={"X-App-Bundle-Id": "com.9learning.app"})
    assert detail.status_code == 404


@pytest.mark.asyncio
async def test_bundle_id_never_leaks_other_workspace(client, storage_dir, monkeypatch):
    """Report published ở workspace A không được lộ khi bundle-id trỏ workspace B."""
    ceo_a_h, ws_a_id = await _ceo_with_headers(client)
    other_signup = {
        "workspace_name": "Cong ty B", "email": "ceo-b@a.vn", "password": "secret123",
        "full_name": "Sep B", "device_uuid": "dev-2", "device_name": "",
    }
    resp_signup = await client.post("/api/v1/auth/signup-workspace", json=other_signup)
    assert resp_signup.status_code == 201, resp_signup.text
    ws_b_id = security.decode_access_token(resp_signup.json()["access_token"])["ws"]
    assert ws_b_id != ws_a_id

    r = await client.post("/api/v1/public-reports", headers=ceo_a_h,
                          data={"title": "A's report"},
                          files={"file": ("a.pdf", b"x", "application/pdf")})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    pub = await client.post(f"/api/v1/public-reports/{rid}/publish", headers=ceo_a_h)
    assert pub.status_code == 200
    assert pub.json()["status"] == "published"

    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "public_app_bundle_ids", "com.9learning.app")
    monkeypatch.setattr(get_settings(), "public_report_workspace_id", ws_b_id)

    listed = await client.get("/api/v1/public-reports",
                              headers={"X-App-Bundle-Id": "com.9learning.app"})
    assert listed.status_code == 200
    assert listed.json() == []

    detail = await client.get(f"/api/v1/public-reports/{rid}",
                              headers={"X-App-Bundle-Id": "com.9learning.app"})
    assert detail.status_code == 404
