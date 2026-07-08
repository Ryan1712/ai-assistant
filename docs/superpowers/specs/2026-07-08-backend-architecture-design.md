# Thiết kế Backend — Trợ lý AI Quản lý Công việc (SaaS)

**Ngày:** 2026-07-08 · **Trạng thái:** Đã duyệt qua thảo luận · **Spec chức năng:** [funtional-plan.md](../../../funtional-plan.md)

**Bối cảnh đội:** 2 dev — 1 BE kiêm tích hợp AI/LLM (chủ spec này), 1 FE dev (React Native/Expo). FE bám theo API contract ở Mục 7.

---

## 1. Tech stack (đã chốt)

| Lớp | Lựa chọn | Lý do chính |
|---|---|---|
| Ngôn ngữ / framework | **Python + FastAPI** (async, Pydantic v2) | BE dev mạnh Python nhất; Swagger tự sinh; Anthropic Python SDK first-class |
| Database | **PostgreSQL** + SQLAlchemy 2.0 async + Alembic | Nguồn chuẩn duy nhất; multi-tenant từ schema |
| Queue & pub/sub | **Redis + arq** | Hàng đợi job + kênh streaming token về API |
| LLM | **Claude Haiku 4.5** (`claude-haiku-4-5`) qua Anthropic API | Rẻ nhất nhà Claude ($1/$5 per 1M tokens), tool use tin cậy. Model đặt trong **config theo loại tác vụ** — nâng tác vụ khó lên Sonnet chỉ là đổi config |
| Realtime với app | **WebSocket** | React Native hỗ trợ WS tốt hơn SSE nhiều |
| FE client | TS client + React Query hooks **tự sinh từ openapi.json** (orval) | Contract-first, không viết interface tay |
| Deploy | **Docker Compose trên VPS** (4 container: api, worker, postgres, redis) | Rẻ, kiểm soát toàn bộ, đủ cho MVP → khách đầu tiên |
| File storage | Lớp `Storage` trừu tượng: MVP = local disk, thương mại = S3-compatible (DO Spaces) | Tránh nợ kỹ thuật khó trả nhất |

**Đã cân nhắc và loại:**
- *TypeScript/NestJS*: cùng ngôn ngữ với FE nhưng BE dev viết chậm hơn ở phần khó nhất (agent loop, quyền, queue). Lợi thế "chung type" được bù bằng OpenAPI codegen.

---

## 2. Kiến trúc tổng thể

```
┌─────────────┐   HTTPS/WSS    ┌──────────────┐
│ React Native │ ─────────────▶ │  api (FastAPI)│──── REST /api/v1, Swagger /docs
│ (Expo)       │ ◀───────────── │  stateless    │
└─────────────┘   WebSocket    └──────┬───────┘
                                      │ enqueue                ┌──────────┐
                                      ▼                        │ postgres  │
                               ┌──────────────┐                │ nguồn     │
                               │ redis         │◀──────────────│ chuẩn     │
                               │ job queue     │               └──────────┘
                               │ pub/sub       │                     ▲
                               └──────┬───────┘                     │
                                      ▼                              │
                               ┌──────────────┐  Claude API          │
                               │ worker (arq)  │───────────▶ tools ──┘
                               │ agent loop    │            (kiểm tra quyền tại đây)
                               └──────────────┘
```

- **api** — stateless; nhận REST + giữ WebSocket. Gửi tin nhắn chat = ghi hàng đợi rồi trả về ngay, không bao giờ chặn.
- **worker** — arq, chạy agent loop (Claude API + tools). Tách riêng để việc chạy lâu không ảnh hưởng API; scale độc lập.
- **postgres** — workspace, user, task, skill, **hàng đợi chat persist tại đây** (sống sót qua restart — phục vụ "tiếp tục công việc", funtional-plan §5.7), nhật ký.
- **redis** — job queue cho arq + pub/sub đẩy token streaming từ worker về đúng WebSocket.

**Tính chất scale (thiết kế mua sẵn):** api stateless + pub/sub → nhân bản api sau load balancer không cần sticky session; worker ăn queue → tăng container là tăng throughput; `workspace_id` mọi bảng → thêm tenant không thêm kiến trúc.

---

## 3. Luồng chat: queue → agent → streaming (lõi sản phẩm)

