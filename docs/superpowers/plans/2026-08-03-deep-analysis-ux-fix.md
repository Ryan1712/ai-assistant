# Fix 3 bug agent chat (deep-analysis mất tin nhắn, bịa tên tool, lộ tường thuật lỗi) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sửa 3 bug độc lập trong luồng chat agent: (1) FE mất tin nhắn trả
lời thật khi WebSocket rớt kết nối giữa lúc route "deep" xử lý nền, (2) model
bịa tên tool không tồn tại, (3) model lộ tường thuật lỗi/retry kỹ thuật ra
câu trả lời cho người dùng.

**Architecture:** Backend thêm `chat_request_id` vào `MessageOut` (cần cho FE
lọc đúng message khi bù dữ liệu bị lỡ) + cải thiện error hint khi gọi sai tên
tool ở `call_tool()` + 2 rule mới trong system prompt. Frontend thêm nhánh
`missedDone` đối xứng với `missedFails` đã có trong `refreshQueue`.

**Tech Stack:** FastAPI + SQLAlchemy async + Pydantic (backend), React
Native/Expo + TypeScript (frontend), pytest + pytest-asyncio (test backend).

## Global Constraints

- Route API dưới `/api/v1` (đã đúng, không đổi).
- Đổi API contract (`MessageOut` thêm field) → chạy `python
  scripts/export_openapi.py` ở cuối, ghi `openapi.json` tại repo root
  (CLAUDE.md).
- TDD: test trước, code sau; mỗi task một commit (CLAUDE.md).
- Không hardcode model LLM ID — không áp dụng ở plan này (không đụng chọn
  model).
- Không auto-redirect tool_name sai bằng fuzzy-match — đã loại vì rủi ro
  (xem spec `docs/superpowers/specs/2026-08-03-deep-analysis-ux-fix-design.md`,
  mục Bug #2: `delete_task`~`create_task` = 0.333, vượt ngưỡng dù đối lập
  hoàn toàn). Chỉ dùng `trigram_similarity` để GỢI Ý trong hint, không tự
  gọi tool khác.
- File Vietnamese-content (docs/specs) chỉnh bằng Edit/Write, KHÔNG dùng
  PowerShell `Get-Content | Set-Content` (mojibake UTF-8 — bài học ghi
  trong CLAUDE.md). Plan này không sửa file tiếng Việt dài nên rủi ro thấp,
  nhưng áp dụng nếu cần chỉnh spec sau này.

---

### Task 1: Thêm `chat_request_id` vào `MessageOut`

**Files:**
- Modify: `backend/app/schemas.py:420-429` (`MessageOut`)
- Test: `backend/tests/test_reports_api.py` — KHÔNG, tạo file mới
  `backend/tests/test_message_out_chat_request_id.py`

**Interfaces:**
- Consumes: `app.models.Message.chat_request_id` (đã tồn tại,
  `Mapped[uuid.UUID | None]`, xem `backend/app/models.py:414-415`).
- Produces: `MessageOut.chat_request_id: uuid.UUID | None` — Task 5 (FE)
  dùng field JSON `chat_request_id` trả về từ `/api/v1/conversations/
  {id}/messages` và `/api/v1/conversations/timeline` để lọc message theo
  request.

- [ ] **Step 1: Viết test thất bại**

Tạo file `backend/tests/test_message_out_chat_request_id.py`:

```python
import uuid

import pytest

from app.models import ChatRequest, Conversation, Message, MessageRole, Role, User, Workspace
from tests.conftest import _ceo_headers


async def _world_with_message(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add(conv)
    await db_session.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="hello", queue_position=1.0)
    db_session.add(req)
    await db_session.flush()
    msg = Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                  role=MessageRole.assistant, content=[{"type": "text", "text": "hi"}])
    db_session.add(msg)
    await db_session.commit()
    return ws, ceo, conv, req, msg


@pytest.mark.asyncio
async def test_message_out_includes_chat_request_id(client, db_session):
    ws, ceo, conv, req, msg = await _world_with_message(db_session)
    from app import security
    token = security.create_access_token(str(ceo.id))
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"/api/v1/conversations/{conv.id}/messages", headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["chat_request_id"] == str(req.id)
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && pytest tests/test_message_out_chat_request_id.py -v`
Expected: FAIL — `KeyError: 'chat_request_id'` hoặc assert `None == str(req.id)`
(vì `MessageOut` chưa có field này, Pydantic sẽ bỏ qua nó khi serialize).

