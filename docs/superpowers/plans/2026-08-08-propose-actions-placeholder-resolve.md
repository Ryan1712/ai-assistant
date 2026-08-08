# Resolve placeholder id trong propose_actions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Khi model gộp nhiều action trong 1 bản nháp `propose_actions` mà action sau cần id do action trước sinh ra (vd `add_employee` rồi `assign_task` cho người vừa thêm, hoặc `create_project`+`create_task`+`assign_task` khi dán Excel), `_resolve_proposal` phải tự thay placeholder bằng id thật trước khi gọi `call_tool()`, thay vì để Pydantic validate UUID fail âm thầm — theo spec `docs/superpowers/specs/2026-08-05-propose-actions-placeholder-resolve-design.md`.

**Architecture:** Chuẩn hóa cú pháp placeholder `$result[N].<field>` (N = chỉ số action 0-based trong cùng bản nháp, field = tên field thật trong dict trả về của action đó). `_resolve_proposal` (`backend/app/agent/loop.py`) quét `tool_input` của action thứ `i` TRƯỚC khi gọi `call_tool()`, tìm placeholder khớp regex, thay bằng giá trị thật từ kết quả action N đã chạy (nếu N thành công và field tồn tại), hoặc skip action hiện tại với lỗi `dependency_failed` rõ ràng (nếu N fail/field không tồn tại/N>=i). System prompt (`loop.py`) và tool description `add_employee` (`tools.py`) cập nhật để dạy model dùng đúng cú pháp mới thay vì tự bịa chuỗi tự nhiên.

**Tech Stack:** Python, FastAPI, pytest-asyncio, regex thuần (`re` module, không cần thư viện ngoài).

## Global Constraints

- Cú pháp placeholder CHUẨN: `$result[N].<field>` — không chuẩn hóa lại tên field trả về của tool hiện có (giữ `add_employee` trả `user_id`, `create_project`/`create_task` trả `id`).
- Chỉ quét placeholder ở **1 cấp** trong `tool_input` (flat dict, giá trị string) — không đệ quy sâu hơn (không tool nào hiện tại có `tool_input` dạng nested object).
- N >= i (tự tham chiếu hoặc tham chiếu tương lai) → lỗi định dạng, skip action, KHÔNG crash toàn bộ `_resolve_proposal`.
- Action N fail hoặc field không tồn tại trong kết quả N → skip action hiện tại, KHÔNG gọi `call_tool()` (tránh side-effect với input còn placeholder chưa resolve).
- Backward compat bắt buộc: action không có placeholder nào phải chạy y hệt như trước — không regression (test cũ đã có phải tiếp tục pass).
- KHÔNG tự động retry action phụ thuộc sau khi action nguồn fail.
- TDD bắt buộc: test trước, thấy fail đúng lý do, rồi mới code.
- Mỗi task 1 commit riêng (CLAUDE.md).
- `python scripts/export_openapi.py` không cần chạy — không đổi API contract (đây là hành vi nội bộ của `_resolve_proposal`, không đổi shape input/output HTTP).

---

### Task 1: `_resolve_placeholder` — hàm thay placeholder trong `tool_input`

**Files:**
- Modify: `backend/app/agent/loop.py` (thêm hàm mới, đặt ngay trước `_resolve_proposal`, khoảng dòng 723)
- Test: `backend/tests/test_resolve_proposal_placeholder.py` (mới)

**Interfaces:**
- Produces: `_resolve_placeholder(tool_input: dict, action_index: int, results: list[dict]) -> tuple[dict, str | None]` — trả về `(tool_input đã resolve, error_message hoặc None)`. Nếu `error_message` không None, `tool_input` trả về KHÔNG đáng tin (action gọi hàm này phải skip `call_tool()`). Dùng ở Task 2 (`_resolve_proposal` gọi hàm này cho từng action trước khi `call_tool()`).
- `results: list[dict]` có shape giống `results` hiện có trong `_resolve_proposal`: mỗi phần tử `{"tool_name": str, "display_text": str | None, "result": dict}` — `result` là dict trả về từ `call_tool()` (có thể chứa `"error"` nếu action đó fail).

