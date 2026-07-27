# Cải thiện UX hội thoại: tự đặt tên chat + thẻ bấm chọn — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (A) Tự động đặt tên cuộc trò chuyện bằng AI (model_fast) sau khi AI trả lời xong tin đầu
tiên, thay cho tên cắt-cứng-60-ký-tự hiện tại; (B) tool `suggest_replies` để AI đưa thẻ bấm chọn nhanh
cho bất kỳ câu hỏi nào có sẵn vài lựa chọn rời rạc.

**Architecture:** (A) cột `title_locked` trên `Conversation` + cron mỗi phút quét tối đa 10 cuộc/lượt,
gọi `model_fast` sinh tiêu đề rồi khoá lại. (B) tool mới không nhạy cảm, agent loop nhận diện tool
này để kết thúc lượt ngay (không gọi lại LLM), FE hiện tool_use này thành thẻ bấm tái dùng đúng cơ chế
`submit()`/style đã có của onboarding chips.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (backend), Expo/React Native + TypeScript
(frontend), pytest + pytest-asyncio (asyncio_mode=auto, không bắt buộc decorator).

## Global Constraints

- Mọi bảng (trừ `workspaces`) có `workspace_id`; mọi query lọc theo workspace — `Conversation` đã có
  sẵn, không đổi.
- Quyền kiểm tra ở service layer, không ở prompt/model — không áp dụng cho 2 tính năng này (không có
  quyền mới nào cần kiểm tra: `suggest_replies` không nhạy cảm, cron không có actor).
- Actor identity luôn lấy từ JWT — không áp dụng (cron không có actor; `suggest_replies` không đụng
  actor).
- Model LLM lấy từ config theo loại tác vụ, không hardcode — dùng `get_llm_client()` mặc định
  (= `settings.model_fast`), đúng pattern `summarizer.py`/`classify_route`.
- Route dưới `/api/v1` — không thêm route mới trong plan này.
- Đổi API contract = chạy lại `export_openapi.py` — KHÔNG áp dụng: `title_locked` không vào
  `ConversationOut`; `suggest_replies` là tool nội bộ agent, không phải REST endpoint.
- TDD: test trước, code sau; mỗi task một commit.
- Không commit secrets.
- KHÔNG dùng PowerShell `Get-Content | Set-Content` để sửa file UTF-8 tiếng Việt — dùng Edit/Write.
- Migration: `alembic revision --autogenerate -m "..."` rồi `alembic upgrade head`, chạy trong
  `backend/` với venv đã activate và `docker compose up -d postgres redis` đang chạy (Postgres dev
  map cổng 5435).

---

### Task 1: Cột `title_locked` trên Conversation + migration

**Files:**
- Modify: `backend/app/models.py:362-379` (class `Conversation`)
- Create: `backend/alembic/versions/<auto>_conversation_title_locked.py` (revision id do alembic tự
  sinh — chỉ `down_revision` là giá trị cố định biết trước)
- Test: `backend/tests/test_chat_models.py`

