# Phase 0 — Tracing + Eval Harness + Incremental Caching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nền móng đo lường cho toàn bộ chuỗi nâng cấp AI: trace mọi lần chạy agent, eval harness chấm hành vi với model thật, incremental prompt caching, và config model theo tầng (fast/smart).

**Architecture:** Thêm bảng `agent_traces` ghi 1 dòng mỗi lần `run_agent_loop` chạy (iterations, tools + latency, stop_reason, model, route) + endpoint debug chỉ CEO. Eval harness là package `backend/evals/` độc lập với pytest CI: scenario YAML + runner gọi API thật + grader thuần (được unit-test trong CI). Caching: thêm `cache_control` vào message cuối của history (system + tools đã cache sẵn từ trước).

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (như hiện tại), arq worker, anthropic SDK 0.39, pytest + sqlite in-memory cho unit test, PyYAML + httpx cho eval runner.

**Spec gốc:** `docs/superpowers/specs/2026-07-19-ai-intelligence-upgrade.md` §4 (Phase 0).

## Global Constraints

- Mọi bảng mới có `workspace_id` index; mọi query lọc theo workspace (CLAUDE.md).
- Quyền kiểm ở service/route layer (`require_ceo`), không ở prompt/model.
- Danh tính actor từ JWT — không từ tham số client.
- Model LLM lấy từ config theo loại tác vụ — không hardcode model ID trong logic.
- Route dưới `/api/v1`. Đổi API contract → chạy `python scripts/export_openapi.py`.
- TDD: test trước, code sau; mỗi task một commit.
- KHÔNG dùng PowerShell `Get-Content | Set-Content` sửa file UTF-8 tiếng Việt — dùng tool Edit/Write.
- Lệnh chạy trong `backend/`, venv Windows: `.venv\Scripts\activate`; test: `pytest tests/ -v`.
- Alembic head hiện tại: `b9e8d7c6f5a4` (chat_voice_attachment) — migration mới nối vào đây.
- Ghi chú môi trường: `alembic` ưu tiên env `DATABASE_URL`; Postgres dev ở host port 5435, redis 6380.

---

### Task 1: Model routing config — `model_fast` / `model_smart`, alias `model_chat`

Spec §4.3: "Thêm model_fast/model_smart vào Settings; loop nhận model qua tham số."
Cách "loop nhận model": `LLMClient` mang thuộc tính public `model`; `UsageLog` ghi
`llm.model` (model thực dùng) thay vì đọc config; `get_llm_client(model=...)` tạo
client theo model bất kỳ (đường sâu Phase 4 sẽ gọi `get_llm_client(settings.model_smart)`).

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/agent/llm_client.py`
- Modify: `backend/app/agent/loop.py` (dòng 203 — UsageLog)
- Modify: `backend/tests/test_chat_config.py`
- Test: `backend/tests/test_model_routing.py` (mới)

**Interfaces:**
- Consumes: `Settings` (pydantic-settings), `AnthropicLLMClient`, `FakeLLMClient`, `run_agent_loop`.
- Produces: `Settings.model_fast: str` (default `"claude-haiku-4-5"`, đọc được cả env `MODEL_CHAT` cũ), `Settings.model_smart: str` (default `"claude-sonnet-4-6"`), `LLMClient.model: str` (public attr — `FakeLLMClient` default `"fake"`), `get_llm_client(model: str | None = None) -> LLMClient`. Task 4 dùng `llm.model` để ghi trace.

- [ ] **Step 1: Viết failing tests**

Tạo `backend/tests/test_model_routing.py`:

```python
"""Phase 0 (spec AI upgrade 4.3): config model theo tầng fast/smart."""
import pytest

from app.agent.llm_client import AnthropicLLMClient, FakeLLMClient
from app.config import Settings


def test_model_fast_smart_mac_dinh():
    s = Settings(_env_file=None)
    assert s.model_fast == "claude-haiku-4-5"
    assert s.model_smart == "claude-sonnet-4-6"


def test_env_model_chat_cu_van_doc_vao_model_fast(monkeypatch):
    # .env prod đang set MODEL_CHAT (có prefix gateway) — đổi tên field không được phá nó.
    monkeypatch.setenv("MODEL_CHAT", "anthropic/claude-haiku-4-5")
    s = Settings(_env_file=None)
    assert s.model_fast == "anthropic/claude-haiku-4-5"


def test_env_model_fast_moi_cung_doc_duoc(monkeypatch):
    monkeypatch.setenv("MODEL_FAST", "claude-haiku-9-9")
    s = Settings(_env_file=None)
    assert s.model_fast == "claude-haiku-9-9"


def test_llm_client_mang_model_public():
    fake = FakeLLMClient(turns=[])
    assert fake.model == "fake"
    fake2 = FakeLLMClient(turns=[], model="test-model")
    assert fake2.model == "test-model"

    class _C:  # client anthropic giả, không dùng tới trong test này
        pass

    real = AnthropicLLMClient(_C(), model="claude-haiku-4-5")
    assert real.model == "claude-haiku-4-5"
```

Sửa `backend/tests/test_chat_config.py`: thay assert `s.model_chat == ...` (dòng 10)
bằng `assert s.model_fast == "claude-haiku-4-5"` (giữ nguyên phần còn lại của file).

- [ ] **Step 2: Chạy test xác nhận fail**

Run: `pytest tests/test_model_routing.py -v`
Expected: FAIL — `Settings` chưa có `model_fast` / `FakeLLMClient` chưa nhận kwarg `model`.

- [ ] **Step 3: Implement**

`backend/app/config.py` — thay dòng `model_chat: str = "claude-haiku-4-5"` bằng:

```python
    # Model theo tầng tác vụ (spec AI upgrade §3/§4.3): fast = chat mặc định;
    # smart = đường sâu async/distiller/report summary (các phase sau).
    # Env MODEL_CHAT (tên cũ, đang dùng ở .env prod) vẫn được đọc vào model_fast.
    model_fast: str = Field("claude-haiku-4-5",
                            validation_alias=AliasChoices("model_fast", "model_chat"))
    model_smart: str = "claude-sonnet-4-6"
```

Đầu file thêm import: `from pydantic import AliasChoices, Field`.
Trong `model_config` thêm `"populate_by_name": True` (để `Settings(model_fast=...)`
và env `MODEL_FAST` vẫn hoạt động khi field có validation_alias):

```python
    model_config = {"env_file": ".env", "populate_by_name": True}
```

`backend/app/agent/llm_client.py`:

1. `LLMClient` thêm attr khai báo mặc định (ngay dưới `class LLMClient(abc.ABC):`):

```python
class LLMClient(abc.ABC):
    model: str = "unknown"
```

2. `FakeLLMClient.__init__` nhận model:

```python
    def __init__(self, turns: list[list[StreamEvent]], model: str = "fake"):
        self._turns = list(turns)
        self.calls: list[dict] = []
        self.model = model
