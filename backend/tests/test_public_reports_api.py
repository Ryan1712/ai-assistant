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