- [ ] **Step 1: Viết test thất bại cho hàm `_resolve_placeholder`**

```python
# backend/tests/test_resolve_proposal_placeholder.py
"""PO #3 (2026-08-05 spec, 2026-08-08 plan): _resolve_proposal phải tự thay
placeholder $result[N].<field> bằng id thật của action N đã chạy, trước khi
gọi call_tool() cho action phụ thuộc — root cause bug thật: model gộp
add_employee+assign_task (hoặc create_project+create_task+assign_task) trong
1 propose_actions, action sau tham chiếu id của action trước bằng chuỗi
placeholder tự bịa, _resolve_proposal không hề thay id thật vào, Pydantic
validate UUID fail âm thầm -> outcome=partially_completed, CEO phải tự gán
lại bằng tay. Xem docs/superpowers/specs/2026-08-05-propose-actions-
placeholder-resolve-design.md."""
from app.agent.loop import _resolve_placeholder


def test_resolve_placeholder_thay_dung_field_tu_action_truoc():
    results = [
        {"tool_name": "add_employee", "display_text": "Thêm Duy Linh",
         "result": {"user_id": "11111111-1111-1111-1111-111111111111",
                    "full_name": "Duy Linh"}},
    ]
    tool_input = {"task_id": "22222222-2222-2222-2222-222222222222",
                 "user_id": "$result[0].user_id"}

    resolved, error = _resolve_placeholder(tool_input, 1, results)

    assert error is None
    assert resolved["user_id"] == "11111111-1111-1111-1111-111111111111"
    assert resolved["task_id"] == "22222222-2222-2222-2222-222222222222"


def test_resolve_placeholder_khong_co_placeholder_giu_nguyen():
    results = []
    tool_input = {"task_id": "22222222-2222-2222-2222-222222222222",
                 "user_id": "33333333-3333-3333-3333-333333333333"}

    resolved, error = _resolve_placeholder(tool_input, 0, results)

    assert error is None
    assert resolved == tool_input


def test_resolve_placeholder_action_nguon_fail_tra_loi():
    results = [
        {"tool_name": "add_employee", "display_text": "Thêm Duy Linh",
         "result": {"error": "invalid_input", "message": "email_taken"}},
    ]
    tool_input = {"task_id": "x", "user_id": "$result[0].user_id"}

    resolved, error = _resolve_placeholder(tool_input, 1, results)

    assert error is not None
    assert "dependency_failed" not in error  # error la MESSAGE, khong phai code -- check noi dung khac o duoi
    assert "Thêm Duy Linh" in error


def test_resolve_placeholder_field_khong_ton_tai_tra_loi():
    results = [
        {"tool_name": "add_employee", "display_text": "Thêm Duy Linh",
         "result": {"user_id": "11111111-1111-1111-1111-111111111111"}},
    ]
    tool_input = {"task_id": "x", "user_id": "$result[0].id"}  # sai ten field

    resolved, error = _resolve_placeholder(tool_input, 1, results)

    assert error is not None
    assert "id" in error


def test_resolve_placeholder_tu_tham_chieu_tra_loi():
    results = [{"tool_name": "a", "display_text": "A", "result": {"id": "x"}}]
    tool_input = {"user_id": "$result[0].id"}

    # action_index=0 tham chieu chinh no ($result[0]) -> N >= i
    resolved, error = _resolve_placeholder(tool_input, 0, results)

    assert error is not None


def test_resolve_placeholder_tham_chieu_tuong_lai_tra_loi():
    results = [{"tool_name": "a", "display_text": "A", "result": {"id": "x"}}]
    tool_input = {"user_id": "$result[5].id"}  # action 5 chua chay (N >= i)

    resolved, error = _resolve_placeholder(tool_input, 1, results)

    assert error is not None
```

- [ ] **Step 2: Chạy test, xác nhận fail vì `_resolve_placeholder` chưa tồn tại**

Run: `cd backend && python -m pytest tests/test_resolve_proposal_placeholder.py -v`
Expected: FAIL với `ImportError: cannot import name '_resolve_placeholder' from 'app.agent.loop'`.