**Interfaces:**
- Produces: `Conversation.title_locked: bool` (default `False`) — Task 2, 3, 4 đều dùng cột này.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/test_chat_models.py`:

```python
@pytest.mark.asyncio
async def test_conversation_title_locked_defaults_false(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    u = User(workspace_id=ws.id, email="tl@a.vn", password_hash="x",
             full_name="U", role=Role.ceo, is_root=True)
    db_session.add(u)
    await db_session.flush()

    conv = Conversation(workspace_id=ws.id, user_id=u.id)
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    assert conv.title_locked is False
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `pytest tests/test_chat_models.py::test_conversation_title_locked_defaults_false -v`
Expected: FAIL — `AttributeError: 'Conversation' object has no attribute 'title_locked'`

- [ ] **Step 3: Thêm cột vào model**

Trong `backend/app/models.py`, sửa `class Conversation` (dòng 362-379), thêm ngay sau dòng
`title: Mapped[str | None] = mapped_column(String(255), nullable=True)`:

```python
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Cron tự đặt tên (worker.py::retitle_conversations) chạy sau khi AI trả lời xong
    # tin đầu — True nghĩa là tiêu đề đã chốt (do cron HOẶC người dùng tự đổi tên tay),
    # cron không được ghi đè nữa.
    title_locked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
```

(`Boolean` đã có sẵn trong import ở đầu file — cột `queue_held` cùng class đã dùng.)

- [ ] **Step 4: Sinh migration**

Run (trong `backend/`, venv active, `docker compose up -d postgres redis` đã chạy):
```bash
alembic revision --autogenerate -m "conversation_title_locked"
```
Mở file mới sinh ra trong `alembic/versions/`, xác nhận `down_revision = 'fd293dc8427b'` (head hiện
tại). Sửa nội dung `upgrade()`/`downgrade()` cho khớp chính xác:

```python
def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('conversations',
                  sa.Column('title_locked', sa.Boolean(), nullable=False,
                            server_default=sa.text('false')))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('conversations', 'title_locked')
```

- [ ] **Step 5: Áp migration + chạy test, xác nhận PASS**

Run: `alembic upgrade head`
Run: `pytest tests/test_chat_models.py::test_conversation_title_locked_defaults_false -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/*_conversation_title_locked.py backend/tests/test_chat_models.py
git commit -m "feat(db): thêm cột Conversation.title_locked cho tính năng tự đặt tên"
```

---

### Task 2: Service sinh tiêu đề (`conversation_title_service.py`)

**Files:**
- Create: `backend/app/services/conversation_title_service.py`
- Test: `backend/tests/test_conversation_title_service.py`

**Interfaces:**
- Consumes: `Conversation.title_locked` (Task 1), `app.agent.llm_client.LLMClient`/`TextDelta`.
- Produces: `async def retitle_pending_conversations(db: AsyncSession, llm: LLMClient, *, batch_size: int = 10) -> int`
  — Task 3 (cron wiring) gọi hàm này.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/test_conversation_title_service.py`:

```python
import uuid

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.models import Conversation, Message, MessageRole
from app.services.conversation_title_service import retitle_pending_conversations


def _fake_title_llm(text="Giao task quy 3 cho Nam"):
    return FakeLLMClient(turns=[[TextDelta(text=text),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)]])


async def _mk_conv_with_reply(db, *, title_locked=False,
                              title="tin nhan dau tien cat 60 ky tu"):
    conv = Conversation(workspace_id=uuid.uuid4(), user_id=uuid.uuid4(),
                        title=title, title_locked=title_locked)
    db.add(conv)
    await db.flush()
    db.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                   role=MessageRole.user, content=[{"type": "text", "text": "giao task cho Nam"}]))
    db.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                   role=MessageRole.assistant, content=[{"type": "text", "text": "Da tao task"}]))
    await db.commit()
    return conv


async def test_retitle_sets_title_and_locks(db_session):
    conv = await _mk_conv_with_reply(db_session)
    llm = _fake_title_llm("Giao task quy 3 cho Nam")

    processed = await retitle_pending_conversations(db_session, llm)

    assert processed == 1
    await db_session.refresh(conv)
    assert conv.title == "Giao task quy 3 cho Nam"
    assert conv.title_locked is True
    assert len(llm.calls) == 1


async def test_retitle_bo_qua_conversation_da_locked(db_session):
    conv = await _mk_conv_with_reply(db_session, title_locked=True)
    llm = _fake_title_llm()

    processed = await retitle_pending_conversations(db_session, llm)

    assert processed == 0
    assert len(llm.calls) == 0
    await db_session.refresh(conv)
    assert conv.title == "tin nhan dau tien cat 60 ky tu"


async def test_retitle_bo_qua_conversation_chua_co_ai_tra_loi(db_session):
    conv = Conversation(workspace_id=uuid.uuid4(), user_id=uuid.uuid4(), title="cho AI tra loi")
    db_session.add(conv)
    await db_session.flush()
    db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                           role=MessageRole.user, content=[{"type": "text", "text": "hoi gi do"}]))
    await db_session.commit()
    llm = _fake_title_llm()

    processed = await retitle_pending_conversations(db_session, llm)

    assert processed == 0
    await db_session.refresh(conv)
    assert conv.title == "cho AI tra loi"


async def test_retitle_gioi_han_batch_size(db_session):
    for _ in range(3):
        await _mk_conv_with_reply(db_session)
    llm = FakeLLMClient(turns=[
        [TextDelta(text=f"Tieu de {i}"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)]
        for i in range(2)
    ])

    processed = await retitle_pending_conversations(db_session, llm, batch_size=2)

    assert processed == 2


