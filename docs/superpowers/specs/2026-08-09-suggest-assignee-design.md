# Gợi ý người phù hợp khi giao task — thiết kế

**Ngày:** 2026-08-09
**Trạng thái:** Đã duyệt (brainstorm), chờ viết plan triển khai.

## Bối cảnh

CEO có danh sách nhân viên và danh sách task trong ngày. Khi hỏi AI "nên
giao task A cho ai", muốn AI tự gợi ý dựa trên (1) nhân viên nào đang rảnh,
(2) nhân viên nào hay làm việc có dạng giống task A. Cần thêm 1 trường mô tả
chuyên môn cho nhân viên (text tự do, CEO tự nhập) để AI dùng làm căn cứ gợi
ý.

## Đặt tên: tránh xung đột với khái niệm `Skill` có sẵn

Hệ thống đã có `Skill`/`SkillVersion`/`SkillGrant` (`app/models.py`) — nghĩa
là **tài liệu/kiến thức AI dùng khi trả lời** (có version, cấp quyền qua
`grant_skill`/`use_skill`, là 1 loại nguồn trong `semantic_search`). Đây là
khái niệm hoàn toàn khác "kỹ năng nhân viên". Nếu dùng chung chữ "skill",
AI dễ nhầm 2 khái niệm khi đọc tool description (rủi ro đã từng xảy ra với
`use_skill` — xem CLAUDE.md mục "Bài học").

**Quyết định:** dùng "chuyên môn" / `expertise` trong toàn bộ thiết kế này,
tránh hoàn toàn chữ "skill" cho phần liên quan nhân viên.

## Phạm vi (đã chốt qua brainstorm)

1. **Nhập chuyên môn:** chỉ CEO tự nhập/sửa (không tự động suy từ lịch sử
   task). Text tự do (vd "design, figma, frontend react").
2. **Tiêu chí "rảnh":** đếm số `Task.status != done` đang gán cho người đó
   (qua `TaskAssignee`) trong toàn workspace — càng ít càng rảnh.
3. **Tiêu chí "hợp việc":** so sánh ngữ nghĩa (embedding) giữa nội dung task
   mới và `expertise_notes` của từng nhân viên — tái dùng hạ tầng RAG có sẵn
   (`embedding_service.py`), không xây hệ thống mới.
4. **Kết hợp 2 tiêu chí:** ưu tiên hợp chuyên môn trước; "rảnh" chỉ dùng để
   phân biệt khi nhiều người cùng hợp chuyên môn tương đương. Nếu không ai
   khớp chuyên môn nào, fallback về "người rảnh nhất toàn workspace".
5. **Khi nào gợi ý:** AI tự gọi tool khi CEO tạo task mà KHÔNG chỉ rõ người
   nhận (vd "tạo task X" không nói giao ai) — không gợi ý nếu CEO đã chỉ rõ
   tên người.
6. **Kiến trúc:** 1 tool mới `suggest_assignee`, AI tự quyết định gọi khi
   phát hiện thiếu người nhận — không tích hợp cứng vào `create_task`.
7. **Lưu trữ:** 1 cột text mới trên bảng `User` (`expertise_notes`), không
   cần bảng riêng.

## Thiết kế

### 1. Model — `User.expertise_notes`

`backend/app/models.py`, thêm vào class `User` (sau `notification_prefs`,
trước `created_at`):

```python
    # Chuyên môn nhân viên (text tự do, CEO tự nhập/sửa) -- dùng cho tool
    # suggest_assignee gợi ý người phù hợp khi giao task. KHÔNG liên quan gì
    # tới bảng Skill/SkillVersion (tài liệu/kiến thức AI dùng khi trả lời,
    # có version/cấp quyền) -- 2 khái niệm khác nhau hoàn toàn, tên field cố
    # ý tránh chữ "skill" để không gây nhầm lẫn.
    expertise_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Migration Alembic: thêm cột nullable, không backfill (giá trị mặc định
`NULL` cho user hiện có, CEO tự bổ sung sau).

### 2. Nhập/sửa chuyên môn

Mở rộng `AddEmployeeIn`/`AddEmployeeToolIn` (route `/api/v1/employees` +
tool `add_employee`) nhận thêm `expertise_notes: str | None = None` tùy
chọn — nhất quán với cách `email` đã là optional trong cùng schema.

Thêm **tool mới** `update_employee_expertise` (CEO-only) để sửa sau khi đã
tạo nhân viên — hiện chưa có cách sửa `full_name`/thông tin nhân viên nào
khác ngoài `change_user_role` (vai trò) nên cần route/tool riêng cho việc
này:

```python
class UpdateEmployeeExpertiseToolIn(BaseModel):
    user_id: uuid.UUID
    expertise_notes: str | None = None
