---
agent: fastapi-backend-lead
task_id: "2.1"
sprint: 2
title: Chat khóa ngữ cảnh theo PROJECT — Phase A (khóa cứng)
description: Thêm project_id vào Conversation, enforce scope ở tool/service layer để AI chỉ thao tác dữ liệu đúng project được chọn
status: COMPLETE
started: 2026-08-08
completed: 2026-08-08
skills_used: []
---

## Progress

- [x] Read state file and filled `description:` field above
- [x] Viết tests trước (TDD) — 19 tests, tất cả đỏ trước khi implement
- [x] Thêm project_id vào Conversation model
- [x] Tạo Alembic migration
- [x] Cập nhật schemas (ConversationCreateIn, ConversationOut)
- [x] Cập nhật API create_conversation (find-or-create + validate project)
- [x] Cập nhật call_tool với scope_project_id
- [x] Cập nhật loop.py truyền scope + inject system prompt
- [x] Cập nhật worker.py load conv.project_id
- [x] Fix bug MissingGreenlet (scope_pid phải đọc TRƯỚC rollback)
- [x] Chạy pytest GREEN — 855 passed, 4 skipped, 0 failed
- [x] Export openapi.json
- [x] Bịt lỗ hổng deep analysis: run_deep_analysis load conv.project_id + truyền scope
- [x] Viết 3 tests TDD cho deep analysis scope
- [x] Chạy pytest GREEN — 858 passed, 4 skipped, 0 failed

## Files Modified

| File | Action | Notes |
|------|--------|-------|
| `backend/app/models.py` | Sửa | Thêm `project_id: Mapped[uuid.UUID | None]` vào Conversation |
| `backend/app/schemas.py` | Sửa | ConversationCreateIn + ConversationOut thêm project_id |
| `backend/app/api/chat.py` | Sửa | create_conversation: validate project + find-or-create semantics |
| `backend/app/agent/tools.py` | Sửa | call_tool nhận scope_project_id; thêm enforcement logic + 2 helper scoped |
| `backend/app/agent/loop.py` | Sửa | run_agent_loop nhận scope; inject scope block vào dynamic_parts; truyền scope vào call_tool |
| `backend/app/agent/worker.py` | Sửa | Đọc conv.project_id (trước rollback) + truyền scope vào run_agent_loop |
| `backend/alembic/versions/a1b2c3d4e5f6_add_project_id_to_conversations.py` | Thêm | Migration: ADD COLUMN project_id + FK + index |
| `backend/tests/test_project_scoped_chat.py` | Thêm/Sửa | 22 tests TDD: API + tool scope + deep analysis scope + regression |

## Completion Notes

### Quyết định thiết kế

1. **Find-or-create semantics**: POST /conversations với project_id → tìm conversation đang sống (archived_at IS NULL) của cùng user+project, trả 200 nếu tìm thấy / tạo mới trả 201. FE phân biệt 200 vs 201 để biết "tìm lại" vs "mới hoàn toàn".

2. **Enforcement ở tool layer (call_tool)**: scope_project_id là keyword-only param của call_tool. Enforcement không phụ thuộc prompt — model không thể "nói chuyện ra ngoài scope" vì tool sẽ trả error: out_of_scope. System prompt chỉ là lớp phụ để agent diễn đạt tự nhiên.

3. **Phân loại tool theo scope**:
   - BLOCKED hoàn toàn: create_project, add_employee, lock/unlock/offboard_user, change_user_role, list_audit_events
   - Task tools (get/update/delete/assign/unassign/add_update/comment/attachment): kiểm tra task.project_id == scope; deny nếu khác
   - list_tasks: filter chỉ trả task thuộc scope project
   - list_projects: restrict chỉ trả đúng 1 project đang scope
   - create_task: ép project_id = scope (ghi đè input model)

4. **Bug fix worker.py**: scope_pid = conv.project_id phải đọc TRƯỚC maybe_compress_history vì rollback() expire mọi ORM object — đọc sau rollback gây MissingGreenlet.

### Câu hỏi mở cho PM/chủ sản phẩm

1. **Có nên cho phép "thoát khóa" trong cùng cuộc chat không?** Hiện tại scope cứng theo conversation — không thể mở rộng ra ngoài project trong cùng conv. Nếu muốn: cần API endpoint để "unscope" một conversation.

2. **Khi project bị xóa, conversation scoped của nó xử lý thế nào?** Migration dùng `ondelete='SET NULL'` nên project_id sẽ về NULL — conversation tự động trở thành unscoped. Có thể cân nhắc archive conversation thay vì unscope.

3. **Scope cho deep analysis job** (run_deep_analysis): hiện tại deep job chưa được pass scope (không có conv loaded). Nếu cần: Phase A chưa cover, Phase B sẽ làm.

### Kết quả test
855 passed, 4 skipped, 0 failed (bao gồm 19 tests mới)