async def test_retitle_loi_llm_khong_lock_thu_lai_luot_sau(db_session, monkeypatch):
    conv = await _mk_conv_with_reply(db_session)

    class _BoomLLM:
        model = "fake"
        calls: list = []

        async def stream(self, *, system, messages, tools):
            raise RuntimeError("gateway loi")
            yield  # pragma: no cover - làm hàm thành async generator hợp lệ

    processed = await retitle_pending_conversations(db_session, _BoomLLM())

    assert processed == 0
    await db_session.refresh(conv)
    assert conv.title_locked is False
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `pytest tests/test_conversation_title_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.conversation_title_service'`

- [ ] **Step 3: Viết implementation**

Tạo `backend/app/services/conversation_title_service.py`:

```python
"""Tự đặt tên cuộc trò chuyện bằng AI (model_fast), sau khi AI trả lời xong tin đầu.

Chạy từ cron (app/agent/worker.py::retitle_conversations, mỗi phút). Quét tối đa
`batch_size` cuộc/lượt để tránh dồn cục chi phí LLM ngay sau khi deploy — sweep toàn
bộ lịch sử cũ trải dần qua nhiều lượt cron (spec 2026-07-27 §2.4).
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_client import LLMClient, TextDelta
from app.models import Conversation, Message, MessageRole

logger = logging.getLogger(__name__)

_TITLE_SYSTEM = (
    "Đặt 1 tiêu đề NGẮN GỌN (tối đa 6 từ, tiếng Việt, không bọc trong dấu ngoặc kép, "
    "không có dấu chấm cuối câu) tóm tắt đúng chủ đề chính của đoạn hội thoại dưới "
    "đây, để hiển thị trong danh sách cuộc trò chuyện. Chỉ trả về đúng tiêu đề, "
    "không thêm lời dẫn hay giải thích."
)


def _render_for_title(msgs: list[Message]) -> str:
    lines: list[str] = []
    for m in msgs:
        who = "Người dùng" if m.role == MessageRole.user else "Trợ lý"
        texts = [b.get("text", "") for b in m.content if b.get("type") == "text"]
        if texts:
            lines.append(f"{who}: {' '.join(t for t in texts if t)}")
    return "\n".join(lines)


async def _generate_title(llm: LLMClient, transcript: str) -> str:
    parts: list[str] = []
    async for event in llm.stream(
        system=_TITLE_SYSTEM,
        messages=[{"role": "user", "content": [{"type": "text", "text": transcript}]}],
        tools=[]):
        if isinstance(event, TextDelta):
            parts.append(event.text)
    return "".join(parts).strip().strip('"').strip("'")[:60]


async def retitle_pending_conversations(db: AsyncSession, llm: LLMClient, *,
                                        batch_size: int = 10) -> int:
    """Sinh tiêu đề cho tối đa `batch_size` conversation có AI trả lời nhưng chưa
    `title_locked`. Trả về số conversation đã xử lý thành công. Lỗi gọi LLM cho 1
    conversation không chặn các conversation khác trong cùng lượt (best-effort —
    conversation lỗi vẫn giữ `title_locked=False`, cron lượt sau tự thử lại)."""
    id_stmt = (
        select(Conversation.id)
        .join(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.title_locked.is_(False), Message.role == MessageRole.assistant)
        .distinct()
        .limit(batch_size)
    )
    conv_ids = (await db.execute(id_stmt)).scalars().all()
    if not conv_ids:
        return 0
    conversations = (await db.execute(
        select(Conversation).where(Conversation.id.in_(conv_ids)))).scalars().all()

    processed = 0
    for conv in conversations:
        msgs = (await db.execute(
            select(Message).where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.asc()).limit(4))).scalars().all()
        transcript = _render_for_title(msgs)
        if not transcript:
            continue
        try:
            title = await _generate_title(llm, transcript)
        except Exception:
            logger.warning("retitle_pending_conversations: lỗi gọi LLM cho conversation %s, "
                           "bỏ qua lượt này", conv.id)
            continue
        if not title:
            continue
        conv.title = title
        conv.title_locked = True
        processed += 1
    await db.commit()
    return processed
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `pytest tests/test_conversation_title_service.py -v`
Expected: PASS (5 test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/conversation_title_service.py backend/tests/test_conversation_title_service.py
git commit -m "feat(chat): service sinh tiêu đề cuộc trò chuyện bằng model_fast"
```