1. **Gửi tin nhắn** → api ghi `chat_requests` (status `queued`, thứ tự trong conversation) → enqueue arq → trả `request_id` ngay. Ô chat không bao giờ khóa.
2. **FIFO theo conversation**: khóa theo `conversation_id` — cùng cuộc chat chạy tuần tự, khác cuộc chat song song. Sửa/xóa/sắp xếp/chèn ưu tiên hàng đợi = update bản ghi `queued` trong Postgres.
3. **Agent loop** (worker): gọi Claude (streaming) với:
   - **System prompt đóng băng** (không timestamp/tên user) + danh sách tools cố định, thứ tự deterministic → ăn prompt caching. Bối cảnh động (workspace, user hiện tại) đẩy xuống message, sau breakpoint cache.
   - **Tools**: `create_task`, `assign_task`, `update_progress`, `use_skill`, `generate_report`, `send_email`, `lock_account`, `create_invite`... Mỗi tool nhận `actor` từ job payload (← JWT phiên đăng nhập, **không bao giờ do model cung cấp**) và gọi service layer có permission check. Không đủ quyền → tool trả lỗi → AI truyền đạt *"Bạn không có quyền làm điều này."*
   - **Tool nhạy cảm 2 bước** (gửi mail, khóa tài khoản, xóa dữ liệu): bước 1 trả về "đề xuất" → request chuyển `awaiting_confirmation`, app hiện nút xác nhận → user bấm → bước 2 thực thi thật. Cưỡng chế ở backend, không phụ thuộc AI tự giác hỏi.
4. **Streaming**: worker publish token/trạng thái ("đang xử lý 1/3", "đang tạo báo cáo...") lên Redis channel `conv:{id}` → api forward qua WebSocket.
5. **Lỗi** (429, DB...): đánh dấu `failed` kèm lý do, **ghi kết quả lỗi vào lịch sử hội thoại** để yêu cầu sau nhìn thấy; yêu cầu phụ thuộc vào cái đã lỗi → AI báo và bỏ qua, không tự chọn đối tượng thay thế (funtional-plan §5.2); yêu cầu độc lập chạy tiếp.
6. **Dừng/hủy**: hủy yêu cầu chờ = update status; dừng yêu cầu đang chạy = cờ cancel trong Redis, agent loop kiểm tra giữa các bước và thoát sạch.
7. **Mất mạng**: hàng đợi không tự chạy lại; job dang dở giữ trạng thái trong Postgres, chỉ tiếp tục khi user gõ "tiếp tục công việc" (§5.7).

---

## 4. Chiến lược chi phí & rate limit (Claude API là điểm nghẽn thật)

**MVP làm ngay:**
- **Prompt caching** — kỷ luật như §3; giảm ~80–90% chi phí input lặp lại.
- **`usage_log`** — ghi input/output/cache tokens của mỗi request theo workspace → dashboard chi phí + nền cho pricing per-seat kèm quota fair-use.
- **Semaphore worker** — trần số lời gọi Claude đồng thời; quá tải thì yêu cầu chờ trong queue thay vì văng 429.
- **Retry backoff** — SDK tự retry 429/5xx; tầng job requeue trước khi fail hẳn.
- **Ngữ cảnh gọn** — giới hạn cửa sổ lịch sử gửi đi; tool results trả bảng tóm tắt, không dump JSON đầy đủ.

**Giai đoạn 2:** phân tầng model theo tác vụ (Haiku → Sonnet cho việc khó, config-driven, quyết định bằng số liệu `usage_log`); quota token-bucket per-workspace; 2 queue ưu tiên (chat tương tác > việc nền).

**Giai đoạn 3:** Batches API (−50%) cho báo cáo định kỳ; compaction cho hội thoại dài; cân nhắc DeepSeek (host Mỹ) cho tác vụ rẻ tiền.

---

## 5. Mô hình dữ liệu (mọi bảng có `workspace_id`; enforce qua repository chung)

| Nhóm | Bảng | Ghi chú |
|---|---|---|
| Tenant & người | `workspaces`, `users`, `invites`, `devices`, `login_events` | `users` gộp tài khoản + nhân sự: role (ceo/manager/employee), `manager_id` (cây phân cấp), `is_root`, `status` (active/locked). `invites` mang sẵn vai trò + manager |
| Chat | `conversations`, `chat_requests`, `messages` | `chat_requests.status`: queued/running/awaiting_confirmation/done/failed/cancelled. `messages` lưu cả tool call/result |
| Công việc | `projects`, `tasks`, `task_assignees`, `task_updates`, `task_comments` | `task_updates` là nguồn cho báo cáo tổng hợp |
| Skill (2 lớp) | `skills`, `skill_versions`, `skill_grants`, `skill_usage_log` | Nội dung CEO soạn có version; trạng thái task ghép lúc truy vấn; log ghi cả version đã đọc |
| Khác | `voice_notes`, `reports`, `notifications`, `audit_log`, `usage_log` | `audit_log`: khóa/mở tài khoản, sửa skill, hành động nhạy cảm |

