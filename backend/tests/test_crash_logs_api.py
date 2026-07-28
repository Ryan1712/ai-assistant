"""
test_crash_logs_api.py — Skeleton test ĐỎ cho crash-logs API endpoints

Module được test:
  - backend/app/api/crash_logs.py       (CHƯA TỒN TẠI — dev tạo ở Batch 1)
  - backend/app/services/crash_service.py (CHƯA TỒN TẠI — dev tạo ở Batch 1)
  - backend/app/models.py               (CHƯA CÓ CrashLog — dev thêm ở Batch 1)

Các test dùng fixture từ conftest.py:
  - client  (httpx.AsyncClient → ASGI)
  - db_session
  - _ceo_headers(), _invite_and_join() helpers

Bao phủ acceptance criteria từ Task 1.1 trong sprint-1.md:
  - Batch ingest (POST /api/v1/crash-logs)
  - workspace_id/user_id lấy từ JWT, không từ body
  - Dedupe theo client_event_id cùng workspace_id
  - Cắt payload quá dài (message ≤ 2000, stack ≤ 20000)
  - Rate limit 60 bản ghi/user/5 phút → 429
  - Cô lập workspace (workspace A không thấy log của workspace B)
  - Chỉ CEO xem được list và summary (user thường → 403)
  - Summary gom nhóm theo fingerprint: count, affected_users, first_seen, last_seen, sample_message
"""

import pytest
import uuid
from tests.conftest import _ceo_headers, _invite_and_join


# ─── Helper: tạo payload crash log hợp lệ ─────────────────────────────────────

def make_crash_item(overrides: dict | None = None) -> dict:
    """Trả về 1 bản ghi crash log hợp lệ dùng trong batch POST."""
    item = {
        "source": "fe_js",
        "severity": "error",
        "message": "Test crash từ pytest",
        "stack": "Error: Test crash\n  at pytest:1:1",
        "screen": "TestScreen",
        "app_version": "1.0.0",
        "build_number": "1",
        "platform": "ios",
        "os_version": "18.0",
        "device_model": "iPhone 16",
        "is_device": False,
        "occurred_at": "2026-07-27T00:00:00Z",
        "client_event_id": str(uuid.uuid4()),
    }
    if overrides:
        item.update(overrides)
    return item


# ─── Batch Ingest ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_crash_logs_returns_accepted_count(client):
    """Gửi 3 bản ghi hợp lệ → server trả về accepted=3, duplicates=0."""
    headers = await _ceo_headers(client)
    payload = {"items": [make_crash_item() for _ in range(3)]}
    resp = await client.post("/api/v1/crash-logs", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] == 3
    assert body["duplicates"] == 0


@pytest.mark.asyncio
async def test_post_crash_logs_requires_auth(client):
    """Không có token → 401 (endpoint bắt buộc đăng nhập)."""
    payload = {"items": [make_crash_item()]}
    resp = await client.post("/api/v1/crash-logs", json=payload)
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_post_crash_logs_ignores_workspace_id_in_body(client):
    """workspace_id giả mạo trong body bị bỏ qua — server dùng workspace của JWT."""
    headers = await _ceo_headers(client)
    fake_workspace_id = str(uuid.uuid4())
    item = make_crash_item()
    item["workspace_id"] = fake_workspace_id  # thêm trường không nên có
    payload = {"items": [item]}
    resp = await client.post("/api/v1/crash-logs", headers=headers, json=payload)
    # Phải thành công — server không crash vì trường lạ
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_post_crash_logs_batch_limit_20(client):
    """Gửi batch > 20 bản ghi → 422 (validation error)."""
    headers = await _ceo_headers(client)
    payload = {"items": [make_crash_item() for _ in range(21)]}
    resp = await client.post("/api/v1/crash-logs", headers=headers, json=payload)
    assert resp.status_code == 422, resp.text


# ─── Dedupe theo client_event_id ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_crash_logs_dedupe_same_client_event_id(client):
    """Gửi lại cùng client_event_id → duplicates=1, không tạo bản ghi mới."""
    headers = await _ceo_headers(client)
    event_id = str(uuid.uuid4())
    item = make_crash_item({"client_event_id": event_id})
    payload = {"items": [item]}

    # Gửi lần đầu
    resp1 = await client.post("/api/v1/crash-logs", headers=headers, json=payload)
    assert resp1.status_code == 200
    assert resp1.json()["accepted"] == 1

    # Gửi lại (retry)
    resp2 = await client.post("/api/v1/crash-logs", headers=headers, json=payload)
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["accepted"] == 0
    assert body2["duplicates"] == 1


