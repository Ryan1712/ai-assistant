# ai-assistant

Trợ lý AI quản lý công việc — app mobile chat-first (CEO/manager/nhân viên điều hành
công việc bằng cách nhắn cho AI). Xem `CLAUDE.md` (quy ước) và `funtional-plan.md`
(spec chức năng) trước khi làm việc lớn.

Solo dev, full-stack: `backend/` (Python/FastAPI + Postgres + Redis/arq + Claude)
và `frontend/` (React Native/Expo).

## Chạy dev — quick start

### 1. Hạ tầng (Docker)

```powershell
cd backend
docker compose up -d postgres redis
```

Postgres host port **5435**, Redis **6380** (không phải mặc định 5432/6379 —
port hay bị project Docker khác trên máy chiếm, xem `CLAUDE.md`).

### 2. Backend

```powershell
cd backend
.venv\Scripts\activate          # tạo venv trước nếu chưa có: python -m venv .venv
pip install -r requirements.txt
copy .env.example .env          # rồi điền ANTHROPIC_API_KEY (+ ANTHROPIC_BASE_URL nếu qua gateway)
alembic upgrade head
pytest tests/ -v                # 216 test, ~5-8 phút

# 2 process riêng, cả hai đọc backend/.env:
uvicorn app.main:app --reload              # http://localhost:8000/docs
arq app.agent.worker.WorkerSettings        # xử lý chat request (bắt buộc, không thì tin nhắn kẹt "queued")
```

Đổi API contract (route/schema) → chạy `python scripts/export_openapi.py` để
cập nhật `openapi.json` ở repo root cho FE.

### 3. Frontend

```powershell
cd frontend
npm install
```

Tạo `.env` (hoặc export trực tiếp) với IP LAN của máy backend — Expo Go trên điện
thoại không hiểu `localhost`:

```
EXPO_PUBLIC_API_URL=http://<ip-máy-dev>:8000
```

```powershell
npx expo start
```

Quét QR bằng Expo Go trên điện thoại (cùng mạng LAN với máy dev).

Trước khi sửa UI: đọc `frontend/DESIGN.md` (guideline) và dùng token trong
`frontend/src/ui/theme.ts` — đừng hardcode màu/spacing.

## Gotcha đã gặp

- **Model Claude phải dùng id có prefix `anthropic/`** khi đi qua gateway trung
  gian (vd `ANTHROPIC_BASE_URL` khác api.anthropic.com) — id không prefix có thể
  bị route sai và ghi đè system prompt. Xem comment trong `app/config.py`.
- **`alembic` ưu tiên env `DATABASE_URL`** nếu set, không thì dùng URL hardcode
  trong `alembic.ini` — tránh migrate nhầm DB khi port bị chiếm.
- **Không sửa file `.md` tiếng Việt bằng `Get-Content | Set-Content` trong
  PowerShell** — codepage mặc định làm hỏng UTF-8 (mojibake). Dùng editor/tool
  ghi file trực tiếp.
- **Worker (`arq`) là process bắt buộc riêng** — quên chạy thì mọi tin nhắn chat
  kẹt ở trạng thái `queued` vĩnh viễn dù API vẫn trả 201 bình thường.

## Test

```powershell
cd backend && pytest tests/ -v
cd frontend && npx tsc --noEmit && npx expo export
```

## Crash Reporting & Sentry

### Cách xem crash log (CEO)

Gọi `GET /api/v1/crash-logs/summary` bằng tài khoản CEO qua Swagger tại
`https://ai-assistant.9learning.edu.vn/docs` — đây là nơi trả lời câu
"app đang crash vì việc gì" mà không cần xem log server.

Hoặc dùng curl (thay `<TOKEN>` bằng JWT của tài khoản CEO):

```bash
curl -s \
  -H "Authorization: Bearer <TOKEN>" \
  "https://ai-assistant.9learning.edu.vn/api/v1/crash-logs/summary" \
  | python3 -m json.tool
```

Response trả về danh sách nhóm lỗi theo `fingerprint`: số lần xảy ra,
số user bị ảnh hưởng, thời điểm đầu/cuối, và message mẫu.

---

### Cài đặt Sentry DSN (native crash)

> **Lưu ý**: `@sentry/react-native` là **native module** — phải build lại
> dev-client hoặc build EAS, **KHÔNG chạy được trên Expo Go**.
> Thiếu DSN thì Sentry tự tắt, app vẫn chạy bình thường (ADR-003).

**Bước 1 — Lấy DSN từ sentry.io**

1. Đăng nhập [sentry.io](https://sentry.io) → tạo project (platform: React Native).
2. Vào **Settings → Projects → {project} → Client Keys (DSN)**.
3. Sao chép DSN dạng `https://<key>@o<org>.ingest.sentry.io/<project-id>`.

**Bước 2 — Gắn DSN vào EAS (không commit vào repo)**

```bash
# Chạy một lần, DSN được lưu ở EAS server và tự inject khi build
eas secret:create \
  --scope project \
  --name EXPO_PUBLIC_SENTRY_DSN \
  --value "https://<key>@o<org>.ingest.sentry.io/<project-id>"
```

Khi build EAS (`eas build --profile preview` hoặc `--profile production`),
giá trị secret tự ghi đè `EXPO_PUBLIC_SENTRY_DSN=""` trong `eas.json`.

**Kiểm tra secrets hiện có:**

```bash
eas secret:list
```

**Dev local** — không cần Sentry, để biến rỗng trong `frontend/.env`:

```
EXPO_PUBLIC_SENTRY_DSN=
```