```

Service `auth_service.update_employee_expertise(db, actor, user_id,
expertise_notes)`: `require_ceo`, load `User` theo `workspace_id` đúng actor
(404 nếu không thuộc workspace), set field, commit, **re-index embedding**
(gọi `embertise_service.index_employee_expertise`, xem mục 3) — cùng
pattern `edit_request` vừa fix re-index (PO audit 2026-08-08).

### 3. Index chuyên môn vào embedding

`backend/app/services/embedding_service.py`:

- Thêm `"employee_expertise"` vào `VALID_SOURCE_TYPES` (hiện có: `note,
  task_update, comment, chat_message, voice_transcript, skill`).
- Thêm `_RAG_LABELS["employee_expertise"] = "chuyên môn nhân viên"` (không
  bắt buộc dùng trong RAG auto-prefetch, nhưng nhất quán nếu sau này có nhu
  cầu).
- Hàm `index_employee_expertise(db, workspace_id, user)`: gọi
  `index_content(db, workspace_id, "employee_expertise", user.id,
  user.expertise_notes or "")` — tái dùng đúng cơ chế upsert đã có (nội dung
  trùng thì bỏ qua, khác thì update tại chỗ — đúng nhu cầu vì
  `expertise_notes` CÓ THỂ sửa nhiều lần, giống case `voice_transcript`).
  Nếu `expertise_notes` rỗng/None, `index_content` tự bỏ qua (đã có guard
  `if not text: return`).
- Gọi hàm này sau `add_employee` (nếu có `expertise_notes` lúc tạo) và sau
  `update_employee_expertise`.

### 4. Tool `suggest_assignee`

`backend/app/agent/tools.py`:

```python
class SuggestAssigneeToolIn(BaseModel):
    task_title: str
    task_description: str = ""
```

```python
async def _suggest_assignee(db, actor, body: SuggestAssigneeToolIn) -> dict:
    return await assignment_service.suggest_assignee(
        db, actor, task_title=body.task_title, task_description=body.task_description)
```

```python
_register("suggest_assignee",
          "Gợi ý người phù hợp nhất để giao 1 task (chỉ CEO). Dùng khi CEO "
          "yêu cầu tạo/giao task nhưng KHÔNG chỉ rõ tên người nhận -- gọi "
          "tool này TRƯỚC khi tạo task để biết nên đề xuất ai, rồi dùng kết "
          "quả điền vào create_task/assign_task qua propose_actions (đối "
          "tượng người nhận là SUY LUẬN nên phải qua luật mức 2). Xét theo "
          "chuyên môn nhân viên (field riêng, KHÁC HẲN Skill/tài liệu công "
          "ty) khớp ngữ nghĩa với nội dung task, và số task đang làm dở "
          "(ít hơn = rảnh hơn) khi nhiều người cùng hợp chuyên môn. Không "
          "tự động gán -- chỉ trả gợi ý kèm lý do để CEO xác nhận.",
          SuggestAssigneeToolIn, _suggest_assignee)
```

Đăng ký vào `TOOL_GROUPS["work"]` (cùng nhóm `create_task`/`assign_task`),
KHÔNG vào `SENSITIVE_TOOLS` (chỉ đọc, không ghi dữ liệu).

### 5. Service logic — `assignment_service.suggest_assignee`

File mới `backend/app/services/assignment_service.py`:

```python
async def suggest_assignee(db, actor, *, task_title: str,
                           task_description: str = "") -> dict:
    require_ceo(actor)
    query = f"{task_title}\n{task_description}".strip()

    # 1) Ứng viên theo chuyên môn (semantic, dùng lại embedding_service).
    matches = await embedding_service.semantic_search(
        db, actor, query, source_types=["employee_expertise"], limit=10)
    # matches: [{"source_id": user_id_str, "score": float, ...}, ...]

    # 2) Đếm task đang làm dở của MỌI nhân viên actor thấy được (1 query).
    open_counts = await _count_open_tasks_by_assignee(db, actor)

    if matches:
        # Lọc ngưỡng, sort theo score giảm dần, tie-break bằng open_counts tăng dần.
        candidates = [m for m in matches
                     if m["score"] >= embedding_service.SEMANTIC_SEARCH_MIN_SCORE]
        candidates.sort(key=lambda m: (-m["score"], open_counts.get(m["source_id"], 0)))
        top = candidates[:2]
        return {"suggestions": [
            {"user_id": c["source_id"], "reason": ...} for c in top
        ]}

    # 3) Fallback: không ai khớp chuyên môn -> người rảnh nhất toàn workspace.
    if not open_counts:
        return {"suggestions": [], "note": "Chưa có nhân viên nào trong workspace."}
    freest = min(open_counts.items(), key=lambda kv: kv[1])
    return {"suggestions": [{"user_id": freest[0],
                             "reason": f"Không có ai khớp chuyên môn task này -- "
                                       f"{freest[0]} đang rảnh nhất ({freest[1]} task dở)."}]}