Nếu lỗi khác (vd `security.create_access_token` không đúng chữ ký), mở
`backend/app/security.py` kiểm tra tên hàm thật trước khi sửa test — chỉ
sửa cách tạo token trong test, không đổi assertion chính.

- [ ] **Step 3: Sửa `MessageOut`**

Trong `backend/app/schemas.py`, sửa class `MessageOut` (dòng 420-429):

```python
class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    chat_request_id: uuid.UUID | None = None
    role: MessageRole
    content: list
    voice_note_id: uuid.UUID | None = None
    is_seed: bool = False
    created_at: dt.datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `cd backend && pytest tests/test_message_out_chat_request_id.py -v`
Expected: PASS

- [ ] **Step 5: Chạy toàn bộ test liên quan chat API để chắc không phá gì**

Run: `cd backend && pytest tests/test_call_tool_errors.py tests/ -k "chat or message" -v`
Expected: PASS toàn bộ (không có test cũ nào assert `MessageOut` không có
field thừa — Pydantic mặc định cho phép field mới không phá test cũ trừ khi
có test so khớp JSON tuyệt đối; nếu có test như vậy fail, đọc lại nó và
thêm `"chat_request_id"` vào dict kỳ vọng thay vì xóa field mới).

- [ ] **Step 6: Commit**

```bash
cd backend
git add app/schemas.py tests/test_message_out_chat_request_id.py
git commit -m "feat(chat): MessageOut trả thêm chat_request_id cho FE lọc message theo request"
```

---

### Task 2: Cải thiện error hint khi `call_tool` nhận tên tool không tồn tại

**Files:**
- Modify: `backend/app/agent/tools.py:64-67` (`call_tool`)
- Test: `backend/tests/test_call_tool_errors.py`

**Interfaces:**
- Consumes: `app.services.fuzzy_match.trigram_similarity(a: str, b: str) -> float`
  (đã tồn tại, `backend/app/services/fuzzy_match.py:21-26` — nhận 2 chuỗi
  ĐÃ normalize, nhưng tên tool vốn đã là ASCII lowercase/underscore nên
  không cần gọi `normalize_vn` trước).
- Produces: `call_tool()` khi `tool_name not in TOOLS` trả về dict có thêm
  field `"candidates": list[str]` (0-3 tên tool thật, sắp theo similarity
  giảm dần, chỉ gồm candidate có similarity > 0) — không đổi field
  `"error"`/`"hint"` đã có, chỉ bổ sung.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `backend/tests/test_call_tool_errors.py`:

```python
async def test_ten_tool_sai_gan_dung_goi_y_candidate_that(actor):
    result = await call_tool(None, actor, "add_member", {})
    assert result["error"] == "not_found"
    assert "add_employee" in result["candidates"]


async def test_ten_tool_sai_hoan_toan_khong_co_candidate(actor):
    result = await call_tool(None, actor, "xyz_khong_lien_quan_gi_ca", {})
    assert result["error"] == "not_found"
    assert result["candidates"] == []
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && pytest tests/test_call_tool_errors.py -v`
Expected: FAIL — `KeyError: 'candidates'` (field chưa tồn tại).

- [ ] **Step 3: Sửa `call_tool`**

Trong `backend/app/agent/tools.py`, thêm import ở đầu file (sau dòng 11,
cạnh các import `app.models`/`app.schemas`):

```python
from app.services.fuzzy_match import trigram_similarity
```

Sửa hàm `call_tool` (dòng 64-67):

```python
_TOOL_NAME_HINT_THRESHOLD = 0.2
_TOOL_NAME_HINT_MAX = 3


