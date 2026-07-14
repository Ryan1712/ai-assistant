# Thiết kế — Tìm kiếm xuyên suốt (Giai đoạn 3)

**Ngày:** 2026-07-14 · **Trạng thái:** Đã duyệt qua brainstorming · **Kiến trúc nền:** [2026-07-08-backend-architecture-design.md](2026-07-08-backend-architecture-design.md) · **Chat/Agent core:** [2026-07-09-chat-agent-core-design.md](2026-07-09-chat-agent-core-design.md) · **Spec chức năng:** [funtional-plan.md](../../../funtional-plan.md) §8 ("Tìm kiếm xuyên suốt"), §10 (Giai đoạn 3)

Lấp khoảng trống nêu ở funtional-plan §8: "Tìm kiếm xuyên suốt: task, ghi âm, note, người, skill, lịch sử chat, báo cáo." Đây là 1 service mới + 1 REST endpoint + 1 tool chat, **không thêm bảng DB nào** — tái dùng toàn bộ model và logic phân quyền đã có từ Plan 1-9.

---

## 1. Phạm vi & Ranh giới

**Trong phạm vi (v1):**
- Tìm kiếm xuyên 5 loại thực thể: **task, note, ghi âm (voice note), người (user), skill**.
- 1 endpoint gộp `GET /api/v1/search?q=...` + 1 tool chat `search` — trả kết quả nhóm theo loại, mỗi nhóm đã lọc quyền riêng theo actor.
- Cơ chế match: `ILIKE` substring, không dấu insensitive, không phân biệt hoa/thường. Chạy được cả SQLite (test) và Postgres (prod), không thêm extension.
- Giới hạn 20 kết quả/nhóm, không phân trang.
- Skill: chỉ tìm theo `name` (không tìm nội dung `SkillVersion.content`).

**Ngoài phạm vi (đẩy sau, theo funtional-plan §8, §10):**
- **Lịch sử chat** (`Message.content` là JSON block, không phải text thuần — cần logic bóc tách riêng, để sau).
- **Báo cáo** (`Report` không có field text tự do để search — chỉ có `kind` + `summary`/`filters` JSON).
- Tìm kiếm bỏ dấu tiếng Việt (unicode-normalize) — v1 chỉ ILIKE substring có dấu.
- Full-text search / trigram / xếp hạng liên quan (relevance ranking) — chưa có hạ tầng, YAGNI.
- Phân trang, tùy chỉnh limit qua query param.

---

## 2. Data model

Không có model mới. Tái dùng nguyên trạng:

| Entity | Bảng | Field search | Phạm vi hiển thị (tái dùng đúng logic hiện có) |
|---|---|---|---|
| Task | `Task` | `title`, `description` | `visible_task_ids(actor)` — CEO: toàn bộ workspace; manager: mình + đội; employee: task được giao |
| Note | `Note` | `content` | luôn `author_id == actor.id` (note private tuyệt đối, kể cả CEO không xem note người khác — theo `note_service.py`) |
| Voice note | `VoiceNote` | `transcript` | luôn `author_id == actor.id` (giống note, theo `voice_service.py`) |
| User | `User` | `full_name`, `email` | `visible_user_ids(actor)` (danh bạ theo vai trò, đã có ở `list_users`) |
| Skill | `Skill` | `name` | CEO: toàn bộ workspace; khác: chỉ skill đã được `SkillGrant` cho actor (theo `skill_service.list_skills`) |

Mọi query đều lọc `workspace_id == actor.workspace_id` trước, đúng quy ước CLAUDE.md.

---

## 3. Service layer + Tool

### `app/services/search_service.py`

```python
async def search(db: AsyncSession, actor: User, q: str) -> dict:
    ...
```

- Input `q`: bắt buộc non-empty sau `.strip()` — validate ở tầng schema (`Field(min_length=1)`), không validate lại trong service.
- Với mỗi entity, viết 1 hàm con `_search_tasks`, `_search_notes`, `_search_voice_notes`, `_search_users`, `_search_skills` — mỗi hàm:
  1. Lấy tập id/điều kiện hiển thị hợp lệ bằng đúng hàm đã có (`visible_task_ids`, `visible_user_ids`, `SkillGrant` join) hoặc điều kiện cứng (`author_id == actor.id` cho note/voice note).
  2. Thêm `or_(Field.ilike(f"%{q}%"), ...)` trên (các) field text liên quan.
  3. `order_by(created_at.desc())` (user: `order_by(full_name)`), `limit(20)`.
- `search()` gọi tuần tự 5 hàm con (cùng 1 `AsyncSession`, không chạy song song được), gộp kết quả:
  ```python
  {
      "tasks": [...], "notes": [...], "voice_notes": [...],
      "users": [...], "skills": [...],
  }
  ```
