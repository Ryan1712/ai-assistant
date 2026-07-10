# Thiết kế Plan 4 — Báo cáo & Xuất Excel

**Ngày:** 2026-07-10 · **Trạng thái:** Đã duyệt qua brainstorming · **Kiến trúc nền:** [2026-07-08-backend-architecture-design.md](2026-07-08-backend-architecture-design.md) · **Chat/Agent core:** [2026-07-09-chat-agent-core-design.md](2026-07-09-chat-agent-core-design.md) · **Spec chức năng:** [funtional-plan.md](../../../funtional-plan.md) §2, §6.5, §10 (Giai đoạn 1)

Đây là mảnh cuối cùng còn thiếu của **Giai đoạn 1 (MVP)** theo funtional-plan.md §10 — Plan 1 (auth/device log), Plan 2 (work domain/skill) và Plan 3 (khung chat/agent loop/21 tool) đã xong. Tài liệu này chỉ thêm 1 tool mới (`generate_report`) + 1 bảng mới (`reports`) + 1 REST endpoint tải file, tái dùng toàn bộ hạ tầng agent-tool đã có từ Plan 3.

---

## 1. Phạm vi & Ranh giới

**Trong phạm vi (Plan 4):**
- Model mới: `Report`.
- Service `report_service.generate_report()` — tổng hợp task theo filter (project/người/khoảng thời gian/trạng thái), ghi file `.xlsx`.
- Tool agent `generate_report` (tool thứ 22, không nhạy cảm) — CEO-only, gọi qua `call_tool` như 21 tool hiện có.
- REST `GET /api/v1/reports/{report_id}/download` — CEO-only, trả file `.xlsx` để FE mobile tải về (qua `expo-file-system` + `expo-sharing`).
- Hạ tầng lưu file: thư mục cấu hình được (`settings.storage_dir`), shared docker volume giữa `api`/`worker`.

**Ngoài phạm vi (đẩy sau, theo funtional-plan §6.5, §10):**
- Tùy biến cột tự do qua chat ("thêm cột X") — v1 chỉ có 1 bộ cột mặc định + filter cơ bản.
- Báo cáo định kỳ tự động (Giai đoạn 3).
- Manager/nhân viên tự xuất báo cáo — v1 chỉ CEO (funtional-plan §6.1: "CEO... yêu cầu báo cáo/Excel"; manager có "tổng hợp nhóm" nhưng qua `list_tasks` đã có sẵn từ Plan 2, không cần tool báo cáo riêng).
- Nhiều loại báo cáo khác nhau (theo skill, theo thiết bị...) — v1 chỉ 1 loại: tổng hợp task.
- Lưu trữ đám mây (S3/MinIO) — v1 dùng đĩa cục bộ/volume docker.

---

## 2. Data model mới

```
Report
  id, workspace_id, requested_by (FK users.id)
  kind: string, default "task_summary"   # cố định 1 giá trị cho v1, để mở rộng sau
  filters: jsonb                          # {project_id?, assignee_id?, date_from?, date_to?, status?}
  summary: jsonb                          # {total, todo, in_progress, blocked, done}
  file_path: string                       # đường dẫn tương đối trong storage_dir
  created_at
```

Ghi chú thiết kế:
- `filters`/`summary` lưu lại JSON để truy vết báo cáo đã tạo (ai tạo, lọc gì, kết quả tóm tắt) mà không cần đọc lại file `.xlsx` — phục vụ cả tool result (tóm tắt AI đọc lại cho CEO ngay trong chat) lẫn khả năng liệt kê lịch sử báo cáo sau này.
- `kind` cố định `"task_summary"` — không có logic rẽ nhánh theo loại ở v1, nhưng đặt sẵn field để không phải migrate lại khi thêm loại báo cáo thứ 2.
- Không có bảng con lưu từng dòng task trong báo cáo — nội dung chi tiết chỉ tồn tại trong file `.xlsx`, DB chỉ giữ metadata + tóm tắt.

---

## 3. Service layer + Tool

### `app/services/report_service.py`

```
generate_report(db, actor, *, project_id=None, assignee_id=None,
                date_from=None, date_to=None, status=None) -> dict
```

- `require_ceo(actor)` — chỉ CEO gọi được (403 nếu không).
- Query `Task` theo `workspace_id == actor.workspace_id`, join `Project` (tên project), `TaskAssignee`→`User` (người phụ trách, có thể nhiều người/task), `TaskUpdate` mới nhất theo `task_id` (nội dung + thời gian cập nhật gần nhất).
- Áp filter tùy chọn: `project_id`, `assignee_id` (task có người này trong `TaskAssignee`), `date_from`/`date_to` (theo `Task.created_at` hoặc `TaskUpdate.created_at` mới nhất — dùng `created_at` của task cho đơn giản, nhất quán), `status` (`TaskStatus` enum).
- `project_id`/`assignee_id` không tồn tại hoặc khác workspace → `HTTPException(404)` (khớp pattern hiện có ở `work_service`).
- Cột cố định trong file Excel: **Tên task, Project, Trạng thái, % hoàn thành, Người phụ trách, Cập nhật mới nhất (nội dung + thời gian), Deadline**.
- Ghi file bằng `openpyxl` vào `{settings.storage_dir}/{workspace_id}/{report_id}.xlsx` (tạo thư mục nếu chưa có).
- Insert `Report` row với `summary` = đếm task theo từng `TaskStatus`.
- Trả `dict`: `{report_id, summary: {...}, row_count, filters_applied}`.
- Không có task nào khớp filter → vẫn tạo file (chỉ có header), `summary.total = 0`, không lỗi — AI tự báo lại cho CEO là không có kết quả.