def _tool_name_candidates(tool_name: str) -> list[str]:
    """Gợi ý tên tool thật gần giống — CHỈ để model đọc và tự chọn gọi lại,
    KHÔNG dùng để auto-redirect (trigram không phân biệt được create_task/
    delete_task về mặt AN TOÀN dữ liệu — xem spec 2026-08-03)."""
    scored = [(name, trigram_similarity(tool_name, name)) for name in TOOLS]
    scored = [(name, s) for name, s in scored if s > _TOOL_NAME_HINT_THRESHOLD]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [name for name, _ in scored[:_TOOL_NAME_HINT_MAX]]


async def call_tool(db: AsyncSession, actor: User, tool_name: str, tool_input: dict) -> dict:
    """Gọi 1 tool theo tên; lỗi service (HTTPException) bọc thành tool_result lỗi, không raise ra ngoài."""
    if tool_name not in TOOLS:
        candidates = _tool_name_candidates(tool_name)
        hint = (f"Tool '{tool_name}' không tồn tại — có thể bạn muốn gọi 1 trong: "
                f"{', '.join(candidates)}. Kiểm tra đúng tên trong danh sách tools trước khi gọi."
                if candidates else
                f"Tool '{tool_name}' không tồn tại — gọi lại với tên tool đúng.")
        return {"error": "not_found", "hint": hint, "candidates": candidates}
```

Ngưỡng `0.2` chọn vì đo thực tế (spec, mục Bug #2): `add_member`~
`add_employee` = 0.2 đúng ngưỡng biên — dùng `>` (không phải `>=`) sẽ loại
0.2 chẵn, nên đổi điều kiện lọc thành `s >= _TOOL_NAME_HINT_THRESHOLD` để
bắt đúng case này:

```python
    scored = [(name, s) for name, s in scored if s >= _TOOL_NAME_HINT_THRESHOLD]
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `cd backend && pytest tests/test_call_tool_errors.py -v`
Expected: PASS toàn bộ (3 test: 1 cũ `test_loi_bat_ngo_trong_handler_thanh_tool_result`
+ 2 mới).

- [ ] **Step 5: Chạy full test suite backend để chắc không phá gì**

Run: `cd backend && pytest tests/ -v`
Expected: PASS toàn bộ (đặc biệt chú ý test nào assert nguyên văn dict trả
về của `call_tool` khi `tool_name not in TOOLS` — nếu có test cũ so khớp
dict tuyệt đối thiếu field `candidates`, sửa test đó thêm field, không xóa
field mới).

- [ ] **Step 6: Commit**

```bash
cd backend
git add app/agent/tools.py tests/test_call_tool_errors.py
git commit -m "fix(agent): goi y ten tool that gan dung khi model goi sai ten (khong auto-redirect)"
```

---

### Task 3: Thêm 2 rule prompt (tra đúng tên tool + không kể lể lỗi/retry)

**Files:**
- Modify: `backend/app/agent/loop.py:61-145` (`_build_system_prompt`)
- Test: `backend/tests/test_agent_loop_basic.py` (thêm test cho nội dung
  system prompt — file này đã test `_build_system_prompt` theo pattern
  hiện có; nếu không có sẵn hàm test system prompt ở đó, tạo file mới
  `backend/tests/test_agent_system_prompt_rules.py`)

**Interfaces:**
- Consumes: `app.agent.loop._build_system_prompt(actor: User, now:
  datetime | None = None) -> str` (đã tồn tại, không đổi chữ ký).
- Produces: chuỗi system prompt có thêm 2 đoạn mới (không đổi các đoạn cũ)
  — không có interface code mới, chỉ nội dung văn bản.

- [ ] **Step 1: Kiểm tra cách test hiện có cho `_build_system_prompt`**