---

### Task 3: Wire cron `retitle_conversations` vào worker

**Files:**
- Modify: `backend/app/agent/worker.py:18-24` (import), `:287-292` (thêm hàm mới sau
  `distill_workspace_memories`), `:331-335` (`WorkerSettings.cron_jobs`)
- Test: `backend/tests/test_worker.py`

**Interfaces:**
- Consumes: `conversation_title_service.retitle_pending_conversations` (Task 2).
- Produces: `async def retitle_conversations(ctx: dict) -> None`, đăng ký cron tên
  `"cron:retitle_conversations"`.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/test_worker.py`:

```python
def test_worker_settings_registers_retitle_conversations_cron():
    from app.agent.worker import retitle_conversations

    names = [j.name for j in WorkerSettings.cron_jobs]
    assert "cron:retitle_conversations" in names
    job = next(j for j in WorkerSettings.cron_jobs if j.name == "cron:retitle_conversations")
    assert job.coroutine is retitle_conversations


@pytest.mark.asyncio
async def test_retitle_conversations_calls_service(engine, monkeypatch):
    from app.agent import worker as worker_module

    called = {}

    async def fake_retitle(db, llm, **kwargs):
        called["db"] = db
        called["llm"] = llm
        return 0

    monkeypatch.setattr(worker_module.conversation_title_service,
                        "retitle_pending_conversations", fake_retitle)
    ctx = {"session_factory": async_sessionmaker(engine, expire_on_commit=False),
          "llm_client": "fake-llm-marker"}

    await worker_module.retitle_conversations(ctx)

    assert called["llm"] == "fake-llm-marker"
```

(`WorkerSettings`, `async_sessionmaker`, `pytest` đã import sẵn ở đầu `test_worker.py`.)

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `pytest tests/test_worker.py -k retitle -v`
Expected: FAIL — `ImportError: cannot import name 'retitle_conversations'`

- [ ] **Step 3: Viết implementation**

Trong `backend/app/agent/worker.py`, sửa khối import dòng 21-24 — thêm
`conversation_title_service` (giữ thứ tự alphabet):

```python
from app.services import (
    conversation_title_service, directive_service, distiller_service, embedding_service,
    example_bank_service, report_schedule_service, voice_service, watcher_service, work_service,
)
```

Thêm hàm mới ngay sau `distill_workspace_memories` (sau dòng 291, trước
`async def transcribe_voice_note`):

```python
async def retitle_conversations(ctx: dict) -> None:
    """arq cron (mỗi phút): tự đặt tên tối đa 10 cuộc trò chuyện/lượt bằng model_fast,
    cho các cuộc đã có AI trả lời nhưng title_locked=False (spec 2026-07-27 §2)."""
    async with ctx["session_factory"]() as db:
        await conversation_title_service.retitle_pending_conversations(db, ctx["llm_client"])
```

Sửa `WorkerSettings.cron_jobs` (dòng 331-335), thêm `retitle_conversations`:

```python
    cron_jobs = [cron(check_report_schedules, second=0), cron(check_task_deadlines, second=0),
                cron(check_directive_escalations, second=0), cron(send_morning_briefs, second=0),
                cron(distill_workspace_memories, second=0), cron(retitle_conversations, second=0),
                # second=30: lệch pha với cụm cron second=0 cho đỡ dồn việc đầu phút
                cron(rescue_stuck_requests, second=30)]
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `pytest tests/test_worker.py -k retitle -v`
Expected: PASS (2 test)