- [ ] **Step 3: Implement `_resolve_placeholder`**

Trong `backend/app/agent/loop.py`, thêm `import re` vào đầu file nếu chưa có (kiểm tra dòng import hiện tại trước — nếu `re` đã được import, bỏ qua bước này), rồi thêm hàm ngay trước `_resolve_proposal`:

```python
_PLACEHOLDER_RE = re.compile(r"^\$result\[(\d+)\]\.(\w+)$")


def _resolve_placeholder(tool_input: dict, action_index: int,
                         results: list[dict]) -> tuple[dict, str | None]:
    """PO #3: quét tool_input (flat dict, KHÔNG đệ quy sâu hơn 1 cấp — không
    tool nào hiện tại có tool_input dạng nested object) tìm placeholder cú
    pháp $result[N].<field>, thay bằng giá trị thật từ kết quả action N ĐÃ
    CHẠY trong cùng bản nháp. Trả (tool_input_đã_resolve, None) nếu OK, hoặc
    (tool_input_gốc, error_message) nếu action hiện tại PHẢI bị skip (không
    gọi call_tool()) — N >= action_index (tự tham chiếu/tham chiếu tương
    lai), action N đã fail, hoặc field không tồn tại trong kết quả N."""
    resolved = dict(tool_input)
    for key, value in tool_input.items():
        if not isinstance(value, str):
            continue
        m = _PLACEHOLDER_RE.match(value)
        if m is None:
            continue
        n, field = int(m.group(1)), m.group(2)
        if n >= action_index:
            return tool_input, (
                f"Placeholder '{value}' tham chiếu action #{n} nhưng action hiện tại "
                f"là #{action_index} — chỉ được tham chiếu action ĐÃ CHẠY trước đó.")
        source_result = results[n]["result"]
        if "error" in source_result:
            source_label = results[n].get("display_text") or results[n]["tool_name"]
            return tool_input, (
                f"Bỏ qua vì action phụ thuộc (#{n}: {source_label}) thất bại.")
        if field not in source_result:
            source_label = results[n].get("display_text") or results[n]["tool_name"]
            return tool_input, (
                f"Placeholder '{value}' tham chiếu field '{field}' nhưng action #{n} "
                f"({source_label}) không trả về field đó.")
        resolved[key] = str(source_result[field])
    return resolved, None
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_resolve_proposal_placeholder.py -v`
Expected: PASS cả 6 test.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/loop.py backend/tests/test_resolve_proposal_placeholder.py
git commit -m "feat(agent): them ham _resolve_placeholder cho cu phap \$result[N].field trong propose_actions"
```

---

### Task 2: Tích hợp `_resolve_placeholder` vào `_resolve_proposal`

**Files:**
- Modify: `backend/app/agent/loop.py` (`_resolve_proposal`, khoảng dòng 723-763)
- Test: `backend/tests/test_resolve_proposal_placeholder.py` (mở rộng)

**Interfaces:**
- Consumes: `_resolve_placeholder` từ Task 1.
- Produces: `_resolve_proposal` skip action với `{"error": "dependency_failed", "message": ...}` khi placeholder không resolve được, thay vì gọi `call_tool()` với input còn placeholder thô.

- [ ] **Step 1: Đọc `_resolve_proposal` hiện tại đầy đủ trước khi sửa (số dòng có thể lệch so với lúc viết plan)**

```bash
grep -n "async def _resolve_proposal" -A 45 backend/app/agent/loop.py
```

- [ ] **Step 2: Viết test thất bại — action 2 tham chiếu `$result[0].user_id` của action 1, xác nhận resolve đúng UUID thật**

Thêm vào `backend/tests/test_resolve_proposal_placeholder.py`:

```python
import pytest

from app.agent.loop import _resolve_proposal
from app.agent.publisher import FakeEventPublisher
from app.models import Project, Role, Task, User, Workspace


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db.add(project)
    await db.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="Thiet ke landing page",
               created_by=ceo.id)
    db.add(task)
    await db.commit()
    return ws, ceo, task