### Tool `generate_report` (`app/agent/tools.py`)

- Input schema: mọi field optional (`project_id: uuid?`, `assignee_id: uuid?`, `date_from: date?`, `date_to: date?`, `status: TaskStatus?`).
- `sensitive=False` — chỉ đọc dữ liệu, không cần xác nhận 2 bước.
- Đăng ký như 21 tool hiện có, không có gì đặc biệt ở tầng `call_tool` (lỗi 403/404 tự động bọc thành tool_result lỗi theo cơ chế sẵn có).
- Tool result trả về cho model đủ để trả lời CEO ngay trong chat (tóm tắt số liệu) — model tự nhắc CEO "báo cáo đã sẵn sàng, tải qua ứng dụng" (FE lấy `report_id` từ tool_result hiển thị trong message để hiện nút tải, không cần link động trong text).

---

## 4. REST endpoint & hạ tầng lưu trữ

### `GET /api/v1/reports/{report_id}/download`

- `app/api/reports.py`, mount vào `main.py` như các router khác.
- Auth qua `get_current_user`.
- 404 nếu `report.workspace_id != actor.workspace_id` **hoặc** `actor.role != Role.ceo` (chỉ CEO tải được — khớp quyết định "chỉ CEO tạo và tải").
- Trả `FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=...)` với `Content-Disposition: attachment`.

### Hạ tầng lưu trữ

- `config.py`: thêm `storage_dir: str = "./storage/reports"`.
- `docker-compose.yml`: thêm named volume `reports_data`, mount cùng path (vd `/data/reports`) vào cả `api` và `worker` — 2 tiến trình khác container nhưng cần đọc/ghi cùng file (`worker` tạo file lúc chạy tool, `api` đọc file lúc phục vụ download).
- Dev chạy ngoài Docker (không compose): `api`/`worker` chạy trực tiếp trên máy, tự nhiên share filesystem qua `storage_dir` tương đối — không cần volume.
- Test: dùng `tmp_path` fixture của pytest làm `storage_dir` qua dependency override / monkeypatch settings — không đụng filesystem thật, không cần Docker.

---

## 5. Xử lý lỗi

| Tình huống | Kết quả |
|---|---|
| Không phải CEO gọi tool | `{"error": "forbidden", "message": "Bạn không có quyền làm điều này."}` |
| `project_id`/`assignee_id` không tồn tại/khác workspace | `{"error": "not_found", ...}` |
| 0 task khớp filter | Vẫn tạo file (chỉ header), `summary.total=0`, không lỗi |
| Không phải CEO gọi endpoint download | 404 |
| `report_id` không tồn tại/khác workspace | 404 |
| Ghi file thất bại (disk đầy, quyền thư mục...) | Lỗi hạ tầng — với tool: không có except riêng, để lỗi nổi lên ngoài `call_tool`'s `except HTTPException`, agent loop hiện có (Plan 3) sẽ tự chuyển `status=failed` (đã có sẵn cơ chế "không catch-all nuốt lỗi khác") |

---

## 6. Testing

Theo đúng pattern TDD đã dùng xuyên suốt Plan 1-3 — test trước, code sau, mỗi task một commit:

- `backend/tests/test_report_service.py` — service layer, dùng `db_session` fixture + `tmp_path` cho storage, không cần Anthropic/Redis.
- `backend/tests/test_agent_tools_report.py` — tool qua `call_tool`, theo style `test_agent_tools_project_task.py`.
- `backend/tests/test_reports_api.py` — REST endpoint qua httpx `ASGITransport`, `tmp_path` cho storage, theo style `test_chat_api.py`.

Không cần `FakeLLMClient`/`FakeEventPublisher` — đây là tool + REST thuần túy, không chạm agent loop hay streaming.

---

## Self-review (đã chạy)

- **Placeholder scan:** không có TBD/`...`; mọi quyết định (quyền tạo/tải, cột cố định, lưu trữ, xử lý lỗi) đã chốt qua brainstorming, không còn mục lửng.
- **Nhất quán nội bộ:** `generate_report` tuân thủ đúng cấu trúc `ToolSpec`/`call_tool` đã có ở Plan 3 (không tạo cơ chế lỗi/permission riêng); `Report.workspace_id` tuân thủ quy ước bất di bất dịch trong CLAUDE.md.
- **Phạm vi:** đủ nhỏ cho 1 implementation plan — ước lượng 5-6 task (model, config storage, report_service, tool, REST endpoint, docker/migration+openapi) theo đúng nhịp Plan 1-3.
