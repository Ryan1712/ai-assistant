# STT thật qua Groq Whisper + bật mock thật trên production

**Ngày:** 2026-08-12
**Trạng thái:** Approved (chờ implement)

## Bối cảnh

Rà soát `.env` production (VPS `51.79.255.102`, thư mục
`/home/dlm/9learning/ai-assistant-backend/`) ngày 2026-08-12 xác nhận 2 vấn đề
đã ghi trong memory từ 2026-07-24 **vẫn còn nguyên**:

1. `MODEL_SMART` không được set trên `.env` production → rơi về default
   `config.py::model_smart = "claude-sonnet-4-6"`, thiếu prefix `anthropic/`
   mà gateway beeknoee bắt buộc. Mọi tác vụ dùng model "smart" (đường sâu,
   phân tích) trên production sẽ lỗi khi gọi LLM.
2. `EMAIL_MOCK`, `PUSH_MOCK`, `STT_MOCK`, `PORTAL_MOCK` đều không set trên
   `.env` production → rơi về default `True` trong `config.py` → toàn bộ 4
   tính năng đang chạy giả lập trên production thật, không có tác dụng thật.

Kiểm tra sâu hơn cho thấy 4 cờ mock không đồng đều về mức độ sẵn sàng để tắt:

| Cờ | Cần gì để tắt an toàn | Trạng thái |
|---|---|---|
| `push_mock` | Không cần credential — `ExpoPushClient` gọi thẳng `https://exp.host/--/api/v2/push/send` (API công khai) | Sẵn sàng tắt ngay |
| `portal_mock` | **KHÔNG an toàn để tắt** — xem cảnh báo dưới | **Loại khỏi scope, không đụng tới** |
| `email_mock` | Dev FE đã điền credentials Gmail thật lên `.env` VPS (2026-08-12) — nhưng có 2 bug cần fix trước khi bật, xem chi tiết dưới | **Đã có credentials, nhưng 2 bug chặn** |
| `stt_mock` | Cần 1 `TranscriptionClient` thật — code hiện tại **chỉ có `MockTranscriptionClient`**, `get_transcription_client()` raise `NotImplementedError` khi tắt mock (`voice_service.py:48`) | **Chưa có code** — đây là việc chính của spec này |

**Phát hiện mới (2026-08-12, sau khi dev FE điền SMTP lên `.env` VPS):**
dev FE đã thêm `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=465`, `SMTP_SECURE=true`,
`SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`, `EMAIL_REPLY_TO` vào `.env` VPS thật
(chưa có `EMAIL_MOCK=false`). Đối chiếu với `config.py` phát hiện **2 bug
chặn việc bật email thật**:

1. **Tên biến lệch, bị Pydantic Settings bỏ qua âm thầm:** `.env` dùng
   `SMTP_SECURE` và `SMTP_PASS`, nhưng `config.py` chỉ có field
   `smtp_starttls` và `smtp_password` — không khớp tên nên 2 biến này
   **không map vào đâu cả**, bị bỏ qua hoàn toàn (Pydantic Settings không
   báo lỗi cho biến `.env` dư thừa không khớp field nào). Hậu quả: nếu bật
   `EMAIL_MOCK=false` ngay bây giờ, `smtp_password` vẫn rỗng (default
   `""`) → gửi mail lỗi authentication ngay lập tức, dù `.env` "nhìn như"
   đã có mật khẩu.
2. **Sai giao thức TLS cho cổng 465:** cổng 465 là SMTPS (implicit TLS —
   kết nối SSL ngay từ đầu), không phải STARTTLS (nâng cấp sau khi connect
   plain, đi với cổng 587). `email_service.py::SmtpEmailClient.send()`
   hiện chỉ gọi `aiosmtplib.send(..., start_tls=s.smtp_starttls)` — không
   có tham số `use_tls` nào cho implicit TLS. `smtp_starttls` default
   `True` nghĩa là code sẽ thử STARTTLS trên cổng 465 → lỗi kết nối/timeout
   với Gmail (Gmail cổng 465 bắt buộc implicit TLS, không chấp nhận
   STARTTLS trên cổng này).

