# STT thật (Groq Whisper) + fix SMTP config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement STT thật qua Groq Whisper API để `STT_MOCK=false` chạy được trên production, và sửa 2 bug trong SMTP config (`SMTP_SECURE`/`SMTP_PASS` không map vào field nào) để `EMAIL_MOCK=false` gửi được thật qua Gmail — cả 2 để chuẩn bị bật mock thật trên production (việc cập nhật `.env` VPS thực hiện sau, ngoài phạm vi code của plan này).

**Architecture:** Thêm `GroqTranscriptionClient` implement `TranscriptionClient` Protocol có sẵn trong `voice_service.py`, gọi Groq REST API qua `httpx` (đã có dependency, không cài mới). Sửa `config.py` thêm field `groq_api_key` + `smtp_secure` (mới, không xoá `smtp_starttls` cũ) + alias `SMTP_PASS` cho `smtp_password`. Sửa `SmtpEmailClient.send()` chọn `use_tls` vs `start_tls` theo `smtp_secure`.

**Tech Stack:** FastAPI, Pydantic Settings (`AliasChoices`), httpx, aiosmtplib, pytest-asyncio.

## Global Constraints

- Model LLM lấy từ config theo loại tác vụ — không hardcode model ID (CLAUDE.md) — áp dụng tương tự cho STT: model Groq `whisper-large-v3` là hardcode chấp nhận được ở đây vì đây là *tên model của provider thứ 3*, không phải model LLM nội bộ app — không có config layer nào khác trong app quản lý STT model theo loại tác vụ.
- TDD: test trước, code sau; mỗi task một commit (CLAUDE.md).
- Không commit secrets; dùng `.env` (đã gitignore) (CLAUDE.md).
- **KHÔNG bật `PORTAL_MOCK`** trong bất kỳ task nào — rủi ro rò rỉ dữ liệu chéo workspace đã biết (finding #16, audit 2026-07-26), ngoài phạm vi plan này.
- Lỗi STT (timeout/HTTP/parse) phải propagate tự nhiên, không tự bọc riêng — `transcribe_note()` (`voice_service.py`, không đổi trong plan này) đã có `except Exception: transcript_status="failed"` bao ngoài.
- Không đổi field `smtp_starttls` hiện có (tương thích ngược cho môi trường khác đã dùng `SMTP_STARTTLS`) — chỉ thêm field mới `smtp_secure`.
- Không xoá/đổi giá trị `SMTP_USER`/`SMTP_PASS`/`SMTP_FROM`/`SMTP_SECURE` đã điền trên `.env` VPS production (việc này chỉ sửa code đọc đúng, không động vào `.env` VPS).
- Việc cập nhật `.env` production (`MODEL_SMART`, `STT_MOCK`, `GROQ_API_KEY`, `PUSH_MOCK`, `EMAIL_MOCK`) và verify trên production **không nằm trong phạm vi plan này** — chỉ chuẩn bị code, thực hiện production riêng sau khi plan merge + deploy.

---

## File Structure

- **Modify** `backend/app/config.py` — thêm field `groq_api_key: str = ""`, `smtp_secure: bool = False`, đổi `smtp_password` dùng `AliasChoices`.
- **Modify** `backend/app/services/voice_service.py` — thêm `import httpx`, class `GroqTranscriptionClient`, sửa `get_transcription_client()`.
- **Modify** `backend/app/services/email_service.py` — sửa `SmtpEmailClient.send()` chọn `use_tls`/`start_tls` theo `smtp_secure`.
- **Modify** `backend/.env.example` — thêm comment `GROQ_API_KEY`, `SMTP_SECURE`.
- **Modify** `backend/tests/test_voice_notes.py` — thêm test cho `GroqTranscriptionClient` + `get_transcription_client()`.
- **Modify** `backend/tests/test_email_smtp.py` — thêm test cho alias `SMTP_PASS` + `smtp_secure`/`use_tls`/`start_tls`.

---

## Task 1: Config fields — `groq_api_key`, `smtp_secure`, alias `smtp_password`

**Files:**
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_email_smtp.py` (phần alias — Task 1 chỉ cần field tồn tại đúng; test hành vi `SmtpEmailClient` dùng chúng ở Task 3)

**Interfaces:**
- Produces: `Settings.groq_api_key: str` (mặc định `""`), `Settings.smtp_secure: bool` (mặc định `False`), `Settings.smtp_password` giờ chấp nhận cả env `SMTP_PASSWORD` và `SMTP_PASS`.

- [ ] **Step 1: Viết test cho alias `smtp_password`**

Mở `backend/tests/test_email_smtp.py`, thêm vào cuối file:

```python
def test_smtp_password_alias_accepts_smtp_pass_env():
    from app.config import Settings
    settings = Settings(_env_file=None, SMTP_PASS="xyz")
    assert settings.smtp_password == "xyz"


def test_smtp_password_alias_still_accepts_smtp_password_env():
    from app.config import Settings
    settings = Settings(_env_file=None, SMTP_PASSWORD="abc")
    assert settings.smtp_password == "abc"
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run (trong `backend/`, venv active): `pytest tests/test_email_smtp.py -v`
Expected: FAIL — `test_smtp_password_alias_accepts_smtp_pass_env` fails vì `settings.smtp_password == ""` (SMTP_PASS chưa được đọc); `test_smtp_password_alias_still_accepts_smtp_password_env` có thể PASS ngay (Pydantic case-insensitive match mặc định) — ghi nhận cả 2 kết quả, không cần cả 2 đều fail.

- [ ] **Step 3: Sửa `config.py`**

Trong `backend/app/config.py`, sửa dòng field `smtp_password` (hiện là dòng 34):

Từ:
```python
    smtp_password: str = ""
```
Thành:
```python
    smtp_password: str = Field("", validation_alias=AliasChoices("smtp_password", "SMTP_PASS"))
```

Ngay sau dòng `smtp_starttls: bool = True` (hiện là dòng 36), thêm:
```python
    # Cổng 465 (SMTPS/implicit TLS, vd Gmail) cần use_tls thay vì start_tls —
    # bật cờ này khi dùng cổng 465; mặc định false giữ hành vi cũ (start_tls
    # trên cổng 587) cho môi trường chỉ set SMTP_STARTTLS.
    smtp_secure: bool = False
```

Ngay sau dòng `stt_mock: bool = True` (hiện là dòng 37, trở thành dòng khác sau khi chèn ở trên — tìm bằng `grep -n "stt_mock" backend/app/config.py` để xác nhận vị trí thật lúc code), thêm:
```python
    # STT thật (Groq Whisper, free tier — https://console.groq.com/keys)
    groq_api_key: str = ""
```

- [ ] **Step 4: Chạy lại test, xác nhận pass**

Run: `pytest tests/test_email_smtp.py -v`
Expected: PASS (cả 2 test mới + test cũ `test_smtp_client_builds_message_and_sends`, `test_get_email_client_returns_mock_when_email_mock_true`)

- [ ] **Step 5: Xác nhận app khởi động không lỗi**

Run: `python -c "from app.config import get_settings; s = get_settings(); print(s.groq_api_key, s.smtp_secure, s.smtp_password)"`
Expected: in ra `` (rỗng) `False` `` — không lỗi.

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/tests/test_email_smtp.py
git commit -m "feat(config): them groq_api_key, smtp_secure, alias SMTP_PASS"
```

---

## Task 2: `SmtpEmailClient` chọn đúng `use_tls`/`start_tls`

**Files:**
- Modify: `backend/app/services/email_service.py`
- Test: `backend/tests/test_email_smtp.py`

**Interfaces:**
- Consumes: `Settings.smtp_secure`, `Settings.smtp_starttls` (Task 1).
- Produces: `SmtpEmailClient.send()` không đổi signature, chỉ đổi tham số truyền vào `aiosmtplib.send()`.

- [ ] **Step 1: Viết test**

Thêm vào cuối `backend/tests/test_email_smtp.py`:

```python
@pytest.mark.asyncio
async def test_smtp_client_uses_use_tls_when_secure(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "smtp_secure", True)

    captured = {}

    async def fake_send(msg, **kwargs):
        captured["kwargs"] = kwargs

    import aiosmtplib
    monkeypatch.setattr(aiosmtplib, "send", fake_send)

    await email_service.SmtpEmailClient().send(
        from_email="boss@a.vn", to_email="user@a.vn",
        subject="S", body="B",
    )
    assert captured["kwargs"]["use_tls"] is True
    assert captured["kwargs"]["start_tls"] is False


@pytest.mark.asyncio
async def test_smtp_client_uses_start_tls_when_not_secure(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "smtp_secure", False)
    monkeypatch.setattr(get_settings(), "smtp_starttls", True)

    captured = {}

    async def fake_send(msg, **kwargs):
        captured["kwargs"] = kwargs

    import aiosmtplib
    monkeypatch.setattr(aiosmtplib, "send", fake_send)

    await email_service.SmtpEmailClient().send(
        from_email="boss@a.vn", to_email="user@a.vn",
        subject="S", body="B",
    )
    assert captured["kwargs"]["use_tls"] is False
    assert captured["kwargs"]["start_tls"] is True
```

Kiểm tra đầu file `test_email_smtp.py` đã có `import pytest` và `from app.services import email_service` chưa (đã có theo file hiện tại) — không thêm trùng.

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `pytest tests/test_email_smtp.py -v`
Expected: FAIL trên `assert captured["kwargs"]["use_tls"] is True` — `KeyError: 'use_tls'` (tham số chưa tồn tại trong lệnh gọi `aiosmtplib.send()` hiện tại).

- [ ] **Step 3: Sửa `email_service.py`**

Trong `backend/app/services/email_service.py`, sửa `SmtpEmailClient.send()` (hiện tại dòng 43-63):

Từ:
```python
        await aiosmtplib.send(
            msg,
            hostname=s.smtp_host,
            port=s.smtp_port,
            username=s.smtp_user or None,
            password=s.smtp_password or None,
            start_tls=s.smtp_starttls,
        )
```
Thành:
```python
        use_tls = s.smtp_secure
        await aiosmtplib.send(
            msg,
            hostname=s.smtp_host,
            port=s.smtp_port,
            username=s.smtp_user or None,
            password=s.smtp_password or None,
            use_tls=use_tls,
            start_tls=False if use_tls else s.smtp_starttls,
        )
```

- [ ] **Step 4: Chạy lại test, xác nhận pass**

Run: `pytest tests/test_email_smtp.py -v`
Expected: PASS (toàn bộ test trong file, bao gồm test cũ `test_smtp_client_builds_message_and_sends` — vẫn pass vì chỉ assert `port`, không assert `use_tls`/`start_tls`)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/email_service.py backend/tests/test_email_smtp.py
git commit -m "feat(email): SmtpEmailClient chon dung use_tls/start_tls theo smtp_secure"
```

---

## Task 3: `.env.example` — comment cho `GROQ_API_KEY`, `SMTP_SECURE`

**Files:**
- Modify: `backend/.env.example`

**Interfaces:** Không có (chỉ comment, không code).

- [ ] **Step 1: Thêm comment SMTP_SECURE**

Trong `backend/.env.example`, tìm block:
```
# SMTP_STARTTLS=true
```
Thêm ngay sau dòng đó (không xoá dòng nào):
```
# Cổng 465 (SMTPS/implicit TLS, vd Gmail) thay vì 587+STARTTLS: set
# SMTP_PORT=465 và SMTP_SECURE=true (bỏ qua SMTP_STARTTLS khi bật cờ này)
# SMTP_SECURE=false
```

- [ ] **Step 2: Thêm comment GROQ_API_KEY**

Thêm vào cuối file `backend/.env.example`:
```

# --- STT thật (Groq Whisper, free tier — https://console.groq.com/keys) ---
# Mặc định STT_MOCK=true (transcript rỗng, không gọi API thật). Để dùng STT
# thật, set STT_MOCK=false và điền GROQ_API_KEY.
# STT_MOCK=false
# GROQ_API_KEY=
```

- [ ] **Step 3: Commit**

```bash
git add backend/.env.example
git commit -m "docs(env): comment huong dan GROQ_API_KEY va SMTP_SECURE"
```

---

## Task 4: `GroqTranscriptionClient`

**Files:**
- Modify: `backend/app/services/voice_service.py`
- Test: `backend/tests/test_voice_notes.py`

**Interfaces:**
- Consumes: `Settings.groq_api_key` (Task 1), `TranscriptionClient` Protocol (đã có, không đổi).
- Produces: class `GroqTranscriptionClient` implement `async def transcribe(self, data: bytes, filename: str) -> tuple[str, str]`.

- [ ] **Step 1: Viết test**

Thêm vào cuối `backend/tests/test_voice_notes.py`:

```python
# --- Groq STT thật ---


@pytest.mark.asyncio
async def test_groq_transcription_client_parses_response(monkeypatch):
    from app.services import voice_service

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            import httpx as _httpx
            # httpx.Response.raise_for_status() crash nếu response không gắn
            # request — kể cả với status 200 — nên PHẢI truyền request= khi
            # tạo Response thủ công trong test, không chỉ cho case lỗi.
            request = _httpx.Request("POST", url)
            return _httpx.Response(
                200, json={"text": "  xin chao  ", "language": "vietnamese"},
                request=request)

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(voice_service.get_settings(), "groq_api_key", "fake-key")

    text, language = await voice_service.GroqTranscriptionClient().transcribe(b"data", "a.m4a")
    assert text == "xin chao"
    assert language == "vietnamese"


@pytest.mark.asyncio
async def test_groq_transcription_client_raises_on_http_error(monkeypatch):
    from app.services import voice_service

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            import httpx as _httpx
            request = _httpx.Request("POST", url)
            return _httpx.Response(401, json={"error": "invalid_api_key"}, request=request)

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(voice_service.get_settings(), "groq_api_key", "bad-key")

    with pytest.raises(Exception):
        await voice_service.GroqTranscriptionClient().transcribe(b"data", "a.m4a")


def test_get_transcription_client_stt_mock_false_khong_co_key(monkeypatch):
    from app.services import voice_service
    monkeypatch.setattr(voice_service.get_settings(), "stt_mock", False)
    monkeypatch.setattr(voice_service.get_settings(), "groq_api_key", "")

    with pytest.raises(RuntimeError):
        voice_service.get_transcription_client()


def test_get_transcription_client_stt_mock_false_co_key(monkeypatch):
    from app.services import voice_service
    monkeypatch.setattr(voice_service.get_settings(), "stt_mock", False)
    monkeypatch.setattr(voice_service.get_settings(), "groq_api_key", "fake-key")

    client = voice_service.get_transcription_client()
    assert isinstance(client, voice_service.GroqTranscriptionClient)
```

Kiểm tra đầu file `test_voice_notes.py` đã có `import pytest` chưa (đã có theo file hiện tại — dùng `@pytest.mark.asyncio` ở các test khác trong file) — không thêm trùng.

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `pytest tests/test_voice_notes.py -v -k groq or transcription_client`
Expected: FAIL — `AttributeError: module 'app.services.voice_service' has no attribute 'GroqTranscriptionClient'`

- [ ] **Step 3: Implement**

Trong `backend/app/services/voice_service.py`, thêm `import httpx` vào đầu file (sau dòng `import asyncio`, hiện là dòng 10):
```python
import asyncio
import httpx
import uuid
```

Sau class `MockTranscriptionClient` (hiện tại dòng 40-42), thêm:
```python
class GroqTranscriptionClient:
    """STT thật qua Groq Whisper API (whisper-large-v3, tương thích OpenAI).
    Free tier — xem console.groq.com. Lỗi (timeout/HTTP/parse) propagate tự
    nhiên; tầng gọi (transcribe_note) đã bọc try/except ghi
    transcript_status="failed", không cần retry ở đây."""

    _URL = "https://api.groq.com/openai/v1/audio/transcriptions"

    async def transcribe(self, data: bytes, filename: str) -> tuple[str, str]:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                self._URL,
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                files={"file": (filename, data)},
                data={"model": "whisper-large-v3", "response_format": "verbose_json"},
            )
            resp.raise_for_status()
            body = resp.json()
        return body.get("text", "").strip(), body.get("language", "und")
```

Sửa `get_transcription_client()` (hiện tại dòng 45-48):

Từ:
```python
def get_transcription_client() -> TranscriptionClient:
    if get_settings().stt_mock:
        return MockTranscriptionClient()
    raise NotImplementedError("STT provider chưa được chọn — xem phụ lục funtional-plan")
```
Thành:
```python
def get_transcription_client() -> TranscriptionClient:
    settings = get_settings()
    if settings.stt_mock:
        return MockTranscriptionClient()
    if not settings.groq_api_key:
        raise RuntimeError("STT_MOCK=false nhưng thiếu GROQ_API_KEY")
    return GroqTranscriptionClient()
```

- [ ] **Step 4: Chạy lại test, xác nhận pass**

Run: `pytest tests/test_voice_notes.py -v`
Expected: PASS (toàn bộ file — test mới + test cũ `test_transcribe_note_cap_nhat_transcript`, `test_transcribe_note_loi_thanh_failed` không bị ảnh hưởng vì chúng stub `get_transcription_client` trực tiếp)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/voice_service.py backend/tests/test_voice_notes.py
git commit -m "feat(voice): GroqTranscriptionClient - STT that qua Groq Whisper"
```

---

## Task 5: Full suite + rà soát cuối

**Files:** không tạo/sửa file mới — chạy toàn bộ test suite hiện có để xác nhận không phá gì.

- [ ] **Step 1: Chạy toàn bộ test suite backend**

Run (trong `backend/`): `pytest tests/ -q`

**QUAN TRỌNG:** lệnh này thường mất ~9-10 phút và có thể bị công cụ tự động đẩy sang chạy nền (background) do vượt quá thời gian chờ mặc định — đây là hành vi bình thường của môi trường thực thi, KHÔNG phải lỗi. Nếu điều đó xảy ra: KHÔNG polling/kiểm tra lặp lại liên tục để chờ kết quả — chỉ chờ thông báo hoàn tất tự động rồi đọc kết quả một lần.

Expected: tất cả PASS, không có test nào từ trước bị fail do thay đổi `config.py`/`voice_service.py`/`email_service.py`.

- [ ] **Step 2: Nếu có fail, sửa và re-run tới khi xanh hết**

(Không thêm bước cụ thể — nội dung fix phụ thuộc lỗi thực tế xuất hiện.)

- [ ] **Step 3: Commit nếu có sửa**

```bash
git add -A
git commit -m "fix: full suite green sau groq-stt + smtp fix"
```

---

## Spec Coverage Checklist (tự rà soát khi viết plan)

- `GroqTranscriptionClient` implement `TranscriptionClient`, dùng Groq Whisper API → Task 4. ✅
- `get_transcription_client()` raise `RuntimeError` rõ ràng khi thiếu `groq_api_key`, trả `GroqTranscriptionClient` khi có → Task 4. ✅
- Config `groq_api_key` → Task 1. ✅
- Config `smtp_secure` mới (không xoá `smtp_starttls`), alias `smtp_password`/`SMTP_PASS` → Task 1. ✅
- `SmtpEmailClient.send()` chọn đúng `use_tls`/`start_tls`, giữ tương thích ngược khi `smtp_secure=False` → Task 2. ✅
- `.env.example` comment cho cả 2 biến mới → Task 3. ✅
- Test: parse response Groq thật, raise trên lỗi HTTP, thiếu key raise rõ ràng, có key trả đúng client, alias SMTP_PASS/SMTP_PASSWORD đều hoạt động, use_tls/start_tls đúng theo smtp_secure, tương thích ngược khi chỉ set STARTTLS → rải Task 1/2/4, tổng hợp full suite Task 5. ✅
- **Không** bật `PORTAL_MOCK`, không đổi `.env` production trong plan này (ngoài phạm vi code) → không có task nào vi phạm. ✅
- Không đổi `_ALLOWED_EXTS`, không thêm retry STT → không có task nào vi phạm. ✅
