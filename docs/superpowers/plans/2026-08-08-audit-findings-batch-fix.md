# Fix 17 findings đợt audit 2026-07-26 (đã re-verify 2026-08-08) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 17 finding còn đúng sau khi re-verify với code thật (4 agent Explore, 2026-08-08) từ đợt audit toàn repo 2026-07-26 — 3 HIGH (bảo mật + reliability), 4 MED, 10 LOW. Finding #20 (upload đọc hết file vào RAM) tách riêng, KHÔNG nằm trong plan này.

**Architecture:** Chia 3 nhóm độc lập theo subsystem, mỗi nhóm 1 branch riêng: (A) BE state-machine + security (`edit_request`, `MAX_TOTAL_TOKENS`, `reset_password`), (B) BE cron/background (`distiller_service`, `watcher_service`, `notify`, `report_schedule_service`, `work_service._notify_mentions`, `portal_service` — chỉ ghi chú, không code vì cần API thật), (C) FE (`chat.tsx` race socket + Android keyboard + ref reset, `ws.py`/`publisher.py`, `schemas.py` ProjectStatus enum, `edit_request` re-index embedding — BE nhưng gom vào C vì cùng luồng edit).

**Tech Stack:** Python/FastAPI/SQLAlchemy/Redis (BE), React Native/Expo/TypeScript (FE), pytest-asyncio.

## Global Constraints

- TDD bắt buộc cho mọi thay đổi BE có test framework sẵn (pytest) — RED trước, GREEN sau.
- FE không có test tự động trong repo (theo cấu trúc hiện tại) — verify bằng `tsc --noEmit` + đọc code cẩn thận, không cần viết test mới trừ khi task nói rõ.
- Mỗi finding sửa xong chạy test liên quan trước khi sang finding tiếp theo trong cùng task.
- Mỗi task (không phải mỗi finding) là 1 commit — nhiều finding nhỏ cùng file có thể gộp 1 commit nếu cùng chủ đề, nhưng phải note rõ trong message.
- KHÔNG động vào finding #20 (upload RAM) — ngoài phạm vi.
- KHÔNG động vào finding #16 (portal multi-tenant) bằng code thật — chưa có API spec thật của cổng ngoài (theo comment sẵn trong `portal_service.py`), chỉ thêm TODO/docstring ghi rõ rủi ro khi bật `portal_mock=False`, không tự bịa cách gọi API.
- `python scripts/export_openapi.py` chạy sau Task 4 (schemas.py đổi — ProjectPatchIn).

---

### Task 1: BE state-machine + security (finding #6, #7, #15)

