# Phase 5 — Session Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Biến chat từ "nhiều cuộc trò chuyện user tự quản" thành MỘT luồng liên tục kiểu Zalo — nén hội thoại cũ (rolling summary), xoay conversation ngầm server-side, hiển thị một timeline xuyên conversation, bỏ nút New chat.

**Architecture:** Rolling summary nén message cũ vào `Conversation.rolling_summary` (tiêm vào SYSTEM prompt, không thành message), chạy trong worker trước agent loop. Xoay conversation ngầm (idle >12h HOẶC >150 msg) resolve lúc FE mount qua `GET /conversations/active`. FE render một timeline xuyên conversation qua `GET /conversations/timeline` phân trang cursor.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy 2.0 async / Alembic / arq; React Native (Expo SDK 57) / react-navigation. Test: pytest + pytest-asyncio (SQLite in-memory) BE; `tsc --noEmit` FE.

## Global Constraints

- Mọi bảng (trừ `workspaces`) có `workspace_id`; mọi query lọc theo `actor.workspace_id`. (CLAUDE.md)
- Quyền kiểm ở service layer; actor luôn từ JWT (`get_current_user`), không từ client/model. (CLAUDE.md)
- Model LLM từ config, không hardcode model ID. (CLAUDE.md)
- Route dưới `/api/v1`. Đổi API contract → chạy lại `python scripts/export_openapi.py`. (CLAUDE.md)
- TDD: test trước, code sau; mỗi task một commit. (CLAUDE.md)
- KHÔNG dùng PowerShell `Get-Content|Set-Content` sửa file UTF-8 tiếng Việt — dùng Edit/Write. (CLAUDE.md)
- Summary phải vào SYSTEM prompt, KHÔNG chèn làm message (phá luật user/assistant xen kẽ của Anthropic — bài học `is_ack` Phase 4).
- Lệnh BE chạy trong `backend/` với venv `.venv` (Windows: `.venv\Scripts\activate`). Lệnh FE chạy trong `frontend/`.
- SQLite trả datetime **naive** — khi so idle phải normalize cả hai vế về aware/UTC (bài học period-bounds).

---

## File Structure

**Tạo mới:**
- `backend/app/agent/summarizer.py` — nén rolling summary (constants + `maybe_compress_history`).
- `backend/app/services/session_service.py` — active conversation + rotation.
- `backend/tests/test_summarizer.py`, `backend/tests/test_session_service.py`, `backend/tests/test_conversation_active_timeline_api.py`.
- `backend/alembic/versions/<rev>_session_model_rolling_summary.py` — migration 3 cột.

**Sửa:**
- `backend/app/models.py` — `Conversation` +3 cột.
- `backend/app/agent/loop.py` — `_load_history(since=)`, tiêm summary + fetch conv trong `run_agent_loop`.
- `backend/app/agent/worker.py` — gọi `maybe_compress_history` trong `process_conversation`.
- `backend/app/api/chat.py` — `GET /active`, `GET /timeline`.
- `backend/app/schemas.py` — `MessageOut.conversation_id`, `ConversationOut.archived_at`.
- `backend/openapi.json` (export lại).
- `frontend/src/api/chat.ts` — types + `getActiveConversation` + `getTimeline`.
- `frontend/app/main/chat.tsx` — LIVE mode timeline + history read-only + bỏ new-chat header + bỏ `coldStart`.
- `frontend/src/navigation/DrawerContent.tsx` — bỏ nút New chat.

---

### Task 1: Migration + 3 cột `Conversation`

**Files:**
- Modify: `backend/app/models.py:362-370` (class `Conversation`)
- Create: `backend/alembic/versions/<rev>_session_model_rolling_summary.py`
- Test: `backend/tests/test_summarizer.py` (smoke cột tồn tại — mở rộng ở Task 3)

**Interfaces:**
- Produces: `Conversation.rolling_summary: str` (default `""`), `Conversation.summary_through_at: datetime | None`, `Conversation.archived_at: datetime | None`.

- [ ] **Step 1: Viết test cột mới tồn tại + default**

Tạo `backend/tests/test_summarizer.py`:
```python
import uuid
from app.models import Conversation


async def test_conversation_co_cot_session_model_defaults(db_session):
    conv = Conversation(workspace_id=uuid.uuid4(), user_id=uuid.uuid4())
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    assert conv.rolling_summary == ""
    assert conv.summary_through_at is None
    assert conv.archived_at is None
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `pytest tests/test_summarizer.py -v`
Expected: FAIL (`AttributeError: 'Conversation' object has no attribute 'rolling_summary'` hoặc lỗi cột SQLite).

- [ ] **Step 3: Thêm 3 cột vào model**

Trong `backend/app/models.py`, class `Conversation`, sau dòng `queue_held` (giữ nguyên các dòng khác):
```python
    # Phase 5 (session model): nén hội thoại cũ + xoay conversation ngầm.
    # rolling_summary tiêm vào SYSTEM prompt (KHÔNG thành message). summary_through_at
    # = mốc message đã gộp vào summary (message sau mốc gửi nguyên văn). archived_at
    # != None = conversation đã bị xoay ra khỏi luồng sống.
    rolling_summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    summary_through_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
