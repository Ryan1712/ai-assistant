# Thiết kế Plan 3 — Lõi Chat/Agent (queue → agent loop → streaming)

**Ngày:** 2026-07-09 · **Trạng thái:** Đã duyệt qua brainstorming · **Kiến trúc nền:** [2026-07-08-backend-architecture-design.md](2026-07-08-backend-architecture-design.md) §3, §5, §9 · **Spec chức năng:** [funtional-plan.md](../../../funtional-plan.md) §5, §5.6

Các lựa chọn kỹ thuật tầng nền (FastAPI/arq/Redis/WebSocket, Postgres-persisted queue, skill 2 lớp...) đã chốt trong backend-architecture-design.md — tài liệu này chỉ cụ thể hóa cách triển khai cho phần **chưa được xây**: khung chat + agent loop + tool-calling, nối vào `work_service`/`skill_service`/`auth_service` đã có từ Plan 1 & 2.

---

## 1. Phạm vi & Ranh giới

**Trong phạm vi (Plan 3):**
- Model mới: `conversations`, `chat_requests`, `messages`, `usage_log`.
- REST: tạo/liệt kê conversation, gửi tin nhắn (enqueue), sửa/hủy/sắp-xếp-lại/chèn-ưu-tiên hàng đợi, xác nhận hành động nhạy cảm, dừng một request/dừng tất cả.
- WebSocket: stream token + trạng thái theo từng conversation.
- Worker (arq) chạy agent loop gọi Claude (Haiku, model lấy từ config theo tác vụ) với **21 tool** bọc toàn bộ `work_service` + `skill_service` + phần liên quan của `auth_service` (`create_invite`, `lock_user`, `unlock_user`) — cả tool đọc lẫn tool ghi.
- Xác nhận 2 bước cho `lock_user`/`unlock_user` (tool nhạy cảm duy nhất hiện có ở tầng service).
- Hàng đợi FIFO theo conversation, dừng/hủy, bỏ-qua-khi-lỗi + giữ lỗi trong lịch sử để yêu cầu sau "thấy" được.
- `usage_log` + giới hạn số lời gọi Claude đồng thời (qua `arq max_jobs`, xem §3) + prompt caching kỷ luật (system prompt đóng băng, không nhúng timestamp/tên user).
- Test: `FakeLLMClient` + `FakeEventPublisher` — toàn bộ TDD chạy không cần Anthropic API key / Redis thật.

**Ngoài phạm vi (đẩy sau):**
- `generate_report` / xuất Excel → Plan 4 (tổng hợp + báo cáo).
- `send_email` → chưa có tầng OAuth send-as trong `auth_service`; thuộc Giai đoạn 2 funtional-plan §10.
- Voice note, dashboard tổng quan, tìm kiếm xuyên suốt, báo cáo định kỳ tự động.
- Lệnh tường minh "tiếp tục công việc" sau mất mạng (§5.7 funtional-plan) — cơ chế nền (request dang dở giữ nguyên trong Postgres, không tự chạy lại) đã có sẵn nhờ queue persist ở DB; endpoint/lệnh kích hoạt tường minh để lại cho lần sau nếu Plan 3 đã đủ dài.

---

## 2. Data model mới

```
Conversation
  id, workspace_id, user_id (chủ sở hữu), title (nullable), created_at

ChatRequest
  id, workspace_id, conversation_id, user_id (actor gửi — luôn từ JWT, không nhận qua field client)
  content: text
  status: queued | running | awaiting_confirmation | done | failed | cancelled
  queue_position: float          # fractional index — chèn ưu tiên / sắp xếp lại chỉ update 1 dòng
  pending_action: jsonb nullable # {tool_name, tool_input} khi status=awaiting_confirmation
  error: text nullable
  result_summary: text nullable
  created_at, started_at nullable, finished_at nullable

Message
  id, workspace_id, conversation_id, chat_request_id nullable
  role: user | assistant         # khớp thẳng Anthropic Messages API roles
  content: jsonb                 # list content block nguyên dạng (text / tool_use / tool_result)
  created_at

UsageLog
  id, workspace_id, chat_request_id nullable, model
  input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
  created_at
```

Ghi chú thiết kế:
- `queue_position` dùng fractional-index (kiểu Trello ordering): chèn ưu tiên = set nhỏ hơn min hiện có; sắp xếp lại = đổi 1 giá trị, không renumber cả hàng đợi.
- `pending_action` nằm ngay trên `chat_requests` (không tách bảng) vì 1 request chỉ có tối đa 1 hành động chờ xác nhận tại một thời điểm.
- `Message.content` lưu nguyên khối JSON theo format Anthropic — agent loop nạp thẳng lại làm history cho lần gọi Claude kế tiếp, không cần lớp chuyển đổi qua lại.