Run toàn bộ suite worker để chắc không phá cron khác:
Run: `pytest tests/test_worker.py -v`
Expected: PASS toàn bộ

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/worker.py backend/tests/test_worker.py
git commit -m "feat(worker): đăng ký cron retitle_conversations mỗi phút"
```

---

### Task 4: Khoá tiêu đề khi người dùng tự đổi tên tay

**Files:**
- Modify: `backend/app/api/chat.py:121-128` (`rename_conversation`)
- Test: `backend/tests/test_chat_api.py`

**Interfaces:**
- Consumes: `Conversation.title_locked` (Task 1).

- [ ] **Step 1: Viết test thất bại**

Thêm vào đầu `backend/tests/test_chat_api.py`, bổ sung import:

```python
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.chat import get_arq_pool
from app.db import get_db
from app.main import create_app
from app.models import Conversation
from tests.conftest import _ceo_headers, _invite_and_join
```

Thêm test mới ngay sau `test_rename_own_conversation`:

```python
@pytest.mark.asyncio
async def test_rename_locks_title_against_auto_retitle(chat_client, engine):
    client, _ = chat_client
    ceo_h = await _ceo_headers(client)
    conv = (await client.post("/api/v1/conversations", headers=ceo_h, json={})).json()

    resp = await client.patch(f"/api/v1/conversations/{conv['id']}", headers=ceo_h,
                              json={"title": "Ke hoach Q3"})
    assert resp.status_code == 200, resp.text

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        row = await db.get(Conversation, uuid.UUID(conv["id"]))
        assert row.title_locked is True
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `pytest tests/test_chat_api.py::test_rename_locks_title_against_auto_retitle -v`
Expected: FAIL — `AssertionError: assert False is True`

- [ ] **Step 3: Viết implementation**

Sửa `rename_conversation` trong `backend/app/api/chat.py:121-128`:

```python
@router.patch("/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(conversation_id: uuid.UUID, body: ConversationRenameIn,
                              actor: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    conv = await _get_owned_conversation_or_404(db, actor, conversation_id)
    conv.title = body.title
    conv.title_locked = True
    await db.commit()
    return conv
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `pytest tests/test_chat_api.py -v`
Expected: PASS toàn bộ (bao gồm test mới + các test rename/send_message cũ không bị ảnh hưởng)

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/chat.py backend/tests/test_chat_api.py
git commit -m "fix(chat): khoá title_locked khi người dùng tự đổi tên cuộc trò chuyện"
```

---

### Task 5: Tool `suggest_replies`

**Files:**
- Modify: `backend/app/agent/tools.py:964-966` (thêm ngay sau block `resolve_person`),
  `:1033-1036` (`TOOL_GROUPS["core"]`)
- Test: `backend/tests/test_agent_tools_suggest_replies.py`

**Interfaces:**
- Produces: tool `"suggest_replies"` trong `TOOLS`, input model `SuggestRepliesToolIn`,
  handler `_suggest_replies`. Task 6 (loop.py) và Task 7 (FE) dùng đúng tên tool này và tên field
  `options`.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/test_agent_tools_suggest_replies.py`:

```python
from app.agent.tools import SENSITIVE_TOOLS, TOOL_GROUPS, TOOLS, call_tool


async def test_suggest_replies_registered_not_sensitive():
    assert "suggest_replies" in TOOLS
    assert "suggest_replies" not in SENSITIVE_TOOLS
    assert "suggest_replies" in TOOL_GROUPS["core"]


async def test_call_tool_suggest_replies_returns_shown_true(db_session):
    result = await call_tool(db_session, None, "suggest_replies",
                             {"options": ["Co, tao task moi", "Khong"]})
    assert result == {"shown": True}


async def test_suggest_replies_input_requires_between_2_and_5_options():
    from pydantic import ValidationError

    from app.agent.tools import SuggestRepliesToolIn

    with pytest.raises(ValidationError):
        SuggestRepliesToolIn(options=["chi 1"])
    with pytest.raises(ValidationError):
        SuggestRepliesToolIn(options=[f"lua chon {i}" for i in range(6)])
    SuggestRepliesToolIn(options=["a", "b"])  # 2 phần tử — hợp lệ, không raise
```

Thêm `import pytest` ở đầu file test (cho `pytest.raises`).

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `pytest tests/test_agent_tools_suggest_replies.py -v`
Expected: FAIL — `AssertionError: assert 'suggest_replies' in TOOLS` (rỗng)

- [ ] **Step 3: Viết implementation**

Trong `backend/app/agent/tools.py`, thêm ngay sau block `resolve_person` (sau dòng 964, trước
`class ResolveTaskToolIn` ở dòng 967):

```python
class SuggestRepliesToolIn(BaseModel):
    options: list[str] = Field(min_length=2, max_length=5)


async def _suggest_replies(db, actor, body: SuggestRepliesToolIn) -> dict:
    return {"shown": True}