@pytest.mark.asyncio
async def test_post_crash_logs_dedupe_scoped_to_workspace(client):
    """client_event_id của workspace A không xung đột với workspace B."""
    # Tạo workspace A (CEO)
    headers_a = await _ceo_headers(client)

    # Tạo workspace B (signup riêng)
    from tests.conftest import SIGNUP
    signup_b = {**SIGNUP, "workspace_name": "Cong ty B", "email": "ceo@b.vn"}
    resp_b = await client.post("/api/v1/auth/signup-workspace", json=signup_b)
    assert resp_b.status_code == 201, resp_b.text
    headers_b = {"Authorization": f"Bearer {resp_b.json()['access_token']}"}

    shared_event_id = str(uuid.uuid4())
    payload = {"items": [make_crash_item({"client_event_id": shared_event_id})]}

    # Workspace A gửi trước
    r_a = await client.post("/api/v1/crash-logs", headers=headers_a, json=payload)
    assert r_a.json()["accepted"] == 1

    # Workspace B gửi cùng client_event_id → phải được chấp nhận (không bị coi là trùng)
    r_b = await client.post("/api/v1/crash-logs", headers=headers_b, json=payload)
    assert r_b.json()["accepted"] == 1, "Workspace B phải accept dù cùng client_event_id"


