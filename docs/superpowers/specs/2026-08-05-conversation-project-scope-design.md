# Gắn project cho conversation — thiết kế

**Ngày:** 2026-08-05
**Trạng thái:** Đã duyệt (brainstorm), chờ viết plan triển khai.

## Bối cảnh

PO feedback: *"Có thể chọn project trong lúc tạo mới chat và scope chỉ trong
project đó thôi"*. Mục đích thật sự (làm rõ qua brainstorm): khi CEO đang
trao đổi về công việc của 1 project cụ thể trong 1 cuộc hội thoại, không
muốn phải nhắc lại tên project mỗi lần giao task mới trong cuộc hội thoại
đó.

## Vì sao không làm đúng nghĩa đen "chọn lúc tạo mới chat"

Điều tra kiến trúc thật (`backend/app/services/session_service.py:1-6`)
cho thấy app **không có khái niệm "user chủ động tạo chat mới"**:

- Bất biến thiết kế ghi rõ trong code: *"mỗi user có ≤1 conversation 'sống'
  (archived_at IS NULL, mới nhất)"*.
- Nút FAB "Cuộc trò chuyện mới" (`frontend/src/navigation/GlobalFab.tsx`)
  chỉ **điều hướng** về màn hình Chat — không gọi `createConversation`.
- `GET /api/v1/conversations/active` (`get_or_rotate_active_conversation`,
  `session_service.py:45-85`) mới là nơi quyết định: dùng lại conversation
  hiện có, hoặc **tự động xoay ngầm** sang conversation mới khi idle >12h
  hoặc >150 tin nhắn sống — không xoay nếu còn việc dang dở trong queue.

Phương án ban đầu (hiện modal chọn project ngay khi bấm FAB) không có chỗ
đứng trong kiến trúc này. Phương án mở rộng hơn (thêm nút "tạo mới thủ
công" thật sự, cho phép nhiều conversation active cùng lúc) đã được cân
nhắc và **loại bỏ** vì phá vỡ bất biến "≤1 conversation sống" — ảnh hưởng
dây chuyền tới `_active_conv`, rotate, watchdog; vượt xa phạm vi PO yêu cầu.

## Quyết định: gắn/đổi project cho conversation đang mở, bất kỳ lúc nào

Thay vì "chọn lúc tạo", cho phép gắn/đổi `project_id` của conversation
**hiện có** — đúng tinh thần PO (khỏi gõ lặp tên project trong 1 đoạn hội
thoại) mà không đụng bất biến kiến trúc.

## Phạm vi tính năng (đã chốt)

- Gắn project là **tùy chọn**, mặc định không gắn gì (không đổi hành vi cũ).
- Áp dụng cho **duy nhất 1 hành vi**: khi conversation có `project_id` và
  AI gọi `create_task` mà người dùng không chỉ rõ project khác trong câu
  → tự dùng project đã gắn làm mặc định.
- **Không** ảnh hưởng các tool đọc (`list_tasks`, `get_project_health`...)
  — người dùng hỏi gì AI vẫn trả lời đúng phạm vi câu hỏi, không bị khóa
  cứng vào project.
- Đổi được project đã gắn bất kỳ lúc nào, giống hệt UX đổi tên conversation
  đã có sẵn.
- Nếu project bị xóa, conversation tự động gỡ về "không gắn project"
  (không lỗi, không mất conversation).

## Backend

1. Thêm cột `project_id: uuid.UUID | None` vào bảng `conversations`
   (`backend/app/models.py`, class `Conversation`) — FK `projects.id`,
   `ondelete="SET NULL"`, nullable.
2. `PATCH /api/v1/conversations/{id}` (endpoint rename hiện có,
   `backend/app/api/chat.py`) mở rộng nhận thêm `project_id: uuid.UUID |
   None` tùy chọn trong body — cùng payload với đổi tên, không tách route
   riêng.
3. `ConversationOut` (`backend/app/schemas.py`) thêm `project_id` và
   `project_name` (denormalized, để FE hiển thị badge không cần gọi thêm
   API list projects).
4. Build context mỗi lượt trong `run_agent_loop`
   (`backend/app/agent/loop.py`): nếu `conversation.project_id` có giá
   trị, thêm 1 đoạn vào phần "dynamic" của system prompt (cùng chỗ với
   instructions/snapshot/rag_context hiện có):
   > "Cuộc trò chuyện này đang gắn với project '{tên}' — khi tạo task mới
   > (create_task) mà người dùng không chỉ rõ project khác, dùng project
   > này làm mặc định."

   Đây là cách nhẹ nhất — không sửa logic tool `create_task`, chỉ hướng
   dẫn model qua prompt, nhất quán với cách hệ thống xử lý các default
   khác (coach_block, memories_text...).

## Frontend

1. `frontend/app/main/conversations.tsx`: mở rộng modal sửa tên hiện có
   (dòng ~192-220) để thêm 1 phần chọn project (dropdown/picker, có lựa
   chọn "Không gắn project"). Dùng chung nút "Lưu" hiện có, gọi
   `renameConversation` mở rộng (hoặc 1 hàm API mới `updateConversation`
   nhận cả `title` và `project_id`).
2. `frontend/app/main/chat.tsx`: hiện badge nhỏ tên project đang gắn (nếu
   có) ở header màn hình chat cho conversation đang mở; bấm vào mở modal
   đổi (tái dùng từ (1) nếu khả thi, hoặc modal riêng gọn hơn ngay tại
   chat).

## Việc cần làm (tổng quan, chi tiết ở plan triển khai)

1. Migration Alembic: thêm cột `project_id` vào `conversations`.
2. Model `Conversation` + relationship (nếu cần) trong `models.py`.
3. Schema `ConversationOut`/`ConversationUpdateIn` (hoặc field tương ứng)
   trong `schemas.py`.
4. API `PATCH /api/v1/conversations/{id}` mở rộng nhận `project_id`.
5. `_build_system_prompt`/build context: tiêm đoạn hướng dẫn khi có
   `project_id`.
6. Frontend: API client (`frontend/src/api/chat.ts`), modal chọn project
   trong `conversations.tsx`, badge + link đổi trong `chat.tsx`.
7. Test:
   - Gắn project → tạo task không chỉ rõ project → xác nhận task được gán
     đúng `project_id`.
   - Gắn project → tạo task CÓ chỉ rõ project khác trong câu → xác nhận
     dùng đúng project user nói, không phải default.
   - Xóa project đang gắn với 1 conversation → xác nhận conversation tự
     về `project_id = NULL`, không lỗi, conversation vẫn dùng được bình
     thường.
   - Conversation không gắn project (mặc định) → hành vi y hệt trước khi
     có tính năng này (backward compatible).
8. `python scripts/export_openapi.py` sau khi route ổn định.

## Ngoài phạm vi (chưa làm ở lần này)

- Không thêm cơ chế "tạo conversation mới thủ công" — đã cân nhắc và loại
  bỏ vì phá vỡ bất biến "≤1 conversation sống" (xem mục "Vì sao không làm
  đúng nghĩa đen" ở trên).
- Không mở rộng default sang các tool khác ngoài `create_task` (không áp
  dụng cho `list_tasks`, `create_note`, `get_project_health`...).
- Không "khóa cứng" conversation vào 1 project — người dùng vẫn hỏi/thao
  tác được về project khác trong cùng conversation bình thường.