---

## 6. Auth, thiết bị, quyền

- **JWT 2 lớp**: access ~15 phút + refresh xoay vòng lưu DB. **Khóa tài khoản** = `status=locked` + thu hồi mọi refresh token (văng khỏi mọi thiết bị ≤ 15 phút) + middleware chặn ngay API nhạy cảm.
- **Đăng nhập** kèm `device_uuid` + tên thiết bị → upsert `devices`, ghi `login_events` (không giới hạn thiết bị, log đầy đủ).
- **Yêu cầu mở khóa**: endpoint công khai nhận email + device_uuid → notification cho CEO gốc.
- **Workspace kiểu Slack**: người tạo workspace = CEO gốc (không ai khóa được); vào workspace chỉ qua invite (kèm vai trò + manager); chỉ CEO gốc khóa/mở tài khoản vai trò CEO.
- **Quyền thực thi ở service layer** (decorator kiểm role + cây phân cấp), tool chỉ là người gọi — chống được cả prompt injection.

---

## 7. API contract cho FE dev

- **REST**: FastAPI tự sinh **Swagger UI `/docs`** + `openapi.json`; route dưới `/api/v1/`.
- **TS client tự sinh**: script export `openapi.json` → FE chạy **orval** sinh client TS + React Query hooks. Contract lệch = TypeScript báo đỏ.
- **WebSocket events** (OpenAPI không tả được): định nghĩa bằng Pydantic models → export JSON Schema + `docs/ws-events.md`. Events: `token`, `status_update`, `queue_position`, `request_done`, `request_failed`, `confirmation_required`, `notification`.

---

## 8. Lộ trình hạ tầng theo tăng trưởng

| Giai đoạn | Hạ tầng | Việc bắt buộc |
|---|---|---|
| MVP → khách đầu | 1 VPS, Docker Compose | **Backup Postgres offsite tự động + monitoring (Sentry, uptime)** ngay khi có khách trả tiền |
| Doanh thu ổn định | VPS + managed Postgres | Đổi connection string |
| Tải lớn | Nhiều VPS + LB (hoặc k8s) | Nhân bản api/worker — code không đổi |

Điểm nghẽn thật là Claude API (đã xử lý ở §4), không phải hạ tầng: 1 VPS 8GB phục vụ được hàng trăm workspace vì app chỉ điều phối async I/O.

---

## 9. Kiểm thử

- **Unit**: permission decorator (ma trận vai trò × hành động — bảng test sinh từ funtional-plan §3), tool handlers, queue state machine (các chuyển trạng thái hợp lệ của `chat_requests`).
- **Integration**: agent loop với Claude API mock (kịch bản: tool call đúng/sai quyền, lỗi giữa chừng, cancel, xác nhận 2 bước); luồng invite → signup → cây phân cấp; khóa tài khoản → token bị thu hồi.
- **Contract**: snapshot `openapi.json` trong CI — thay đổi contract phải là diff có chủ đích để FE biết.
- **E2E mỏng**: một kịch bản Luồng 6 (3 yêu cầu liên tiếp, yêu cầu 2 lỗi) chạy với Claude thật trong staging.

---

## 10. Phạm vi MVP (khớp funtional-plan §10 Giai đoạn 1)

Đăng ký/đăng nhập + workspace/invite + log thiết bị · khung chat + hàng đợi FIFO + streaming + dừng/hủy + bỏ qua lỗi + quyền tại tool · project/task/người · skill gói tri thức (2 lớp) · cập nhật tiến độ · tổng hợp + xuất Excel (openpyxl) cơ bản · usage_log + semaphore + caching.

Đẩy sau: khóa/mở tài khoản UI đầy đủ, email OAuth send-as (đăng ký Google app verification **sớm** — duyệt mất vài tuần), push notification, ghi âm/STT, báo cáo định kỳ, dashboard.