_register("suggest_replies",
          "Gọi tool này NGAY SAU KHI đã viết câu hỏi cho người dùng trong phần text, nếu câu "
          "hỏi có một tập lựa chọn ngắn, rời rạc, rõ ràng (vd: chọn giữa 2 người trùng tên, "
          "xác nhận có/không, chọn 1 trong vài mốc thời gian). Mỗi phần tử trong `options` "
          "PHẢI là nguyên văn câu trả lời ngắn gọn mà người dùng sẽ gửi nếu chọn (vd: "
          "'Nam Nguyễn', 'Có, tạo task mới'), KHÔNG phải nhãn mô tả. Tối đa 5 lựa chọn. "
          "KHÔNG gọi tool này nếu câu hỏi mở, cần câu trả lời tự do không có sẵn đáp án ngắn.",
          SuggestRepliesToolIn, _suggest_replies)
```

Sửa `TOOL_GROUPS["core"]` (dòng 1033-1036), thêm `"suggest_replies"`:

```python
    "core": frozenset({
        "get_task", "search", "semantic_search", "resolve_person", "resolve_task",
        "propose_actions", "suggest_replies",
    }),
```

- [ ] **Step 4: Cập nhật test đếm số lượng tool đã có**

`backend/tests/test_agent_tools_propose_actions.py` dòng 9 hard-code `len(TOOLS) == 62`. Sửa:

```python
    assert len(TOOLS) == 63  # +suggest_replies (2026-07-27, thẻ bấm chọn)
```

- [ ] **Step 5: Chạy test, xác nhận PASS**

Run: `pytest tests/test_agent_tools_suggest_replies.py tests/test_agent_tools_propose_actions.py -v`
Expected: PASS toàn bộ

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/tools.py backend/tests/test_agent_tools_suggest_replies.py backend/tests/test_agent_tools_propose_actions.py
git commit -m "feat(agent): thêm tool suggest_replies cho thẻ bấm chọn nhanh"
```

---

### Task 6: Agent loop kết thúc lượt ngay khi gặp `suggest_replies`

**Files:**
- Modify: `backend/app/agent/loop.py:483-499` (chèn nhánh mới giữa `first_gate` và vòng lặp
  tool thường)
- Test: `backend/tests/test_agent_loop_suggest_replies.py`

**Interfaces:**
- Consumes: tool `"suggest_replies"` (Task 5).

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/test_agent_loop_suggest_replies.py`:

```python
import pytest
from sqlalchemy import select

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta, ToolUseBlock
from app.agent.loop import run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import ChatRequest, Conversation, Message, MessageRole, Role, User, Workspace


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db.add(conv)
    await db.flush()
    await db.commit()
    return ws, ceo, conv


def _make_request(ws, conv, ceo, content="giao viec cho Nam"):
    return ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                       content=content, queue_position=1.0)


@pytest.mark.asyncio
async def test_suggest_replies_ends_turn_without_second_llm_call(db_session):
    ws, ceo, conv = await _world(db_session)
    req = _make_request(ws, conv, ceo)
    db_session.add(req)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    options = ["Nam Nguyen", "Nam Tran"]
    llm = FakeLLMClient(turns=[
        [TextDelta(text="Anh muon giao cho Nam nao?"),
         StreamDone(tool_uses=[ToolUseBlock(id="t1", name="suggest_replies",
                                            input={"options": options})],
                    stop_reason="tool_use", input_tokens=10, output_tokens=5)],
    ])
    pub = FakeEventPublisher()

    await run_agent_loop(db_session, req, llm, pub)

    assert req.status.value == "done"
    assert len(llm.calls) == 1  # KHÔNG gọi LLM lần 2 sau suggest_replies
    event = next(e for _, e in pub.events if e["type"] == "request_done")
    assert event["chat_request_id"] == str(req.id)

    msgs = (await db_session.execute(
        select(Message).where(Message.conversation_id == conv.id)
        .order_by(Message.created_at))).scalars().all()
    tool_result_msg = next(m for m in msgs if m.role == MessageRole.user
                           and m.content and m.content[0].get("type") == "tool_result")
    assert tool_result_msg.content[0]["tool_use_id"] == "t1"
    assistant_msg = next(m for m in msgs if m.role == MessageRole.assistant)
    tool_use_block = next(b for b in assistant_msg.content if b.get("type") == "tool_use")
    assert tool_use_block["name"] == "suggest_replies"
    assert tool_use_block["input"]["options"] == options
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `pytest tests/test_agent_loop_suggest_replies.py -v`
Expected: FAIL — `req.status.value` thực tế không phải `"done"` (loop chạy tiếp gọi LLM lần 2, rồi
`FakeLLMClient` hết turns → `IndexError: pop from empty list`)