@pytest.mark.asyncio
async def test_resolve_proposal_thay_placeholder_dung_id_that(db_session):
    ws, ceo, task = await _world(db_session)
    action = {
        "kind": "proposal",
        "actions": [
            {"tool_name": "add_employee", "tool_input": {"full_name": "Duy Linh"},
             "display_text": "Thêm Duy Linh vào danh sách nhân viên"},
            {"tool_name": "assign_task",
             "tool_input": {"task_id": str(task.id), "user_id": "$result[0].user_id"},
             "display_text": "Gán Duy Linh vào task Thiết kế landing page"},
        ],
        "reasoning": "Duy Linh chưa có trong danh sách",
    }
    trace_tools: list[dict] = []

    result = await _resolve_proposal(db_session, ceo, action, True, ws.id, trace_tools)

    assert result["outcome"] == "completed"
    assert result["failed"] == []
    assert len(result["succeeded"]) == 2
    assign_result = result["proposal_results"][1]["result"]
    assert "error" not in assign_result


@pytest.mark.asyncio
async def test_resolve_proposal_action_nguon_fail_skip_phu_thuoc_khong_side_effect(db_session):
    """Action nguồn (add_employee) fail vì full_name rỗng (giả lập lỗi input) ->
    assign_task phụ thuộc PHẢI bị skip, KHÔNG gọi call_tool() thật (verify bằng
    cách task KHÔNG có assignee nào sau khi chạy)."""
    ws, ceo, task = await _world(db_session)
    action = {
        "kind": "proposal",
        "actions": [
            # full_name rỗng -> AddEmployeeToolIn validate fail (giả định full_name
            # bắt buộc non-empty; nếu schema thật cho phép rỗng, đổi sang input khác
            # chắc chắn fail, vd field sai kiểu) -- XÁC NHẬN lại AddEmployeeToolIn
            # trong tools.py trước khi finalize test này.
            {"tool_name": "add_employee", "tool_input": {},  # thiếu full_name bắt buộc
             "display_text": "Thêm nhân viên (thiếu tên, cố ý gây lỗi)"},
            {"tool_name": "assign_task",
             "tool_input": {"task_id": str(task.id), "user_id": "$result[0].user_id"},
             "display_text": "Gán vào task"},
        ],
        "reasoning": "test",
    }
    trace_tools: list[dict] = []

    result = await _resolve_proposal(db_session, ceo, action, True, ws.id, trace_tools)

    assert result["outcome"] == "failed"
    assign_result = result["proposal_results"][1]["result"]
    assert assign_result["error"] == "dependency_failed"
    # Xác nhận KHÔNG có side-effect: assign_task không thật sự chạy, task vẫn
    # chưa có assignee.
    from sqlalchemy import select
    from app.models import TaskAssignee
    assignees = (await db_session.execute(
        select(TaskAssignee).where(TaskAssignee.task_id == task.id))).scalars().all()
    assert assignees == []


@pytest.mark.asyncio
async def test_resolve_proposal_khong_co_placeholder_van_chay_binh_thuong(db_session):
    """Backward compat: action không có placeholder chạy y hệt trước đây."""
    ws, ceo, task = await _world(db_session)
    action = {
        "kind": "proposal",
        "actions": [
            {"tool_name": "update_task",
             "tool_input": {"task_id": str(task.id), "percent": 50},
             "display_text": "Cập nhật task lên 50%"},
        ],
        "reasoning": "test",
    }
    trace_tools: list[dict] = []

    result = await _resolve_proposal(db_session, ceo, action, True, ws.id, trace_tools)

    assert result["outcome"] == "completed"