**Quyết định:** sửa `config.py` đổi tên field cho khớp `.env` VPS đã điền
(`smtp_secure`/`smtp_password` giữ nguyên tên field code, KHÔNG đổi tên
field `smtp_password` — chỉ thêm field `smtp_secure: bool` mới khớp
`SMTP_SECURE`; xoá field `smtp_starttls` cũ không dùng, hoặc giữ song song
nếu cổng 587/STARTTLS còn dùng nơi khác — xem chi tiết ở mục Kiến trúc),
và sửa `SmtpEmailClient.send()` chọn đúng `use_tls` vs `start_tls` theo
`smtp_secure`. Việc "chỉ cần thêm `EMAIL_MOCK=false`" KHÔNG còn đúng nữa —
cần 1 đợt fix code nhỏ trước.

**Phát hiện quan trọng khi audit `portal_service.py`:** class `HttpPortalClient`
đã có sẵn docstring cảnh báo — đây chính là **finding #16 của đợt audit
2026-07-26** (nằm trong danh sách "~23 findings mở" chưa xử lý, xem memory
`project-repo-audit-2026-07-26`): client gọi thẳng
`{portal_base_url}/api/reports` **không truyền `workspace_id`/tenant nào**
trong query/header. Nếu bật `portal_mock=False` mà cổng ngoài
(`ceo.9learning.edu.vn`) không tự phân tenant theo cách khác (token/cookie
riêng biệt theo workspace), **mọi CEO gọi vào cùng 1 endpoint sẽ đọc chung
dữ liệu, không phân biệt workspace** — rò rỉ dữ liệu chéo workspace thật
trên production. Code tự ghi rõ "KHÔNG bật portal_mock=False trên
production tới khi xác nhận cổng ngoài xử lý tenant đúng, hoặc bổ sung
tham số tenant vào request". **Spec này KHÔNG bật `PORTAL_MOCK` — để riêng
cho một lần xử lý finding #16 sau, có audit + fix code trước khi bật, không
phải việc "chỉ sửa .env".**

## Mục tiêu

1. Implement `GroqTranscriptionClient` — provider STT thật dùng Groq Whisper
   API (`whisper-large-v3`), để `STT_MOCK=false` chạy được trên production
   mà không lỗi.
2. Sửa `config.py` + `SmtpEmailClient` để khớp đúng biến `.env` VPS đã điền
   (`SMTP_SECURE`, `SMTP_PASS`) và chọn đúng implicit-TLS cho cổng 465, để
   `EMAIL_MOCK=false` gửi được thật qua Gmail.
3. Sau khi cả 2 xong, hướng dẫn cập nhật `.env` production: fix
   `MODEL_SMART`, bật `STT_MOCK=false` + `GROQ_API_KEY`, bật
   `PUSH_MOCK=false`, bật `EMAIL_MOCK=false` (credentials đã có sẵn trên
   VPS từ dev FE).

**Ngoài phạm vi:** **KHÔNG bật `PORTAL_MOCK`** (rủi ro rò rỉ dữ liệu chéo
workspace — finding #16 chưa xử lý, xem cảnh báo ở trên); không đổi
provider push (đã có sẵn, chỉ cần bật); không thêm cơ chế retry cho STT
(transcript_status="failed" + user tự re-transcribe qua endpoint có sẵn là
đủ, theo quyết định của user); không đổi cơ chế lưu file voice note;
không đổi danh sách `_ALLOWED_EXTS`; không fix finding #16 (việc riêng,
cần audit code portal + cổng ngoài trước, không thuộc phạm vi STT); không
đổi giá trị `SMTP_USER`/`SMTP_PASS`/`SMTP_FROM` đã điền trên VPS (chỉ sửa
code đọc đúng chúng).

## Vì sao chọn Groq Whisper

So sánh nhanh (đã trình bày với user, user chọn):
- **OpenAI Whisper API**: trả phí theo usage, không có free tier, cần
  credential riêng ngoài hệ Anthropic đang dùng.
- **Google Cloud STT**: free tier 60 phút/tháng, setup phức tạp hơn
  (service account JSON, GCP project).
- **Groq Whisper (whisper-large-v3)**: free tier thực sự dùng lâu dài
  (không phải trial), cùng chất lượng model Whisper, API tương thích
  OpenAI (multipart form, JSON response), tốc độ nhanh (chip LPU). **Chọn
  phương án này.**

## Kiến trúc

### `GroqTranscriptionClient` (backend/app/services/voice_service.py)

Thêm class mới cạnh `MockTranscriptionClient` hiện có (dòng 40-42), cùng
implement `TranscriptionClient` Protocol không đổi
(`async def transcribe(data: bytes, filename: str) -> tuple[str, str]`):

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