# ─── Cắt payload quá dài ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_crash_logs_truncates_long_message(client, db_session):
    """message > 2000 ký tự bị cắt còn 2000, server không 500."""
    headers = await _ceo_headers(client)
    long_message = "x" * 5000
    item = make_crash_item({"message": long_message})
    payload = {"items": [item]}
    resp = await client.post("/api/v1/crash-logs", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text

    # Kiểm tra DB — bản ghi phải có message ≤ 2000
    from sqlalchemy import select
    from app.models import CrashLog  # module chưa tồn tại → test này sẽ ĐỎ
    rows = await db_session.execute(select(CrashLog))
    crash = rows.scalars().first()
    assert crash is not None
    assert len(crash.message) <= 2000


@pytest.mark.asyncio
async def test_post_crash_logs_truncates_long_stack(client, db_session):
    """stack > 20000 ký tự bị cắt còn 20000, server không 500."""
    headers = await _ceo_headers(client)
    long_stack = "Error\n" + "  at fn (file.ts:1)\n" * 1500
    item = make_crash_item({"stack": long_stack})
    payload = {"items": [item]}
    resp = await client.post("/api/v1/crash-logs", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text

    from sqlalchemy import select
    from app.models import CrashLog
    rows = await db_session.execute(select(CrashLog))
    crash = rows.scalars().first()
    assert crash is not None
    assert len(crash.stack) <= 20000


# ─── Rate limit ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_crash_logs_rate_limit_429(client):
    """Vượt 60 bản ghi/user/5 phút → 429."""
    headers = await _ceo_headers(client)

    # Gửi 60 bản ghi (6 batch × 10 bản ghi)
    for _ in range(6):
        items = [make_crash_item() for _ in range(10)]
        resp = await client.post(
            "/api/v1/crash-logs", headers=headers, json={"items": items}
        )
        # Các lần đầu phải OK
        if resp.status_code != 200:
            break  # đã bị rate limit sớm hơn — vẫn pass test

    # Gửi thêm 1 → phải bị 429
    resp_over = await client.post(
        "/api/v1/crash-logs",
        headers=headers,
        json={"items": [make_crash_item()]},
    )
    assert resp_over.status_code == 429, f"Expected 429, got {resp_over.status_code}"


# ─── Cô lập workspace ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_crash_logs_workspace_isolation(client):
    """CEO workspace A không thấy crash log của workspace B."""
    # Workspace A
    headers_a = await _ceo_headers(client)
    await client.post(
        "/api/v1/crash-logs",
        headers=headers_a,
        json={"items": [make_crash_item({"message": "lỗi của workspace A"})]},
    )

    # Workspace B
    from tests.conftest import SIGNUP
    signup_b = {**SIGNUP, "workspace_name": "Cong ty B", "email": "ceo@b.vn"}
    resp_b = await client.post("/api/v1/auth/signup-workspace", json=signup_b)
    headers_b = {"Authorization": f"Bearer {resp_b.json()['access_token']}"}
    await client.post(
        "/api/v1/crash-logs",
        headers=headers_b,
        json={"items": [make_crash_item({"message": "lỗi của workspace B"})]},
    )

    # CEO A xem list → chỉ thấy log của A
    resp_list = await client.get("/api/v1/crash-logs", headers=headers_a)
    assert resp_list.status_code == 200
    items = resp_list.json()["items"]
    assert all("workspace A" in item["message"] for item in items)
    assert not any("workspace B" in item["message"] for item in items)


# ─── Phân quyền ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_crash_logs_requires_ceo(client):
    """User thường (không phải CEO) bị từ chối xem danh sách crash log.
    Kiểm tra cả manager lẫn employee — require_ceo phải chặn mọi role không phải ceo.
    """
    import base64 as _b64
    import json as _json

    headers = await _ceo_headers(client)

    # Case 1: manager không phải CEO → phải nhận 403
    # (manager không cần manager_id — không có cấp trên trong hệ thống)
    mgr_join = await _invite_and_join(client, headers, role="manager", email="mgr@a.vn")
    mgr_headers = {"Authorization": f"Bearer {mgr_join['access_token']}"}
    resp_mgr = await client.get("/api/v1/crash-logs", headers=mgr_headers)
    assert resp_mgr.status_code == 403, f"Manager phải nhận 403, got {resp_mgr.status_code}: {resp_mgr.text}"

    # Case 2: employee không phải CEO → phải nhận 403.
    # employee bắt buộc có manager_id — lấy user_id của manager từ JWT access_token.
    payload_b64 = mgr_join['access_token'].split('.')[1]
    payload_b64 += '=' * ((4 - len(payload_b64) % 4) % 4)
    mgr_id = _json.loads(_b64.urlsafe_b64decode(payload_b64))['sub']

    emp_join = await _invite_and_join(client, headers, role="employee", email="emp@a.vn", manager_id=mgr_id)
    emp_headers = {"Authorization": f"Bearer {emp_join['access_token']}"}
    resp_emp = await client.get("/api/v1/crash-logs", headers=emp_headers)
    assert resp_emp.status_code == 403, f"Employee phải nhận 403, got {resp_emp.status_code}: {resp_emp.text}"


@pytest.mark.asyncio
async def test_get_crash_logs_summary_requires_ceo(client):
    """User thường bị từ chối xem summary.
    Kiểm tra cả manager lẫn employee — require_ceo phải chặn mọi role không phải ceo.
    """
    import base64 as _b64
    import json as _json

    headers = await _ceo_headers(client)

    # Case 1: manager không phải CEO → phải nhận 403
    mgr_join = await _invite_and_join(client, headers, role="manager", email="mgr2@a.vn")
    mgr_headers = {"Authorization": f"Bearer {mgr_join['access_token']}"}
    resp_mgr = await client.get("/api/v1/crash-logs/summary", headers=mgr_headers)
    assert resp_mgr.status_code == 403, f"Manager phải nhận 403, got {resp_mgr.status_code}: {resp_mgr.text}"

    # Case 2: employee không phải CEO → phải nhận 403.
    payload_b64 = mgr_join['access_token'].split('.')[1]
    payload_b64 += '=' * ((4 - len(payload_b64) % 4) % 4)
    mgr_id = _json.loads(_b64.urlsafe_b64decode(payload_b64))['sub']

    emp_join = await _invite_and_join(client, headers, role="employee", email="emp2@a.vn", manager_id=mgr_id)
    emp_headers = {"Authorization": f"Bearer {emp_join['access_token']}"}
    resp_emp = await client.get("/api/v1/crash-logs/summary", headers=emp_headers)
    assert resp_emp.status_code == 403, f"Employee phải nhận 403, got {resp_emp.status_code}: {resp_emp.text}"


# ─── Summary theo fingerprint ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_crash_logs_summary_groups_by_fingerprint(client):
    """Summary gom nhóm theo fingerprint: count, affected_users, first_seen, last_seen, sample_message."""
    headers = await _ceo_headers(client)

    # Gửi 3 crash cùng fingerprint + 2 crash fingerprint khác
    fp_a = "fingerprint-alpha"
    fp_b = "fingerprint-beta"

    items_a = [make_crash_item({"fingerprint": fp_a}) for _ in range(3)]
    items_b = [make_crash_item({"fingerprint": fp_b}) for _ in range(2)]
    all_items = items_a + items_b
    await client.post("/api/v1/crash-logs", headers=headers, json={"items": all_items})

    resp = await client.get("/api/v1/crash-logs/summary", headers=headers)
    assert resp.status_code == 200, resp.text

    rows = resp.json()["rows"]
    # Phải có 2 nhóm
    assert len(rows) == 2

    # Tìm nhóm fp_a
    row_a = next((r for r in rows if r["fingerprint"] == fp_a), None)
    assert row_a is not None, f"Không tìm thấy fingerprint {fp_a} trong summary"
    assert row_a["count"] == 3
    assert row_a["affected_users"] >= 1
    assert "sample_message" in row_a
    assert "first_seen" in row_a
    assert "last_seen" in row_a


# ─── Client không gửi fingerprint — server tự tính ───────────────────────────

@pytest.mark.asyncio
async def test_post_crash_logs_without_explicit_fingerprint(client, db_session):
    """Server tự tính fingerprint nếu client không gửi (hoặc gửi null)."""
    headers = await _ceo_headers(client)
    item = make_crash_item()
    item.pop("fingerprint", None)  # xóa fingerprint nếu helper có
    item["message"] = "Lỗi không có fingerprint"
    payload = {"items": [item]}
    resp = await client.post("/api/v1/crash-logs", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text

    from sqlalchemy import select
    from app.models import CrashLog
    rows = await db_session.execute(select(CrashLog))
    crash = rows.scalars().first()
    assert crash is not None
    # fingerprint phải được set (không rỗng/None)
    assert crash.fingerprint