Dùng Grep tool (pattern `_build_system_prompt`, path `backend/tests/`) để
tìm file test đã import thẳng hàm này. Nếu có file test sẵn (dự kiến
`test_agent_loop_basic.py` hoặc tương tự), thêm test vào đó; nếu không có
file nào import trực tiếp `_build_system_prompt`, tạo file mới
`backend/tests/test_agent_system_prompt_rules.py`.

- [ ] **Step 2: Viết test thất bại**

Tạo/thêm vào file test (giả sử file mới
`backend/tests/test_agent_system_prompt_rules.py`):

```python
import uuid
from datetime import datetime, timezone

from app.agent.loop import _build_system_prompt
from app.models import Role, User


def _actor():
    return User(id=uuid.uuid4(), workspace_id=uuid.uuid4(), email="c@a.vn",
               password_hash="x", full_name="Chi", role=Role.ceo)


def test_prompt_cam_bia_ten_tool():
    prompt = _build_system_prompt(_actor(), now=datetime(2026, 8, 3, tzinfo=timezone.utc))
    assert "không suy đoán/bịa tên tool" in prompt or "không được bịa tên tool" in prompt


def test_prompt_cam_ke_lai_loi_da_tu_sua():
    prompt = _build_system_prompt(_actor(), now=datetime(2026, 8, 3, tzinfo=timezone.utc))
    assert "không kể lại" in prompt and "lỗi" in prompt
```

(2 assertion trên kiểm tra sự tồn tại cụm từ khóa — sẽ khớp chính xác với
văn bản viết ở Step 3; đây là kiểu test "tồn tại rule trong prompt", chấp
nhận được vì bản chất thay đổi là nội dung văn bản hướng dẫn model, không
phải logic có thể unit-test hành vi model thật.)

- [ ] **Step 3: Chạy test, xác nhận fail**

Run: `cd backend && pytest tests/test_agent_system_prompt_rules.py -v`
Expected: FAIL — cụm từ chưa có trong prompt.

- [ ] **Step 4: Thêm 2 rule vào `_build_system_prompt`**

Trong `backend/app/agent/loop.py`, hàm `_build_system_prompt` (dòng
61-145), chèn đoạn mới ngay sau đoạn cấm lộ tên tool/UUID (sau dòng 89,
trước đoạn "Câu hỏi ngoài phạm vi..." ở dòng 90):

```python
        "Tên tool phải LẤY ĐÚNG NGUYÊN VĂN từ danh sách tools đã cấp cho bạn — "
        "TUYỆT ĐỐI không suy đoán/bịa tên tool nghe hợp lý (vd đoán 'add_member' "
        "hay 'create_user' khi tool thật tên 'add_employee'). Nếu không chắc tên "
        "chính xác, tra list_* liên quan trước hoặc đọc kỹ danh sách tools thay vì "
        "đoán. Nếu gọi nhầm tên và tool_result trả lỗi 'not_found' kèm gợi ý "
        "'candidates', chọn đúng tên trong đó cho lượt gọi tiếp theo.\n"
        "Khi 1 tool_result trả về có field 'error' (not_found/invalid_input/"
        "forbidden/tool_failed...) và bạn tự sửa bằng cách gọi lại tool đúng/tham "
        "số đúng NGAY trong cùng lượt trả lời: câu trả lời CUỐI CÙNG cho người "
        "dùng TUYỆT ĐỐI không kể lại việc vừa gặp lỗi/thử lại — chỉ báo kết quả "
        "cuối cùng, y hệt cách trả lời khi mọi thứ chạy đúng ngay từ đầu. Việc "
        "gọi sai/tự sửa là chi tiết kỹ thuật nội bộ, không phải điều người dùng "
        "cần biết.\n"
```

- [ ] **Step 5: Chạy test, xác nhận pass**

Run: `cd backend && pytest tests/test_agent_system_prompt_rules.py -v`
Expected: PASS

- [ ] **Step 6: Chạy full test suite backend**