```

Trước khi finalize test 2, đọc `AddEmployeeToolIn` trong `backend/app/agent/tools.py` để xác nhận field nào bắt buộc gây fail thật khi thiếu — sửa `tool_input` cho khớp đúng schema thật (comment trong test đã nhắc rõ điều này).

- [ ] **Step 3: Chạy test, xác nhận fail đúng lý do (action phụ thuộc hiện tại vẫn gọi thẳng `call_tool()` với placeholder thô — Pydantic UUID parse fail, KHÔNG phải `dependency_failed`)**

Run: `cd backend && python -m pytest tests/test_resolve_proposal_placeholder.py -v -k resolve_proposal`
Expected: `test_resolve_proposal_thay_placeholder_dung_id_that` FAIL (outcome vẫn "partially_completed" vì assign_task nhận `user_id="$result[0].user_id"` thô, Pydantic UUID validate fail). `test_resolve_proposal_action_nguon_fail_skip_phu_thuoc_khong_side_effect` có thể PASS "tình cờ" (assign_task vẫn fail nhưng vì lý do khác — kiểm tra kỹ `assign_result["error"]` KHÔNG phải `"dependency_failed"` mà là lỗi Pydantic khác, xác nhận đây thực sự là RED đúng lý do). `test_resolve_proposal_khong_co_placeholder_van_chay_binh_thuong` PASS sẵn (không đổi hành vi cần).

- [ ] **Step 4: Sửa `_resolve_proposal` gọi `_resolve_placeholder` trước `call_tool()`**

Đổi đoạn vòng lặp `for a in action["actions"]:` — thêm resolve placeholder ngay sau khi lấy `tool_input`, trước khi gọi `call_tool()`:

```python
    for i, a in enumerate(action["actions"]):
        tool_started = time.monotonic()
        # tool_input là optional trong schema propose_actions (default {}) — LLM có
        # thể bỏ trống với tool không cần tham số (get_today_dashboard...). Trước đây
        # a["tool_input"] KeyError → confirm 500 → request kẹt awaiting_confirmation.
        tool_input = a.get("tool_input") or {}
        tool_name = a["tool_name"]
        label = a.get("display_text") or tool_name
        # PO #3: resolve cú pháp $result[N].<field> TRƯỚC khi gọi call_tool() —
        # xem docs/superpowers/specs/2026-08-05-propose-actions-placeholder-
        # resolve-design.md. Nếu action nguồn fail/field sai/N>=i, skip action
        # NÀY (không gọi call_tool() với input còn placeholder chưa resolve,
        # tránh side-effect ngoài ý muốn).
        tool_input, placeholder_error = _resolve_placeholder(tool_input, i, results)
        if placeholder_error is not None:
            r = {"error": "dependency_failed", "message": placeholder_error}
            results.append({"tool_name": tool_name, "display_text": a.get("display_text"),
                            "result": r})
            failed.append(label)
            continue
        r = await call_tool(db, actor, tool_name, tool_input)
        trace_tools.append(_tool_trace_entry(tool_name, tool_input, r,
                                             int((time.monotonic() - tool_started) * 1000)))
        results.append({"tool_name": tool_name, "display_text": a.get("display_text"),
                        "result": r})
        if "error" in r:
            failed.append(label)
        else:
            succeeded.append(label)
            if tool_name in SNAPSHOT_WRITE_TOOLS:
                any_write = True
```

Lưu ý: đổi `for a in action["actions"]:` thành `for i, a in enumerate(action["actions"]):` — cần chỉ số `i` để truyền vào `_resolve_placeholder`. Đọc lại toàn bộ hàm sau khi sửa để xác nhận không còn dòng `label = a.get("display_text") or tool_name` bị lặp lại phía dưới (đã di chuyển lên trên trong bản sửa) — xoá dòng cũ nếu vẫn còn.

- [ ] **Step 5: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_resolve_proposal_placeholder.py -v`
Expected: PASS toàn bộ (10 test: 6 từ Task 1 + 3 mới + đảm bảo không trùng tên).

- [ ] **Step 6: Chạy test liên quan `loop.py`/`propose_actions` để đảm bảo không phá gì**

Run: `cd backend && python -m pytest tests/test_agent_add_employee_flow.py tests/test_agent_tools_report.py -k propose -v`

Nếu lệnh trên không match test nào (tên file/pattern có thể khác), chạy rộng hơn:

Run: `cd backend && python -m pytest tests/ -k "propose or resolve_proposal or add_employee_flow" -v`