- [ ] **Step 3: Viết implementation**

Trong `backend/app/agent/loop.py`, chèn nhánh mới giữa dòng 497 (`return` của nhánh `first_gate`) và
dòng 499 (`tool_results = []`):

```python
            reply_gate = next((tu for tu in done.tool_uses if tu.name == "suggest_replies"), None)
            if reply_gate is not None:
                # Không sensitive/propose_actions nên không khớp first_gate ở trên — nhưng
                # vẫn phải kết thúc lượt ngay (không gọi LLM thêm 1 vòng), vì suggest_replies
                # LÀ cách model báo "đã hỏi xong, đang chờ người dùng chọn". Vẫn phải sinh
                # tool_result cho tool_use này (hợp đồng API Anthropic: mọi tool_use phải có
                # tool_result ở lượt kế tiếp, thiếu sẽ lỗi 400 ở lần gọi sau).
                db.add(Message(workspace_id=req.workspace_id, conversation_id=req.conversation_id,
                               chat_request_id=req.id, role=MessageRole.user,
                               content=[{"type": "tool_result", "tool_use_id": reply_gate.id,
                                        "content": json.dumps({"shown": True})}]))
                req.status = ChatRequestStatus.done
                req.finished_at = datetime.now(timezone.utc)
                req.result_summary = "".join(text_parts)[:500]
                await db.commit()
                if text_parts and assistant_msg is not None:
                    await embedding_service.index_content(
                        db, req.workspace_id, "chat_message", assistant_msg.id,
                        "".join(text_parts))
                await publisher.publish(req.conversation_id,
                                        {"type": "request_done", "chat_request_id": str(req.id),
                                         "result_summary": req.result_summary})
                await _write_trace(done.stop_reason)
                return

            tool_results = []
```

(`json`, `datetime`, `timezone`, `embedding_service`, `MessageRole`, `Message`, `ChatRequestStatus`
đều đã import sẵn ở đầu `loop.py` — dùng lại nguyên như nhánh kết thúc lượt bình thường ở dòng
434-449.)

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `pytest tests/test_agent_loop_suggest_replies.py -v`
Expected: PASS

Chạy lại toàn bộ test loop để chắc không phá nhánh `first_gate`/`propose_actions` cũ:
Run: `pytest tests/test_agent_loop_propose_actions.py tests/test_agent_loop_confirmation.py tests/test_agent_loop_basic.py -v`
Expected: PASS toàn bộ

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/loop.py backend/tests/test_agent_loop_suggest_replies.py
git commit -m "feat(agent): agent loop kết thúc lượt ngay khi model gọi suggest_replies"
```

---

### Task 7: Frontend — hiện thẻ bấm chọn từ `suggest_replies`

**Files:**
- Modify: `frontend/app/main/chat.tsx:43-47` (`Row` type), `:145-165` (`messagesToRows`),
  `:575-638` (`renderRow`)

**Interfaces:**
- Consumes: tool_use block `{ type: "tool_use", name: "suggest_replies", input: { options: string[] } }`
  (Task 5/6 — đây là format do backend sinh, KHÔNG đổi được từ FE).

Không có test tự động (frontend repo này chưa có test suite/Jest — xác nhận qua
`package.json`/không có config Jest). Verify bằng chạy Expo Go thủ công ở Step 4.

- [ ] **Step 1: Sửa `Row` type**

Trong `frontend/app/main/chat.tsx`, sửa khối `type Row` (dòng 43-47):

```ts
type Row =
  | { key: string; kind: "user" | "assistant"; text: string; voiceNoteId?: string | null; isSeed?: boolean }
  | { key: string; kind: "streaming"; text: string }
  | { key: string; kind: "system"; text: string }
  | { key: string; kind: "choices"; options: string[] }
  | { key: string; kind: "failed"; text: string; retryContent: string | null };