```
(`Text`, `DateTime`, `Mapped`, `mapped_column`, `datetime` đã được import sẵn ở đầu `models.py`.)

- [ ] **Step 4: Chạy test — PASS**

Run: `pytest tests/test_summarizer.py -v`
Expected: PASS (SQLite `create_all` tự tạo cột mới).

- [ ] **Step 5: Tạo migration Alembic**

Chạy: `alembic revision --autogenerate -m "session_model_rolling_summary"`
Mở file migration vừa sinh trong `backend/alembic/versions/`, xác nhận `upgrade()` có 3 `op.add_column("conversations", ...)` cho `rolling_summary`/`summary_through_at`/`archived_at` và `downgrade()` có `op.drop_column` tương ứng. Nếu autogenerate bỏ sót (do env DATABASE_URL chưa trỏ Postgres), viết tay:
```python
def upgrade() -> None:
    op.add_column("conversations", sa.Column("rolling_summary", sa.Text(),
                  server_default="", nullable=False))
    op.add_column("conversations", sa.Column("summary_through_at",
                  sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("archived_at",
                  sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "archived_at")
    op.drop_column("conversations", "summary_through_at")
    op.drop_column("conversations", "rolling_summary")
```
Sửa `down_revision` = revision của `message_is_ack_flag` (migration head hiện tại) nếu autogenerate chưa đặt đúng.

- [ ] **Step 6: Áp migration lên Postgres dev + commit**

```bash
docker compose up -d postgres redis
alembic upgrade head
```
Expected: chạy sạch, không lỗi.
```bash
git add app/models.py alembic/versions/ tests/test_summarizer.py
git commit -m "feat(be): them cot rolling_summary/summary_through_at/archived_at cho Conversation (Phase 5)"
```

---

### Task 2: `_load_history(since=)`

**Files:**
- Modify: `backend/app/agent/loop.py:143-178` (`_load_history`)
- Test: `backend/tests/test_load_history_queue.py`

**Interfaces:**
- Consumes: `_load_history` hiện tại.
- Produces: `_load_history(db, conversation_id, current_request_id, since: datetime | None = None)` — khi `since` != None chỉ nạp message `created_at > since`.

- [ ] **Step 1: Viết test — since lọc bỏ message cũ**

Thêm vào cuối `backend/tests/test_load_history_queue.py`:
```python
async def test_load_history_since_bo_message_cu(db_session):
    conv = await _mk_conv(db_session)
    old = await _mk_req(db_session, conv, "tin cu da nen", 1.0, status=ChatRequestStatus.done)
    new = await _mk_req(db_session, conv, "tin moi verbatim", 2.0, status=ChatRequestStatus.done)
    await db_session.commit()
    await db_session.refresh(old)  # lay created_at cua message cua request cu
    from app.models import Message
    from sqlalchemy import select
    old_msg = (await db_session.execute(select(Message).where(
        Message.chat_request_id == old.id))).scalar_one()

    history = await _load_history(db_session, conv.id, new.id, since=old_msg.created_at)
    texts = [b["text"] for m in history for b in m["content"] if b.get("type") == "text"]
    assert "tin cu da nen" not in texts
    assert "tin moi verbatim" in texts
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `pytest tests/test_load_history_queue.py::test_load_history_since_bo_message_cu -v`
Expected: FAIL (`_load_history() got an unexpected keyword argument 'since'`).

- [ ] **Step 3: Thêm tham số `since`**

Trong `backend/app/agent/loop.py`, sửa chữ ký + thân `_load_history`:
```python
async def _load_history(db: AsyncSession, conversation_id: uuid.UUID,
                        current_request_id: uuid.UUID,
                        since: datetime | None = None) -> list[dict]:
```
Sau khi dựng `skip_ids` (giữ nguyên), thay khối `rows = await db.execute(...)` bằng:
```python
    stmt = select(Message).where(
        Message.conversation_id == conversation_id,
        or_(Message.chat_request_id.is_(None),
            Message.chat_request_id.not_in(skip_ids)),
        Message.is_ack.is_(False),
    )
    if since is not None:
        # Phase 5: message <= mốc summary_through_at đã gộp vào rolling_summary
        # (tiêm ở system prompt), chỉ nạp đuôi verbatim.
        stmt = stmt.where(Message.created_at > since)
    rows = await db.execute(stmt.order_by(Message.created_at.asc(), Message.id.asc()))
```
Giữ NGUYÊN phần cap `MAX_HISTORY_MESSAGES` + guard tool_result mồ côi bên dưới.

- [ ] **Step 4: Chạy test — PASS**

Run: `pytest tests/test_load_history_queue.py -v`
Expected: PASS toàn bộ (test cũ + test mới — `since=None` giữ hành vi cũ).

- [ ] **Step 5: Commit**

```bash
git add app/agent/loop.py tests/test_load_history_queue.py
git commit -m "feat(be): _load_history nhan tham so since de loc message da nen (Phase 5)"
```

---

### Task 3: `summarizer.py` — nén rolling summary

**Files:**
- Create: `backend/app/agent/summarizer.py`
- Test: `backend/tests/test_summarizer.py`

**Interfaces:**
- Consumes: `FakeLLMClient` (test), `Conversation`, `Message`.
- Produces: hằng số `SUMMARY_TRIGGER=60`, `SUMMARY_KEEP_RECENT=40`; `maybe_compress_history(db, conv, llm, *, force=False, keep_recent=SUMMARY_KEEP_RECENT) -> bool` (True nếu đã nén + commit).

- [ ] **Step 1: Viết test nén khi vượt ngưỡng**

Thêm vào `backend/tests/test_summarizer.py`:
```python
from datetime import datetime, timedelta, timezone

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.summarizer import SUMMARY_KEEP_RECENT, maybe_compress_history
from app.models import Conversation, Message, MessageRole


async def _mk_conv(db):
    conv = Conversation(workspace_id=uuid.uuid4(), user_id=uuid.uuid4())
    db.add(conv)
    await db.flush()
    return conv


def _fake_summary_llm(text="TOM TAT: chot deadline X ngay 30, giao Duy task Y"):
    return FakeLLMClient(turns=[[TextDelta(text=text),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)]])


async def test_nen_khi_vuot_trigger(db_session):
    conv = await _mk_conv(db_session)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(70):  # > SUMMARY_TRIGGER(60)
        role = MessageRole.user if i % 2 == 0 else MessageRole.assistant
        db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                               role=role, content=[{"type": "text", "text": f"tin {i}"}],
                               created_at=base + timedelta(minutes=i)))
    await db_session.commit()

    llm = _fake_summary_llm()
    changed = await maybe_compress_history(db_session, conv, llm)
    await db_session.refresh(conv)
    assert changed is True
    assert "TOM TAT" in conv.rolling_summary
    assert conv.summary_through_at is not None
    # mốc phải nằm ở message thứ (70 - KEEP_RECENT) trở về trước
    assert conv.summary_through_at <= base + timedelta(minutes=70 - SUMMARY_KEEP_RECENT)


async def test_khong_nen_khi_duoi_trigger(db_session):
    conv = await _mk_conv(db_session)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(10):
        db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                               role=MessageRole.user, content=[{"type": "text", "text": f"t{i}"}],
                               created_at=base + timedelta(minutes=i)))
    await db_session.commit()
    llm = _fake_summary_llm()
    changed = await maybe_compress_history(db_session, conv, llm)
    assert changed is False
    assert llm.calls == []  # khong goi LLM khi duoi nguong


async def test_force_nen_toan_bo_du_it(db_session):
    conv = await _mk_conv(db_session)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(5):
        role = MessageRole.user if i % 2 == 0 else MessageRole.assistant
        db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                               role=role, content=[{"type": "text", "text": f"t{i}"}],
                               created_at=base + timedelta(minutes=i)))
    await db_session.commit()
    llm = _fake_summary_llm("TOM TAT NGAN")
    changed = await maybe_compress_history(db_session, conv, llm, force=True, keep_recent=0)
    await db_session.refresh(conv)
    assert changed is True
    assert conv.rolling_summary == "TOM TAT NGAN"
    assert conv.summary_through_at == base + timedelta(minutes=4)  # message cuoi


async def test_ack_va_rong_khong_tinh(db_session):
    conv = await _mk_conv(db_session)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                           role=MessageRole.assistant, content=[{"type": "text", "text": "ack"}],
                           is_ack=True, created_at=base))
    await db_session.commit()
    llm = _fake_summary_llm()
    changed = await maybe_compress_history(db_session, conv, llm, force=True, keep_recent=0)
    assert changed is False  # chi co 1 ack -> khong co gi de nen
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `pytest tests/test_summarizer.py -v`
Expected: FAIL (`ModuleNotFoundError: app.agent.summarizer`).

- [ ] **Step 3: Viết `summarizer.py`**

Tạo `backend/app/agent/summarizer.py`:
```python
"""Phase 5 (session model): nén rolling summary cho 1 conversation.

Khi số message sống (sau summary_through_at, đã lọc is_ack/rỗng) vượt
SUMMARY_TRIGGER → gộp phần cũ (trừ ~KEEP_RECENT đuôi) vào Conversation.rolling_summary
bằng 1 lượt model_fast KHÔNG tool. Summary tiêm vào SYSTEM prompt ở run_agent_loop,
KHÔNG bao giờ chèn làm message (bài học is_ack: phá luật user/assistant xen kẽ).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_client import LLMClient, TextDelta
from app.models import Conversation, Message, MessageRole

SUMMARY_TRIGGER = 60
SUMMARY_KEEP_RECENT = 40

_SUMMARY_SYSTEM = (
    "Bạn là bộ nén hội thoại của một trợ lý điều hành công ty. Gộp phần tóm tắt cũ "
    "(nếu có) và đoạn hội thoại mới thành MỘT đoạn tóm tắt tiếng Việt ngắn gọn. "
    "BẮT BUỘC giữ lại: quyết định đã chốt, con số, tên người/task/project/deadline "
    "cụ thể, và việc còn dang dở. Bỏ lời chào và câu xã giao. Chỉ trả về đoạn tóm "
    "tắt, không thêm lời dẫn."
)


def _render_for_summary(msgs: list[Message]) -> str:
    lines: list[str] = []
    for m in msgs:
        who = "Người dùng" if m.role == MessageRole.user else "Trợ lý"
        texts = [b.get("text", "") for b in m.content if b.get("type") == "text"]
        tools = [b.get("name", "") for b in m.content if b.get("type") == "tool_use"]
        if texts:
            lines.append(f"{who}: {' '.join(t for t in texts if t)}")
        for name in tools:
            lines.append(f"Trợ lý gọi công cụ: {name}")
    return "\n".join(lines)


async def _summarize(llm: LLMClient, old_summary: str, chunk: str) -> str:
    prompt_parts = []
    if old_summary:
        prompt_parts.append("Tóm tắt hiện có:\n" + old_summary)
    prompt_parts.append("Đoạn hội thoại cần gộp vào tóm tắt:\n" + chunk)
    parts: list[str] = []
    async for event in llm.stream(
        system=_SUMMARY_SYSTEM,
        messages=[{"role": "user",
                   "content": [{"type": "text", "text": "\n\n".join(prompt_parts)}]}],
        tools=[]):
        if isinstance(event, TextDelta):
            parts.append(event.text)
    return "".join(parts).strip()


async def maybe_compress_history(db: AsyncSession, conv: Conversation, llm: LLMClient,
                                 *, force: bool = False,
                                 keep_recent: int = SUMMARY_KEEP_RECENT) -> bool:
    """Nén message cũ vào conv.rolling_summary nếu vượt ngưỡng (hoặc force). Trả True
    nếu đã nén + commit. force=True (dùng khi xoay conversation) bỏ qua SUMMARY_TRIGGER."""
    stmt = select(Message).where(
        Message.conversation_id == conv.id, Message.is_ack.is_(False))
    if conv.summary_through_at is not None:
        stmt = stmt.where(Message.created_at > conv.summary_through_at)
    stmt = stmt.order_by(Message.created_at.asc(), Message.id.asc())
    msgs = [m for m in (await db.execute(stmt)).scalars().all() if m.content]

    if not msgs:
        return False
    if not force and len(msgs) <= SUMMARY_TRIGGER:
        return False

    cut = max(0, len(msgs) - keep_recent)
    # Đuôi giữ lại phải bắt đầu bằng user-text (không mở đầu bằng tool_result mồ côi).
    while cut < len(msgs):
        m = msgs[cut]
        if (m.role == MessageRole.user and m.content
                and m.content[0].get("type") == "text"):
            break
        cut += 1
    to_fold = msgs[:cut]
    if not to_fold:
        return False

    new_summary = await _summarize(llm, conv.rolling_summary, _render_for_summary(to_fold))
    if not new_summary:
        return False  # LLM trả rỗng -> đừng ghi đè summary cũ / đừng đẩy mốc
    conv.rolling_summary = new_summary
    conv.summary_through_at = to_fold[-1].created_at
    await db.commit()
    return True
```

- [ ] **Step 4: Chạy test — PASS**

Run: `pytest tests/test_summarizer.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add app/agent/summarizer.py tests/test_summarizer.py
git commit -m "feat(be): summarizer.maybe_compress_history nen rolling summary (Phase 5)"
```

---

### Task 4: Tiêm `rolling_summary` vào system prompt + `since` trong `run_agent_loop`

**Files:**
- Modify: `backend/app/agent/loop.py` (imports; `run_agent_loop` chỗ fetch actor ~dòng 230; chỗ dựng `dynamic_parts`/`history` ~dòng 286-296)
- Test: `backend/tests/test_loop_rolling_summary.py` (mới)

**Interfaces:**
- Consumes: `_load_history(since=)` (Task 2), `Conversation.rolling_summary`/`summary_through_at` (Task 1).
- Produces: `run_agent_loop` nạp history bằng `since=conv.summary_through_at` và thêm block `# Tóm tắt hội thoại trước đó\n{rolling_summary}` vào system prompt khi có.

- [ ] **Step 1: Viết test — summary vào system, không vào messages**

Tạo `backend/tests/test_loop_rolling_summary.py`:
```python
import uuid
from datetime import datetime, timedelta, timezone

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.loop import run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Role, User, Workspace,
)


async def _seed(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
               role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    return ws, ceo


async def test_rolling_summary_vao_system_khong_vao_messages(db_session):
    ws, ceo = await _seed(db_session)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id,
                        rolling_summary="TOM TAT CU: da giao Duy task X",
                        summary_through_at=base)
    db_session.add(conv)
    await db_session.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="tiep theo lam gi", queue_position=1.0)
    db_session.add(req)
    await db_session.flush()
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user,
                           content=[{"type": "text", "text": "tiep theo lam gi"}],
                           created_at=base + timedelta(minutes=1)))  # SAU moc
    await db_session.commit()

    llm = FakeLLMClient(turns=[[TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)]])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    call = llm.calls[0]
    system = call["system"]
    system_text = system if isinstance(system, str) else "\n".join(
        b["text"] for b in system if b.get("type") == "text")
    assert "TOM TAT CU: da giao Duy task X" in system_text
    # summary KHONG duoc la 1 message trong lich su
    for m in call["messages"]:
        for b in m["content"]:
            assert "TOM TAT CU" not in str(b)
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `pytest tests/test_loop_rolling_summary.py -v`
Expected: FAIL (summary chưa xuất hiện trong system_text).

- [ ] **Step 3: Sửa `run_agent_loop`**

Trong `backend/app/agent/loop.py`:

3a. Thêm `Conversation` vào import từ `app.models` (dòng 18-20):
```python
from app.models import (
    AgentTrace, ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole,
    UsageLog, User,
)
```

3b. Sau `actor = await db.get(User, req.user_id)` (~dòng 230) thêm:
```python
    conv = await db.get(Conversation, req.conversation_id)
```

3c. Đổi dòng nạp history (~dòng 286) từ:
```python
            history = await _load_history(db, req.conversation_id, req.id)
```
thành:
```python
            history = await _load_history(db, req.conversation_id, req.id,
                                          since=conv.summary_through_at if conv else None)
```

3d. Trong khối dựng `dynamic_parts` (sau khi append snapshot_text, ~dòng 294-296), thêm:
```python
            if conv is not None and conv.rolling_summary:
                # Phase 5: tóm tắt hội thoại cũ — block ĐỘNG cuối, gần message nhất.
                dynamic_parts.append(
                    "# Tóm tắt hội thoại trước đó\n" + conv.rolling_summary)
```

- [ ] **Step 4: Chạy test — PASS**

Run: `pytest tests/test_loop_rolling_summary.py -v`
Expected: PASS.

- [ ] **Step 5: Chạy regression loop**

Run: `pytest tests/test_load_history_queue.py tests/test_agent_loop.py -v` (nếu có `test_agent_loop.py`; nếu không, bỏ file đó).
Expected: PASS (không hồi quy).

- [ ] **Step 6: Commit**

```bash
git add app/agent/loop.py tests/test_loop_rolling_summary.py
git commit -m "feat(be): tiem rolling_summary vao system prompt + since trong run_agent_loop (Phase 5)"
```

---

### Task 5: Gọi `maybe_compress_history` trong `process_conversation`

**Files:**
- Modify: `backend/app/agent/worker.py` (imports; `process_conversation` sau khi chọn `req`, trước router ~dòng 80-84)
- Test: `backend/tests/test_worker_compress.py` (mới)

**Interfaces:**
- Consumes: `maybe_compress_history` (Task 3).
- Produces: `process_conversation` nén history conv (bằng `llm` fast) trước khi dispatch router/loop.

- [ ] **Step 1: Viết test — worker nén khi conv dài**

Tạo `backend/tests/test_worker_compress.py`:
```python
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.publisher import FakeEventPublisher
from app.agent.worker import process_conversation
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Role, User, Workspace,
)


async def test_process_conversation_nen_history_dai(engine, db_session):
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
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(65):  # > SUMMARY_TRIGGER
        role = MessageRole.user if i % 2 == 0 else MessageRole.assistant
        db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, role=role,
                               content=[{"type": "text", "text": f"cu {i}"}],
                               created_at=base + timedelta(minutes=i)))
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="xem dashboard hom nay", queue_position=100.0)  # heuristic -> khong deep
    db_session.add(req)
    await db_session.flush()
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user,
                           content=[{"type": "text", "text": "xem dashboard hom nay"}],
                           created_at=base + timedelta(minutes=100)))
    await db_session.commit()

    # Luot 1 = summary; luot 2 = tra loi agent loop cua req.
    llm = FakeLLMClient(turns=[
        [TextDelta(text="TOM TAT DA NEN"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
        [TextDelta(text="tra loi"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
    ])

    async def never_cancelled(_id):
        return False

    ctx = {
        "session_factory": async_sessionmaker(engine, expire_on_commit=False),
        "llm_client": llm,
        "event_publisher": FakeEventPublisher(),
        "is_cancelled": never_cancelled,
    }
    await process_conversation(ctx, conv.id)

    await db_session.refresh(conv)
    assert conv.rolling_summary == "TOM TAT DA NEN"
    assert conv.summary_through_at is not None
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `pytest tests/test_worker_compress.py -v`
Expected: FAIL (`conv.rolling_summary` vẫn `""`).

- [ ] **Step 3: Wire compression vào worker**

Trong `backend/app/agent/worker.py`:

3a. Thêm import (cạnh các import `app.agent.*`):
```python
from app.agent.summarizer import maybe_compress_history
```

3b. Trong `process_conversation`, sau khối `if req.voice_note_id is not None:` (inject transcript) và TRƯỚC dòng `group = await classify_route(...)`, thêm:
```python
            # Phase 5: nén hội thoại cũ trước khi chạy loop (dùng model_fast = llm).
            # Lỗi nén không được giết job — request vẫn chạy với summary cũ.
            try:
                await maybe_compress_history(db, conv, llm)
            except Exception:
                logger.exception("nen rolling summary fail cho conversation %s",
                                 conversation_id)
                await db.rollback()
```
(`conv` đã được load ở dòng `conv = await db.get(Conversation, conversation_id)` phía trên trong vòng lặp — xác nhận biến `conv` còn trong scope; nếu không, thêm `conv = await db.get(Conversation, conversation_id)` ngay trước khối try.)

- [ ] **Step 4: Chạy test — PASS**

Run: `pytest tests/test_worker_compress.py tests/test_worker.py -v`
Expected: PASS (test mới + test worker cũ không hồi quy).

- [ ] **Step 5: Commit**

```bash
git add app/agent/worker.py tests/test_worker_compress.py
git commit -m "feat(be): process_conversation nen rolling summary truoc khi dispatch (Phase 5)"
```

---

### Task 6: `session_service.py` — active conversation + rotation

**Files:**
- Create: `backend/app/services/session_service.py`
- Test: `backend/tests/test_session_service.py`

**Interfaces:**
- Consumes: `maybe_compress_history` (Task 3).
- Produces: `ROTATE_IDLE_HOURS=12`, `ROTATE_MAX_MESSAGES=150`; `get_or_rotate_active_conversation(db, actor, llm_factory, *, now=None) -> Conversation`. `llm_factory` là callable trả LLMClient, CHỈ gọi khi thật sự xoay (tránh dựng client thật trong path không xoay).

- [ ] **Step 1: Viết test rotation**

Tạo `backend/tests/test_session_service.py`:
```python
import uuid
from datetime import datetime, timedelta, timezone

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Role, User, Workspace,
)
from app.services.session_service import (
    ROTATE_MAX_MESSAGES, get_or_rotate_active_conversation,
)


async def _seed(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
               role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    return ws, ceo


def _fake_llm():
    return FakeLLMClient(turns=[[TextDelta(text="SEED SUMMARY"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)]])


async def test_tao_moi_khi_chua_co(db_session):
    ws, ceo = await _seed(db_session)
    conv = await get_or_rotate_active_conversation(db_session, ceo, _fake_llm)
    assert conv.id is not None
    assert conv.archived_at is None


async def test_tra_lai_conv_song_khi_chua_can_xoay(db_session):
    ws, ceo = await _seed(db_session)
    existing = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add(existing)
    await db_session.commit()
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    conv = await get_or_rotate_active_conversation(db_session, ceo, _fake_llm, now=now)
    assert conv.id == existing.id


async def test_xoay_khi_idle_qua_12h(db_session):
    ws, ceo = await _seed(db_session)
    old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id, created_at=old_time)
    db_session.add(conv)
    await db_session.flush()
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, role=MessageRole.user,
                           content=[{"type": "text", "text": "hom qua dan viec X"}],
                           created_at=old_time))
    await db_session.commit()
    now = old_time + timedelta(hours=13)  # idle > 12h
    llm = _fake_llm()
    new = await get_or_rotate_active_conversation(db_session, ceo, lambda: llm, now=now)
    await db_session.refresh(conv)
    assert new.id != conv.id
    assert conv.archived_at is not None
    assert new.rolling_summary == "SEED SUMMARY"  # seed tu summary conv cu (da fold tail)


async def test_xoay_khi_qua_150_message(db_session):
    ws, ceo = await _seed(db_session)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id, created_at=base)
    db_session.add(conv)
    await db_session.flush()
    for i in range(ROTATE_MAX_MESSAGES + 2):
        db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, role=MessageRole.user,
                               content=[{"type": "text", "text": f"m{i}"}],
                               created_at=base + timedelta(seconds=i)))
    await db_session.commit()
    now = base + timedelta(seconds=200)  # chua idle
    new = await get_or_rotate_active_conversation(db_session, ceo, lambda: _fake_llm(), now=now)
    await db_session.refresh(conv)
    assert new.id != conv.id
    assert conv.archived_at is not None


async def test_khong_xoay_khi_con_viec_dang_do(db_session):
    ws, ceo = await _seed(db_session)
    old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id, created_at=old_time)
    db_session.add(conv)
    await db_session.flush()
    db_session.add(ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                               content="dang cho", queue_position=1.0,
                               status=ChatRequestStatus.queued))
    await db_session.commit()
    now = old_time + timedelta(hours=20)  # idle nhung con viec queued
    conv2 = await get_or_rotate_active_conversation(db_session, ceo, _fake_llm, now=now)
    assert conv2.id == conv.id  # khong xoay
    await db_session.refresh(conv)
    assert conv.archived_at is None


async def test_khong_lo_conv_user_khac(db_session):
    ws, ceo = await _seed(db_session)
    other = User(workspace_id=ws.id, email="o@a.vn", password_hash="x", full_name="O",
                 role=Role.manager)
    db_session.add(other)
    await db_session.flush()
    db_session.add(Conversation(workspace_id=ws.id, user_id=other.id))
    await db_session.commit()
    conv = await get_or_rotate_active_conversation(db_session, ceo, _fake_llm)
    assert conv.user_id == ceo.id
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `pytest tests/test_session_service.py -v`
Expected: FAIL (`ModuleNotFoundError: app.services.session_service`).

- [ ] **Step 3: Viết `session_service.py`**

Tạo `backend/app/services/session_service.py`:
```python
"""Phase 5 (session model): active conversation + xoay conversation ngầm.

Bất biến: mỗi user có ≤1 conversation "sống" (archived_at IS NULL, mới nhất). Xoay
khi idle > ROTATE_IDLE_HOURS HOẶC > ROTATE_MAX_MESSAGES message sống, nhưng KHÔNG
xoay nếu còn việc dang dở (queue). Resolve lúc FE mount qua GET /conversations/active.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_client import LLMClient
from app.agent.summarizer import maybe_compress_history
from app.models import ChatRequest, ChatRequestStatus, Conversation, Message, User

ROTATE_IDLE_HOURS = 12
ROTATE_MAX_MESSAGES = 150

_BUSY_STATUSES = [
    ChatRequestStatus.queued, ChatRequestStatus.running,
    ChatRequestStatus.deep_running, ChatRequestStatus.awaiting_confirmation,
]


def _as_aware(dt: datetime) -> datetime:
    """SQLite trả datetime naive — chuẩn hóa về aware/UTC trước khi so (bài học period-bounds)."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


async def _active_conv(db: AsyncSession, actor: User) -> Conversation | None:
    return (await db.execute(select(Conversation).where(
        Conversation.workspace_id == actor.workspace_id,
        Conversation.user_id == actor.id,
        Conversation.archived_at.is_(None),
    ).order_by(Conversation.created_at.desc()).limit(1))).scalar_one_or_none()


async def get_or_rotate_active_conversation(
        db: AsyncSession, actor: User,
        llm_factory: Callable[[], LLMClient], *,
        now: datetime | None = None) -> Conversation:
    now = _as_aware(now) if now is not None else datetime.now(timezone.utc)
    conv = await _active_conv(db, actor)
    if conv is None:
        conv = Conversation(workspace_id=actor.workspace_id, user_id=actor.id)
        db.add(conv)
        await db.commit()
        return conv

    # Còn việc dang dở -> không xoay (tránh bỏ rơi queue).
    busy = (await db.execute(select(ChatRequest.id).where(
        ChatRequest.conversation_id == conv.id,
        ChatRequest.status.in_(_BUSY_STATUSES),
    ).limit(1))).scalar_one_or_none()
    if busy is not None or conv.queue_held:
        return conv

    live = [m for m in (await db.execute(select(Message).where(
        Message.conversation_id == conv.id, Message.is_ack.is_(False),
    ).order_by(Message.created_at.asc(), Message.id.asc()))).scalars().all() if m.content]
    count = len(live)
    last_at = _as_aware(live[-1].created_at) if live else _as_aware(conv.created_at)
    idle = (now - last_at) > timedelta(hours=ROTATE_IDLE_HOURS)
    too_big = count > ROTATE_MAX_MESSAGES
    if not (idle or too_big):
        return conv

    # Xoay: fold toàn bộ đuôi vào summary conv cũ -> seed conv mới -> archive conv cũ.
    await maybe_compress_history(db, conv, llm_factory(), force=True, keep_recent=0)
    conv.archived_at = now
    new = Conversation(workspace_id=actor.workspace_id, user_id=actor.id,
                       rolling_summary=conv.rolling_summary)
    db.add(new)
    await db.commit()
    return new
```

- [ ] **Step 4: Chạy test — PASS**

Run: `pytest tests/test_session_service.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add app/services/session_service.py tests/test_session_service.py
git commit -m "feat(be): session_service.get_or_rotate_active_conversation (Phase 5)"
```

---

### Task 7: `MessageOut.conversation_id` + `ConversationOut.archived_at` + `GET /conversations/active`

**Files:**
- Modify: `backend/app/schemas.py:306-311` (`ConversationOut`), `:400-407` (`MessageOut`)
- Modify: `backend/app/api/chat.py` (thêm route `/active`; import `session_service`)
- Test: `backend/tests/test_conversation_active_timeline_api.py` (mới)

**Interfaces:**
- Consumes: `get_or_rotate_active_conversation` (Task 6).
- Produces: `GET /api/v1/conversations/active -> ConversationOut`; `ConversationOut.archived_at`; `MessageOut.conversation_id`.

- [ ] **Step 1: Viết test endpoint /active**

Tạo `backend/tests/test_conversation_active_timeline_api.py`:
```python
from tests.conftest import _ceo_headers


async def test_active_tao_moi_khi_chua_co(client):
    headers = await _ceo_headers(client)
    r = await client.get("/api/v1/conversations/active", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"]
    assert body["archived_at"] is None


async def test_active_tra_lai_cung_conv(client):
    headers = await _ceo_headers(client)
    r1 = await client.get("/api/v1/conversations/active", headers=headers)
    r2 = await client.get("/api/v1/conversations/active", headers=headers)
    assert r1.json()["id"] == r2.json()["id"]  # chua can xoay -> giu nguyen


async def test_active_can_dang_nhap(client):
    r = await client.get("/api/v1/conversations/active")
    assert r.status_code == 401
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `pytest tests/test_conversation_active_timeline_api.py -v`
Expected: FAIL (404 — route chưa có).

- [ ] **Step 3a: Thêm field schema**

Trong `backend/app/schemas.py`:
```python
class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str | None
    queue_held: bool = False
    archived_at: dt.datetime | None = None
    created_at: dt.datetime

    model_config = {"from_attributes": True}
```
```python
class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    role: MessageRole
    content: list
    voice_note_id: uuid.UUID | None = None
    created_at: dt.datetime

    model_config = {"from_attributes": True}
```
(`ConversationOut` trước đây không có `model_config` — thêm `from_attributes` để trả trực tiếp ORM object như các route hiện tại đang làm; các route `create/list/rename` đang `return conv`/`list(rows.scalars())` sẽ vẫn hoạt động.)

- [ ] **Step 3b: Thêm route /active**

Trong `backend/app/api/chat.py`:

Thêm import:
```python
from app.services import continuity, session_service, voice_service
```
(gộp vào dòng import `from app.services import ...` sẵn có.)

Thêm route (đặt SAU `list_conversations`, trước `rename_conversation` để rõ ràng — không đụng path param):
```python
@router.get("/active", response_model=ConversationOut)
async def active_conversation(actor: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    from app.agent.llm_client import get_llm_client
    # llm_factory chỉ được gọi khi thật sự xoay (fold tail) — path không xoay
    # không dựng client thật, nên test /active không cần ANTHROPIC_API_KEY.
    conv = await session_service.get_or_rotate_active_conversation(
        db, actor, get_llm_client)
    return conv
```

- [ ] **Step 4: Chạy test — PASS**

Run: `pytest tests/test_conversation_active_timeline_api.py -v`
Expected: PASS.

- [ ] **Step 5: Regression chat API**

Run: `pytest tests/test_chat_api.py -v` (nếu tồn tại; nếu tên khác, chạy `pytest tests/ -k conversation -v`).
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/schemas.py app/api/chat.py tests/test_conversation_active_timeline_api.py
git commit -m "feat(be): GET /conversations/active + MessageOut.conversation_id + ConversationOut.archived_at (Phase 5)"
```

---

### Task 8: `GET /conversations/timeline` + export OpenAPI

**Files:**
- Modify: `backend/app/api/chat.py` (route `/timeline`; imports `or_`, `and_`, `datetime`)
- Modify: `backend/openapi.json` (export lại)
- Test: `backend/tests/test_conversation_active_timeline_api.py` (mở rộng)

**Interfaces:**
- Consumes: `MessageOut.conversation_id` (Task 7).
- Produces: `GET /api/v1/conversations/timeline?before_at=<iso>&before_id=<uuid>&limit=<n> -> list[MessageOut]` (newest-first, xuyên conversation của actor).

- [ ] **Step 1: Viết test timeline phân trang + quyền**

Thêm vào `backend/tests/test_conversation_active_timeline_api.py`:
```python
import uuid
from datetime import datetime, timedelta, timezone

from app.models import Conversation, Message, MessageRole
from sqlalchemy import select


async def _mk_msgs_for_ceo(client, headers, db_engine_session):
    """Tao 2 conversation cho CEO, moi cai 2 message, thoi gian tang dan."""
    # Lay ceo id qua /me
    me = (await client.get("/api/v1/users/me", headers=headers)).json()
    return me


async def test_timeline_xuyen_conversation_theo_thu_tu(client, db_session):
    headers = await _ceo_headers(client)
    me = (await client.get("/api/v1/users/me", headers=headers)).json()
    ceo_id = uuid.UUID(me["id"])
    ws_id = uuid.UUID(me["workspace_id"])
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    c1 = Conversation(workspace_id=ws_id, user_id=ceo_id, created_at=base)
    c2 = Conversation(workspace_id=ws_id, user_id=ceo_id, created_at=base + timedelta(hours=1))
    db_session.add_all([c1, c2])
    await db_session.flush()
    for i, (c, t) in enumerate([(c1, 0), (c1, 1), (c2, 2), (c2, 3)]):
        db_session.add(Message(workspace_id=ws_id, conversation_id=c.id, role=MessageRole.user,
                               content=[{"type": "text", "text": f"m{t}"}],
                               created_at=base + timedelta(minutes=t)))
    await db_session.commit()

    r = await client.get("/api/v1/conversations/timeline?limit=3", headers=headers)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 3
    # newest-first
    texts = [b["text"] for m in rows for b in m["content"] if b.get("type") == "text"]
    assert texts == ["m3", "m2", "m1"]
    assert rows[0]["conversation_id"]

    # trang ke tiep (cu hon rows[-1])
    last = rows[-1]
    r2 = await client.get(
        f"/api/v1/conversations/timeline?limit=3&before_at={last['created_at']}"
        f"&before_id={last['id']}", headers=headers)
    texts2 = [b["text"] for m in r2.json() for b in m["content"] if b.get("type") == "text"]
    assert texts2 == ["m0"]


async def test_timeline_khong_lo_conv_user_khac(client, db_session):
    from tests.conftest import _invite_and_join
    headers = await _ceo_headers(client)
    # nhan vien khac
    other = await _invite_and_join(client, headers, "manager", "m@a.vn")
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    me = (await client.get("/api/v1/users/me", headers=headers)).json()
    ws_id = uuid.UUID(me["workspace_id"])
    other_id = uuid.UUID(other["user"]["id"] if "user" in other else
                         (await client.get("/api/v1/users/me", headers=other_headers)).json()["id"])
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    c = Conversation(workspace_id=ws_id, user_id=other_id, created_at=base)
    db_session.add(c)
    await db_session.flush()
    db_session.add(Message(workspace_id=ws_id, conversation_id=c.id, role=MessageRole.user,
                           content=[{"type": "text", "text": "bi mat cua nguoi khac"}],
                           created_at=base))
    await db_session.commit()

    r = await client.get("/api/v1/conversations/timeline", headers=headers)
    texts = [b["text"] for m in r.json() for b in m["content"] if b.get("type") == "text"]
    assert "bi mat cua nguoi khac" not in texts
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `pytest tests/test_conversation_active_timeline_api.py -k timeline -v`
Expected: FAIL (404).

- [ ] **Step 3: Thêm route /timeline**

Trong `backend/app/api/chat.py`:

3a. Bổ sung imports (dòng `from sqlalchemy import ...` + `datetime`):
```python
import uuid
from datetime import datetime
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import and_, delete, func, or_, select
```
(Giữ nguyên các import khác; thêm `and_`, `or_`, `Query`, và `from datetime import datetime`.)

3b. Thêm route (đặt sau `active_conversation`):
```python
@router.get("/timeline", response_model=list[MessageOut])
async def timeline(actor: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db),
                   before_at: datetime | None = Query(None),
                   before_id: uuid.UUID | None = Query(None),
                   limit: int = Query(50, ge=1, le=100)):
    """Một luồng liền mạch xuyên các conversation của actor (Phase 5). Newest-first,
    cursor = (before_at, before_id) của message cũ nhất trang trước. Chỉ conversation
    của chính actor."""
    conv_ids = select(Conversation.id).where(
        Conversation.workspace_id == actor.workspace_id,
        Conversation.user_id == actor.id)
    stmt = select(Message).where(Message.conversation_id.in_(conv_ids))
    if before_at is not None and before_id is not None:
        stmt = stmt.where(or_(
            Message.created_at < before_at,
            and_(Message.created_at == before_at, Message.id < before_id)))
    stmt = stmt.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())
```

- [ ] **Step 4: Chạy test — PASS**

Run: `pytest tests/test_conversation_active_timeline_api.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Export OpenAPI + commit**

Run: `python scripts/export_openapi.py`
Expected: ghi lại `openapi.json` ở repo root.
```bash
git add app/api/chat.py tests/test_conversation_active_timeline_api.py ../openapi.json
git commit -m "feat(be): GET /conversations/timeline phan trang xuyen conversation (Phase 5)"
```
(Nếu `openapi.json` ở repo root `d:\8. AI\ai-assistant\openapi.json`, điều chỉnh đường dẫn `git add` cho đúng.)

---

### Task 9: FE api layer — `getActiveConversation` + `getTimeline`

**Files:**
- Modify: `frontend/src/api/chat.ts`

**Interfaces:**
- Consumes: `GET /conversations/active`, `GET /conversations/timeline` (Task 7, 8).
- Produces: `getActiveConversation(): Promise<Conversation>`; `getTimeline(opts?): Promise<Message[]>`; `Conversation.archived_at`, `Message.conversation_id`.

- [ ] **Step 1: Thêm field types + hàm API**

Trong `frontend/src/api/chat.ts`:

1a. `Conversation` type — thêm `archived_at`:
```typescript
export type Conversation = {
  id: string;
  title: string | null;
  queue_held: boolean;
  archived_at: string | null;
  created_at: string;
};
```

1b. `Message` type — thêm `conversation_id`:
```typescript
export type Message = {
  id: string;
  conversation_id: string | null;
  role: "user" | "assistant";
  content: ContentBlock[];
  voice_note_id: string | null;
  created_at: string;
};
```

1c. Thêm 2 hàm (sau `listMessages`):
```typescript
export const getActiveConversation = () =>
  apiFetch<Conversation>("/api/v1/conversations/active");

export const getTimeline = (opts?: { beforeAt?: string; beforeId?: string; limit?: number }) => {
  const p = new URLSearchParams();
  if (opts?.limit) p.set("limit", String(opts.limit));
  if (opts?.beforeAt && opts?.beforeId) {
    p.set("before_at", opts.beforeAt);
    p.set("before_id", opts.beforeId);
  }
  const qs = p.toString();
  return apiFetch<Message[]>(`/api/v1/conversations/timeline${qs ? `?${qs}` : ""}`);
};
```

- [ ] **Step 2: Kiểm tra tsc**

Run (trong `frontend/`): `npx tsc --noEmit`
Expected: 0 lỗi.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/chat.ts
git commit -m "feat(fe): api getActiveConversation + getTimeline (Phase 5)"
```

---

### Task 10: FE `chat.tsx` — LIVE mode timeline + history read-only + bỏ new-chat

**Files:**
- Modify: `frontend/app/main/chat.tsx`

**Interfaces:**
- Consumes: `getActiveConversation`, `getTimeline`, `listMessages`, `listConversations` (Task 9).
- Produces: Chat mở không param = LIVE (active + timeline xuyên conversation, cuộn lên nạp trang cũ); mở có `?id` = xem lại (read-only nếu conversation đã archived).

- [ ] **Step 1: Bỏ `coldStart` + nút tạo mới header**

1a. Xóa dòng module var `coldStart` (dòng ~144-146):
```typescript
// Cold start (app khởi động lại) → mở Chat với cuộc trò chuyện MỚI. Biến module,
// tự reset về true mỗi khi app nạp lại bundle (tức khởi động lại).
let coldStart = true;
```

1b. Trong header, xóa nút `create-outline` (`onPress={newConversation}`) và hàm `newConversation`. Thay bằng: khi ở history mode hiện nút "Về luồng hiện tại"; khi LIVE mode để trống (hoặc giữ khoảng trắng cân đối header). (Chi tiết ở Step 3.)

- [ ] **Step 2: Thêm import + hàm dựng rows dùng chung**

2a. Cập nhật import từ `../../src/api/chat`: thêm `getActiveConversation`, `getTimeline`; bỏ `createConversation` nếu không còn dùng.

2b. Thêm helper module-level (cạnh `textOfMessage`) dựng `Row[]` từ danh sách `Message` (tái dùng cho cả timeline lẫn history), chèn divider khi đổi conversation:
```typescript
function messagesToRows(msgs: Message[]): Row[] {
  const out: Row[] = [];
  let prevConv: string | null | undefined = undefined;
  for (const m of msgs) {
    if (prevConv !== undefined && m.conversation_id && m.conversation_id !== prevConv) {
      out.push({ key: `divider-${m.id}`, kind: "system", text: "— cuộc trò chuyện mới —" });
    }
    prevConv = m.conversation_id ?? prevConv;
    const text = textOfMessage(m);
    if (text)
      out.push({ key: m.id, kind: m.role === "user" ? "user" : "assistant", text,
                 voiceNoteId: m.voice_note_id });
    for (const b of m.content) {
      if (b.type === "tool_use")
        out.push({ key: `${m.id}-${b.id}`, kind: "system", text: labelForTool(b.name) });
    }
  }
  return out;
}
```

- [ ] **Step 3: Viết lại effect mount (LIVE vs history) + state phân trang + read-only**

3a. Thêm state:
```typescript
  const [archived, setArchived] = useState(false);         // conv đang xem đã lưu trữ?
  const [historyMode, setHistoryMode] = useState(false);   // mở theo ?id (xem lại)?
  const [olderCursor, setOlderCursor] = useState<{ at: string; id: string } | null>(null);
  const [hasMoreOlder, setHasMoreOlder] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
```

3b. Thay `loadHistory` cũ bằng 2 nhánh. Sửa effect mount (khối `useEffect` ~294-334):
```typescript
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    setRows([]);
    setQueue([]);
    setHeld(false);
    setConversationTitle(null);
    setArchived(false);
    setOlderCursor(null);
    setHasMoreOlder(false);
    closeWs.current?.();
    (async () => {
      try {
        let convId: string;
        if (requestedId) {
          // History mode: xem lại 1 conversation cụ thể.
          setHistoryMode(true);
          const all = await listConversations();
          const conv = all.find((c) => c.id === requestedId);
          if (!conv) throw new Error("Không tìm thấy cuộc trò chuyện này");
          convId = conv.id;
          setConversationTitle(conv.title);
          setArchived(conv.archived_at != null);
          setHeld(conv.queue_held);
          const msgs = await listMessages(convId);
          if (cancelled) return;
          setRows(messagesToRows(msgs));
        } else {
          // LIVE mode: active conversation + timeline xuyên conversation.
          setHistoryMode(false);
          const active = await getActiveConversation();
          convId = active.id;
          setConversationTitle(active.title);
          setArchived(false);
          setHeld(active.queue_held);
          const LIMIT = 50;
          const page = await getTimeline({ limit: LIMIT });
          if (cancelled) return;
          const chrono = [...page].reverse(); // API newest-first -> hiển thị cũ→mới
          setRows(messagesToRows(chrono));
          if (page.length === LIMIT && page.length > 0) {
            const oldest = page[page.length - 1];
            setOlderCursor({ at: oldest.created_at, id: oldest.id });
            setHasMoreOlder(true);
          }
        }
        if (cancelled) return;
        setConversationId(convId);
        await refreshQueue(convId);
        closeWs.current = await openConversationStream(convId, onWsEvent(convId));
      } catch (e: any) {
        if (!cancelled) setLoadError(String(e?.message ?? e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      closeWs.current?.();
    };
  }, [requestedId, onWsEvent, refreshQueue]);
```
(Xóa `loadHistory` cũ và mọi tham chiếu tới nó.)

3c. Thêm hàm nạp trang cũ hơn (LIVE mode) — prepend:
```typescript
  const loadOlder = async () => {
    if (!olderCursor || loadingOlder) return;
    setLoadingOlder(true);
    try {
      const LIMIT = 50;
      const page = await getTimeline({ beforeAt: olderCursor.at, beforeId: olderCursor.id, limit: LIMIT });
      const chrono = [...page].reverse();
      setRows((prev) => [...messagesToRows(chrono), ...prev]);
      if (page.length === LIMIT && page.length > 0) {
        const oldest = page[page.length - 1];
        setOlderCursor({ at: oldest.created_at, id: oldest.id });
      } else {
        setHasMoreOlder(false);
      }
    } catch {
      setActionError("Không tải được đoạn cũ hơn — thử lại.");
    } finally {
      setLoadingOlder(false);
    }
  };
```

3d. Header: thay nút phải. Khi `historyMode` → nút "Về luồng hiện tại" (`navigation.navigate("Chat", {})` sau khi clear param); khi LIVE → không có nút tạo mới:
```tsx
        {historyMode ? (
          <TouchableOpacity
            style={styles.headerBtn}
            onPress={() => navigation.navigate("Chat", { id: undefined })}
            accessibilityLabel="Về luồng hiện tại"
          >
            <Ionicons name="arrow-undo-outline" size={22} color={colors.text} />
          </TouchableOpacity>
        ) : (
          <View style={styles.headerBtn} />
        )}
```

3e. FlatList: thêm header "Tải đoạn cũ hơn" (chỉ LIVE mode, khi `hasMoreOlder`):
```tsx
        ListHeaderComponent={
          !historyMode && hasMoreOlder ? (
            <TouchableOpacity style={styles.loadOlder} onPress={loadOlder} disabled={loadingOlder}>
              {loadingOlder ? (
                <ActivityIndicator color={colors.primary} size="small" />
              ) : (
                <Text style={styles.loadOlderText}>↑ Tải đoạn hội thoại cũ hơn</Text>
              )}
            </TouchableOpacity>
          ) : null
        }
```
Thêm style:
```typescript
  loadOlder: { alignItems: "center", paddingVertical: spacing.md },
  loadOlderText: { color: colors.primary, fontFamily: fonts.semibold, fontSize: 14 },
```

3f. Composer: ẩn khi `historyMode && archived` (conversation lưu trữ = read-only). Bọc khối `composerWrap`:
```tsx
      {historyMode && archived ? (
        <View style={styles.readonlyBar}>
          <Text style={styles.readonlyText}>Cuộc trò chuyện đã lưu trữ — chỉ xem lại.</Text>
          <TouchableOpacity style={styles.pillPrimary}
            onPress={() => navigation.navigate("Chat", { id: undefined })}>
            <Text style={styles.pillPrimaryText}>Về luồng hiện tại</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <View style={[styles.composerWrap, { paddingBottom: kbVisible ? spacing.sm : insets.bottom || spacing.sm }]}>
          {/* ...composerCard giữ nguyên... */}
        </View>
      )}
```
Thêm style:
```typescript
  readonlyBar: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    backgroundColor: colors.surfaceAlt,
  },
  readonlyText: { flex: 1, color: colors.textSecondary, fontFamily: fonts.medium, fontSize: 13 },
```

3g. `submit`/`resumeQueue`: khi `archived` không cho gửi (guard đầu hàm `if (archived) return;`).

- [ ] **Step 4: Kiểm tra tsc**

Run (trong `frontend/`): `npx tsc --noEmit`
Expected: 0 lỗi. Sửa hết các tham chiếu `loadHistory`/`newConversation`/`coldStart`/`createConversation` còn sót cho tới khi sạch.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/main/chat.tsx
git commit -m "feat(fe): chat LIVE mode timeline xuyen conversation + history read-only, bo new-chat (Phase 5)"
```

---

### Task 11: FE `DrawerContent` — bỏ nút New chat

**Files:**
- Modify: `frontend/src/navigation/DrawerContent.tsx`

**Interfaces:**
- Consumes: (không). Produces: drawer không còn nút "New chat"; "Gần đây" + "Xem tất cả" giữ nguyên làm history.

- [ ] **Step 1: Bỏ nút New chat + hàm `newChat`**

1a. Xóa hàm `newChat` (dòng ~41-48) và import `createConversation` (bỏ khỏi dòng import `../api/chat` nếu không còn dùng — `openChat` vẫn dùng nên giữ `Conversation, listConversations`).

1b. Trong `bottomBar` (dòng ~103-114), xóa `<TouchableOpacity style={styles.newChatBtn} onPress={newChat}>...`; giữ avatar + userName. Có thể để userName chiếm chỗ (`flex: 1` đã có).

1c. Xóa các style không còn dùng: `newChatBtn`, `newChatText` (để tránh cảnh báo lint; tsc không bắt buộc nhưng dọn cho sạch).

- [ ] **Step 2: Kiểm tra tsc**

Run (trong `frontend/`): `npx tsc --noEmit`
Expected: 0 lỗi (không còn tham chiếu `newChat`/`createConversation` mồ côi).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/navigation/DrawerContent.tsx
git commit -m "feat(fe): bo nut New chat khoi drawer (Phase 5 session model)"
```

---

### Task 12: Verify toàn bộ + cập nhật docs

**Files:**
- Modify: `PROJECT_CONTEXT.md`, `C:\Users\dpham\.claude\projects\d--8--AI-ai-assistant\memory\` (memory + MEMORY.md)

- [ ] **Step 1: Full pytest**

Run (trong `backend/`): `pytest tests/ -v`
Expected: tất cả PASS (số test tăng so với 675 trước đó; 0 fail). Nếu có fail, sửa trước khi tiếp.

- [ ] **Step 2: Full tsc**

Run (trong `frontend/`): `npx tsc --noEmit`
Expected: 0 lỗi.

- [ ] **Step 3: Smoke migration trên Postgres dev**

Run (trong `backend/`): `alembic upgrade head` (sau `docker compose up -d postgres redis`).
Expected: đã ở head (migration Task 1 đã áp), không lỗi.

- [ ] **Step 4: Cập nhật `PROJECT_CONTEXT.md`**

Cập nhật: mục 2/6 (rolling summary + xoay conversation), mục 4 (bảng API thêm `GET /active`, `GET /timeline`), mục 5 (FE bỏ New chat, chat LIVE timeline + history read-only), mục 9 (thêm migration `session_model_rolling_summary` + 3 cột `Conversation`), mục 13 (dòng tiến độ 2026-07-24 Phase 5). Đổi "Last verified"/"Verified against commit" sang commit HEAD mới. Dùng Edit/Write (KHÔNG PowerShell Set-Content).

- [ ] **Step 5: Cập nhật memory**

Sửa `project-phase0-ai-upgrade-progress.md` (hoặc tạo file mới `project-phase5-session-model.md`) ghi Phase 5 xong; cập nhật dòng tương ứng trong `MEMORY.md`. Ghi rõ: embeddings/pgvector đẩy Phase 6; rotation resolve lúc mount; summary vào system prompt (không message).

- [ ] **Step 6: Commit docs**

```bash
git add PROJECT_CONTEXT.md
git commit -m "docs: PROJECT_CONTEXT.md - Phase 5 session model (rolling summary + xoay conversation + timeline)"
```

---

## Self-Review

**1. Spec coverage:**
- Rolling summary (spec §3) → Task 1-5. ✔
- Xoay conversation ngầm (spec §4) → Task 6-7 (`/active` resolve lúc mount). ✔
- Timeline xuyên conversation (spec §5) → Task 8 (`/timeline`) + Task 10 (FE). ✔
- Bỏ New chat (spec §6) → Task 10 (header + coldStart) + Task 11 (drawer). ✔
- History read-only (spec §6) → Task 10 (Step 3f/3g). ✔
- Queue/queue_held giữ nguyên (spec §4) → không sửa `continuity.py`/queue-part của `process_conversation`; rotation guard "busy" bảo toàn. ✔
- Embeddings → Phase 6 (spec §1 loại trừ) → không có task. ✔ (đúng chủ đích)
- Test đầy đủ (spec §7) → mỗi task backend có test; FE verify bằng tsc (repo không có FE test suite). ✔
- SQLite timezone gotcha (spec §7) → `_as_aware` trong session_service (Task 6). ✔
- Export OpenAPI sau đổi contract → Task 8 Step 5. ✔

**2. Placeholder scan:** Không có TBD/TODO; mọi step backend có code đầy đủ; FE step có snippet cụ thể. Đường dẫn `openapi.json` ở Task 8 ghi rõ cần chỉnh nếu ở repo root — không phải placeholder mà là điều kiện môi trường.

**3. Type consistency:**
- `maybe_compress_history(db, conv, llm, *, force=False, keep_recent=SUMMARY_KEEP_RECENT) -> bool` — dùng thống nhất Task 3/5/6.
- `get_or_rotate_active_conversation(db, actor, llm_factory, *, now=None) -> Conversation` — Task 6/7 khớp (endpoint truyền `get_llm_client` làm factory).
- `_load_history(..., since=None)` — Task 2/4 khớp.
- FE `getTimeline({beforeAt, beforeId, limit})` — Task 9/10 khớp param naming; endpoint nhận `before_at/before_id/limit` (Task 8) — FE map đúng.
- `messagesToRows(msgs: Message[]): Row[]` — Task 10 định nghĩa + dùng nội bộ.

Không phát hiện lệch tên/kiểu.