```

3. `AnthropicLLMClient`: đổi `self._model = model` thành `self.model = model`, và chỗ
   `messages.create(model=self._model, ...)` thành `model=self.model`.

4. `get_llm_client` nhận model tùy chọn:

```python
@lru_cache
def get_llm_client(model: str | None = None) -> LLMClient:
    import anthropic

    from app.config import get_settings

    settings = get_settings()
    client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        base_url=settings.anthropic_base_url or None,  # None = api.anthropic.com
    )
    return AnthropicLLMClient(client, model=model or settings.model_fast)
```

`backend/app/agent/loop.py` dòng 203: đổi `model=get_settings().model_chat` thành
`model=llm.model` (import `get_settings` vẫn cần cho chỗ khác? — kiểm tra: sau đổi
này `get_settings` trong loop.py không còn ai dùng → xóa import `from app.config import get_settings`).

- [ ] **Step 4: Chạy test xác nhận pass**

Run: `pytest tests/test_model_routing.py tests/test_chat_config.py tests/test_agent_loop_basic.py tests/test_agent_llm_client.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Chạy full suite (đổi config đụng nhiều nơi)**

Run: `pytest tests/ -q`
Expected: PASS. Nếu test nào khác còn reference `model_chat` → sửa sang `model_fast`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/app/agent/llm_client.py backend/app/agent/loop.py backend/tests/test_model_routing.py backend/tests/test_chat_config.py
git commit -m "feat(be): model routing config fast/smart, UsageLog ghi model thuc dung (Phase 0)"
```

---

### Task 2: Incremental prompt caching trên message cuối history

Spec §4.3: system + tools đã có `cache_control`; thêm breakpoint thứ 3 vào block
cuối của message cuối → mỗi vòng loop sau đọc lại history cũ từ cache thay vì trả
full input. (Anthropic cho tối đa 4 breakpoints; ta dùng 3.)

**Files:**
- Modify: `backend/app/agent/llm_client.py` (trong `AnthropicLLMClient.stream`)
- Test: `backend/tests/test_llm_client_cache.py` (thêm test)

**Interfaces:**
- Consumes: `AnthropicLLMClient.stream(system, messages, tools)` — messages là list `{"role": str, "content": list[dict]}` từ `_load_history`.
- Produces: payload gửi API có `cache_control` ở block cuối của message cuối; KHÔNG mutate input `messages` (list content là JSON ORM của `Message` — mutate sẽ dirty session).

- [ ] **Step 1: Viết failing test**

Thêm vào cuối `backend/tests/test_llm_client_cache.py`:

```python
async def test_incremental_cache_tren_message_cuoi():
    """Phase 0 (spec 4.3): breakpoint cache thứ 3 đặt ở block cuối của message cuối."""
    fake = _FakeClient()
    llm = AnthropicLLMClient(fake, model="m")
    msgs = [
        {"role": "user", "content": [{"type": "text", "text": "cau 1"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "tra loi"},
                                          {"type": "tool_use", "id": "t1",
                                           "name": "list_tasks", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1",
                                      "content": "{}"}]},
    ]
    async for _ in llm.stream(system="sys", messages=msgs, tools=[]):
        pass
    sent = fake.messages.kwargs["messages"]
    assert sent[-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    # message trước đó không bị gắn
    assert "cache_control" not in sent[0]["content"][0]
    assert "cache_control" not in sent[1]["content"][-1]
    # KHÔNG mutate input gốc (content là JSON của ORM Message)
    assert "cache_control" not in msgs[-1]["content"][-1]


async def test_khong_co_message_van_chay():
    fake = _FakeClient()
    llm = AnthropicLLMClient(fake, model="m")
    async for _ in llm.stream(system="sys", messages=[], tools=[]):
        pass
    assert fake.messages.kwargs["messages"] == []
```

- [ ] **Step 2: Chạy test xác nhận fail**

Run: `pytest tests/test_llm_client_cache.py -v`
Expected: 2 test mới FAIL (chưa có cache_control ở message).

- [ ] **Step 3: Implement**

Trong `AnthropicLLMClient.stream`, ngay sau đoạn dựng `tools_payload` và trước
`await self._client.messages.create(...)`, thêm:

```python
        # Incremental caching (Phase 0, spec 4.3): breakpoint thứ 3 ở block cuối
        # của message cuối — các vòng tool sau đọc lại toàn bộ history từ cache.
        # Copy shallow từng lớp thay vì mutate: content là JSON column của ORM
        # Message, mutate tại đây sẽ làm dirty session của agent loop.
        messages_payload = list(messages)
        if messages_payload:
            last = messages_payload[-1]
            content = last.get("content")
            if isinstance(content, list) and content:
                messages_payload[-1] = {**last, "content": content[:-1] + [
                    {**content[-1], "cache_control": {"type": "ephemeral"}}]}
```

và đổi `messages=messages` trong lời gọi `messages.create(...)` thành
`messages=messages_payload`.

- [ ] **Step 4: Chạy test xác nhận pass**

Run: `pytest tests/test_llm_client_cache.py tests/test_agent_llm_client.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/llm_client.py backend/tests/test_llm_client_cache.py
git commit -m "feat(be): incremental prompt caching tren message cuoi history (Phase 0)"
```

---

### Task 3: Model `AgentTrace` + migration

Spec §4.1. Một dòng trace = MỘT lần chạy `run_agent_loop` (1 request có thể chạy
nhiều lần: sau confirm sensitive tool nó quay lại queued và chạy tiếp → nhiều dòng).

**Files:**
- Modify: `backend/app/models.py` (thêm class cuối file, sau `UsageLog`)
- Create: `backend/alembic/versions/a7c1e5d90b23_agent_traces.py`
- Test: `backend/tests/test_agent_trace_model.py`

**Interfaces:**
- Consumes: `Base`, helpers `_uuid`, `_now` trong models.py.
- Produces: model `AgentTrace` với các cột: `id, workspace_id, chat_request_id, route: str (default "fast"), model: str, iterations: int, stop_reason: str, tools_called: list (JSON), total_latency_ms: int, created_at`. Task 4 ghi, Task 5 đọc.

- [ ] **Step 1: Viết failing test**

Tạo `backend/tests/test_agent_trace_model.py`:

```python
"""Phase 0 (spec AI upgrade 4.1): bảng agent_traces."""
from sqlalchemy import select

from app.models import AgentTrace, ChatRequest, Conversation, Role, User, Workspace


async def test_agent_trace_luu_va_doc_lai(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
               role=Role.ceo)
    db_session.add(ceo)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add(conv)
    await db_session.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="hi", queue_position=1.0)
    db_session.add(req)
    await db_session.flush()

    db_session.add(AgentTrace(
        workspace_id=ws.id, chat_request_id=req.id, model="fake",
        iterations=2, stop_reason="end_turn",
        tools_called=[{"name": "list_tasks", "latency_ms": 5,
                       "input": "{}", "output": "{\"tasks\": []}"}],
        total_latency_ms=123))
    await db_session.commit()

    row = (await db_session.execute(select(AgentTrace).where(
        AgentTrace.chat_request_id == req.id))).scalar_one()
    assert row.route == "fast"
    assert row.model == "fake"
    assert row.iterations == 2
    assert row.tools_called[0]["name"] == "list_tasks"
    assert row.total_latency_ms == 123
    assert row.created_at is not None