```

Dùng thẳng `embedding_service.SEMANTIC_SEARCH_MIN_SCORE = 0.15` đã có sẵn
(nhất quán với `semantic_search`/`build_example_block`, không tạo hằng số
riêng cho ngưỡng này).

`_count_open_tasks_by_assignee`: 1 query SQL đếm
`TaskAssignee.user_id, count(Task.id)` join `Task.status != done`, giới hạn
trong `visible_task_ids(db, actor)` (đúng convention quyền — CEO thấy toàn
workspace nên thực chất không giới hạn, nhưng dùng chung hàm cho nhất
quán).

Response `reason` viết tiếng Việt tự nhiên, gồm tên thật (không chỉ id) —
cần join `User.full_name` trước khi trả về, để AI echo lại cho CEO đọc
được ngay (đúng luật mức 1 "echo đầy đủ đối tượng đã tác động").

### 6. System prompt — hướng dẫn khi nào gọi `suggest_assignee`

`backend/app/agent/loop.py`, thêm câu vào đoạn hướng dẫn hiện có (cạnh chỗ
đã thêm câu về `$result[N].field` — PO audit 2026-08-08):

```
Khi CEO yêu cầu tạo/giao task mà KHÔNG chỉ rõ người nhận (vd "tạo task X"
không nói giao ai, khác với "giao task X cho Duy" đã rõ ràng): gọi
suggest_assignee TRƯỚC để biết nên đề xuất ai, rồi dùng kết quả đó làm
người nhận trong create_task/assign_task qua propose_actions (đối tượng
người nhận là SUY LUẬN → luật mức 2), display_text nêu rõ lý do gợi ý
(chuyên môn khớp hay đang rảnh) để CEO thấy trước khi duyệt.
```

## Test cần thêm (chi tiết ở plan triển khai)

1. `expertise_notes` set lúc `add_employee` → tự động index vào embedding.
2. `update_employee_expertise` sửa nội dung → embedding update tại chỗ
   (không tạo row trùng), semantic_search phản ánh nội dung MỚI.
3. `suggest_assignee` với task khớp rõ 1 người theo chuyên môn → trả đúng
   người đó, `reason` có tên thật.
4. `suggest_assignee` với 2 người cùng hợp chuyên môn tương đương, khác số
   task đang làm → ưu tiên người ít task dở hơn.
5. `suggest_assignee` không ai khớp chuyên môn nào → fallback đúng người
   rảnh nhất toàn workspace, `reason` giải thích rõ đây là fallback.
6. `suggest_assignee` gọi bởi non-CEO → 403 (`require_ceo`).
7. Test tool description/wording không dùng chữ "skill" viết thường một
   mình (grep xác nhận), tránh tái phát nhầm lẫn với `Skill` model.

## Ngoài phạm vi (chưa làm ở lần này)

- Không tự động suy luận `expertise_notes` từ lịch sử task đã làm (CEO tự
  nhập, đã chốt qua brainstorm).
- Không xây UI/màn hình riêng trên FE để sửa `expertise_notes` — dùng qua
  chat (tool `add_employee`/`update_employee_expertise`) trước; màn hình
  riêng (nếu cần) là việc khác, ngoài phạm vi thiết kế này.
- Không dùng lịch sử task cũ của nhân viên (title các task họ từng làm) làm
  thêm tín hiệu ngữ nghĩa — chỉ dùng `expertise_notes` CEO nhập. Có thể mở
  rộng sau nếu độ chính xác chưa đủ, nhưng không nằm trong bản đầu.
- Không tự động gán (`assign_task`) — `suggest_assignee` chỉ trả gợi ý, CEO
  vẫn phải duyệt qua `propose_actions` như bình thường.