Ghi chú kỹ thuật cần xác nhận lúc code (không đoán trước, verify khi viết
test với response mẫu thật từ tài liệu Groq hiện hành):
- Field tên ngôn ngữ trong response `verbose_json` của Groq — tài liệu
  Groq nói theo chuẩn OpenAI Whisper (`language` là tên đầy đủ, vd
  `"vietnamese"`, không phải mã ISO `"vi"`) — khác với field
  `MockTranscriptionClient` trả (`"und"`, `"vi"` trong test hiện có).
  KHÔNG tự ý đổi hành vi cột `language` trong DB (vẫn `String`, không đổi
  kiểu) — chỉ lưu đúng giá trị Groq trả về nguyên văn, không cố ánh xạ
  sang mã ISO (over-engineering ngoài phạm vi).
- `httpx.HTTPStatusError` (từ `raise_for_status()`) là exception hợp lệ để
  propagate — `transcribe_note()`'s `except Exception` đã bắt được.

### `get_transcription_client()` (voice_service.py:45-48)

Sửa từ:
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

Lý do check `groq_api_key` tường minh thay vì để lỗi HTTP 401 mơ hồ từ
Groq: fail nhanh, rõ nguyên nhân trong log thay vì phải suy luận từ lỗi
network.

### Config (`backend/app/config.py`)

Thêm 1 field, đặt cạnh các field STT-liên-quan hiện có (gần `stt_mock`,
dòng ~37):
```python
    groq_api_key: str = ""
```

### `.env.example`

Thêm comment hướng dẫn (không giá trị thật):
```
# STT thật (Groq Whisper, free tier — https://console.groq.com/keys)
# STT_MOCK=false
# GROQ_API_KEY=
```

### Import mới trong `voice_service.py`

Thêm `import httpx` vào đầu file (đã có `httpx==0.27.*` trong
`requirements.txt`, không cần cài mới — dùng chung version với
`llm_client`/`embedding_service` nếu có, xác nhận không xung đột lúc code).

### SMTP config + client (`backend/app/config.py`, `backend/app/services/email_service.py`)

**Không xoá `smtp_starttls`** (`.env.example` hiện có đã công bố
`SMTP_STARTTLS=true` như tên biến chuẩn — xoá sẽ phá format cho bất kỳ môi
trường nào khác đã dùng đúng tên đó). Thay vào đó **thêm field mới**
`smtp_secure: bool = False` cạnh nó (`config.py`, ngay sau dòng
`smtp_starttls: bool = True`, hiện là dòng 36):
```python
    smtp_starttls: bool = True
    # Cổng 465 (SMTPS/implicit TLS, vd Gmail) cần use_tls thay vì start_tls —
    # bật cờ này khi dùng cổng 465; mặc định false giữ hành vi cũ (start_tls
    # trên cổng 587) cho môi trường chỉ set SMTP_STARTTLS.
    smtp_secure: bool = False
```

`smtp_password` giữ nguyên tên field (Pydantic Settings mặc định tự khớp
`SMTP_PASSWORD` case-insensitive) — nhưng `.env` VPS dùng `SMTP_PASS`
(viết tắt khác, không tự khớp). `AliasChoices` đã được import sẵn ở đầu
`config.py:3` và có tiền lệ dùng thật trong file (field `model_fast` alias
`"model_chat"`, dòng 22-23) — dùng đúng cách đó cho field mới:
```python
    smtp_password: str = Field("", validation_alias=AliasChoices("smtp_password", "SMTP_PASS"))
```
để chấp nhận cả 2 tên biến env mà không cần đổi `.env` VPS đã điền sẵn.
Lưu ý include tên field gốc (`"smtp_password"`) trong `AliasChoices`, không
chỉ alias mới — nếu không, `SMTP_PASSWORD` (đang set ở môi trường khác nếu
có) sẽ ngừng hoạt động vì Pydantic dùng ĐÚNG danh sách `AliasChoices` khi
field có `validation_alias`, không tự thêm case-insensitive match nữa.

Sửa `SmtpEmailClient.send()` (`email_service.py:43-63`) chọn `use_tls` khi
`smtp_secure=True` (cổng 465, implicit TLS), else giữ nguyên hành vi cũ
dùng `start_tls=smtp_starttls` (cổng 587 hoặc bất kỳ giá trị
`SMTP_STARTTLS` nào đã set) — `use_tls`/`start_tls` loại trừ nhau trong
`aiosmtplib.send()`:
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

### `.env.example`