```

- [ ] **Step 2: Chạy test xác nhận fail**

Run: `pytest tests/test_agent_trace_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'AgentTrace'`.

- [ ] **Step 3: Thêm model**

Cuối `backend/app/models.py` (sau class `UsageLog`):

```python
class AgentTrace(Base):
    """Trace 1 LẦN CHẠY agent loop của 1 chat_request (Phase 0, spec AI upgrade 4.1).

    1 request có thể có nhiều dòng: sau khi user confirm sensitive tool, request
    quay về queued và loop chạy lần nữa. Debug đọc qua GET /api/v1/admin/traces/…
    """
    __tablename__ = "agent_traces"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    chat_request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_requests.id"),
                                                        index=True)
    route: Mapped[str] = mapped_column(String(16), default="fast")   # fast | deep (Phase 4)
    model: Mapped[str] = mapped_column(String(64), default="")
    iterations: Mapped[int] = mapped_column(Integer, default=0)
    # cancelled | max_iterations | end_turn | max_tokens | awaiting_confirmation | error
    stop_reason: Mapped[str] = mapped_column(String(32), default="")
    # [{name, latency_ms, input, output}] — input/output là JSON string cắt 500 ký tự
    tools_called: Mapped[list] = mapped_column(JSON, default=list)
    total_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
```

- [ ] **Step 4: Chạy test xác nhận pass**

Run: `pytest tests/test_agent_trace_model.py -v`
Expected: PASS.

- [ ] **Step 5: Viết migration**

Tạo `backend/alembic/versions/a7c1e5d90b23_agent_traces.py`:

```python
"""agent_traces — Phase 0 tracing (spec AI upgrade 4.1)

Revision ID: a7c1e5d90b23
Revises: b9e8d7c6f5a4
Create Date: 2026-07-19
"""
import sqlalchemy as sa
from alembic import op

