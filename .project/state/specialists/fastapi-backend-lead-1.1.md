---
agent: fastapi-backend-lead
task_id: "1.1"
sprint: 1
title: Bỏ chặn embedding trong luồng gửi tin nhắn chat
description: Tách embedding Voyage AI ra khỏi đường đồng bộ send_message sang chạy nền, không chặn response FE
status: COMPLETE
started: 2026-07-30
completed: 2026-07-30
skills_used: []
---

## Progress

- [x] Read state file and filled `description:` field above
- [x] Đọc chat.py, embedding_service.py, worker.py
- [x] Xác nhận index_content dùng DB (query + commit) → chọn option (a) arq job
- [x] Viết test trước (TDD): test_chat_api.py + test_embedding_service.py
- [x] Thêm arq job index_chat_message vào worker.py
- [x] Đổi chat.py: enqueue_job thay vì await index_content
- [x] Chạy pytest GREEN — 825 passed, 4 skipped, 0 failed

## Files Modified

| File | Action | Notes |
|------|--------|-------|
| `backend/app/agent/worker.py` | Thêm | Hàm `index_chat_message` + đăng ký `WorkerSettings.functions` |
| `backend/app/api/chat.py` | Sửa | Thay `await embedding_service.index_content(...)` → `await arq_pool.enqueue_job("index_chat_message", ...)` |
| `backend/tests/test_chat_api.py` | Sửa/Thêm | Cập nhật test enqueue (2 jobs thay vì 1) + thêm test non-blocking |
| `backend/tests/test_embedding_service.py` | Sửa | Thêm `uuid` import, trigger `index_content` thủ công trong test search |
| `backend/tests/test_worker.py` | Thêm | Test job `index_chat_message` + test đăng ký `WorkerSettings` |

## Completion Notes

Chọn option (a) arq job vì `index_content` rõ ràng ghi DB (select + commit Embedding row) — không thể dùng asyncio.create_task với session cũ hay BackgroundTask dùng session của test engine.

Arq job `index_chat_message` mở session riêng qua `ctx["session_factory"]`, phù hợp hoàn toàn pattern hiện có trong repo (`transcribe_voice_note`, `run_deep_analysis`...).

Kết quả pytest: 825 passed, 4 skipped, 0 failed. API contract không đổi — không cần export_openapi.py.