`.env.example` hiện có sẵn 1 block SMTP (comment, không giá trị thật):
```
# --- Email thật qua SMTP ---
# Mặc định EMAIL_MOCK=true (không gửi thật, chỉ ghi vào email_messages/log). Để gửi
# email thật (vd mã OTP quên mật khẩu), set EMAIL_MOCK=false và điền SMTP bên dưới.
# EMAIL_MOCK=false
# SMTP_HOST=smtp.gmail.com
# SMTP_PORT=587
# SMTP_USER=you@yourdomain.com
# SMTP_PASSWORD=your-app-password    # Gmail: dùng App Password, KHÔNG phải mật khẩu thường
# SMTP_FROM=no-reply@yourdomain.com  # rỗng = dùng SMTP_USER
# SMTP_STARTTLS=true
```
Thêm 1 dòng comment mới ngay sau `# SMTP_STARTTLS=true`, không xoá dòng
nào có sẵn:
```
# Cổng 465 (SMTPS/implicit TLS, vd Gmail) thay vì 587+STARTTLS: set
# SMTP_PORT=465 và SMTP_SECURE=true (bỏ qua SMTP_STARTTLS khi bật cờ này)
# SMTP_SECURE=false
```

## Test (TDD)

File: `backend/tests/test_voice_notes.py` (cùng file test voice note hiện
có, thêm section mới cuối file, không tách file riêng — theo cách tổ chức
hiện tại của repo, 1 service = 1 file test).

1. `test_groq_transcription_client_parses_response` — repo KHÔNG có
   `respx` hay thư viện mock HTTP chuyên dụng nào (đã xác nhận qua
   `requirements.txt`); dùng `httpx.MockTransport` (built-in trong httpx,
   không cần cài thêm) truyền vào `httpx.AsyncClient(transport=...)` —
   pattern gần nhất đã có trong repo dùng `MockTransport` qua ASGI app
   (`tests/conftest.py:47`), nhưng ở đây cần mock 1 external HTTP call
   thay vì gọi app nội bộ, nên tạo `MockTransport` với 1 handler function
   trả `httpx.Response(200, json={"text": "...", "language": "..."})`.
   Vì `GroqTranscriptionClient.transcribe()` tự tạo `httpx.AsyncClient()`
   bên trong hàm (không nhận client qua tham số), cách đơn giản nhất là
   `monkeypatch.setattr(httpx, "AsyncClient", ...)` trả về 1 client dùng
   `MockTransport`, hoặc refactor `transcribe()` nhận `client` qua tham số
   optional (mặc định `None` → tự tạo) để test truyền client giả vào —
   chọn cách nào ít xâm lấn code nhất khi viết, miễn test không gọi mạng
   thật. Assert `GroqTranscriptionClient().transcribe(...)` trả đúng tuple
   `(text, language)`.
2. `test_groq_transcription_client_raises_on_http_error` — mock response
   trả status 4xx/5xx, assert `transcribe()` raise (không nuốt lỗi).
3. `test_get_transcription_client_stt_mock_false_khong_co_key` — set
   `stt_mock=False`, `groq_api_key=""`, assert `get_transcription_client()`
   raise `RuntimeError` rõ ràng.
4. `test_get_transcription_client_stt_mock_false_co_key` — set
   `stt_mock=False`, `groq_api_key="fake"`, assert trả về instance
   `GroqTranscriptionClient` (không raise).

Test hiện có (`test_transcribe_note_cap_nhat_transcript`,
`test_transcribe_note_loi_thanh_failed`) đã stub
`get_transcription_client` trực tiếp — không cần sửa, không bị ảnh hưởng
bởi thay đổi này.

File: `backend/tests/test_email_smtp.py` (đã tồn tại — có sẵn
`test_smtp_client_builds_message_and_sends` dùng đúng pattern
`monkeypatch.setattr(aiosmtplib, "send", fake_send)` cần theo). File này
đã có `AliasChoices` dùng làm mẫu trong `config.py:23`
(`model_fast` field alias `"model_chat"`) — copy đúng cách dùng đó cho
`smtp_password`, không phải kỹ thuật mới trong repo.

5. `test_smtp_password_alias_accepts_smtp_pass_env` — khởi tạo
   `Settings(_env_file=None, SMTP_PASS="xyz")` trực tiếp (không qua
   `get_settings()` singleton — alias chỉ áp dụng lúc parse env lúc khởi
   tạo), assert `settings.smtp_password == "xyz"`.