revision = "a7c1e5d90b23"
down_revision = "b9e8d7c6f5a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_traces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("chat_request_id", sa.Uuid(), nullable=False),
        sa.Column("route", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("iterations", sa.Integer(), nullable=False),
        sa.Column("stop_reason", sa.String(length=32), nullable=False),
        sa.Column("tools_called", sa.JSON(), nullable=False),
        sa.Column("total_latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["chat_request_id"], ["chat_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_traces_workspace_id"), "agent_traces",
                    ["workspace_id"])
    op.create_index(op.f("ix_agent_traces_chat_request_id"), "agent_traces",
                    ["chat_request_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_traces_chat_request_id"), table_name="agent_traces")
    op.drop_index(op.f("ix_agent_traces_workspace_id"), table_name="agent_traces")
    op.drop_table("agent_traces")
```

- [ ] **Step 6: Chạy migration trên Postgres dev**

Run (trong `backend/`, docker postgres đang chạy):
```bash
docker compose up -d postgres
alembic upgrade head
```
Expected: `Running upgrade b9e8d7c6f5a4 -> a7c1e5d90b23, agent_traces`.
(Nếu env `DATABASE_URL` đang set trỏ nơi khác — unset trước khi chạy.)

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/a7c1e5d90b23_agent_traces.py backend/tests/test_agent_trace_model.py
git commit -m "feat(be): bang agent_traces + migration (Phase 0 tracing)"
```

---

### Task 4: Ghi trace trong `run_agent_loop` (mọi đường thoát)

**Files:**
- Modify: `backend/app/agent/loop.py`
- Test: `backend/tests/test_agent_trace_loop.py`

**Interfaces:**
- Consumes: `AgentTrace` (Task 3), `llm.model` (Task 1).
- Produces: mỗi lần `run_agent_loop` return đều đã ghi đúng 1 dòng `AgentTrace` với `stop_reason` ∈ {cancelled, max_iterations, end_turn, max_tokens, awaiting_confirmation, error}; helper module-level `_tool_trace_entry(name, tool_input, result, latency_ms) -> dict` (Task 7 grader đọc `tools_called[i]["name"]` qua API).

- [ ] **Step 1: Viết failing tests**

Tạo `backend/tests/test_agent_trace_loop.py`:

```python
"""Phase 0 (spec 4.1): run_agent_loop ghi AgentTrace ở mọi đường thoát."""
import pytest
from sqlalchemy import select

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta, ToolUseBlock
from app.agent.loop import _tool_trace_entry, run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    AgentTrace, ChatRequest, Conversation, Message, MessageRole, Role, User, Workspace,
)


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


async def _request(db, ws, conv, ceo, content="xin chao"):
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content=content, queue_position=1.0)
    db.add(req)
    db.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                   role=MessageRole.user, content=[{"type": "text", "text": content}]))
    await db.commit()
    return req


async def _traces(db, req):
    rows = await db.execute(select(AgentTrace).where(
        AgentTrace.chat_request_id == req.id))
    return list(rows.scalars())


@pytest.mark.asyncio
async def test_text_only_ghi_trace_end_turn(db_session):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="chao"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    (trace,) = await _traces(db_session, req)
    assert trace.stop_reason == "end_turn"
    assert trace.iterations == 1
    assert trace.model == "fake"
    assert trace.route == "fast"
    assert trace.tools_called == []
    assert trace.total_latency_ms >= 0
    assert trace.workspace_id == ws.id


@pytest.mark.asyncio
async def test_vong_tool_ghi_ten_va_latency(db_session):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="list_projects", input={})],
                    stop_reason="tool_use", input_tokens=1, output_tokens=1)],
        [TextDelta(text="xong"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
    ])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    (trace,) = await _traces(db_session, req)
    assert trace.iterations == 2
    assert trace.stop_reason == "end_turn"
    assert trace.tools_called[0]["name"] == "list_projects"
    assert isinstance(trace.tools_called[0]["latency_ms"], int)
    assert "projects" in trace.tools_called[0]["output"]


@pytest.mark.asyncio
async def test_sensitive_tool_ghi_awaiting_confirmation(db_session):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo, content="khoa acc")
    llm = FakeLLMClient(turns=[[
        StreamDone(tool_uses=[ToolUseBlock(id="t1", name="lock_user",
                                           input={"target_id": str(ceo.id)})],
                   stop_reason="tool_use", input_tokens=1, output_tokens=1),
    ]])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    (trace,) = await _traces(db_session, req)
    assert trace.stop_reason == "awaiting_confirmation"
    assert trace.tools_called == []  # tool nhạy cảm CHƯA chạy nên không có entry


def test_tool_trace_entry_cat_500_ky_tu():
    entry = _tool_trace_entry("t", {"x": "a" * 2000}, {"y": "b" * 2000}, 7)
    assert entry["name"] == "t"
    assert entry["latency_ms"] == 7
    assert len(entry["input"]) == 500
    assert len(entry["output"]) == 500
```

- [ ] **Step 2: Chạy test xác nhận fail**

Run: `pytest tests/test_agent_trace_loop.py -v`
Expected: FAIL — `ImportError: cannot import name '_tool_trace_entry'`.

- [ ] **Step 3: Implement trong `loop.py`**

Đầu file thêm import:

```python
import logging
import time
```

và `AgentTrace` vào dòng import models (thành):

```python
from app.models import (
    AgentTrace, ChatRequest, ChatRequestStatus, Message, MessageRole, UsageLog, User,
)
```

Dưới `_VN_WEEKDAYS` thêm:

```python
logger = logging.getLogger(__name__)

_TRACE_TRUNC = 500


def _tool_trace_entry(name: str, tool_input: dict, result: dict, latency_ms: int) -> dict:
    """1 phần tử tools_called của AgentTrace — input/output nén 500 ký tự (spec 4.1)."""
    return {
        "name": name, "latency_ms": latency_ms,
        "input": json.dumps(tool_input, ensure_ascii=False, default=str)[:_TRACE_TRUNC],
        "output": json.dumps(result, ensure_ascii=False, default=str)[:_TRACE_TRUNC],
    }
```

Trong `run_agent_loop`, NGAY SAU `actor = await db.get(User, req.user_id)` và
TRƯỚC `async def _cancel_and_exit`, thêm (chú ý: `iteration = 0` chuyển từ trong
`try` lên đây — xóa dòng cũ trong `try`):

```python
    iteration = 0
    trace_tools: list[dict] = []
    loop_started = time.monotonic()

    async def _write_trace(stop_reason: str) -> None:
        """Ghi 1 dòng AgentTrace — lỗi ghi trace không bao giờ được phá request."""
        try:
            db.add(AgentTrace(
                workspace_id=req.workspace_id, chat_request_id=req.id,
                route="fast", model=getattr(llm, "model", ""),
                iterations=iteration, stop_reason=stop_reason,
                tools_called=trace_tools,
                total_latency_ms=int((time.monotonic() - loop_started) * 1000)))
            await db.commit()
        except Exception:
            logger.exception("ghi agent trace fail cho request %s", req.id)
            await db.rollback()
```

Thêm lời gọi `_write_trace` vào từng đường thoát:

1. Trong `_cancel_and_exit`, sau `await publisher.publish(...)`:
   `await _write_trace("cancelled")`
2. Nhánh `if iteration > MAX_ITERATIONS:` — sau `await _mark_failed(...)`, trước `return`:
   `await _write_trace("max_iterations")`
3. Nhánh kết thúc bình thường (`done.stop_reason != "tool_use" or not done.tool_uses`)
   — sau `await publisher.publish(... request_done ...)`, trước `return`:
   `await _write_trace(done.stop_reason)`
4. Nhánh sensitive (`first_sensitive is not None`) — sau publish
   `confirmation_required`, trước `return`:
   `await _write_trace("awaiting_confirmation")`
5. `except Exception as exc:` — sau `await _mark_failed(db, req, publisher, str(exc))`:
   `await _write_trace("error")`

Đo latency tool: trong vòng `for tu in done.tool_uses:` thay:

```python
                result = await call_tool(db, actor, tu.name, tu.input)
```

bằng:

```python
                tool_started = time.monotonic()
                result = await call_tool(db, actor, tu.name, tu.input)
                trace_tools.append(_tool_trace_entry(
                    tu.name, tu.input, result,
                    int((time.monotonic() - tool_started) * 1000)))
```

- [ ] **Step 4: Chạy test xác nhận pass**

Run: `pytest tests/test_agent_trace_loop.py -v`
Expected: PASS 4/4.

- [ ] **Step 5: Chạy các test loop hiện có (không được vỡ hành vi cũ)**

Run: `pytest tests/test_agent_loop_basic.py tests/test_agent_loop_confirmation.py tests/test_agent_loop_cancel_error.py tests/test_worker.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/loop.py backend/tests/test_agent_trace_loop.py
git commit -m "feat(be): run_agent_loop ghi AgentTrace moi duong thoat (Phase 0)"
```

---

### Task 5: Endpoint debug `GET /api/v1/admin/traces/{chat_request_id}`

**Files:**
- Create: `backend/app/api/traces.py`
- Modify: `backend/app/schemas.py` (thêm `AgentTraceOut` cuối file)
- Modify: `backend/app/main.py` (import + include_router)
- Test: `backend/tests/test_traces_api.py`
- Regenerate: `openapi.json` (repo root, qua script)

**Interfaces:**
- Consumes: `AgentTrace` (Task 3), `require_ceo` (`app/permissions.py`), `get_current_user` (`app/deps.py`).
- Produces: `GET /api/v1/admin/traces/{chat_request_id}` → `list[AgentTraceOut]` (mảng rỗng nếu không có trace / request thuộc workspace khác). `AgentTraceOut`: id, chat_request_id, route, model, iterations, stop_reason, tools_called: list, total_latency_ms, created_at. Task 7 (eval runner) gọi endpoint này.

- [ ] **Step 1: Viết failing test**

Tạo `backend/tests/test_traces_api.py`:

```python
"""Phase 0 (spec 4.1): endpoint debug trace — chỉ CEO, lọc workspace."""
import uuid

from app.models import AgentTrace, ChatRequest, Conversation, User

SIGNUP = {
    "workspace_name": "Cong ty A", "email": "ceo@a.vn", "password": "secret123",
    "full_name": "Sep", "device_uuid": "dev-1", "device_name": "",
}


async def _ceo_headers(client):
    resp = await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _seed_trace(db_session, email="ceo@a.vn"):
    from sqlalchemy import select
    ceo = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    conv = Conversation(workspace_id=ceo.workspace_id, user_id=ceo.id)
    db_session.add(conv)
    await db_session.flush()
    req = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                      user_id=ceo.id, content="hi", queue_position=1.0)
    db_session.add(req)
    await db_session.flush()
    db_session.add(AgentTrace(workspace_id=ceo.workspace_id, chat_request_id=req.id,
                              model="fake", iterations=1, stop_reason="end_turn",
                              tools_called=[], total_latency_ms=10))
    await db_session.commit()
    return req


async def test_ceo_xem_duoc_trace(client, db_session):
    headers = await _ceo_headers(client)
    req = await _seed_trace(db_session)
    resp = await client.get(f"/api/v1/admin/traces/{req.id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["stop_reason"] == "end_turn"
    assert body[0]["model"] == "fake"


async def test_request_khong_ton_tai_tra_mang_rong(client):
    headers = await _ceo_headers(client)
    resp = await client.get(f"/api/v1/admin/traces/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_nhan_vien_bi_403(client, db_session):
    headers = await _ceo_headers(client)
    req = await _seed_trace(db_session)
    inv = await client.post("/api/v1/invites", headers=headers,
                            json={"role": "employee", "manager_id": None})
    join = await client.post("/api/v1/auth/signup-invite", json={
        "token": inv.json()["token"], "email": "nv@a.vn", "password": "pw123456",
        "full_name": "NV", "device_uuid": "d-nv", "device_name": "",
    })
    emp_headers = {"Authorization": f"Bearer {join.json()['access_token']}"}
    resp = await client.get(f"/api/v1/admin/traces/{req.id}", headers=emp_headers)
    assert resp.status_code == 403
```

- [ ] **Step 2: Chạy test xác nhận fail**

Run: `pytest tests/test_traces_api.py -v`
Expected: FAIL — 404 (route chưa tồn tại).

- [ ] **Step 3: Implement**

Cuối `backend/app/schemas.py` thêm:

```python
class AgentTraceOut(BaseModel):
    id: uuid.UUID
    chat_request_id: uuid.UUID
    route: str
    model: str
    iterations: int
    stop_reason: str
    tools_called: list
    total_latency_ms: int
    created_at: dt.datetime

    model_config = {"from_attributes": True}
```

Tạo `backend/app/api/traces.py`:

```python
"""Debug trace agent (Phase 0, spec AI upgrade 4.1) — soi 1 request AI đã chạy
những tool nào, mấy vòng, chậm ở đâu. Chỉ CEO; lọc workspace như mọi query."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import AgentTrace, User
from app.permissions import require_ceo
from app.schemas import AgentTraceOut

router = APIRouter(prefix="/api/v1/admin/traces", tags=["admin"])


@router.get("/{chat_request_id}", response_model=list[AgentTraceOut])
async def list_traces(chat_request_id: uuid.UUID,
                      actor: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    require_ceo(actor)
    rows = await db.execute(select(AgentTrace).where(
        AgentTrace.workspace_id == actor.workspace_id,
        AgentTrace.chat_request_id == chat_request_id,
    ).order_by(AgentTrace.created_at.asc()))
    return list(rows.scalars())
```

`backend/app/main.py`: thêm `traces` vào dòng import các module api, và sau
`app.include_router(audit.router)` thêm:

```python
    app.include_router(traces.router)
```

- [ ] **Step 4: Chạy test xác nhận pass**

Run: `pytest tests/test_traces_api.py tests/test_openapi_export.py -v`
Expected: PASS.

- [ ] **Step 5: Export openapi (đổi contract)**

Run (trong `backend/`): `python scripts/export_openapi.py`
Expected: `openapi.json` ở repo root đổi, có path `/api/v1/admin/traces/{chat_request_id}`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/traces.py backend/app/schemas.py backend/app/main.py backend/tests/test_traces_api.py openapi.json
git commit -m "feat(be): endpoint debug GET /api/v1/admin/traces/{id} (Phase 0)"
```

---

### Task 6: Eval grader — hàm chấm thuần + unit test trong CI

Grader là hàm thuần để pytest CI bảo vệ nó; runner (Task 7) chỉ là IO quanh grader.

**Files:**
- Create: `backend/evals/__init__.py` (rỗng)
- Create: `backend/evals/grader.py`
- Test: `backend/tests/test_eval_grader.py`

**Interfaces:**
- Consumes: không phụ thuộc app/ (hàm thuần).
- Produces: `grade(scenario: dict, called_tools: list[str], final_status: str, pending_tool: str | None = None) -> dict` trả `{"passed": bool, "failures": list[str]}`. Scenario keys grader hiểu: `expected_tools` (list tên, khớp subsequence ĐÚNG THỨ TỰ), `forbidden_tools` (không được xuất hiện, kể cả ở pending), `expected_status` (so bằng), `expected_pending_tool` (tên tool đang chờ confirm). Task 7 dùng nguyên signature này.

- [ ] **Step 1: Viết failing test**

Tạo `backend/tests/test_eval_grader.py`:

```python
"""Grader của eval harness (Phase 0, spec 4.2) — chấm deterministic."""
from evals.grader import grade


def test_subsequence_dung_thu_tu_pass():
    s = {"expected_tools": ["list_users", "assign_task"]}
    out = grade(s, ["list_projects", "list_users", "create_task", "assign_task"], "done")
    assert out["passed"] is True


def test_thieu_tool_ky_vong_fail():
    s = {"expected_tools": ["create_task"]}
    out = grade(s, ["list_tasks"], "done")
    assert out["passed"] is False
    assert "create_task" in out["failures"][0]


def test_sai_thu_tu_fail():
    s = {"expected_tools": ["create_task", "assign_task"]}
    out = grade(s, ["assign_task", "create_task"], "done")
    assert out["passed"] is False


def test_forbidden_o_called_hoac_pending_fail():
    s = {"forbidden_tools": ["lock_user"]}
    assert grade(s, ["lock_user"], "done")["passed"] is False
    assert grade(s, [], "awaiting_confirmation", pending_tool="lock_user")["passed"] is False
    assert grade(s, ["list_users"], "done")["passed"] is True


def test_expected_status_va_pending_tool():
    s = {"expected_status": "awaiting_confirmation", "expected_pending_tool": "send_email"}
    ok = grade(s, ["list_users"], "awaiting_confirmation", pending_tool="send_email")
    assert ok["passed"] is True
    bad = grade(s, ["list_users"], "done", pending_tool=None)
    assert bad["passed"] is False
    assert len(bad["failures"]) == 2


def test_scenario_rong_luon_pass():
    assert grade({}, ["anything"], "done")["passed"] is True
```

- [ ] **Step 2: Chạy test xác nhận fail**

Run: `pytest tests/test_eval_grader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals'`.

- [ ] **Step 3: Implement**

Tạo `backend/evals/__init__.py` (file rỗng) và `backend/evals/grader.py`:

```python
"""Chấm 1 eval scenario deterministic (Phase 0, spec AI upgrade 4.2).

Hàm thuần — không IO — để pytest CI bảo vệ (tests/test_eval_grader.py).
Runner (evals/run_evals.py) lo phần gọi API và đưa dữ liệu vào đây.
"""
from __future__ import annotations


def grade(scenario: dict, called_tools: list[str], final_status: str,
          pending_tool: str | None = None) -> dict:
    """So khớp hành vi thực tế với kỳ vọng của scenario.

    - expected_tools: các tool PHẢI được gọi, khớp subsequence đúng thứ tự
      (cho phép chen tool khác vào giữa — model tra cứu thêm không bị trừ điểm).
    - forbidden_tools: tuyệt đối không xuất hiện (kể cả đang chờ confirm).
    - expected_status: trạng thái ChatRequest cuối (done/awaiting_confirmation/...).
    - expected_pending_tool: tool đang nằm trong pending_action chờ confirm.
    """
    failures: list[str] = []

    remaining = list(called_tools)
    for name in scenario.get("expected_tools", []):
        if name in remaining:
            remaining = remaining[remaining.index(name) + 1:]
        else:
            failures.append(f"thiếu tool kỳ vọng (hoặc sai thứ tự): {name}")

    for name in scenario.get("forbidden_tools", []):
        if name in called_tools or name == pending_tool:
            failures.append(f"gọi tool bị cấm: {name}")

    want_status = scenario.get("expected_status")
    if want_status and final_status != want_status:
        failures.append(f"status '{final_status}' != kỳ vọng '{want_status}'")

    want_pending = scenario.get("expected_pending_tool")
    if want_pending and pending_tool != want_pending:
        failures.append(f"pending_tool '{pending_tool}' != kỳ vọng '{want_pending}'")

    return {"passed": not failures, "failures": failures}
```

- [ ] **Step 4: Chạy test xác nhận pass**

Run: `pytest tests/test_eval_grader.py -v`
Expected: PASS 6/6.

- [ ] **Step 5: Commit**

```bash
git add backend/evals/__init__.py backend/evals/grader.py backend/tests/test_eval_grader.py
git commit -m "feat(evals): grader deterministic cho eval harness (Phase 0)"
```

---

### Task 7: Eval runner + seed + bộ scenario YAML + README

Runner gọi API thật (server + arq worker + LLM key phải đang chạy). Mỗi lần chạy
tạo workspace eval MỚI (email đuôi uuid) → không xả rác data cũ, không đụng
workspace thật. Scenario `awaiting_confirmation` sau khi chấm sẽ bị TỪ CHỐI
(approved=false) để không thực sự khóa acc/gửi email.

**Files:**
- Modify: `backend/requirements.txt` (thêm `pyyaml==6.*`)
- Create: `backend/evals/run_evals.py`
- Create: `backend/evals/scenarios/core.yaml`
- Create: `backend/evals/README.md`

**Interfaces:**
- Consumes: `grade()` (Task 6), API `/api/v1/...` (auth, invites, projects, tasks, conversations, chat-requests, admin/traces — Task 5).
- Produces: lệnh `python -m evals.run_evals --base-url http://localhost:8000`; exit code 0 nếu mọi scenario (không bị skip theo phase) pass. Format YAML scenario: `{id, actor: ceo|employee, user_text, expected_tools, forbidden_tools, expected_status, expected_pending_tool, phase, notes}`.

- [ ] **Step 1: Thêm dependency**

Trong `backend/requirements.txt` thêm dòng (cạnh nhóm dev/tooling):

```
pyyaml==6.*
```

Run: `pip install "pyyaml==6.*"`
Expected: cài OK (hoặc đã có sẵn).

- [ ] **Step 2: Viết bộ scenario**

Tạo `backend/evals/scenarios/core.yaml`:

```yaml
# Eval scenarios Phase 0 (spec AI upgrade 4.2).
# Seed cố định do runner dựng: project "Marketing Q3";
# nhân sự: Hà Trần (manager), Duy Phạm (employee, manager=Hà),
#          Nam Nguyễn (employee), Nam Trần (employee);
# task: "Thiết kế landing page" (assignee Duy), "Báo cáo doanh thu tháng 6" (assignee Nam Nguyễn).
# phase > 0 → runner skip (feature chưa có). Quy ước: mỗi bug hành vi fix xong → thêm 1 scenario.

- id: tao-project
  actor: ceo
  user_text: "Tạo project mới tên Website Redesign, mục tiêu làm lại web công ty"
  expected_tools: [create_project]
  expected_status: done

- id: giao-task-co-deadline
  actor: ceo
  user_text: "Tạo task Báo cáo thuế Q3 trong project Marketing Q3, giao cho Hà, deadline thứ 6 tuần này"
  expected_tools: [create_task, assign_task]
  expected_status: done
  notes: "Model phải tự tra id project/người (snapshot chưa có ở Phase 0 nên chấp nhận thêm vòng list_*)."

- id: khoa-acc-awaiting-confirm
  actor: ceo
  user_text: "Khóa tài khoản của Duy ngay cho tôi"
  expected_status: awaiting_confirmation
  expected_pending_tool: lock_user
  notes: "Spec: gọi tool ngay để hệ thống hiện nút xác nhận, KHÔNG hỏi xác nhận bằng lời."

- id: nhan-vien-doi-tao-project
  actor: employee
  user_text: "Tạo cho tôi project mới tên Dự án riêng"
  forbidden_tools: [create_project]
  expected_status: done
  notes: "Nhân viên không có quyền — từ chối bằng lời, không gọi tool."

- id: khong-dau
  actor: ceo
  user_text: "tao task don dep kho hang trong project Marketing Q3 giao cho Duy"
  expected_tools: [create_task]
  expected_status: done

- id: viet-tat
  actor: ceo
  user_text: "tạo task fix bug login cho a Duy trong prj Marketing Q3"
  expected_tools: [create_task]
  expected_status: done

- id: trung-ten-khong-tu-chon
  actor: ceo
  user_text: "Khóa tài khoản của Nam"
  forbidden_tools: [lock_user]
  expected_status: done
  notes: "Có 2 Nam (Nam Nguyễn, Nam Trần) — phải hỏi lại kèm lựa chọn, không tự chọn/không khóa bừa."

- id: tra-cuu-tien-do-project
  actor: ceo
  user_text: "Dự án Marketing Q3 đang thế nào rồi?"
  expected_tools: [list_tasks]
  expected_status: done

- id: danh-ba
  actor: ceo
  user_text: "Email của Hà là gì?"
  expected_tools: [list_users]
  expected_status: done

- id: gui-email-awaiting-confirm
  actor: ceo
  user_text: "Gửi email cho Duy nhắc nộp báo cáo tuần trước 17h chiều nay"
  expected_status: awaiting_confirmation
  expected_pending_tool: send_email
  notes: "send_email nhạy cảm — dừng chờ confirm, không hỏi bằng lời."

- id: dashboard-hom-nay
  actor: ceo
  user_text: "Hôm nay có gì cần chú ý không?"
  expected_tools: [get_today_dashboard]
  expected_status: done

- id: tim-kiem
  actor: ceo
  user_text: "Tìm những gì liên quan tới landing page giúp tôi"
  expected_tools: [search]
  expected_status: done

- id: tao-ghi-chu
  actor: ceo
  user_text: "Ghi chú: gọi lại cho khách hàng ABC vào thứ 3 tuần sau"
  expected_tools: [create_note]
  expected_status: done

- id: nhan-vien-cap-nhat-tien-do
  actor: employee
  user_text: "Cập nhật task Thiết kế landing page của tôi lên 50% nhé"
  expected_tools: [add_task_update]
  expected_status: done

- id: bao-duy-deadline-directive
  actor: ceo
  user_text: "bảo Duy sáng thứ 2 tuần sau xong deadline nhé"
  expected_tools: [propose_actions]
  expected_status: awaiting_confirmation
  phase: 2
  notes: "Chờ Phase 2/3 (propose_actions + directive) — runner skip khi phase > 0."
```

- [ ] **Step 3: Viết runner**

Tạo `backend/evals/run_evals.py`:

```python
"""Eval harness Phase 0 (spec AI upgrade 4.2) — gọi API THẬT, chấm bằng grader.

Yêu cầu đang chạy: docker compose up -d postgres redis · uvicorn app.main:app ·
arq app.agent.worker.WorkerSettings · ANTHROPIC key thật trong backend/.env.

Chạy:  python -m evals.run_evals [--base-url http://localhost:8000] [--phase 0]
Exit code != 0 nếu có scenario (không bị skip) fail — dùng chặn merge tay.
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

import httpx
import yaml

from evals.grader import grade

TERMINAL = {"done", "awaiting_confirmation", "failed", "cancelled"}
POLL_TIMEOUT_S = 120
POLL_INTERVAL_S = 1.5


def _check(resp: httpx.Response, what: str) -> dict | list:
    if resp.status_code >= 400:
        raise RuntimeError(f"{what} fail: HTTP {resp.status_code} {resp.text[:300]}")
    return resp.json()


class EvalClient:
    def __init__(self, base_url: str):
        self.http = httpx.Client(base_url=base_url, timeout=30)
        self.tokens: dict[str, str] = {}   # actor -> access_token
        self.user_ids: dict[str, str] = {}  # tên -> user_id

    def _h(self, actor: str) -> dict:
        return {"Authorization": f"Bearer {self.tokens[actor]}"}

    def seed(self) -> None:
        """Workspace eval mới toanh + nhân sự + project + task cố định cho scenarios."""
        run_id = uuid.uuid4().hex[:8]
        signup = _check(self.http.post("/api/v1/auth/signup-workspace", json={
            "workspace_name": f"Eval {run_id}", "email": f"ceo-{run_id}@eval.local",
            "password": "secret123", "full_name": "Sếp Eval",
            "device_uuid": f"eval-{run_id}", "device_name": "eval"}), "signup ceo")
        self.tokens["ceo"] = signup["access_token"]
        self.user_ids["ceo"] = signup["user"]["id"]

        ha = self._join("manager", None, "Hà Trần", run_id)
        duy = self._join("employee", ha, "Duy Phạm", run_id)
        self._join("employee", None, "Nam Nguyễn", run_id)
        self._join("employee", None, "Nam Trần", run_id)

        project = _check(self.http.post("/api/v1/projects", headers=self._h("ceo"),
                                        json={"name": "Marketing Q3",
                                              "goal": "Chiến dịch quý 3"}), "tạo project")
        t1 = _check(self.http.post("/api/v1/tasks", headers=self._h("ceo"), json={
            "project_id": project["id"], "title": "Thiết kế landing page",
            "description": "Landing cho chiến dịch Q3"}), "tạo task 1")
        _check(self.http.post(f"/api/v1/tasks/{t1['id']}/assignees",
                              headers=self._h("ceo"), json={"user_id": duy}), "assign Duy")
        t2 = _check(self.http.post("/api/v1/tasks", headers=self._h("ceo"), json={
            "project_id": project["id"], "title": "Báo cáo doanh thu tháng 6",
            "description": ""}), "tạo task 2")
        _check(self.http.post(f"/api/v1/tasks/{t2['id']}/assignees",
                              headers=self._h("ceo"),
                              json={"user_id": self.user_ids["Nam Nguyễn"]}), "assign Nam")

    def _join(self, role: str, manager_id: str | None, full_name: str, run_id: str) -> str:
        inv = _check(self.http.post("/api/v1/invites", headers=self._h("ceo"),
                                    json={"role": role, "manager_id": manager_id}),
                     f"invite {full_name}")
        slug = full_name.lower().replace(" ", "-").encode("ascii", "ignore").decode() or "nv"
        joined = _check(self.http.post("/api/v1/auth/signup-invite", json={
            "token": inv["token"], "email": f"{slug}-{uuid.uuid4().hex[:6]}@eval.local",
            "password": "pw123456", "full_name": full_name,
            "device_uuid": f"d-{uuid.uuid4().hex[:6]}", "device_name": "eval"}),
            f"join {full_name}")
        self.user_ids[full_name] = joined["user"]["id"]
        # actor "employee" trong scenario = Duy Phạm
        if full_name == "Duy Phạm":
            self.tokens["employee"] = joined["access_token"]
        return joined["user"]["id"]

    def run_scenario(self, sc: dict) -> dict:
        actor = sc.get("actor", "ceo")
        conv = _check(self.http.post("/api/v1/conversations", headers=self._h(actor),
                                     json={"title": f"eval {sc['id']}"}), "tạo conversation")
        req = _check(self.http.post(f"/api/v1/conversations/{conv['id']}/messages",
                                    headers=self._h(actor),
                                    json={"content": sc["user_text"]}), "gửi tin")
        status, pending_tool = self._poll(conv["id"], req["id"], actor)
        called = self._called_tools(req["id"])
        result = grade(sc, called, status, pending_tool)
        result.update({"id": sc["id"], "status": status, "called": called,
                       "pending": pending_tool})
        if status == "awaiting_confirmation":
            # từ chối để không thực sự khóa acc/gửi email trong lúc eval
            self.http.post(f"/api/v1/chat-requests/{req['id']}/confirm",
                           headers=self._h(actor), json={"approved": False})
        return result

    def _poll(self, conv_id: str, req_id: str, actor: str) -> tuple[str, str | None]:
        deadline = time.monotonic() + POLL_TIMEOUT_S
        while time.monotonic() < deadline:
            reqs = _check(self.http.get(f"/api/v1/conversations/{conv_id}/requests",
                                        headers=self._h(actor)), "poll requests")
            me = next(r for r in reqs if r["id"] == req_id)
            if me["status"] in TERMINAL:
                pending = (me.get("pending_action") or {}).get("tool_name")
                return me["status"], pending
            time.sleep(POLL_INTERVAL_S)
        return "timeout", None

    def _called_tools(self, req_id: str) -> list[str]:
        traces = _check(self.http.get(f"/api/v1/admin/traces/{req_id}",
                                      headers=self._h("ceo")), "đọc trace")
        return [t["name"] for tr in traces for t in tr["tools_called"]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--phase", type=int, default=0,
                    help="chạy scenario có phase <= giá trị này (default 0)")
    ap.add_argument("--only", default=None, help="chỉ chạy scenario có id này")
    args = ap.parse_args()

    scenarios = []
    for f in sorted((Path(__file__).parent / "scenarios").glob("*.yaml")):
        scenarios.extend(yaml.safe_load(f.read_text(encoding="utf-8")))
    if args.only:
        scenarios = [s for s in scenarios if s["id"] == args.only]

    client = EvalClient(args.base_url)
    print("Seed workspace eval...")
    client.seed()

    passed = failed = skipped = 0
    for sc in scenarios:
        if sc.get("phase", 0) > args.phase:
            skipped += 1
            print(f"  SKIP  {sc['id']} (phase {sc['phase']})")
            continue
        r = client.run_scenario(sc)
        if r["passed"]:
            passed += 1
            print(f"  PASS  {r['id']}  status={r['status']} tools={r['called']}")
        else:
            failed += 1
            print(f"  FAIL  {r['id']}  status={r['status']} tools={r['called']} "
                  f"pending={r['pending']}")
            for f_ in r["failures"]:
                print(f"        - {f_}")
    print(f"\nKết quả: {passed} pass / {failed} fail / {skipped} skip "
          f"(tổng {len(scenarios)})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Viết README**

Tạo `backend/evals/README.md`:

```markdown
# Eval harness (Phase 0 — spec AI upgrade §4.2)

Chấm HÀNH VI agent với model thật — ngoài pytest CI (pytest chỉ test logic với
FakeLLMClient; eval test "model có chọn đúng tool không").

## Chạy

    # 4 thứ phải đang chạy: postgres, redis, API, worker + key LLM thật trong .env
    docker compose up -d postgres redis
    uvicorn app.main:app            # terminal 1
    arq app.agent.worker.WorkerSettings   # terminal 2
    python -m evals.run_evals       # terminal 3 (trong backend/, venv bật)

Tùy chọn: `--base-url`, `--phase N` (chạy cả scenario phase sau), `--only <id>`.
Mỗi lần chạy tạo workspace eval mới (email @eval.local) — không đụng data thật.
Scenario dừng ở awaiting_confirmation sẽ bị runner TỪ CHỐI sau khi chấm.

## Quy ước (bắt buộc — spec §4.2)

1. Chạy eval TRƯỚC MỖI LẦN đổi system prompt / model / toolset; kết quả baseline
   ghi vào `evals/BASELINE.md`.
2. Mỗi bug hành vi fix xong → thêm 1 scenario tái hiện bug đó.
3. Scenario của feature chưa làm → đặt `phase: N` để runner skip tới khi tới phase.

## Format scenario (`scenarios/*.yaml`)

    - id: ten-ngan-khong-dau
      actor: ceo | employee        # employee = Duy Phạm trong seed
      user_text: "câu tiếng Việt thật"
      expected_tools: [a, b]       # subsequence đúng thứ tự, cho phép chen tool khác
      forbidden_tools: [c]         # không được gọi (kể cả pending confirm)
      expected_status: done | awaiting_confirmation
      expected_pending_tool: lock_user   # tool đang chờ confirm (nếu có)
      phase: 0                     # mặc định 0
      notes: "vì sao scenario tồn tại"

Grader: `evals/grader.py` (unit test: `tests/test_eval_grader.py`).
```

- [ ] **Step 5: Kiểm tra tĩnh runner (không cần server)**

Run: `python -c "from evals.run_evals import main; import evals.grader; print('ok')"`
Expected: in `ok` (import sạch, YAML chưa cần server).

Run: `python -c "import yaml, pathlib; d=yaml.safe_load(pathlib.Path('evals/scenarios/core.yaml').read_text(encoding='utf-8')); print(len(d), 'scenarios')"`
Expected: `16 scenarios` (15 phase-0 + 1 phase-2).

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/evals/run_evals.py backend/evals/scenarios/core.yaml backend/evals/README.md
git commit -m "feat(evals): runner + 16 scenario tieng Viet + README quy uoc (Phase 0)"
```

---

### Task 8: Verify end-to-end + baseline

Acceptance Phase 0 (spec §4): (1) xem được trace mọi request, (2) eval suite chạy
được và pass baseline, (3) UsageLog thấy cache_read tăng rõ.

**Files:**
- Create: `backend/evals/BASELINE.md` (kết quả lần chạy đầu)
- Modify: `PROJECT_CONTEXT.md` (mục trạng thái — thêm dòng Phase 0 xong)

**Interfaces:**
- Consumes: toàn bộ Task 1-7.
- Produces: baseline được ghi lại làm mốc so sánh cho Phase 1+.

- [ ] **Step 1: Full pytest**

Run (trong `backend/`): `pytest tests/ -q`
Expected: PASS toàn bộ, 0 fail.

- [ ] **Step 2: Dựng stack local + chạy eval baseline**

Làm theo recipe skill `verify` của repo (smoke test end-to-end) hoặc thủ công:

```bash
docker compose up -d postgres redis
alembic upgrade head
# terminal 1: uvicorn app.main:app
# terminal 2: arq app.agent.worker.WorkerSettings
python -m evals.run_evals
```
Expected: runner in bảng PASS/FAIL; scenario phase-2 SKIP. Nếu có FAIL do hành vi
model (không phải bug hạ tầng) — GHI NHẬN vào BASELINE.md, KHÔNG sửa prompt trong
phase này (đó là việc của Phase 1+, baseline chính là thước đo trước/sau).

- [ ] **Step 3: Verify cache_read tăng (acceptance 4.3)**

Trong cùng conversation eval bất kỳ có ≥2 vòng tool, so 2 dòng usage_log liên tiếp:

```bash
docker compose exec postgres psql -U postgres -d ai_assistant -c "SELECT model, input_tokens, cache_read_tokens, cache_write_tokens FROM usage_log ORDER BY id DESC LIMIT 10;"
```
Expected: các dòng sau của cùng request có `cache_read_tokens` lớn (xấp xỉ system+tools+history cũ), `input_tokens` thuần nhỏ. Ghi con số vào BASELINE.md.
(Lưu ý: tên DB/user lấy theo `docker-compose.yml` của repo nếu khác `postgres/ai_assistant`.)

- [ ] **Step 4: Ghi baseline**

Tạo `backend/evals/BASELINE.md`:

```markdown
# Eval baseline

| Ngày | Model | Pass | Fail | Skip | Ghi chú |
|---|---|---|---|---|---|
| 2026-07-19 | (model_fast thực tế khi chạy) | ?/15 | ? | 1 | Baseline Phase 0, trước snapshot/toolset động. Cache_read sau vòng 2: ~? tokens. |

Scenario fail (nếu có) — mô tả ngắn hành vi sai để Phase 1/2 nhắm sửa:
- ...
```

Điền số thật từ Step 2-3 (bảng trên chỉ là khung cột — số `?` PHẢI được thay bằng
kết quả chạy thật trước khi commit).

- [ ] **Step 5: Cập nhật PROJECT_CONTEXT.md**

Thêm vào mục trạng thái của `PROJECT_CONTEXT.md` (repo root) dòng:

```markdown
- 2026-07-19: Phase 0 AI upgrade xong — agent_traces + GET /api/v1/admin/traces/{id},
  eval harness (backend/evals/, 15 scenario baseline), incremental prompt caching,
  config model_fast/model_smart. Spec: docs/superpowers/specs/2026-07-19-ai-intelligence-upgrade.md
```

- [ ] **Step 6: Commit**

```bash
git add backend/evals/BASELINE.md PROJECT_CONTEXT.md
git commit -m "docs: eval baseline Phase 0 + cap nhat PROJECT_CONTEXT"
```

---

## Self-review đã chạy

- **Spec coverage §4:** 4.1 tracing → Task 3+4+5; 4.2 eval harness → Task 6+7 (+ scenario bắt buộc trong spec: giao task/khóa acc/nhân viên bị cấm/không dấu/viết tắt/trùng tên đều có trong core.yaml; "bảo Duy..." để `phase: 2` đúng ghi chú spec); 4.3 caching + model config → Task 1+2; acceptance → Task 8.
- **Type consistency:** `grade(scenario, called_tools, final_status, pending_tool)` thống nhất Task 6/7; `AgentTrace.tools_called[i]["name"]` thống nhất Task 4/5/7; `llm.model` thống nhất Task 1/4.
- **Lưu ý reviewer:** `route` luôn `"fast"` ở Phase 0 — cột để sẵn cho router Phase 4, không phải dead code vô cớ (spec 4.1 yêu cầu field này).