---

## 3. Kiến trúc runtime & luồng xử lý

**Tách tiến trình:** `api` (FastAPI, REST + WS, đã có) và `worker` (arq, mới) — 2 service Docker Compose dùng chung image, khác entrypoint.

**Gửi tin nhắn** — `POST /api/v1/conversations/{id}/messages {content}`:
1. Check actor sở hữu conversation (workspace + user_id khớp) → 404 nếu không.
2. Insert `chat_requests` (status=`queued`, `queue_position` = lớn nhất hiện có của conversation +1) + `messages` (role=`user`).
3. `arq_pool.enqueue_job("process_conversation", conversation_id, _job_id=f"conv:{conversation_id}")`. arq dedupe theo `_job_id`: nếu job cho conversation này đang chạy/đang chờ, enqueue thứ 2 no-op → **tự nhiên đảm bảo 1 conversation chỉ có 1 agent loop chạy tại 1 thời điểm**, khác conversation chạy song song. `arq WorkerSettings.max_jobs` giới hạn số job (= số agent loop = số lời gọi Claude) đồng thời — đóng luôn vai trò semaphore của §4 kiến trúc nền, không cần cơ chế riêng.
4. Trả `chat_request.id` + `queued` ngay — API không bao giờ chặn.

**Worker `process_conversation(conversation_id)`:** vòng lặp — lấy `chat_request` `queued` có `queue_position` nhỏ nhất của conversation, chạy agent loop cho nó, lặp tới khi hết `queued`. Agent loop mỗi request:
1. Nạp toàn bộ `messages` của conversation làm history → gọi `LLMClient.stream(system, messages, tools)` (system prompt đóng băng + tool list cố định thứ tự deterministic → cache hit).
2. Mỗi text delta → publish qua `EventPublisher` lên kênh `conv:{id}` (Redis pub/sub) → WS forward (`type:"token"`).
3. Gặp `tool_use`:
   - Tool nhạy cảm (`lock_user`/`unlock_user`) chưa được xác nhận cho lần gọi này → lưu `pending_action`, `status=awaiting_confirmation`, publish `confirmation_required`, **kết thúc xử lý request này** — vòng lặp `process_conversation` chuyển sang request `queued` kế tiếp (không chặn yêu cầu độc lập khác, đúng funtional-plan §5.2).
   - Tool thường (hoặc đã confirm) → gọi thẳng hàm service với `actor` dựng từ `req.user_id`. Lỗi service (`HTTPException` 403/404/422) → bọc thành `tool_result` lỗi `{"error": "forbidden", "message": "Bạn không có quyền làm điều này."}`, Claude tự đọc lại cho user — không catch-all nuốt lỗi khác.
4. Claude trả `end_turn` → `status=done`, `result_summary` = text cuối, publish `request_done`.
5. Lỗi hạ tầng (429/DB...) → `status=failed`, ghi `error`, publish `request_failed`, **không dừng** các request `queued` khác của conversation.

**Xác nhận 2 bước** — `POST /api/v1/chat/requests/{id}/confirm {approved}`: chỉ actor tạo request được xác nhận (`req.user_id == current_user.id`, không dựa theo prompt). Approve → `status=queued` trở lại, re-enqueue qua cùng cơ chế `_job_id`; tool thật sự chạy khi tới lượt, **quyền được check lại lúc thực thi** (không tin vào lúc đề xuất — actor có thể mất quyền giữa lúc đề xuất và lúc xác nhận). Deny → `tool_result="user_denied"`, hội thoại tiếp tục/kết thúc bình thường.

**Dừng/hủy:**
- Hủy request `queued` = update `status=cancelled` trực tiếp (worker bỏ qua khi tới lượt).
- Dừng request `running` = set Redis key `cancel:{request_id}` (TTL ngắn); agent loop kiểm tra cờ này giữa các bước/chunk, thoát sạch nếu thấy, set `status=cancelled`.
- "Dừng tất cả" = hủy mọi `queued` của conversation + set cờ cancel cho request đang `running`.

**WebSocket:** `wss://.../ws/conversations/{id}?token=<access_token>` — xác thực qua query param (đơn giản nhất cho React Native, không cần custom header lúc handshake). Mỗi kết nối subscribe kênh Redis `conv:{id}`.