Run: `cd backend && pytest tests/ -v`
Expected: PASS toàn bộ (kiểm tra không có test nào so khớp độ dài/nội dung
nguyên văn `_build_system_prompt` — nếu có, cập nhật test đó cho khớp văn
bản mới thay vì rút gọn đoạn vừa thêm).

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/agent/loop.py tests/test_agent_system_prompt_rules.py
git commit -m "fix(agent): them rule cam bia ten tool + cam ke lai loi da tu sua trong system prompt"
```

---

### Task 4: FE — theo dõi `chat_request_id` đã nhận `request_done` qua WS

**Files:**
- Modify: `frontend/app/main/chat.tsx`

**Interfaces:**
- Consumes: state/refs hiện có trong component `Chat()` —
  `watchedRequests` (ref, `Set<string>`, dòng 230), `onWsEvent` callback
  (dòng 291-370, nhánh `request_done` dòng 310-320).
- Produces: ref mới `doneSeen: React.MutableRefObject<Set<string>>` —
  Task 5 đọc ref này để biết request nào đã hiển thị đúng qua WS (bỏ qua),
  request nào cần bù bằng REST.

- [ ] **Step 1: Thêm ref `doneSeen` cạnh `watchedRequests`**

Trong `frontend/app/main/chat.tsx`, sau dòng 230 (`const watchedRequests
= useRef<Set<string>>(new Set());`):

```typescript
  // Request đã nhận đúng event request_done qua WS trong phiên này — dùng
  // để phát hiện request "done" mà FE CHƯA từng thấy kết quả thật (WS rớt
  // đúng lúc route "deep" publish, xem refreshQueue bên dưới).
  const doneSeen = useRef<Set<string>>(new Set());
```

- [ ] **Step 2: Đánh dấu `doneSeen` trong nhánh `request_done` của `onWsEvent`**

Sửa nhánh `else if (e.type === "request_done")` (dòng 310-320) — thêm 1
dòng đánh dấu, giữ nguyên toàn bộ logic cũ:

```typescript
      } else if (e.type === "request_done") {
        doneSeen.current.add(e.chat_request_id);
        setRunningTool(null);
        streamingText.current.delete(e.chat_request_id);
        setRows((prev) =>
          prev.map((r) =>
            r.key === `stream-${e.chat_request_id}` && r.kind === "streaming"
              ? { ...r, kind: "assistant" as const }
              : r,
          ),
        );
        refreshQueue(cid);
      }
```

- [ ] **Step 3: Verify bằng type-check (không có unit test FE trong repo)**

Run: `cd frontend && npx tsc --noEmit`
Expected: không có lỗi type mới liên quan tới `chat.tsx` (dự án có thể đã
có lỗi type ở file khác không liên quan — chỉ cần xác nhận không phát sinh
lỗi mới ở `chat.tsx`).

- [ ] **Step 4: Commit**

```bash
cd frontend
git add app/main/chat.tsx
git commit -m "fix(chat): theo doi chat_request_id da nhan request_done qua WS"
```

---

### Task 5: FE — bù tin nhắn bị lỡ khi request đã `done` nhưng chưa từng thấy qua WS

**Files:**
- Modify: `frontend/app/main/chat.tsx`

**Interfaces:**
- Consumes:
  - `doneSeen` (Task 4).
  - `listMessages(conversationId: string) => Promise<Message[]>`
    (`frontend/src/api/chat.ts:99-100`).
  - `Message.chat_request_id: string | null` — MỚI, chỉ tồn tại sau khi
    Task 1 (backend) deploy VÀ type `Message` ở FE được cập nhật (xem Step
    1 dưới đây — field này hiện KHÔNG có trong type `Message` ở
    `frontend/src/api/chat.ts:74-82`, phải thêm trước khi dùng).
  - `messagesToRows(msgs: Message[]) => Row[]` (`chat.tsx:146-173`).
  - `refreshQueue(cid: string)` (`chat.tsx:235-...`, sẽ sửa trực tiếp).
- Produces: không có interface mới cho task khác — đây là task cuối của
  luồng bug #1.

- [ ] **Step 1: Thêm `chat_request_id` vào type `Message` ở FE**

Trong `frontend/src/api/chat.ts`, sửa type `Message` (dòng 74-82):

```typescript
export type Message = {
  id: string;
  conversation_id: string | null;
  chat_request_id: string | null;
  role: "user" | "assistant";
  content: ContentBlock[];
  voice_note_id: string | null;
  is_seed: boolean;
  created_at: string;
};
```

- [ ] **Step 2: Sửa `refreshQueue` — thêm nhánh bù `missedDone`**

Trong `frontend/app/main/chat.tsx`, hàm `refreshQueue` (dòng 235 trở đi).
Đọc lại đoạn hiện có xử lý `missedFails` (dòng 246-261) để chèn đoạn mới
NGAY SAU nó, cùng cấu trúc. Đoạn hiện có:

```typescript
    const missedFails = reqs.filter(
      (r) => r.status === "failed" && watchedRequests.current.has(r.id),
    );
    if (missedFails.length > 0) {
      setRows((prev) => {
        const next = [...prev];
        for (const r of missedFails) {
          const key = `fail-${r.id}`;
          if (!next.some((row) => row.key === key))
            next.push({ key, kind: "failed", text: friendlyError(r.error ?? "unknown"),
                        retryContent: r.content });
        }
        return next;
      });
      missedFails.forEach((r) => watchedRequests.current.delete(r.id));
    }