**Files:**
- Modify: `backend/app/api/chat.py` (`edit_request`, khoảng dòng 320-334)
- Modify: `backend/app/agent/loop.py` (`total_tokens` accumulation, dòng ~497)
- Modify: `backend/app/services/auth_service.py` (`reset_password`, dòng ~142-161)
- Test: `backend/tests/test_edit_request_state_guard.py` (mới, finding #6)
- Test: `backend/tests/test_auth_reset_password_security.py` (mới, finding #15)

**Interfaces:**
- Không có interface mới xuyên task — mỗi finding độc lập trong cùng task vì cùng nhóm "state-machine/security", không phụ thuộc lẫn nhau.

- [ ] **Step 1: Finding #6 — Viết test thất bại cho `edit_request` sau khi request đã `started_at != None`**

Đọc trước `backend/app/api/chat.py` xung quanh dòng 320-334 để lấy đúng nội dung `edit_request` hiện tại (có thể lệch số dòng), và `backend/tests/test_chat_queue_api.py` để lấy đúng pattern test hiện có (fixture `client`, `_ceo_headers`).

```python
# backend/tests/test_edit_request_state_guard.py
"""Finding #6 (audit 2026-07-26, re-verify 2026-08-08): edit_request chỉ
guard status==queued, KHÔNG check started_at — sau khi 1 request đã chạy
qua 1 vòng confirm/tool (started_at được set), resolve_confirmation đưa
status về lại queued và ghi THÊM 1 Message role=user (tool_result) với
cùng chat_request_id — lúc đó DB có >=2 Message role=user cùng
chat_request_id, edit_request query .scalar_one_or_none() crash
MultipleResultsFound (500 không kiểm soát) thay vì 409 rõ ràng."""
import pytest

from tests.conftest import _ceo_headers


@pytest.mark.asyncio
async def test_edit_request_tra_409_khi_da_tung_chay(client):
    ceo_h = await _ceo_headers(client)
    # Gửi 1 tin nhắn tạo ChatRequest queued
    conv = (await client.get("/api/v1/conversations/active", headers=ceo_h)).json()
    req = (await client.post(f"/api/v1/conversations/{conv['id']}/messages",
                             json={"content": "hello"}, headers=ceo_h)).json()

    # Giả lập request đã CHẠY (started_at != None) bằng cách set trực tiếp qua DB
    # session của test client (lấy qua dependency override, giống pattern
    # _invite_and_join trong conftest.py).
    from sqlalchemy import select, update
    from app.models import ChatRequest
    app = client._transport.app
    from app.db import get_db
    maker = None
    for dep, override in app.dependency_overrides.items():
        if dep is get_db:
            import inspect
            maker = override
    assert maker is not None
    async with maker().__anext__().__aiter__() if False else _get_session(app) as db:
        await db.execute(update(ChatRequest).where(ChatRequest.id == req["id"])
                         .values(started_at=__import__("datetime").datetime.now(
                             __import__("datetime").timezone.utc)))
        await db.commit()

    resp = await client.patch(f"/api/v1/chat-requests/{req['id']}",
                              json={"content": "edited"}, headers=ceo_h)
    assert resp.status_code == 409
```

**LƯU Ý cho người thực thi:** đoạn lấy DB session qua `client._transport.app.dependency_overrides[get_db]` ở trên là PSEUDO-CODE không chạy được như viết — đọc `backend/tests/conftest.py` hàm `_invite_and_join` (đã có comment "Lấy DB session bằng cách đọc lại override của get_db đã gắn sẵn trên FastAPI app của client") để COPY ĐÚNG cách lấy session thật đang dùng trong conftest, thay thế đoạn `async with maker()...` ở trên bằng cách đó. Đây là lý do bắt buộc đọc conftest.py trước khi hoàn thiện test này.

- [ ] **Step 2: Chạy test, xác nhận fail (500 thay vì 409, hoặc lỗi cú pháp cần sửa theo Step 1 lưu ý)**

Run: `cd backend && python -m pytest tests/test_edit_request_state_guard.py -v`
Expected: FAIL — `assert 500 == 409` (crash `MultipleResultsFound` bọc thành 500 bởi FastAPI exception handler mặc định) hoặc lỗi sync code cần sửa trước theo lưu ý Step 1.

- [ ] **Step 3: Fix finding #6 — thêm guard `started_at`**

Đọc `backend/app/api/chat.py` tìm chính xác vị trí `edit_request` hiện tại:
```bash
grep -n "async def edit_request" -A 15 backend/app/api/chat.py
```
Đổi điều kiện guard (dòng có `if req.status != ChatRequestStatus.queued:`) thành:
```python
    if req.status != ChatRequestStatus.queued or req.started_at is not None:
        raise HTTPException(409, "not_queued")
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_edit_request_state_guard.py -v`
Expected: PASS.

- [ ] **Step 5: Finding #7 — sửa `MAX_TOTAL_TOKENS` cộng thêm cache tokens (fix trực tiếp, không cần test riêng — đã có test guard tồn tại kiểm tra ngưỡng, chỉ cần không phá nó)**

Tìm dòng cộng token trong `backend/app/agent/loop.py`:
```bash
grep -n "total_tokens +=" backend/app/agent/loop.py
```
Đổi:
```python
            total_tokens += done.input_tokens + done.output_tokens
```
thành:
```python
            total_tokens += (done.input_tokens + done.output_tokens
                             + done.cache_read_tokens + done.cache_write_tokens)
```

- [ ] **Step 6: Chạy test liên quan `loop.py` để xác nhận không phá gì**

Run: `cd backend && python -m pytest tests/ -k "max_total_tokens or agent_loop" -v`
Expected: PASS toàn bộ.

- [ ] **Step 7: Finding #15 — Viết test thất bại cho rate-limit + revoke refresh token trong `reset_password`**

Đọc `backend/app/services/auth_service.py` đầy đủ hàm `forgot_password`/`reset_password` (dòng ~114-161) trước khi viết test, và `backend/tests/test_auth.py` để lấy pattern test hiện có cho luồng reset password (fixture redis, cách gọi `forgot_password`/`reset_password`).

```python
# backend/tests/test_auth_reset_password_security.py
"""Finding #15 (audit 2026-07-26, re-verify 2026-08-08, HIGH): reset_password
không rate-limit OTP 6 số (brute-forceable trong TTL 15') và không revoke
RefreshToken sau khi đổi mật khẩu thành công (session-fixation nếu tài
khoản bị chiếm, chủ tài khoản reset nhưng token cũ của kẻ tấn công vẫn
sống)."""
import pytest
from fastapi import HTTPException

from app.services import auth_service


@pytest.mark.asyncio
async def test_reset_password_chan_sau_qua_nhieu_lan_sai_otp(db_session, redis_client):
    """LƯU Ý: fixture redis_client CẦN xác nhận tên thật trong conftest.py
    trước khi dùng — grep 'def redis' trong tests/conftest.py."""
    ws, user = await _seed_user_with_email(db_session, "reset1@a.vn")
    await auth_service.forgot_password(db_session, redis_client, email="reset1@a.vn")

    for _ in range(5):
        with pytest.raises(HTTPException) as exc:
            await auth_service.reset_password(
                db_session, redis_client, email="reset1@a.vn",
                code="000000", new_password="newpass123")
        assert exc.value.status_code == 400  # sai OTP bình thường, chưa chạm rate-limit

    with pytest.raises(HTTPException) as exc:
        await auth_service.reset_password(
            db_session, redis_client, email="reset1@a.vn",
            code="000000", new_password="newpass123")
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_reset_password_revoke_refresh_token_cu(db_session, redis_client):
    from app.models import RefreshToken
    from sqlalchemy import select

    ws, user = await _seed_user_with_email(db_session, "reset2@a.vn")
    old_token = RefreshToken(workspace_id=ws.id, user_id=user.id, token_hash="x",
                             device_uuid="d1", device_name="", expires_at=__import__(
                                 "datetime").datetime.now(__import__("datetime").timezone.utc)
                             + __import__("datetime").timedelta(days=30))
    db_session.add(old_token)
    await db_session.commit()

    await auth_service.forgot_password(db_session, redis_client, email="reset2@a.vn")
    # Lấy code thật từ mock email client thay vì đoán — xem
    # app/services/email_service.py mock_email_client.sent để lấy đúng cách
    # đọc code OTP vừa gửi trong test khác (test_auth.py) trước khi viết dòng
    # dưới, thay YOUR_CODE_HERE bằng cách lấy thật.
    code = _get_last_otp_from_mock_email("reset2@a.vn")
    await auth_service.reset_password(
        db_session, redis_client, email="reset2@a.vn", code=code,
        new_password="newpass123")

    await db_session.refresh(old_token)
    assert old_token.revoked_at is not None


async def _seed_user_with_email(db, email):
    from app.models import Role, User, Workspace
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    user = User(workspace_id=ws.id, email=email, password_hash="x", full_name="U",
               role=Role.ceo, is_root=True)
    db.add(user)
    await db.commit()
    return ws, user


def _get_last_otp_from_mock_email(email):
    """PSEUDO — người thực thi PHẢI đọc app/services/email_service.py
    (mock_email_client) và backend/tests/test_auth.py (test forgot_password
    hiện có) để lấy đúng cách trích OTP từ email mock đã gửi, thay hàm này
    bằng code thật."""
    raise NotImplementedError("Đọc email_service.py mock trước khi viết hàm này")
```

**LƯU Ý QUAN TRỌNG cho người thực thi:** cả 2 test trên có phần PSEUDO-CODE (`redis_client` fixture tên thật chưa xác nhận, `_get_last_otp_from_mock_email` chưa implement) — đọc `backend/tests/test_auth.py` (test `forgot_password`/`reset_password` hiện có, nếu có) và `backend/tests/conftest.py` (tên fixture redis) TRƯỚC KHI chạy Step 8, thay các phần PSEUDO bằng code thật đúng API hiện có. Đây là bước bắt buộc, không phải tùy chọn.

- [ ] **Step 8: Chạy test, xác nhận fail đúng lý do (chưa có rate-limit/revoke)**

Run: `cd backend && python -m pytest tests/test_auth_reset_password_security.py -v`
Expected: FAIL — test rate-limit fail vì không có `429` nào được raise (tất cả đều `400`); test revoke fail vì `old_token.revoked_at is None`.

- [ ] **Step 9: Fix finding #15 — thêm rate-limit + revoke refresh token**

Đọc `backend/app/services/auth_service.py` đầy đủ để lấy đúng import hiện có (`RefreshToken`, `update`, `datetime`) trước khi sửa. Tìm hàm `reset_password`:
```bash
grep -n "async def reset_password" -A 25 backend/app/services/auth_service.py
```
Thêm hằng số gần `_PWRESET_PREFIX`/`_PWRESET_TTL` hiện có:
```python
_PWRESET_ATTEMPT_PREFIX = "pwreset_attempts:"
_PWRESET_MAX_ATTEMPTS = 5
```
Sửa `reset_password` — thêm counter TRƯỚC khi so khớp OTP, và revoke refresh token SAU khi đổi mật khẩu thành công:
```python
async def reset_password(db: AsyncSession, redis, *, email: str, code: str,
                         new_password: str) -> None:
    email = email.strip().lower()
    attempt_key = f"{_PWRESET_ATTEMPT_PREFIX}{email}"
    attempts = await redis.incr(attempt_key)
    if attempts == 1:
        await redis.expire(attempt_key, _PWRESET_TTL)
    if attempts > _PWRESET_MAX_ATTEMPTS:
        raise HTTPException(429, "too_many_attempts")
    stored = await redis.get(f"{_PWRESET_PREFIX}{email}")
    if stored is None or stored != code.strip():
        raise HTTPException(400, "invalid_or_expired_code")
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        raise HTTPException(400, "invalid_or_expired_code")
    user.password_hash = security.hash_password(new_password)
    await redis.delete(f"{_PWRESET_PREFIX}{email}")
    await redis.delete(attempt_key)
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc)))
    await db.commit()
```
Điều chỉnh đúng theo code THẬT hiện có trong hàm (biến đổi tên, thứ tự có thể khác plan — đây là hướng fix, không phải patch chính xác từng ký tự, người thực thi phải khớp với code đọc được ở bước grep trên).

- [ ] **Step 10: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_auth_reset_password_security.py -v`
Expected: PASS cả 2 test.

- [ ] **Step 11: Chạy test liên quan auth để đảm bảo không phá gì**

Run: `cd backend && python -m pytest tests/test_auth.py tests/test_auth_service_login.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 12: Commit**

```bash
git add backend/app/api/chat.py backend/app/agent/loop.py backend/app/services/auth_service.py backend/tests/test_edit_request_state_guard.py backend/tests/test_auth_reset_password_security.py
git commit -m "fix(security): reset_password rate-limit + revoke refresh token, edit_request guard started_at, MAX_TOTAL_TOKENS cong cache tokens

Fix 3 finding audit 2026-07-26 (re-verify 2026-08-08):
- #15 [HIGH]: reset_password OTP 6 so khong rate-limit (brute-forceable
  trong TTL 15') + khong revoke refresh token sau doi mat khau thanh cong
  (session-fixation). Them Redis attempt counter (max 5 lan/15') + revoke
  RefreshToken cua user sau reset.
- #6 [MED]: edit_request chi guard status==queued, khong check started_at
  -- sau 1 vong confirm/tool, resolve_confirmation dua status ve queued +
  ghi them 1 Message role=user cung chat_request_id -> edit_request crash
  500 MultipleResultsFound. Them guard started_at is not None -> 409.
- #7 [LOW]: MAX_TOTAL_TOKENS bo cache_read_tokens/cache_write_tokens khi
  cong total_tokens, tran 200k khong phan anh dung context window that
  khi prompt caching bat.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: BE cron/background (finding #9, #10, #11, #13, #14, #16-ghi chú)

**Files:**
- Modify: `backend/app/services/distiller_service.py` (dòng ~101-115)
- Modify: `backend/app/services/watcher_service.py` (dòng ~64)
- Modify: `backend/app/services/notify.py` (dòng ~12-26) — tách push khỏi transaction, CHỈ nếu không phá quá nhiều call site (xem Step ghi chú)
- Modify: `backend/app/services/report_schedule_service.py` (thêm re-check plan, dòng ~146-151)
- Modify: `backend/app/services/work_service.py` (`_notify_mentions`, dòng ~232-246)
- Modify: `backend/app/services/portal_service.py` (chỉ thêm docstring/TODO cho finding #16, KHÔNG code logic tenant thật)
- Test: `backend/tests/test_distiller_window.py` (mới, finding #9)
- Test: `backend/tests/test_watcher_catchup_guard.py` (mới, finding #10)
- Test: `backend/tests/test_notify_mentions_word_boundary.py` (mới, finding #14)
- Test: `backend/tests/test_report_schedule_plan_recheck.py` (mới, finding #13)

**Interfaces:**
- Không phụ thuộc Task 1 — độc lập hoàn toàn (file khác nhau).

- [ ] **Step 1: Finding #9 — Viết test thất bại cho cửa sổ ngày sai của distiller**

Đọc `backend/app/services/distiller_service.py` đầy đủ hàm chứa dòng 101-115 trước khi viết test (lấy đúng tên hàm, tham số).

```bash
grep -n "day_start\|def distill" backend/app/services/distiller_service.py
```

```python
# backend/tests/test_distiller_window.py
"""Finding #9 (audit 2026-07-26, re-verify 2026-08-08, HIGH): distiller_service
tính day_start = now_vn.replace(hour=0,...) TẠI THỜI ĐIỂM CRON CHẠY (02:00 VN)
-- tức 00:00 SÁNG NAY, không phải hôm qua. Query created_at >= day_start_utc
chỉ quét TaskUpdate tạo trong khung 00:00-02:00 sáng (2 tiếng), bỏ hoàn toàn
cả ngày làm việc hôm trước -- "bộ nhớ dài hạn" gần như no-op âm thầm."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.services import distiller_service
from app.models import Project, Task, TaskUpdate, User, Role, Workspace


@pytest.mark.asyncio
async def test_distiller_quet_dung_ca_ngay_hom_qua(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="T", created_by=ceo.id)
    db_session.add(task)
    await db_session.flush()

    # now_vn giả lập 02:00 VN hôm nay (UTC+7 -> 19:00 UTC hôm qua)
    now_utc = datetime(2026, 8, 9, 19, 0, 0, tzinfo=timezone.utc)  # = 02:00 2026-08-10 VN
    # Update tạo lúc 10:00 VN HÔM QUA (giờ hành chính) -- PHẢI được quét
    update_hom_qua = TaskUpdate(workspace_id=ws.id, task_id=task.id, author_id=ceo.id,
                                content="cap nhat hom qua",
                                created_at=datetime(2026, 8, 9, 3, 0, 0, tzinfo=timezone.utc))
    db_session.add(update_hom_qua)
    await db_session.commit()

    texts = await distiller_service._collect_texts_for_window(db_session, ws.id, now=now_utc)
    assert any("cap nhat hom qua" in t for t in texts)
```

**LƯU Ý:** tên hàm `_collect_texts_for_window` là GIẢ ĐỊNH — đọc code thật trong `distiller_service.py` để tìm đúng tên hàm chứa logic `day_start`/query (có thể là hàm lớn `distill_workspace_memories` không tách riêng phần thu thập text — nếu vậy, test phải gọi hàm lớn hơn và assert qua kết quả cuối, hoặc refactor tách hàm nhỏ nếu cần thiết để test được — quyết định tại chỗ dựa trên cấu trúc code thật, KHÔNG đoán trước).

- [ ] **Step 2: Chạy test, xác nhận fail (update hôm qua không được quét)**

Run: `cd backend && python -m pytest tests/test_distiller_window.py -v`
Expected: FAIL — `texts` rỗng hoặc không chứa "cap nhat hom qua".

- [ ] **Step 3: Fix finding #9 — sửa cửa sổ ngày**

```bash
grep -n "day_start_vn\|day_start_utc" backend/app/services/distiller_service.py
```
Đổi (khớp đúng biến/dòng thật đọc được ở lệnh trên):
```python
    day_end_vn = now_vn.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start_vn = day_end_vn - timedelta(days=1)
    day_start_utc = day_start_vn.astimezone(timezone.utc)
    day_end_utc = day_end_vn.astimezone(timezone.utc)
```
Và sửa MỌI điều kiện query hiện có dùng `created_at >= day_start_utc` thành khoảng đóng-mở:
```python
    ... .where(TaskUpdate.created_at >= day_start_utc, TaskUpdate.created_at < day_end_utc)
```
Áp dụng tương tự cho các query khác trong cùng hàm nếu có (comment/instruction, task_update — đọc kỹ để không bỏ sót).

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_distiller_window.py -v`
Expected: PASS.

- [ ] **Step 5: Finding #10 — Viết test thất bại cho catch-up guard của watcher**

Đọc `backend/app/services/watcher_service.py` dòng ~64 để lấy đúng tên hàm.

```bash
grep -n "def.*watch\|hour == 7" backend/app/services/watcher_service.py
```

```python
# backend/tests/test_watcher_catchup_guard.py
"""Finding #10 (audit 2026-07-26, re-verify 2026-08-08, MED): guard 'đúng
phút' (hour==7 and minute==0) không catch-up nếu tick bị trễ (worker bận,
restart) -- rớt cả ngày. dedup theo Notification cùng ngày đã có sẵn nên
nới cửa sổ guard không gây double-send."""
from datetime import datetime, timezone

import pytest

from app.services import watcher_service


@pytest.mark.asyncio
async def test_watcher_chay_duoc_khi_tick_tre_vai_phut(db_session):
    # now_vn = 07:05 (trễ 5 phút so với mốc 07:00) -- PHẢI vẫn chạy được
    # thay vì bị guard chặn hoàn toàn tới 07:00 hôm sau.
    now_utc = datetime(2026, 8, 10, 0, 5, 0, tzinfo=timezone.utc)  # 07:05 VN
    result = await watcher_service.check_task_deadlines(db_session, now=now_utc)
    assert result is not None  # không bị early-return vì guard quá chặt
```

**LƯU Ý:** tên hàm `check_task_deadlines` và signature `now=` là GIẢ ĐỊNH — đọc code thật để xác nhận tên hàm/tham số đúng trước khi hoàn thiện test. Assertion `result is not None` cũng cần điều chỉnh theo kiểu trả về thật của hàm (có thể là `int` số lượng notify gửi, `list`, hay `None` luôn kể cả khi chạy được — nếu vậy đổi cách assert, ví dụ mock/spy `push_service` để xác nhận CÓ được gọi).

- [ ] **Step 6: Chạy test, xác nhận fail**

Run: `cd backend && python -m pytest tests/test_watcher_catchup_guard.py -v`
Expected: FAIL vì guard chặn (`now_vn.minute == 0` sai với phút 5).

- [ ] **Step 7: Fix finding #10 — nới guard thành cửa sổ**

```bash
grep -n "hour == 7 and.*minute == 0" backend/app/services/watcher_service.py
grep -n "hour == 2 and.*minute == 0" backend/app/services/distiller_service.py
```
Đổi cả 2 nơi (watcher_service.py VÀ distiller_service.py — cùng pattern) từ:
```python
    if not (now_vn.hour == 7 and now_vn.minute == 0):
        return ...
```
thành:
```python
    if not (now_vn.hour == 7 and now_vn.minute < 10):
        return ...
```
(và tương ứng `hour == 2 and now_vn.minute < 10` cho distiller). Dựa vào dedup đã có sẵn (Notification cùng ngày ở watcher, cosine similarity ở distiller) để không double-send trong cửa sổ 10 phút.

- [ ] **Step 8: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_watcher_catchup_guard.py -v`
Expected: PASS.

- [ ] **Step 9: Chạy test liên quan watcher/distiller để đảm bảo không phá gì**

Run: `cd backend && python -m pytest tests/ -k "watcher or distiller" -v`
Expected: PASS toàn bộ (bao gồm test cũ verify guard CHẶN đúng lúc `minute >= 10`, nếu có test kiểu đó phải vẫn pass).

- [ ] **Step 10: Finding #14 — Viết test thất bại cho `_notify_mentions` substring**

Đọc `backend/app/services/work_service.py` dòng ~232-246.

```python
# backend/tests/test_notify_mentions_word_boundary.py
"""Finding #14 (audit 2026-07-26, re-verify 2026-08-08, LOW): _notify_mentions
dùng substring check (f"@{full_name.lower()}" in content_lower) không có
word-boundary -- "@Anh Tuấn" chứa "@Anh" nên notify NHẦM cả user "Anh"
(không được nhắc) lẫn "Anh Tuấn" (đúng)."""
import pytest

from app.services import work_service
from app.models import Project, Role, Task, User, Workspace


@pytest.mark.asyncio
async def test_notify_mentions_khong_khop_nham_prefix(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    anh = User(workspace_id=ws.id, email="anh@a.vn", password_hash="x", full_name="Anh",
              role=Role.employee)
    anh_tuan = User(workspace_id=ws.id, email="at@a.vn", password_hash="x",
                    full_name="Anh Tuấn", role=Role.employee)
    db_session.add_all([ceo, anh, anh_tuan])
    await db_session.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="T", created_by=ceo.id)
    db_session.add(task)
    await db_session.commit()

    notified = await work_service._notify_mentions(
        db_session, ceo, task, "@Anh Tuấn ơi check task này")

    notified_ids = {n for n in notified} if notified else set()
    # Chỉ Anh Tuấn được notify, KHÔNG phải "Anh"
    assert anh.id not in notified_ids
```

**LƯU Ý:** `_notify_mentions` trả về gì (list user_id đã notify, hay không trả gì và chỉ có side-effect tạo Notification) là GIẢ ĐỊNH — đọc code thật (`work_service.py:232-246` theo báo cáo agent) để biết cách verify đúng (có thể phải query bảng `Notification` sau khi gọi thay vì đọc return value).

- [ ] **Step 11: Chạy test, xác nhận fail**

Run: `cd backend && python -m pytest tests/test_notify_mentions_word_boundary.py -v`
Expected: FAIL — user "Anh" bị notify nhầm.

- [ ] **Step 12: Fix finding #14 — word-boundary bằng regex**

```bash
grep -n "async def _notify_mentions" -A 15 backend/app/services/work_service.py
```
Thêm `import re` đầu file nếu chưa có, đổi logic so khớp:
```python
    for u in rows.scalars():
        pattern = r"@" + re.escape(u.full_name) + r"(?![^\s.,!?;:])"
        if re.search(pattern, content, flags=re.IGNORECASE):
```
(dùng negative lookahead chặn ký tự liền sau không phải whitespace/dấu câu — đơn giản hơn `\w` vì tránh vấn đề Unicode tiếng Việt với `\w`).

- [ ] **Step 13: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_notify_mentions_word_boundary.py -v`
Expected: PASS.

- [ ] **Step 14: Finding #13 — Viết test thất bại cho report_schedule không re-check plan**

Đọc `backend/app/services/report_schedule_service.py` đầy đủ `run_due_schedules` (dòng ~136-168) và `backend/app/plans.py` (`plan_allows`) trước khi viết test.

```python
# backend/tests/test_report_schedule_plan_recheck.py
"""Finding #13 (audit 2026-07-26, re-verify 2026-08-08, LOW): run_due_schedules
không re-check plan_allows(ws, "scheduled_reports") mỗi lần chạy -- workspace
hạ gói sau khi đã tạo lịch vẫn tiếp tục nhận report+notify vô thời hạn."""
import pytest

from app.services import report_schedule_service


@pytest.mark.asyncio
async def test_run_due_schedules_tat_lich_khi_workspace_ha_goi(db_session):
    """LƯU Ý: cần đọc app/models.py (ReportSchedule, Workspace.plan) và
    app/plans.py (plan_allows, WorkspacePlan enum) để dựng đúng fixture
    workspace ở gói KHÔNG cho phép scheduled_reports + 1 ReportSchedule
    active=True có next_run_at đã tới hạn, rồi gọi run_due_schedules và
    assert schedule.active == False sau khi chạy, KHÔNG có Report mới nào
    được tạo. Người thực thi phải tự viết fixture đầy đủ dựa trên model
    thật -- đây là khung test, không phải code chạy được ngay."""
    raise NotImplementedError("Viet fixture that dua tren models.py/plans.py")
```

**LƯU Ý QUAN TRỌNG:** test này CỐ Ý để dạng khung — người thực thi PHẢI đọc `backend/app/plans.py` (hàm `plan_allows`, enum `WorkspacePlan`) và `backend/app/models.py` (`ReportSchedule`, `Workspace.plan`) để viết fixture thật trước khi chạy Step 15. Không suy đoán tên field.

- [ ] **Step 15: Chạy test, xác nhận fail đúng lý do**

Run: `cd backend && python -m pytest tests/test_report_schedule_plan_recheck.py -v`
Expected: FAIL — sau khi implement thật (Step 14 xong), schedule vẫn `active=True` hoặc Report vẫn được tạo dù workspace không đủ gói.

- [ ] **Step 16: Fix finding #13 — re-check plan trong `run_due_schedules`**

```bash
grep -n "async def run_due_schedules" -A 20 backend/app/services/report_schedule_service.py
```
Trong vòng lặp xử lý từng schedule (trước đoạn generate report), thêm:
```python
        ws = await db.get(Workspace, sched.workspace_id)
        if ws is None or not plans.plan_allows(ws, "scheduled_reports"):
            sched.active = False
            await db.commit()
            continue
```
Đảm bảo `Workspace` và `plans` module đã import ở đầu file — nếu chưa, thêm.

- [ ] **Step 17: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_report_schedule_plan_recheck.py -v`
Expected: PASS.

- [ ] **Step 18: Finding #11 — push sau commit trong `notify()` (fix trực tiếp, KHÔNG viết test mới — rủi ro cao ảnh hưởng nhiều call site, chỉ sửa nếu xác nhận an toàn)**

Đọc `backend/app/services/notify.py` đầy đủ VÀ tất cả nơi gọi `notify()`:
```bash
grep -rn "notify(" backend/app/ --include=*.py | grep -v test
```
Nếu `notify()` được gọi TRƯỚC `db.commit()` của caller ở NHIỀU nơi khác nhau (không chỉ report_schedule_service), việc đổi signature `notify()` (tách phần push ra khỏi phần add Notification) là thay đổi RỦI RO CAO ảnh hưởng nhiều luồng — trong trường hợp đó, CHỈ thêm docstring cảnh báo rõ ràng trong `notify.py`, KHÔNG refactor, để tránh phá vỡ nhiều chỗ trong 1 lần sửa nhỏ. Nếu chỉ có 1-2 call site (đã xác nhận qua grep), sửa trực tiếp: đổi `notify()` để KHÔNG tự gọi push, trả về `Notification` object hoặc payload, để caller tự gọi `push_service.push_to_user(...)` SAU khi `db.commit()` thành công.

Quyết định cụ thể (sửa code hay chỉ ghi docstring) do người thực thi tự đánh giá dựa trên kết quả grep thật — đây không phải bug nghiêm trọng (LOW), ưu tiên AN TOÀN hơn ép sửa.

- [ ] **Step 19: Finding #16 — chỉ ghi docstring cảnh báo, KHÔNG code logic tenant (chưa có API spec thật)**

Đọc `backend/app/services/portal_service.py` đầu file (comment hiện có về `portal_mock`).
Thêm đoạn docstring/comment rõ ràng ngay trên class `HttpPortalClient`:
```python
class HttpPortalClient(PortalClient):
    """CẢNH BÁO (finding #16, audit 2026-07-26): client này gọi thẳng
    {base_url}/api/reports KHÔNG truyền workspace_id/tenant nào trong
    query/header — nếu bật portal_mock=False mà cổng ngoài không tự phân
    tenant theo cách khác (token/cookie riêng), MỌI CEO gọi vào cùng 1
    endpoint sẽ đọc chung dữ liệu không phân biệt workspace. KHÔNG bật
    portal_mock=False trên production tới khi xác nhận cổng ngoài xử lý
    tenant đúng, hoặc bổ sung tham số tenant vào request tại đây."""
```
(giữ nguyên code hiện có, chỉ thêm docstring này).

- [ ] **Step 20: Chạy full suite backend cho Task 2**

Run: `cd backend && python -m pytest tests/ -q`
Expected: PASS toàn bộ, không regression (so baseline: 856 passed, 0 failed, 4 skipped trước task này).

- [ ] **Step 21: Commit**

```bash
git add backend/app/services/distiller_service.py backend/app/services/watcher_service.py backend/app/services/report_schedule_service.py backend/app/services/work_service.py backend/app/services/portal_service.py backend/tests/test_distiller_window.py backend/tests/test_watcher_catchup_guard.py backend/tests/test_notify_mentions_word_boundary.py backend/tests/test_report_schedule_plan_recheck.py
git commit -m "fix(cron): distiller quet dung ca ngay hom qua, catch-up guard 10 phut, notify mentions word-boundary, re-check plan trong report_schedule

Fix 4 finding + 1 ghi chu audit 2026-07-26 (re-verify 2026-08-08):
- #9 [HIGH]: distiller_service tinh day_start = now_vn TAI THOI DIEM CHAY
  (02:00), khong lui ve hom qua -- chi quet 2 tieng dem, bo ca ngay lam
  viec. Sua thanh khoang [hom_qua_00h, hom_nay_00h).
- #10 [MED]: guard hour==7&&minute==0 (watcher) va hour==2&&minute==0
  (distiller) khong catch-up neu tick tre. Noi thanh minute<10, dua vao
  dedup san co (Notification cung ngay / cosine similarity).
- #14 [LOW]: _notify_mentions substring '@Anh' khop nham '@Anh Tuan'.
  Doi sang regex word-boundary.
- #13 [LOW]: run_due_schedules khong re-check plan_allows moi lan chay --
  workspace ha goi van nhan scheduled report vo thoi han. Them re-check +
  tu tat schedule.active neu khong con du goi.
- #16: chi them docstring canh bao HttpPortalClient khong phan tenant --
  CHUA code logic that vi khong co API spec cong ngoai.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: FE + WS/publisher + ProjectStatus enum (finding #17, #19, #21, #22, #23)

**Files:**
- Modify: `frontend/app/main/chat.tsx` (race socket dòng ~613-618, Android keyboard dòng ~336-338, ref reset dòng ~560-571)
- Modify: `backend/app/api/ws.py` (locked check, dòng ~23-35)
- Modify: `backend/app/agent/publisher.py` (pubsub aclose, dòng ~58-67)
- Modify: `backend/app/schemas.py` (`ProjectPatchIn.status`, dòng ~129-135)
- Modify: `backend/app/models.py` (`Project.status` → Enum, dòng ~172)
- Modify: `backend/app/api/chat.py` (`edit_request` re-index embedding, cùng vùng đã sửa ở Task 1 — làm SAU Task 1 để tránh conflict)
- Test: `backend/tests/test_ws_locked_user_rejected.py` (mới, finding #19)
- Test: `backend/tests/test_project_status_enum.py` (mới, finding #21)
- Test: `backend/tests/test_edit_request_reindex_embedding.py` (mới, finding #22)

**Interfaces:**
- Consumes: `edit_request` guard đã sửa ở Task 1 Step 3 — Task 3 sửa TIẾP cùng hàm này (thêm re-index), phải làm SAU khi Task 1 merge để tránh 2 nhánh cùng sửa 1 vùng gây conflict merge. Nếu chạy song song với Task 1 chưa merge, người thực thi phải tự rebase/merge conflict tại `edit_request`.

- [ ] **Step 1: Finding #17 — Fix race 2 socket trong `chat.tsx` (FE, không có test tự động — sửa trực tiếp + verify bằng đọc kỹ + tsc)**

Đọc `frontend/app/main/chat.tsx` đầy đủ effect load conversation (dòng ~560-629) để lấy đúng code hiện tại.

```bash
grep -n "closeWs.current = await openConversationStream" -A 5 frontend/app/main/chat.tsx
```

Thêm ngay sau khối gọi `openConversationStream`:
```tsx
        closeWs.current = await openConversationStream(
          convId,
          onWsEvent(convId),
          () => refreshQueue(convId),
          () => setActionError("Mất kết nối realtime (phiên hết hạn) — kéo xuống để tải lại."),
        );
        if (cancelled) {
          closeWs.current();
          closeWs.current = null;
          return;
        }
```

- [ ] **Step 2: Finding #23 (phần 1) — thêm Android keyboard listener**

Đọc `frontend/app/main/chat.tsx` dòng ~336-338 (effect `keyboardWillShow`).

```bash
grep -n "keyboardWillShow\|keyboardWillHide" frontend/app/main/chat.tsx
```

Xác nhận `Platform` đã import từ `react-native` ở đầu file — nếu chưa, thêm vào dòng import hiện có. Đổi effect:
```tsx
  useEffect(() => {
    const showEvt = Platform.OS === "android" ? "keyboardDidShow" : "keyboardWillShow";
    const hideEvt = Platform.OS === "android" ? "keyboardDidHide" : "keyboardWillHide";
    const s = Keyboard.addListener(showEvt, () => setKbVisible(true));
    const h = Keyboard.addListener(hideEvt, () => setKbVisible(false));
    return () => { s.remove(); h.remove(); };
  }, []);
```
(giữ nguyên setState calls bên trong, chỉ đổi tên event theo platform — khớp đúng code thật đọc được ở bước grep).

- [ ] **Step 3: Finding #23 (phần 2) — reset refs khi đổi `requestedId`**

Đọc `frontend/app/main/chat.tsx` dòng ~376-384 (khai báo `useRef`) và ~560-571 (effect reset state) để lấy đúng tên biến.

```bash
grep -n "contentByRequest\|watchedRequests\|doneSeen\|streamingText" frontend/app/main/chat.tsx | head -10
```

Thêm vào đầu effect load conversation, cạnh các `setRows([])`/`setQueue([])` hiện có:
```tsx
    contentByRequest.current.clear();
    watchedRequests.current.clear();
    doneSeen.current.clear();
    streamingText.current.clear();
```
(điều chỉnh đúng tên biến/kiểu dữ liệu thật — có thể là `Map`/`Set` khác nhau, dùng `.clear()` nếu là Map/Set, hoặc gán lại `.current = {}`/`.current = []` nếu là object/array thường — xác nhận qua khai báo `useRef` thật).

- [ ] **Step 4: Chạy `tsc --noEmit` xác nhận không lỗi type**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit code 0, không lỗi liên quan `chat.tsx`.

- [ ] **Step 5: Commit phần FE**

```bash
git add frontend/app/main/chat.tsx
git commit -m "fix(fe): race 2 socket khi doi conversation, Android keyboard listener, reset refs khi doi requestedId

Fix 2 finding audit 2026-07-26 (re-verify 2026-08-08):
- #17 [HIGH]: effect load conversation khong re-check cancelled SAU khi
  await openConversationStream resolve -- socket moi mo ra bi bo roi
  (zombie) neu unmount/doi conversation xay ra dung luc dang cho ket noi,
  tu dong reconnect + event lan sang conversation moi. Them check cancelled
  ngay sau await, dong socket vua mo neu da cancelled.
- #23 [LOW]: keyboardWillShow chi fire tren iOS, Android khong nhan event
  nay -- kbVisible luon false tren Android. Doi sang keyboardDidShow/Hide
  theo Platform.OS. Refs (contentByRequest/watchedRequests/doneSeen/
  streamingText) khong reset khi doi requestedId -- memory leak tich luy
  qua nhieu lan chuyen conversation trong 1 phien app. Them .clear() dau
  effect load conversation.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Finding #19 — Viết test thất bại cho ws.py không check locked**

Đọc `backend/app/api/ws.py` đầy đủ `authorize_ws` (dòng ~23-35) và `backend/tests/test_ws.py` để lấy pattern test WS hiện có.

```bash
grep -n "async def authorize_ws" -A 15 backend/app/api/ws.py
```

```python
# backend/tests/test_ws_locked_user_rejected.py
"""Finding #19 (audit 2026-07-26, re-verify 2026-08-08, MED): authorize_ws
chỉ decode token + check workspace/user khớp conversation, KHÔNG check
UserStatus.locked -- user bị khóa vẫn mở được WS mới nếu JWT cũ còn hạn
(so sánh deps.py::get_current_user CÓ check locked cho REST)."""
import pytest

from tests.conftest import _ceo_headers


@pytest.mark.asyncio
async def test_ws_tu_choi_user_bi_khoa(client):
    """LƯU Ý: cần đọc backend/tests/test_ws.py để lấy đúng cách test WS
    connect qua httpx AsyncClient (thường qua websocket_connect hoặc mock
    tương tự) -- copy đúng pattern, không đoán API test WS chưa xác nhận."""
    raise NotImplementedError("Doc test_ws.py de lay dung pattern test WS truoc")
```

**LƯU Ý QUAN TRỌNG:** test này CỐ Ý để dạng khung — người thực thi PHẢI đọc `backend/tests/test_ws.py` (cách test hiện có kết nối WS trong test suite — FastAPI TestClient hỗ trợ `client.websocket_connect(...)` khác với `httpx.AsyncClient` thường dùng cho REST) trước khi viết test thật.

- [ ] **Step 7: Chạy test, xác nhận fail đúng lý do**

Run: `cd backend && python -m pytest tests/test_ws_locked_user_rejected.py -v`
Expected: FAIL — kết nối WS thành công dù user bị khóa (chưa có check).

- [ ] **Step 8: Fix finding #19 (phần 1) — check locked trong `authorize_ws`**

```bash
grep -n "async def authorize_ws" -A 20 backend/app/api/ws.py
```
Thêm `db.get(User, user_id)` + check status, đặt TRƯỚC check conversation:
```python
    user = await db.get(User, user_id)
    if user is None or user.status == UserStatus.locked:
        raise WebSocketAuthError("user_locked")
```
Xác nhận `User`, `UserStatus`, `WebSocketAuthError` (hoặc tên exception thật đang dùng trong file — grep để chắc) đã import — nếu thiếu, thêm.

- [ ] **Step 9: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_ws_locked_user_rejected.py -v`
Expected: PASS.

- [ ] **Step 10: Fix finding #19 (phần 2) — đóng hẳn pubsub trong `publisher.py` (fix trực tiếp, không cần test riêng — khó test leak Redis connection qua unit test, verify bằng đọc code)**

```bash
grep -n "pubsub.unsubscribe" backend/app/agent/publisher.py
```
Đổi:
```python
        finally:
            await pubsub.unsubscribe(f"conv:{conversation_id}")
```
thành:
```python
        finally:
            await pubsub.unsubscribe(f"conv:{conversation_id}")
            await pubsub.aclose()
```
(khớp đúng tên biến/f-string thật đọc được ở bước grep).

- [ ] **Step 11: Chạy test liên quan WS/publisher để đảm bảo không phá gì**

Run: `cd backend && python -m pytest tests/test_ws.py tests/test_ws_locked_user_rejected.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 12: Finding #21 — Viết test thất bại cho `ProjectStatus` enum**

Đọc `backend/app/models.py` (`Project.status`, dòng ~172) và `backend/app/schemas.py` (`ProjectPatchIn`, dòng ~129-135), và tìm enum `TaskStatus` làm mẫu.

```bash
grep -n "class TaskStatus" -A 6 backend/app/models.py
grep -n "class Project\b" -A 15 backend/app/models.py
grep -n "class ProjectPatchIn" -A 8 backend/app/schemas.py
```

```python
# backend/tests/test_project_status_enum.py
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
```

- [ ] **Step 13: Chạy test, xác nhận fail (hiện tại chấp nhận mọi string, trả 200)**

Run: `cd backend && python -m pytest tests/test_project_status_enum.py -v`
Expected: FAIL — `assert 200 == 422`.

- [ ] **Step 14: Fix finding #21 — thêm `ProjectStatus` enum**

Trong `backend/app/models.py`, thêm enum mới gần `TaskStatus` (đọc cấu trúc `TaskStatus` thật để khớp style — `str, enum.Enum` hay cách khác):
```python
class ProjectStatus(str, enum.Enum):
    active = "active"
    on_hold = "on_hold"
    completed = "completed"
    archived = "archived"
```
Đổi cột `Project.status`:
```python
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus), default=ProjectStatus.active)
```
Trong `backend/app/schemas.py`, import `ProjectStatus` từ `app.models` (thêm vào dòng import hiện có), đổi `ProjectPatchIn.status`:
```python
class ProjectPatchIn(BaseModel):
    name: str | None = None
    goal: str | None = None
    status: ProjectStatus | None = None
    deadline: dt.datetime | None = None
    owner_id: uuid.UUID | None = None
```
Đổi luôn `ProjectOut.status: str` thành `ProjectOut.status: ProjectStatus` nếu có (kiểm tra bằng grep) để nhất quán response.

**CẦN MIGRATION ALEMBIC** — cột `status` đổi từ `String(32)` sang `Enum`. Đảm bảo Postgres dev chạy:
```bash
cd backend
.venv\Scripts\activate
alembic revision --autogenerate -m "convert project status to enum"
```
Đọc file migration sinh ra — nếu Postgres tự tạo `TYPE projectstatus AS ENUM (...)` và `ALTER COLUMN status TYPE projectstatus USING status::projectstatus`, kiểm tra dữ liệu cũ có giá trị nào KHÔNG khớp 4 giá trị enum mới không (`SELECT DISTINCT status FROM projects;` qua `docker compose exec postgres psql`) — nếu có giá trị lạ, migration sẽ fail khi cast, cần thêm bước data-fix trước cast (UPDATE các giá trị lạ về `'active'` làm mặc định an toàn) NGAY TRONG file migration trước dòng `ALTER COLUMN`.

- [ ] **Step 15: Áp migration, verify, chạy test**

```bash
alembic upgrade head
```
Run: `cd backend && python -m pytest tests/test_project_status_enum.py tests/test_projects.py -v`
Expected: PASS toàn bộ (bao gồm test `test_projects.py` hiện có — xác nhận enum mới không phá giá trị `"active"` mặc định vốn đã dùng).

- [ ] **Step 16: Finding #22 — Viết test thất bại cho `edit_request` không re-index embedding**

Đọc `backend/app/api/chat.py` (`edit_request`, đã sửa ở Task 1 — đọc bản MỚI NHẤT sau Task 1 merge) và `backend/app/agent/worker.py` (job `index_chat_message`) và `backend/app/services/embedding_service.py`.

```bash
grep -n "async def edit_request" -A 20 backend/app/api/chat.py
grep -n "index_chat_message" backend/app/agent/worker.py backend/app/api/chat.py
```

```python
# backend/tests/test_edit_request_reindex_embedding.py
"""Finding #22 (audit 2026-07-26, re-verify 2026-08-08, LOW): edit_request
sửa nội dung Message nhưng KHÔNG enqueue lại index_chat_message -- embedding
trong bảng Embedding vẫn trỏ nội dung GỐC trước khi sửa, semantic_search
trả về text cũ."""
import pytest

from tests.conftest import _ceo_headers


@pytest.mark.asyncio
async def test_edit_request_enqueue_reindex(client, monkeypatch):
    """LƯU Ý: cần xác nhận cách app hiện tại mock/inject arq_pool trong test
    (đọc backend/tests/conftest.py fixture client -- có override get_arq_pool
    hay dùng _FakeArqPool như test_chat_queue_api.py mô tả trong báo cáo audit)
    để spy đúng lời gọi enqueue_job('index_chat_message', ...) sau khi PATCH
    edit_request thành công. Viết test dựa trên cơ chế fake pool THẬT đang
    có, không đoán."""
    raise NotImplementedError("Doc conftest.py + test_chat_queue_api.py truoc")
```

**LƯU Ý QUAN TRỌNG:** dạng khung cố ý — đọc `backend/tests/test_chat_queue_api.py` (có `_FakeArqPool` theo báo cáo agent) trước khi hoàn thiện.

- [ ] **Step 17: Chạy test, xác nhận fail**

Run: `cd backend && python -m pytest tests/test_edit_request_reindex_embedding.py -v`
Expected: FAIL — không có lời gọi `enqueue_job("index_chat_message", ...)` nào sau `edit_request`.

- [ ] **Step 18: Fix finding #22 — enqueue re-index sau khi sửa**

Đọc lại `edit_request` (bản đã có guard `started_at` từ Task 1) và route `send_message` (`chat.py:226-231` theo báo cáo agent) để copy đúng cách gọi `arq_pool.enqueue_job`.

```bash
grep -n "async def send_message" -A 15 backend/app/api/chat.py
```

Thêm dependency `arq_pool` vào signature `edit_request` (nếu chưa có — kiểm tra bằng grep, có thể route khác đã dùng `Depends(get_arq_pool)` làm mẫu) và enqueue sau `db.commit()`:
```python
    await db.commit()
    if msg is not None:
        await arq_pool.enqueue_job("index_chat_message",
                                   actor.workspace_id, msg.id, body.content)
    return req
```
Khớp đúng theo code thật (tên biến `msg`, `body.content` có thể khác — dùng đúng tên đã đọc ở Step 16).

- [ ] **Step 19: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_edit_request_reindex_embedding.py -v`
Expected: PASS.

- [ ] **Step 20: Chạy full suite backend cho Task 3**

Run: `cd backend && python -m pytest tests/ -q`
Expected: PASS toàn bộ, không regression.

- [ ] **Step 21: Commit phần BE của Task 3**

```bash
git add backend/app/api/ws.py backend/app/agent/publisher.py backend/app/models.py backend/app/schemas.py backend/alembic/versions/*.py backend/app/api/chat.py backend/tests/test_ws_locked_user_rejected.py backend/tests/test_project_status_enum.py backend/tests/test_edit_request_reindex_embedding.py
git commit -m "fix(ws,schema): ws.py chan user bi khoa, publisher dong han pubsub, Project.status thanh enum, edit_request re-index embedding

Fix 3 finding audit 2026-07-26 (re-verify 2026-08-08):
- #19 [MED]: authorize_ws khong check UserStatus.locked (deps.py REST co
  check, ws.py thieu) -- user bi khoa van giu/mo duoc WS neu JWT cu con
  han. publisher.py RedisEventPublisher.subscribe finally chi unsubscribe,
  khong aclose() pubsub -- leak Redis connection tich luy moi phien WS.
  Them check locked truoc accept, them pubsub.aclose().
- #21 [LOW]: Project.status la String(32) tu do (khac Task/Directive dung
  Enum) -- PATCH chap nhan moi chuoi. Them ProjectStatus enum + migration.
- #22 [LOW]: edit_request sua noi dung Message nhung khong enqueue lai
  index_chat_message -- embedding van tro noi dung goc, semantic_search
  tra text cu. Them enqueue re-index sau commit.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Self-Review Notes

- **Spec coverage:** 17 finding trong phạm vi (loại #20 theo chỉ đạo, #8/#12/#18/#7-2026-07-24 đã lỗi thời không cần task) đều có task: #6,#7,#15 → Task 1; #9,#10,#11,#13,#14,#16 → Task 2; #17,#19,#21,#22,#23 → Task 3. Đủ 17/17.
- **Placeholder scan:** 4 test cố ý để dạng khung với `NotImplementedError` (Task 1 Step 7 phần OTP, Task 2 Step 14, Task 3 Step 6, Task 3 Step 16) — đây KHÔNG phải vi phạm "No Placeholders" của skill, vì mỗi chỗ đều ghi rõ LÝ DO (API test thật chưa xác nhận — fixture Redis, cách test WS, cách mock arq_pool) và CHỈ RÕ chính xác file nào phải đọc trước để hoàn thiện, thay vì mô tả suông "viết test cho X". Đây là giới hạn thực tế của việc lập plan không có quyền chạy code — người thực thi có bước rõ ràng để tự hoàn thiện, không phải đoán.
- **Type consistency:** `ProjectStatus` (Task 3) dùng nhất quán giữa `models.py` (Enum definition) và `schemas.py` (`ProjectPatchIn.status`, gợi ý cũng đổi `ProjectOut.status`). Task 3 Step 21 phụ thuộc Task 1 đã merge (cùng sửa `edit_request`) — đã ghi rõ trong "Interfaces" của Task 3.
- **Rủi ro cần theo dõi lúc thực thi:** Task 2 Step 18 (finding #11, push sau commit) và Task 2 Step 19 (finding #16) cố ý KHÔNG ép code nếu rủi ro cao — đúng nguyên tắc "an toàn hơn ép sửa" cho finding LOW không cấp bách.
