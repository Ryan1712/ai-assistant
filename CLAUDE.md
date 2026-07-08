# AI Assistant — Trợ lý AI Quản lý Công việc (SaaS)

App mobile chat-first: CEO/manager/nhân viên điều hành công việc bằng cách nhắn cho AI.
Đội 2 dev: BE (Python, kiêm AI/LLM) + FE (React Native/Expo).

## Tài liệu nguồn (đọc trước khi làm việc lớn)
- Spec chức năng: `funtional-plan.md` (tên file cố ý giữ nguyên, đừng "sửa chính tả")
- Thiết kế BE: `docs/superpowers/specs/2026-07-08-backend-architecture-design.md`
- Plans: `docs/superpowers/plans/`

## Lệnh thường dùng (chạy trong `backend/`)
- Kích hoạt venv (Windows): `.venv\Scripts\activate`
- Test: `pytest tests/ -v`
- Chạy dev: `uvicorn app.main:app --reload` → Swagger tại http://localhost:8000/docs
- Hạ tầng local: `docker compose up -d postgres redis`
- Migration: `alembic revision --autogenerate -m "..."` rồi `alembic upgrade head`
- Export contract cho FE: `python scripts/export_openapi.py` (ghi `openapi.json` ở repo root)

## Quy ước bất di bất dịch
- Mọi bảng (trừ `workspaces`) có `workspace_id`; mọi query phải lọc theo workspace.
- Quyền kiểm tra ở **service layer** (`app/permissions.py`), không bao giờ ở prompt/model.
- Danh tính (`actor`) lấy từ JWT phiên đăng nhập — không bao giờ từ tham số client hay model.
- Model LLM lấy từ config theo loại tác vụ — không hardcode model ID.
- Route dưới `/api/v1`. Đổi API contract = chạy lại export_openapi cho FE.
- TDD: test trước, code sau; mỗi task một commit.
- Không commit secrets; dùng `.env` (đã gitignore).

## Bài học (bổ sung khi Claude/dev làm sai điều gì đáng nhớ)
- (trống)