```

Thêm NGAY SAU đoạn này (vẫn trong `refreshQueue`, trước dòng
`setQueue(reqs.filter(...))`):

```typescript
    const missedDone = reqs.filter(
      (r) => r.status === "done" && watchedRequests.current.has(r.id)
             && !doneSeen.current.has(r.id),
    );
    if (missedDone.length > 0) {
      const missedIds = new Set(missedDone.map((r) => r.id));
      const msgs = await listMessages(cid);
      const newRows = messagesToRows(
        msgs.filter((m) => m.chat_request_id && missedIds.has(m.chat_request_id)),
      );
      setRows((prev) => {
        const existingKeys = new Set(prev.map((r) => r.key));
        const toAdd = newRows.filter((r) => !existingKeys.has(r.key));
        if (toAdd.length === 0) return prev;
        // Xoá dòng "streaming" tạm của các request vừa bù (nếu còn sót do
        // race giữa reconnect và event token cuối cùng bị lỡ).
        const withoutStreaming = prev.filter(
          (r) => !(r.kind === "streaming"
                   && missedDone.some((req) => r.key === `stream-${req.id}`)),
        );
        return [...withoutStreaming, ...toAdd];
      });
      missedDone.forEach((r) => {
        doneSeen.current.add(r.id);
        watchedRequests.current.delete(r.id);
      });
    }