---

## 4. Tầng Tool — bọc service thành tool cho Claude

- Registry `app/agent/tools.py`: mỗi tool = `{name, description, input_schema, handler, sensitive: bool}`.
- `input_schema` sinh từ chính Pydantic schema REST đã có (`.model_json_schema()` của `TaskCreateIn`, `ProjectPatchIn`...) — không định nghĩa lại, tránh lệch giữa REST contract và tool contract.
- `handler(db, actor, **kwargs)` gọi thẳng hàm service tương ứng, trả **dict tóm tắt** (không dump ORM/JSON đầy đủ — vd. `assign_task` trả `{"task_id", "assignee_id", "already_assigned"}` chứ không trả cả `Task`).
- `SENSITIVE_TOOLS = {"lock_user", "unlock_user"}` — set cố định, agent loop check trước khi thực thi.

**21 tool:**

| Nhóm | Tool |
|---|---|
| Project (3) | `create_project`, `update_project`, `list_projects` |
| Task (6) | `create_task`, `update_task`, `list_tasks`, `get_task`, `assign_task`, `unassign_task` |
| Tiến độ (2) | `add_task_update`, `list_task_updates` |
| Bình luận (2) | `add_comment`, `list_comments` |
| Skill (5) | `create_skill`, `add_skill_version`, `grant_skill`, `list_skills`, `use_skill` |
| Tài khoản (3) | `create_invite`, `lock_user` (nhạy cảm), `unlock_user` (nhạy cảm) |

---

## 5. Testing

Không phụ thuộc Anthropic API thật — đúng quy ước TDD của dự án (test trước, code sau):

- **`LLMClient`** interface (`app/agent/llm_client.py`): `stream(system, messages, tools) -> AsyncIterator[Event]`. Prod impl gọi Anthropic SDK; `FakeLLMClient` trong test nhận kịch bản dựng sẵn (chuỗi text/tool_use/stop qua nhiều lượt) — dựng được test multi-turn tool-calling mà không cần mạng.
- **`EventPublisher`** interface bọc Redis pub/sub tương tự — `FakeEventPublisher` trong test để assert đúng event publish mà không cần Redis thật.
- Unit: `run_agent_loop(db, req, fake_llm, fake_publisher)` test trực tiếp qua `db_session` (SQLite, như Plan 1/2) — status transitions, tool execute, lỗi quyền relay, xác nhận 2 bước, cờ hủy.
- Integration nhẹ: REST endpoints (enqueue/confirm/cancel/reorder) với arq pool mock — assert `enqueue_job` gọi đúng `_job_id`.
- WS: FastAPI `TestClient` WebSocket + `FakeEventPublisher` — assert token/status event forward đúng.
- Không cần `ANTHROPIC_API_KEY` để chạy `pytest tests/`. Kịch bản Claude thật (E2E mỏng, kiến trúc nền §9) chạy thủ công/staging, không vào CI.

---

## 6. Infra & Config mới

- `requirements.txt`: thêm `anthropic`, `arq`, `redis` (async client, arq phụ thuộc sẵn).
- `docker-compose.yml`: thêm service `worker` (cùng image `api`, `command: arq app.agent.worker.WorkerSettings`, `depends_on: [postgres, redis]`, cùng env).
- `config.py`: thêm `anthropic_api_key`, `redis_url` (`redis://localhost:6379` dev / `redis://redis:6379` trong compose), `model_chat: str = "claude-haiku-4-5"` (model theo tác vụ — hiện chỉ 1 loại "chat", chừa chỗ thêm loại sau không hardcode).
- `.env.example` bổ sung 2 dòng trên.

---

## Self-review

- **Placeholder scan:** không có TBD/`...` ngoài khối schema minh họa.
- **Internal consistency:** `pending_action`/`SENSITIVE_TOOLS` khớp nhau (đúng 2 tool); `_job_id` dedupe (§3) và giới hạn concurrency qua `arq max_jobs` không mâu thuẫn — cả hai cùng dựa trên cơ chế queue của arq, không chồng lấn.
- **Scope check:** tập trung đúng 1 subsystem (chat/agent core), loại report/Excel và email ra ngoài như đã thống nhất — đủ gọn cho 1 implementation plan theo phong cách Plan 1/2.
- **Ambiguity check:** quyền xác nhận hành động nhạy cảm giới hạn đúng 1 người (actor tạo request) — không mơ hồ giữa "actor" và "bất kỳ CEO nào".