- Mỗi item serialize theo shape tối giản (không tái dùng nguyên `_task_out`/`_note_out` đầy đủ của các service khác — chỉ field cần cho danh sách kết quả tìm kiếm):
  - task: `id, title, status, project_id`
  - note: `id, content, note_date`
  - voice_note: `id, transcript, created_at`
  - user: `id, full_name, email, role`
  - skill: `id, name, kind`

### Tool `search` (`app/agent/tools.py`)

- Input schema: `{q: str}` (`Field(min_length=1)`).
- `sensitive=False` — chỉ đọc dữ liệu.
- Trả nguyên dict 5 nhóm như trên — model tự tóm tắt lại cho user trong chat (VD: "Tìm thấy 2 task, 1 note khớp 'website mới'").
- Đăng ký theo đúng pattern `_register(...)` hiện có, không có gì đặc biệt ở `call_tool`.

---

## 4. REST endpoint

### `GET /api/v1/search?q=...`

- `app/api/search.py`, mount router vào `main.py` như các router khác.
- Auth qua `get_current_user` — không giới hạn vai trò (mọi actor tìm trong phạm vi họ được thấy, y hệt tool).
- `q` là query param bắt buộc, `min_length=1` → thiếu hoặc rỗng trả `422` (FastAPI tự validate).
- `response_model`: `SearchOut` (5 field list, mỗi field 1 schema con — `SearchTaskOut`, `SearchNoteOut`, `SearchVoiceNoteOut`, `SearchUserOut`, `SearchSkillOut`).

---

## 5. Xử lý lỗi

| Tình huống | Kết quả |
|---|---|
| `q` rỗng/thiếu | `422` (REST, tự động qua Pydantic) / tool trả lỗi validate chuẩn của `call_tool` |
| Không có kết quả khớp ở 1 hoặc nhiều nhóm | Nhóm đó là mảng rỗng `[]`, không lỗi, không `404` |
| Actor không có quyền xem entity nào (VD employee mới, chưa được gán task/skill) | Nhóm tương ứng luôn rỗng — không phải lỗi, là kết quả hợp lệ |

Không có tình huống 403/404 ở tầng search — mọi lọc quyền xảy ra *bên trong* từng nhóm (loại bỏ kết quả không được thấy), không chặn cả request.

---

## 6. Testing

Theo đúng pattern TDD xuyên suốt các plan trước — test trước, code sau, mỗi task 1 commit:

- `backend/tests/test_search_service.py` — service layer, `db_session` fixture:
  - Mỗi entity: match đúng field, không match field khác; case-insensitive; giới hạn 20; sắp xếp đúng.
  - Phân quyền: employee chỉ thấy task/skill của mình; note/voice note của actor A không xuất hiện khi actor B search dù cùng workspace; user tìm theo `visible_user_ids` (manager không thấy nhân viên ngoài đội).
  - Cách ly workspace: dữ liệu workspace khác dù trùng từ khóa không xuất hiện.
- `backend/tests/test_search_api.py` — REST qua httpx `ASGITransport`: `q` rỗng → 422; kết quả đúng shape `SearchOut`; cách ly quyền/workspace lặp lại ở tầng REST (smoke test, không lặp toàn bộ test case service).
- `backend/tests/test_agent_tools_search.py` — tool `search` qua `call_tool`, theo style các test tool khác (`test_agent_tools_report_schedule.py`) + cập nhật số đếm `len(TOOLS)` ở `test_agent_tools_report.py`.

Không cần `FakeLLMClient`/storage/Redis — thuần service + REST + tool, không chạm agent loop hay streaming.

---

## Self-review (đã chạy)

- **Placeholder scan:** không có TBD; mọi quyết định (phạm vi 5 entity, match ILIKE không dấu, limit 20, gộp 1 endpoint/tool, skill chỉ tìm `name`) đã chốt qua brainstorming.
- **Nhất quán nội bộ:** không thêm cơ chế phân quyền mới — mỗi entity tái dùng đúng hàm/điều kiện đã có trong `permissions.py`/`note_service.py`/`voice_service.py`/`skill_service.py`; khớp quy ước CLAUDE.md (quyền ở service layer, workspace_id lọc mọi query).
- **Phạm vi:** đủ nhỏ cho 1 implementation plan — ước lượng 4-5 task (search_service theo từng entity hoặc gộp, schemas, REST endpoint, tool + migration openapi vì đổi contract). Không cần migration DB (không bảng mới).
- **Ambiguity check:** đã chốt rõ "note/voice note luôn theo `author_id`" (không theo role), "skill chỉ tìm `name`", "không phân trang/không truncate text" — không còn chỗ hiểu 2 nghĩa.