Expected: tất cả PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/agent/loop.py backend/tests/test_resolve_proposal_placeholder.py
git commit -m "fix(agent): _resolve_proposal tu thay placeholder \$result[N].field bang id that truoc khi goi call_tool"
```

---

### Task 3: Cập nhật system prompt + tool description `add_employee`

**Files:**
- Modify: `backend/app/agent/loop.py` (system prompt, khoảng dòng 120-157)
- Modify: `backend/app/agent/tools.py` (`add_employee` description, khoảng dòng 434-444)
- Test: `backend/tests/test_agent_add_employee_flow.py` (mở rộng — đóng gap đã nêu trong spec)

**Interfaces:**
- Consumes: `_resolve_placeholder`/`_resolve_proposal` từ Task 1-2 (test Task 3 verify hành vi qua `run_agent_loop`/`resolve_confirmation` đầu-cuối).
- Produces: không có API/function mới — chỉ đổi nội dung string (system prompt, tool description) và mở rộng test.

- [ ] **Step 1: Đọc đoạn system prompt hiện tại đầy đủ (dòng 120-157) và tool description `add_employee` (dòng 434-444) để lấy đúng text hiện tại trước khi sửa — số dòng đã ghi trong Task này CÓ THỂ lệch nếu Task 1-2 thêm dòng phía trên, dùng grep xác nhận lại**

```bash
grep -n "Luật hành xử 3 mức" -A 40 backend/app/agent/loop.py
grep -n "_register(\"add_employee\"" -A 12 backend/app/agent/tools.py
```

- [ ] **Step 2: Thêm câu hướng dẫn cú pháp placeholder vào system prompt, ngay sau đoạn mức 2 (rule 3-mức) hiện có**

Tìm đoạn (đã xác nhận nội dung thật ở bản đọc trước lúc viết plan):

```python
        "2) Phải SUY LUẬN đối tượng (đoán task/người/deadline từ ngữ cảnh thay vì "
        "người dùng nói tường minh), hành động khó đảo ngược, hoặc gộp nhiều hành "
        "động trong 1 câu → gọi propose_actions NGAY (không tự hỏi trước bằng lời), "
        "điền hết tham số bằng suy luận hợp lý, mỗi action kèm display_text là 1 câu "
        "tiếng Việt người đọc hiểu ngay, và 1 câu reasoning ngắn giải thích vì sao "
        "suy luận vậy. Hệ thống tự hiện thẻ cho người dùng duyệt.\n"
```

Thêm ngay sau (trước dòng `"3) Nhạy cảm..."`):

```python
        "Khi 1 action trong bản nháp propose_actions cần id do action TRƯỚC nó "
        "(cùng bản nháp) sinh ra (vd assign_task cần user_id của add_employee vừa "
        "đề xuất, hoặc create_task cần project_id của create_project vừa đề xuất): "
        "PHẢI dùng đúng cú pháp $result[N].<field> (N = chỉ số action đó, 0-based, "
        "trong list actions; <field> = tên field THẬT tool đó trả về — vd "
        "add_employee trả user_id nên dùng $result[0].user_id, create_project/"
        "create_task trả id nên dùng $result[0].id) — KHÔNG tự bịa chuỗi placeholder "
        "khác, hệ thống chỉ nhận diện đúng cú pháp này để tự điền id thật khi CEO "
        "duyệt.\n"