6. `test_smtp_client_uses_use_tls_when_secure` — theo đúng pattern
   `fake_send`/`monkeypatch.setattr(aiosmtplib, "send", fake_send)` có sẵn
   trong file; set `smtp_secure=True` qua
   `monkeypatch.setattr(get_settings(), "smtp_secure", True)`, gọi
   `SmtpEmailClient().send(...)`, assert
   `captured["kwargs"]["use_tls"] is True` và
   `captured["kwargs"]["start_tls"] is False`.
7. `test_smtp_client_uses_start_tls_when_not_secure` — set
   `smtp_secure=False` (giá trị default, nhưng set tường minh để test độc
   lập với default), `smtp_starttls=True` (giá trị default), assert
   `captured["kwargs"]["use_tls"] is False` và
   `captured["kwargs"]["start_tls"] is True` — đây CHÍNH LÀ hành vi cũ
   (trước thay đổi này), test này là regression test xác nhận tương thích
   ngược cho môi trường chỉ dùng `SMTP_STARTTLS`, chưa set `SMTP_SECURE`.

Test hiện có `test_smtp_client_builds_message_and_sends` chỉ assert
`captured["kwargs"]["port"] == 587` — không assert `start_tls`/`use_tls`,
nên không bị breaking bởi thay đổi này.

## Việc production (không phải code — hướng dẫn thực hiện qua SSH)

Sau khi code STT xong, deploy qua CI/CD bình thường (push `main`, workflow
tự build+deploy — xem `project-vps-deployment` memory), rồi cập nhật
`.env` production:

```
MODEL_SMART=anthropic/claude-sonnet-4-6
STT_MOCK=false
GROQ_API_KEY=<user tự lấy tại console.groq.com, free>
PUSH_MOCK=false
EMAIL_MOCK=false
```
(`PORTAL_MOCK` KHÔNG đụng tới — xem cảnh báo finding #16 ở trên.)

`SMTP_HOST`/`SMTP_PORT`/`SMTP_SECURE`/`SMTP_USER`/`SMTP_PASS`/`SMTP_FROM`
đã có sẵn trên `.env` VPS (dev FE điền 2026-08-12) — sau khi code fix
(alias `SMTP_PASS` + `smtp_secure`) deploy lên, các biến này tự đọc đúng,
không cần sửa gì thêm trên `.env`.

Sau khi sửa `.env` (thêm `MODEL_SMART`/`STT_MOCK`/`GROQ_API_KEY`/
`PUSH_MOCK`/`EMAIL_MOCK`), cần restart container để đọc config mới:
```
docker compose -f docker-compose.prod.yml up -d api worker
```
(image mới đã tự rebuild qua CI/CD nếu code STT+SMTP đã push cùng lần
deploy — bước restart này gộp chung với deploy, không cần thao tác thủ
công riêng trừ khi chỉ đổi `.env` mà không đổi code).

Verify sau khi bật:
- Gửi thử 1 voice note qua app thật, xác nhận `transcript_status` chuyển
  `done` với nội dung transcript thật (không rỗng như trước).
- Gửi thử 1 push notification, xác nhận nhận được trên điện thoại thật
  (không chỉ ghi log).
- Trigger 1 luồng gửi email thật (vd action "AI gửi mail" nếu có, hoặc
  endpoint nào gọi `email_service` trong app) và xác nhận nhận được email
  thật ở hộp thư đích, không chỉ ghi log nội bộ. Nếu Gmail chặn (ví dụ
  "App Password" hết hạn hoặc bị Google revoke), lỗi sẽ xuất hiện trong
  `docker compose logs api/worker` — kiểm tra ngay sau khi bật, đừng chờ
  người dùng report.

## Rủi ro & lưu ý

- `PORTAL_MOCK` cố tình KHÔNG bật trong plan này — rủi ro rò rỉ dữ liệu
  chéo workspace đã ghi rõ ở trên (finding #16). Xử lý riêng, sau khi có
  audit + fix code `portal_service.py` để truyền tenant đúng, hoặc xác
  nhận cổng ngoài tự phân tenant theo cách khác.
- `GROQ_API_KEY` là secret — không commit vào `.env.example` với giá trị
  thật, không log ra console/log file.
- Free tier Groq có rate limit (theo phút) — nếu traffic voice note tăng
  đột biến, có thể gặp 429. Không xử lý trong scope này (YAGNI — traffic
  hiện tại của app nội bộ thấp); nếu xảy ra thật, xử lý ở lần sau tương tự
  cách đã fix Voyage 429 (xem commit `39c062b`).
