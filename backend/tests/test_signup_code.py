import pytest

from tests.conftest import SIGNUP, _ceo_headers, _invite_and_join

# POST /api/v1/auth/signup-code tắt tạm (comment out ở app/api/auth.py) - product
# quyết định nhân viên không còn tự đăng nhập vào app (2026-07-23). Test nào gọi
# thẳng route này skip tạm, không xóa - bật lại route thì bỏ skip là chạy được ngay.
_SIGNUP_CODE_DISABLED = "POST /auth/signup-code tam tat - nhan vien khong con dang nhap (2026-07-23)"


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


def _signup_code_body(code, email="nv@a.vn"):
    return {"invite_code": code, "email": email, "password": "pw123456",
            "full_name": "NV Moi", "device_uuid": "d-" + email, "device_name": "iPhone"}


@pytest.mark.skip(reason=_SIGNUP_CODE_DISABLED)
@pytest.mark.asyncio
async def test_ceo_reads_code_and_employee_self_signs_up(client):
    ceo_h = await _ceo_headers(client)
    r = await client.get("/api/v1/workspace/invite-code", headers=ceo_h)
    assert r.status_code == 200
    code = r.json()["invite_code"]
    assert len(code) == 8

    join = await client.post("/api/v1/auth/signup-code", json=_signup_code_body(code))
    assert join.status_code == 201, join.text
    assert join.json()["user"]["role"] == "employee"
    assert "access_token" in join.json()

    # thiết bị được log
    uid = join.json()["user"]["id"]
    devices = await client.get(f"/api/v1/users/{uid}/devices", headers=ceo_h)
    assert devices.status_code == 200
    assert devices.json()[0]["device_uuid"] == "d-nv@a.vn"


@pytest.mark.skip(reason=_SIGNUP_CODE_DISABLED)
@pytest.mark.asyncio
async def test_wrong_code_404(client):
    await _ceo_headers(client)
    r = await client.post("/api/v1/auth/signup-code", json=_signup_code_body("XXXXXXXX"))
    assert r.status_code == 404
    assert r.json()["detail"] == "invalid_invite_code"


@pytest.mark.skip(reason=_SIGNUP_CODE_DISABLED)
@pytest.mark.asyncio
async def test_rotate_kills_old_code(client):
    ceo_h = await _ceo_headers(client)
    old = (await client.get("/api/v1/workspace/invite-code", headers=ceo_h)).json()["invite_code"]
    rotated = await client.post("/api/v1/workspace/invite-code/rotate", headers=ceo_h)
    assert rotated.status_code == 200
    new = rotated.json()["invite_code"]
    assert new != old
    dead = await client.post("/api/v1/auth/signup-code", json=_signup_code_body(old))
    assert dead.status_code == 404
    alive = await client.post("/api/v1/auth/signup-code", json=_signup_code_body(new))
    assert alive.status_code == 201


@pytest.mark.asyncio
async def test_non_ceo_cannot_see_or_rotate_code(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    assert (await client.get("/api/v1/workspace/invite-code", headers=_h(m1))).status_code == 403
    assert (await client.post("/api/v1/workspace/invite-code/rotate",
                              headers=_h(m1))).status_code == 403


@pytest.mark.skip(reason=_SIGNUP_CODE_DISABLED)
@pytest.mark.asyncio
async def test_member_limit_applies_to_code_signup(client, monkeypatch):
    from app import plans
    monkeypatch.setitem(plans.BASIC_LIMITS, "members", 1)  # chỉ còn CEO
    ceo_h = await _ceo_headers(client)
    code = (await client.get("/api/v1/workspace/invite-code", headers=ceo_h)).json()["invite_code"]
    r = await client.post("/api/v1/auth/signup-code", json=_signup_code_body(code))
    assert r.status_code == 403
    assert r.json()["detail"] == "plan_limit_reached"