```

- [ ] **Step 2: Sửa `messagesToRows`**

Sửa vòng lặp tool_use trong `messagesToRows` (dòng 159-162):

```ts
    for (const b of m.content) {
      if (b.type === "tool_use") {
        if (b.name === "suggest_replies") {
          const options = (b.input as { options?: unknown })?.options;
          if (Array.isArray(options) && options.length > 0)
            out.push({ key: `${m.id}-${b.id}`, kind: "choices", options: options as string[] });
        } else {
          out.push({ key: `${m.id}-${b.id}`, kind: "system", text: labelForTool(b.name) });
        }
      }
    }
```

- [ ] **Step 3: Sửa `renderRow`**

Trong `renderRow`, chèn nhánh mới ngay sau khối xử lý `item.kind === "user"` kết thúc (sau dòng 618
`}`) và trước dòng 619 (`// system (tool-use) hoặc failed...`):

```tsx
    if (item.kind === "choices") {
      return (
        <View style={styles.onboardingChipsRow}>
          {item.options.map((opt, i) => (
            <TouchableOpacity
              key={`${item.key}-${i}`}
              style={styles.onboardingChip}
              onPress={() => submit(opt)}
            >
              <Text style={styles.onboardingChipText}>{opt}</Text>
            </TouchableOpacity>
          ))}
        </View>
      );
    }
```

(Tái dùng nguyên `styles.onboardingChipsRow`/`onboardingChip`/`onboardingChipText` đã có sẵn — dòng
930-938 — không thêm style mới. `submit` là hàm đã có ở dòng 435, gửi ngay nguyên văn `opt` làm tin
nhắn mới, giống hệt cách `ONBOARDING_CHIPS` dùng.)

- [ ] **Step 4: Verify thủ công qua Expo Go**

Run (trong `frontend/`): `npx expo start --max-workers 2`

Kết nối điện thoại qua Expo Go (cùng LAN, nhập `exp://<LAN-IP>:8081`). Vì backend cần model thật gọi
`suggest_replies` để tự nhiên xuất hiện thẻ (không mock được từ FE), cách nhanh nhất để verify UI:
tạm thời gọi thẳng API tạo 1 message có sẵn tool_use `suggest_replies` trong content qua
`POST /api/v1/conversations/{id}/messages` là KHÔNG khả thi (endpoint chỉ nhận tin người dùng) — thay
vào đó verify bằng cách nhắn 1 câu chắc chắn kích hoạt disambiguation (vd tên trùng nhiều người trong
danh bạ công ty test) và quan sát: (a) chỉ báo card thẻ xuất hiện đúng bên dưới câu hỏi của AI thay vì
dòng "Đã dùng suggest_replies", (b) bấm thẻ gửi đúng nguyên văn lựa chọn làm tin nhắn mới. Nếu môi
trường test chưa có dữ liệu trùng tên sẵn, kiểm tra tối thiểu: ứng dụng không crash khi nhận
message có `tool_use` bất kỳ (regression check cho `messagesToRows`/`renderRow`).

- [ ] **Step 5: Commit**

```bash
git add frontend/app/main/chat.tsx
git commit -m "feat(fe): hiện thẻ bấm chọn nhanh khi AI gọi suggest_replies"
```

---

## Self-review (đã chạy khi viết plan)

- **Spec coverage**: §2 (auto-title) → Task 1-4. §3 (suggest_replies) → Task 5-7. §4 (rủi ro) không
  cần task riêng (đã note trong docstring/comment). §5 (ngoài phạm vi) không tạo task.
- **Placeholder scan**: không còn TBD/TODO; migration revision id để trống có chủ đích (giá trị do
  `alembic revision --autogenerate` sinh ra lúc chạy, không phải placeholder mơ hồ) — `down_revision`
  đã cho giá trị cố định `'fd293dc8427b'`.
- **Type/tên nhất quán**: `retitle_pending_conversations(db, llm, *, batch_size=10)` (Task 2) khớp
  đúng cách gọi ở Task 3 (`ctx["llm_client"]`, không truyền batch_size → dùng default). Tên tool
  `"suggest_replies"` và field `options` nhất quán xuyên Task 5 (backend đăng ký) → Task 6 (loop.py
  check `tu.name == "suggest_replies"`) → Task 7 (FE check `b.name === "suggest_replies"`,
  `b.input.options`).