```

- [ ] **Step 3: Cập nhật tool description `add_employee`**

Đổi đoạn cấm gộp hiện tại:

```python
_register("add_employee", "Thêm 1 người vào DANH SÁCH NHÂN VIÊN của công ty để giao "
          "việc (chỉ CEO). Chỉ cần tên; email là tùy chọn. Đây KHÔNG PHẢI tạo tài "
          "khoản/đăng nhập — nhân viên không dùng app này, chỉ CEO dùng. Dùng khi CEO "
          "nhắc tên người chưa có trong danh sách (kiểm tra trước bằng resolve_person "
          "hoặc danh bạ trong system prompt) mà muốn giao việc cho họ — nếu vậy: người "
          "đó CHƯA có id nên gọi add_employee TRỰC TIẾP ngay (không sensitive, không "
          "cần propose_actions/xác nhận), rồi dùng user_id THẬT trả về trong "
          "tool_result để gọi assign_task ở lượt gọi tool tiếp theo trong CÙNG lượt "
          "trả lời — TUYỆT ĐỐI đừng gộp add_employee chung với assign_task trong 1 "
          "bản nháp propose_actions, vì lúc đề xuất người đó chưa tồn tại nên "
          "assign_task sẽ tham chiếu 1 id không có thật và lỗi khi được duyệt.",
```

thành:

```python
_register("add_employee", "Thêm 1 người vào DANH SÁCH NHÂN VIÊN của công ty để giao "
          "việc (chỉ CEO). Chỉ cần tên; email là tùy chọn. Đây KHÔNG PHẢI tạo tài "
          "khoản/đăng nhập — nhân viên không dùng app này, chỉ CEO dùng. Dùng khi CEO "
          "nhắc tên người chưa có trong danh sách (kiểm tra trước bằng resolve_person "
          "hoặc danh bạ trong system prompt) mà muốn giao việc cho họ. 2 cách hợp lệ: "
          "(1) đối tượng/hành động đã rõ ràng theo luật mức 1 → gọi add_employee TRỰC "
          "TIẾP ngay, rồi dùng user_id THẬT trả về để gọi assign_task ở lượt tool tiếp "
          "theo trong CÙNG lượt trả lời; (2) cần gộp với assign_task trong 1 bản nháp "
          "propose_actions (theo luật mức 2, vd gộp nhiều hành động trong 1 câu) → "
          "PHẢI dùng cú pháp $result[N].user_id (N = chỉ số action add_employee trong "
          "list) làm user_id của assign_task, hệ thống tự điền id thật khi CEO duyệt.",
```

- [ ] **Step 4: Viết test mở rộng `test_agent_add_employee_flow.py` — verify CẢ bước duyệt thật (đóng gap đã nêu trong spec)**

Đọc file `backend/tests/test_agent_add_employee_flow.py` hiện tại đầy đủ trước (đã đọc lúc lập plan — test hiện có tên `test_ceo_giao_viec_cho_nguoi_moi_qua_propose_actions`, dừng ở bước tạo `pending_action`, dùng placeholder cũ `"<id_Duy_Linh_sau_khi_them>"`). Sửa file:

```python
import pytest

from app.agent.llm_client import FakeLLMClient, StreamDone, ToolUseBlock
from app.agent.loop import resolve_confirmation, run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Project, Role, Task,
    TaskAssignee, User, Workspace,
)


@pytest.mark.asyncio
async def test_ceo_giao_viec_cho_nguoi_moi_qua_propose_actions(db_session):
    """Mô phỏng đúng luồng CEO báo lỗi: giao việc cho người chưa có trong danh sách.
    AI (giả lập) phải đề xuất GỘP CẢ HAI add_employee + assign_task qua propose_actions
    trong 1 bản nháp — không hỏi lại, không tự chạy tool luôn (add_employee không
    sensitive nhưng đối tượng phải SUY LUẬN nên qua propose_actions theo luật 3 mức
    trong system prompt). Đây là crux của bug gốc: CEO không chỉ cần Duy Linh được
    THÊM vào danh bạ — CEO cần task ĐƯỢC GIAO cho Duy Linh.

    PO #3 (2026-08-08): dùng cú pháp $result[0].user_id (chuẩn mới) thay vì chuỗi
    placeholder tự bịa, và MỞ RỘNG test verify CẢ bước duyệt thật qua
    resolve_confirmation — đóng gap đã khiến bug gốc lọt qua (test cũ chỉ dừng ở
    bước tạo pending_action)."""
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="Thiet ke landing page",
               created_by=ceo.id)
    db_session.add(task)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add(conv)
    await db_session.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="giao viec thiet ke landing page cho Duy Linh",
                      queue_position=1.0)
    db_session.add(req)
    await db_session.flush()
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    actions = [
        {"tool_name": "add_employee", "tool_input": {"full_name": "Duy Linh"},
         "display_text": "Thêm Duy Linh vào danh sách nhân viên"},
        {"tool_name": "assign_task",
         "tool_input": {"task_id": str(task.id), "user_id": "$result[0].user_id"},
         "display_text": "Gán Duy Linh (vừa thêm ở trên) vào task Thiết kế landing page"},
    ]
    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[ToolUseBlock(
            id="t1", name="propose_actions",
            input={"actions": actions, "reasoning": "Duy Linh chưa có trong danh sách"})],
            stop_reason="tool_use", input_tokens=1, output_tokens=1)],
    ])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    await db_session.refresh(req)
    assert req.status == ChatRequestStatus.awaiting_confirmation
    assert req.pending_action["kind"] == "proposal"
    assert req.pending_action["actions"] == actions

    # PO #3: verify bước duyệt THẬT — Duy Linh phải được tạo VÀ gán vào task,
    # không chỉ dừng ở pending_action.
    await resolve_confirmation(db_session, req, True)
    await db_session.refresh(req)
    assert req.status == ChatRequestStatus.queued
    assert req.pending_action is None

    from sqlalchemy import select
    duy_linh = (await db_session.execute(
        select(User).where(User.workspace_id == ws.id, User.full_name == "Duy Linh")
    )).scalar_one()
    assignees = (await db_session.execute(
        select(TaskAssignee).where(TaskAssignee.task_id == task.id)
    )).scalars().all()
    assert len(assignees) == 1
    assert assignees[0].user_id == duy_linh.id
