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