```

**Lưu ý quan trọng cho người triển khai:** `refreshQueue` hiện tại là
`async` (dòng 235: `useCallback(async (cid: string) => {...})`) — đoạn
`await listMessages(cid)` mới thêm hợp lệ vì đã trong hàm async, không cần
đổi chữ ký.

- [ ] **Step 3: Verify type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: không có lỗi type mới ở `chat.tsx`/`api/chat.ts`.

- [ ] **Step 4: Verify thủ công trên thiết bị/simulator thật**

Không có test tự động cho luồng WebSocket-rớt-giữa-chừng trong repo này
(đã xác nhận lúc viết spec). Verify bằng tay:

1. Chạy backend local (`uvicorn app.main:app --reload`), chạy app Expo Go
   trên máy/emulator (xem `[Android emulator dev loop]` trong memory dự án
   nếu cần dựng lại môi trường).
2. Gửi 1 tin nhắn đủ phức tạp để route vào "deep" (nhiều yêu cầu gộp trong
   1 câu, giống test case gốc "giao Hiếu mafia 5 việc...").
3. Ngay sau khi thấy dòng ack ("~30 giây, tôi sẽ báo khi xong"), tắt
   WiFi/mất mạng vài giây rồi bật lại (mô phỏng WS rớt) TRƯỚC khi
   `run_deep_analysis` publish xong.
4. Xác nhận: sau khi mạng lại, màn hình chat tự hiện đầy đủ câu trả lời
   thật (không chỉ đứng yên ở dòng ack) mà KHÔNG cần user tự gõ thêm tin
   nhắn.
5. Nếu không tái hiện được race đúng lúc, verify đường an toàn hơn: gọi
   trực tiếp API backend tạo 1 `ChatRequest` deep + giả lập
   `run_deep_analysis` xong (`status=done`) trong khi FE đang mở
   conversation nhưng đã đóng/mở lại WS thủ công (dev tool), xác nhận
   `refreshQueue` khi mount lại bù đúng message.

- [ ] **Step 5: Commit**

```bash
cd frontend
git add src/api/chat.ts app/main/chat.tsx
git commit -m "fix(chat): bu tin nhan bi lo khi WS rot dung luc deep-analysis xong (missedDone)"
```

---

### Task 6: Export lại OpenAPI contract (đổi `MessageOut`)

**Files:**
- Modify: `openapi.json` (repo root, tự sinh — không sửa tay)

**Interfaces:**
- Consumes: toàn bộ route đã đăng ký trong `backend/app/main.py` (không
  đổi gì thêm ở task này).
- Produces: `openapi.json` cập nhật, phản ánh field `chat_request_id` mới
  trong `MessageOut`.

- [ ] **Step 1: Chạy script export**

Run (từ `backend/`, theo CLAUDE.md): `cd backend && python
scripts/export_openapi.py`

Expected: ghi đè `openapi.json` ở repo root, không lỗi.

- [ ] **Step 2: Xác nhận field mới có trong output**

Run: dùng Grep tool tìm `"chat_request_id"` trong `openapi.json` ở phần
định nghĩa `MessageOut` — xác nhận field xuất hiện với type
`string | null` (format uuid).

- [ ] **Step 3: Commit**

```bash
git add openapi.json
git commit -m "chore: export lai openapi.json (MessageOut them chat_request_id)"
```

---

### Task 7: Full test suite + review cuối

**Files:** không tạo/sửa file mới — bước xác nhận cuối cùng.

- [ ] **Step 1: Chạy toàn bộ test suite backend**

Run: `cd backend && pytest tests/ -v`
Expected: PASS toàn bộ. Đây là bước bắt buộc theo bài học đã ghi trong
memory dự án (`feedback-full-suite-before-finishing-branch`) — test theo
từng task không đủ, phải chạy full suite trước khi coi nhánh hoàn tất.

- [ ] **Step 2: Type-check frontend toàn bộ**

Run: `cd frontend && npx tsc --noEmit`
Expected: không phát sinh lỗi type mới so với trước khi bắt đầu plan này
(nếu repo đã có lỗi type tồn tại từ trước không liên quan, ghi chú lại,
không phải trách nhiệm sửa của plan này).

- [ ] **Step 3: Xác nhận thủ công Task 5 Step 4 đã thực hiện**

Nếu Task 5 Step 4 (verify trên thiết bị thật) chưa làm vì thiếu môi
trường lúc đó, PHẢI thực hiện trước khi coi plan hoàn tất — đây là bug
duy nhất trong 3 bug có thể verify được hành vi thật (bug #2/#3 chỉ verify
được gián tiếp qua nội dung prompt, không đảm bảo hành vi model).

---

## Tổng kết phạm vi

- Bug #1 (mất tin nhắn khi WS rớt): Task 1, 4, 5, 6 — có fix xác định rõ
  ràng, verify được bằng test + thao tác thủ công.
- Bug #2 (bịa tên tool): Task 2, 3 — giảm xác suất/tác hại, không loại trừ
  hoàn toàn (giới hạn đã ghi trong spec).
- Bug #3 (lộ tường thuật lỗi): Task 3 — cùng giới hạn như bug #2.
- Task 7 là bước đóng plan, không tạo thay đổi code mới.