```

- [ ] **Step 5: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_agent_add_employee_flow.py -v`
Expected: PASS — bao gồm assertion mới verify Duy Linh thật sự được gán vào task.

- [ ] **Step 6: Chạy full suite backend**

Run: `cd backend && python -m pytest tests/ -q`
Expected: tất cả PASS, không phá gì hiện có (baseline trước task này: 847 passed, 0 failed, 4 skipped).

- [ ] **Step 7: Commit**

```bash
git add backend/app/agent/loop.py backend/app/agent/tools.py backend/tests/test_agent_add_employee_flow.py
git commit -m "docs(agent): cap nhat system prompt + tool description add_employee day cu phap \$result[N].field, mo rong test verify buoc duyet that"
```

---

## Self-Review Notes

- **Spec coverage:** đối chiếu "Test cần thêm" trong spec (6 mục) — mục 1 (resolve đúng) = Task 2 Step 2 test 1; mục 2 (action nguồn fail → skip, không side-effect) = Task 2 Step 2 test 2; mục 3 (field sai tên) = Task 1 test `field_khong_ton_tai`; mục 4 (N>=i) = Task 1 test `tu_tham_chieu`/`tham_chieu_tuong_lai`; mục 5 (backward compat) = Task 2 Step 2 test 3 + Task 1 test `khong_co_placeholder`; mục 6 (cập nhật test_agent_add_employee_flow.py) = Task 3 Step 4.
- **Placeholder scan:** không còn "TBD"/mô tả suông — mọi step code có nội dung đầy đủ. 2 chỗ ghi "đọc lại trước khi sửa vì số dòng có thể lệch" (Task 2 Step 1, Task 3 Step 1) là chủ đích (tasks trước có thể đổi số dòng), có sẵn lệnh `grep` cụ thể để tự xác nhận, không phải placeholder.
- **Type consistency:** `_resolve_placeholder(tool_input: dict, action_index: int, results: list[dict]) -> tuple[dict, str | None]` nhất quán giữa Task 1 (định nghĩa) và Task 2 (gọi trong `_resolve_proposal`). `results` shape (`{"tool_name", "display_text", "result"}`) khớp đúng cấu trúc `results.append(...)` đã có sẵn trong `_resolve_proposal` gốc.
- **Rủi ro cần xác nhận lúc thực thi:** Task 2 Step 2 test 2 dùng `add_employee` với `tool_input={}` để giả lập fail — cần xác nhận `AddEmployeeToolIn.full_name` thật sự bắt buộc (đã ghi chú rõ trong plan, người thực thi phải đọc `tools.py` xác nhận trước khi chạy, không đoán).
