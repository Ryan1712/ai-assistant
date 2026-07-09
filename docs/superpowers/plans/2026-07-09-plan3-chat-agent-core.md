# Plan 3 — Lõi Chat/Agent (queue → agent loop → streaming)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây khung chat + agent loop + tool-calling nối vào `work_service`/`skill_service`/`auth_service` đã có, theo đúng thiết kế đã duyệt.

**Architecture:** `api` (FastAPI) ghi `chat_requests` rồi enqueue job arq theo `_job_id=f"conv:{id}"` (dedupe = khóa per-conversation); `worker` (arq) chạy `process_conversation` lặp qua các request `queued`, mỗi request chạy `run_agent_loop` gọi `LLMClient` (Claude qua Anthropic SDK, model từ config) với 21 tool bọc service layer sẵn có; token/trạng thái publish qua `EventPublisher` (Redis pub/sub) → WebSocket. Toàn bộ TDD dùng `FakeLLMClient`/`FakeEventPublisher`, không cần Anthropic API key hay Redis thật.

**Tech Stack:** như Plan 1/2 (FastAPI, SQLAlchemy 2.0 async, pytest + SQLite StaticPool) + `anthropic` SDK, `arq` + `redis` (Redis đã chạy sẵn qua docker-compose từ Plan 2).

## Global Constraints

- Mọi bảng mới có `workspace_id` NOT NULL FK `workspaces.id`.
- `actor` trong mọi tool/agent loop luôn dựng từ `chat_requests.user_id` (← JWT lúc gửi tin nhắn), KHÔNG bao giờ lấy từ tool_input hay do model tự khai.
- Quyền kiểm tra ở **service layer đã có từ Plan 1/2** — tool chỉ là lớp gọi lại, KHÔNG tự check quyền, KHÔNG catch-all nuốt lỗi (403/404/422 phải nổi lên thành tool_result lỗi).
- Model LLM lấy từ `settings.model_chat` — không hardcode model ID.
- Route dưới `/api/v1`; đổi API contract = chạy lại `scripts/export_openapi.py`.
- TDD: test trước, code sau; mỗi task một commit.
- Test suite (`pytest tests/`) KHÔNG cần `ANTHROPIC_API_KEY` hay Redis thật — dùng `FakeLLMClient`/`FakeEventPublisher`.
- Chạy lệnh trong `backend/`; Windows PowerShell: `Set-Location "d:\8. AI\ai-assistant\backend"` rồi `.venv\Scripts\python.exe -m pytest tests/ -v`.
- Suite hiện tại: **71 passed** — không được làm hỏng test cũ.
- Không commit secrets; dùng `.env` (đã gitignore).

## Cấu trúc file (mới/sửa)

```
backend/app/
  models.py            # sửa: + Conversation, ChatRequest, Message, UsageLog, 2 enum mới
  schemas.py           # sửa: + schemas conversation/chat_request/message
  config.py            # sửa: + anthropic_api_key, redis_url, model_chat
  main.py              # sửa: mount chat.router + ws.router
  agent/
    __init__.py
    llm_client.py       # LLMClient (ABC), TextDelta, ToolUseBlock, StreamDone, FakeLLMClient, AnthropicLLMClient, get_llm_client()
    publisher.py         # EventPublisher (ABC), FakeEventPublisher, RedisEventPublisher, get_event_publisher()
    tools.py              # ToolSpec, TOOLS registry, SENSITIVE_TOOLS, call_tool()
    loop.py                # run_agent_loop()
    worker.py               # process_conversation(), enqueue_conversation(), WorkerSettings
  api/
    chat.py              # REST: conversations, messages, confirm, cancel, reorder
    ws.py                 # WebSocket streaming + stream_events()/authorize_ws() (testable không cần socket thật)
backend/tests/
  test_chat_models.py
  test_agent_llm_client.py
  test_agent_publisher.py
  test_agent_tools_project_task.py
  test_agent_tools_progress_skill.py
  test_agent_tools_account.py
  test_agent_loop_basic.py
  test_agent_loop_confirmation.py
  test_agent_loop_cancel_error.py
  test_worker.py
  test_chat_api.py
  test_chat_queue_api.py
  test_ws.py
```

---

### Task 1: Data models — conversation/chat_request/message/usage_log

**Files:**
- Modify: `backend/app/models.py`
- Test: `backend/tests/test_chat_models.py`

**Interfaces:**
- Produces enums: `ChatRequestStatus` (queued/running/awaiting_confirmation/done/failed/cancelled), `MessageRole` (user/assistant).
- Produces models: `Conversation(id, workspace_id, user_id, title?, created_at)`; `ChatRequest(id, workspace_id, conversation_id, user_id, content, status, queue_position: float, pending_action: dict?, error?, result_summary?, created_at, started_at?, finished_at?)`; `Message(id, workspace_id, conversation_id, chat_request_id?, role, content: list, created_at)`; `UsageLog(id, workspace_id, chat_request_id?, model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, created_at)`.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_chat_models.py`:
```python
import pytest
from sqlalchemy import select

from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Role,
    UsageLog, User, Workspace,
)


@pytest.mark.asyncio
async def test_conversation_chatrequest_message_usagelog_roundtrip(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    u = User(workspace_id=ws.id, email="c@a.vn", password_hash="x",
             full_name="C", role=Role.ceo, is_root=True)
    db_session.add(u)
    await db_session.flush()

    conv = Conversation(workspace_id=ws.id, user_id=u.id)
    db_session.add(conv)
    await db_session.flush()

    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=u.id,
                      content="tao task X", queue_position=1.0)
    db_session.add(req)
    await db_session.flush()

    msg = Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                  role=MessageRole.user, content=[{"type": "text", "text": "tao task X"}])
    db_session.add(msg)
    db_session.add(UsageLog(workspace_id=ws.id, chat_request_id=req.id,
                            model="claude-haiku-4-5", input_tokens=10, output_tokens=5))
    await db_session.commit()

    found_req = (await db_session.execute(select(ChatRequest))).scalar_one()
    assert found_req.status == ChatRequestStatus.queued
    assert found_req.queue_position == 1.0
    assert found_req.pending_action is None

    found_msg = (await db_session.execute(select(Message))).scalar_one()
    assert found_msg.role == MessageRole.user
    assert found_msg.content == [{"type": "text", "text": "tao task X"}]

    found_usage = (await db_session.execute(select(UsageLog))).scalar_one()
    assert found_usage.model == "claude-haiku-4-5"
```

Run: `pytest tests/test_chat_models.py -v` → FAIL (ImportError: ChatRequest không tồn tại).

- [ ] **Step 2: Implement — thêm vào cuối `backend/app/models.py`**

(bổ sung import `Float` từ sqlalchemy — dòng import hiện có ở đầu file cần sửa thành: `from sqlalchemy import String, Boolean, ForeignKey, DateTime, Enum, JSON, Uuid, Integer, Text, UniqueConstraint, Float`)
```python
class ChatRequestStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    awaiting_confirmation = "awaiting_confirmation"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ChatRequest(Base):
    __tablename__ = "chat_requests"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[ChatRequestStatus] = mapped_column(Enum(ChatRequestStatus),
                                                       default=ChatRequestStatus.queued)
    queue_position: Mapped[float] = mapped_column(Float)
    pending_action: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    chat_request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chat_requests.id"),
                                                               nullable=True)
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole))
    content: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UsageLog(Base):
    __tablename__ = "usage_log"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    chat_request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chat_requests.id"),
                                                               nullable=True)
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
```

- [ ] **Step 3: Run toàn bộ → PASS (72)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): chat/agent core models - conversation/chat_request/message/usage_log"
```

---

### Task 2: Config + dependencies mới

**Files:**
- Modify: `backend/requirements.txt`, `backend/app/config.py`, `backend/.env.example`
- Test: `backend/tests/test_chat_config.py`

**Interfaces:**
- Produces: `Settings.anthropic_api_key: str = ""`, `Settings.redis_url: str = "redis://localhost:6379"`, `Settings.model_chat: str = "claude-haiku-4-5"`.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_chat_config.py`:
```python
from app.config import Settings


def test_chat_settings_defaults():
    s = Settings()
    assert s.anthropic_api_key == ""
    assert s.redis_url == "redis://localhost:6379"
    assert s.model_chat == "claude-haiku-4-5"
```

Run: `pytest tests/test_chat_config.py -v` → FAIL (AttributeError).

- [ ] **Step 2: Implement**

`backend/requirements.txt` — thêm 3 dòng cuối:
```
anthropic==0.39.*
arq==0.26.*
redis==5.*
```

`backend/app/config.py` — sửa class `Settings` (thêm 3 field, giữ nguyên phần còn lại của file):
```python
class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///:memory:"
    jwt_secret: str = "dev-secret-change-me"
    access_ttl_minutes: int = 15
    refresh_ttl_days: int = 30
    env: str = "dev"
    anthropic_api_key: str = ""
    redis_url: str = "redis://localhost:6379"
    model_chat: str = "claude-haiku-4-5"

    model_config = {"env_file": ".env"}
```

`backend/.env.example` — thêm 3 dòng cuối:
```
ANTHROPIC_API_KEY=
REDIS_URL=redis://localhost:6379
MODEL_CHAT=claude-haiku-4-5
```

- [ ] **Step 3: Run toàn bộ → PASS (73)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): config for chat - anthropic key, redis url, model_chat"
pip install -r backend/requirements.txt
```

Lưu ý: chạy `pip install` (hoặc `.venv\Scripts\pip.exe install -r requirements.txt`) trước khi làm Task 3 — Task 3 import `anthropic`/`redis`/`arq`.

---

### Task 3: `LLMClient` — interface + fake test double

**Files:**
- Create: `backend/app/agent/__init__.py`, `backend/app/agent/llm_client.py`
- Test: `backend/tests/test_agent_llm_client.py`

**Interfaces:**
- Produces: `TextDelta(text)`, `ToolUseBlock(id, name, input)`, `StreamDone(tool_uses, stop_reason, input_tokens, output_tokens, cache_read_tokens=0, cache_write_tokens=0)`, `LLMClient` (ABC với `stream(*, system, messages, tools) -> AsyncIterator[TextDelta | StreamDone]`), `FakeLLMClient(turns: list[list[TextDelta | StreamDone]])` — mỗi lần `.stream()` được gọi, trả (bằng cách yield) đúng 1 "lượt" kế tiếp trong `turns`; lưu lại mọi lời gọi vào `.calls`.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_agent_llm_client.py`:
```python
import pytest

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta, ToolUseBlock


@pytest.mark.asyncio
async def test_fake_llm_client_replays_scripted_turns_in_order():
    fake = FakeLLMClient(turns=[
        [TextDelta(text="Xin "), TextDelta(text="chao"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=10, output_tokens=5)],
        [StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=3, output_tokens=1)],
    ])

    events = [e async for e in fake.stream(system="sys", messages=[], tools=[])]
    assert [type(e).__name__ for e in events] == ["TextDelta", "TextDelta", "StreamDone"]
    assert events[-1].stop_reason == "end_turn"
    assert events[-1].input_tokens == 10

    second = [e async for e in fake.stream(system="sys", messages=[{"role": "user"}], tools=[])]
    assert len(second) == 1
    assert len(fake.calls) == 2
    assert fake.calls[1]["messages"] == [{"role": "user"}]


@pytest.mark.asyncio
async def test_fake_llm_client_yields_tool_use():
    fake = FakeLLMClient(turns=[[
        StreamDone(tool_uses=[ToolUseBlock(id="t1", name="create_task", input={"title": "X"})],
                  stop_reason="tool_use", input_tokens=20, output_tokens=8),
    ]])
    events = [e async for e in fake.stream(system="sys", messages=[], tools=[])]
    assert events[0].tool_uses[0].name == "create_task"
```

Run: `pytest tests/test_agent_llm_client.py -v` → FAIL (ModuleNotFoundError: app.agent).

- [ ] **Step 2: Implement**

`backend/app/agent/__init__.py`: file rỗng.

`backend/app/agent/llm_client.py`:
```python
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import AsyncIterator, Union


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict


@dataclass
class StreamDone:
    tool_uses: list[ToolUseBlock]
    stop_reason: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


StreamEvent = Union[TextDelta, StreamDone]


class LLMClient(abc.ABC):
    @abc.abstractmethod
    def stream(self, *, system: str, messages: list[dict],
              tools: list[dict]) -> AsyncIterator[StreamEvent]:
        ...


class FakeLLMClient(LLMClient):
    """Test double: phát lại kịch bản dựng sẵn, 1 lượt/lần gọi .stream()."""

    def __init__(self, turns: list[list[StreamEvent]]):
        self._turns = list(turns)
        self.calls: list[dict] = []

    async def stream(self, *, system: str, messages: list[dict],
                     tools: list[dict]) -> AsyncIterator[StreamEvent]:
        self.calls.append({"system": system, "messages": messages, "tools": tools})
        events = self._turns.pop(0)
        for event in events:
            yield event
```

- [ ] **Step 3: Run toàn bộ → PASS (75)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): LLMClient interface + FakeLLMClient test double"
```

---

### Task 4: `EventPublisher` — interface + fake test double

**Files:**
- Create: `backend/app/agent/publisher.py`
- Test: `backend/tests/test_agent_publisher.py`

**Interfaces:**
- Produces: `EventPublisher` (ABC: `async publish(conversation_id, event: dict)`, `subscribe(conversation_id) -> AsyncIterator[dict]`), `FakeEventPublisher` — `.events` giữ toàn bộ lịch sử publish; `.subscribe()` fan-out realtime qua `asyncio.Queue`; `.close(conversation_id)` kết thúc mọi subscriber đang chờ của conversation đó.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_agent_publisher.py`:
```python
import asyncio
import uuid

import pytest

from app.agent.publisher import FakeEventPublisher


@pytest.mark.asyncio
async def test_publish_records_history():
    pub = FakeEventPublisher()
    conv_id = uuid.uuid4()
    await pub.publish(conv_id, {"type": "token", "text": "hi"})
    assert pub.events == [(conv_id, {"type": "token", "text": "hi"})]


@pytest.mark.asyncio
async def test_subscribe_receives_events_published_after_subscribing():
    pub = FakeEventPublisher()
    conv_id = uuid.uuid4()
    received = []

    async def reader():
        async for event in pub.subscribe(conv_id):
            received.append(event)

    task = asyncio.create_task(reader())
    await asyncio.sleep(0)  # để subscriber đăng ký queue trước khi publish
    await pub.publish(conv_id, {"type": "token", "text": "a"})
    await pub.publish(conv_id, {"type": "request_done"})
    await pub.close(conv_id)
    await asyncio.wait_for(task, timeout=1)

    assert received == [{"type": "token", "text": "a"}, {"type": "request_done"}]


@pytest.mark.asyncio
async def test_subscribers_are_scoped_per_conversation():
    pub = FakeEventPublisher()
    conv_a, conv_b = uuid.uuid4(), uuid.uuid4()
    received = []

    async def reader():
        async for event in pub.subscribe(conv_a):
            received.append(event)

    task = asyncio.create_task(reader())
    await asyncio.sleep(0)
    await pub.publish(conv_b, {"type": "token", "text": "khac conversation"})
    await pub.close(conv_a)
    await asyncio.wait_for(task, timeout=1)
    assert received == []
```

Run: `pytest tests/test_agent_publisher.py -v` → FAIL (ModuleNotFoundError).

- [ ] **Step 2: Implement**

`backend/app/agent/publisher.py`:
```python
from __future__ import annotations

import abc
import asyncio
import uuid
from typing import AsyncIterator


class EventPublisher(abc.ABC):
    @abc.abstractmethod
    async def publish(self, conversation_id: uuid.UUID, event: dict) -> None:
        ...

    @abc.abstractmethod
    def subscribe(self, conversation_id: uuid.UUID) -> AsyncIterator[dict]:
        ...


class FakeEventPublisher(EventPublisher):
    """Test double: giữ lịch sử publish + fan-out cho subscriber qua asyncio.Queue."""

    def __init__(self):
        self.events: list[tuple[uuid.UUID, dict]] = []
        self._queues: dict[uuid.UUID, list[asyncio.Queue]] = {}

    async def publish(self, conversation_id: uuid.UUID, event: dict) -> None:
        self.events.append((conversation_id, event))
        for q in self._queues.get(conversation_id, []):
            await q.put(event)

    def subscribe(self, conversation_id: uuid.UUID) -> AsyncIterator[dict]:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues.setdefault(conversation_id, []).append(queue)

        async def _gen():
            while True:
                event = await queue.get()
                if event is None:
                    return
                yield event

        return _gen()

    async def close(self, conversation_id: uuid.UUID) -> None:
        for q in self._queues.get(conversation_id, []):
            await q.put(None)
```

- [ ] **Step 3: Run toàn bộ → PASS (78)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): EventPublisher interface + FakeEventPublisher test double"
```

---

### Task 5: Prod implementations — `AnthropicLLMClient` + `RedisEventPublisher`

**Files:**
- Modify: `backend/app/agent/llm_client.py`, `backend/app/agent/publisher.py`
- Test: `backend/tests/test_agent_llm_client.py`, `backend/tests/test_agent_publisher.py`

**Interfaces:**
- Produces: `AnthropicLLMClient(client, model, max_tokens=4096)` — dịch SDK stream (`client.messages.stream(...)` async context manager với `.text_stream` + `.get_final_message()`) sang `TextDelta`/`StreamDone`; `get_llm_client() -> LLMClient` (đọc `settings.anthropic_api_key`/`model_chat`). `RedisEventPublisher(redis)` — publish JSON lên kênh `conv:{id}`, subscribe qua `redis.pubsub()`; `get_event_publisher() -> EventPublisher` (đọc `settings.redis_url`). `client`/`redis` được **inject qua constructor** — test dùng double tự viết, không cần network/Redis thật.

- [ ] **Step 1: Viết test fail**

Thêm vào cuối `backend/tests/test_agent_llm_client.py`:
```python
class _FakeUsage:
    def __init__(self, input_tokens, output_tokens, cache_read=0, cache_write=0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_input_tokens = cache_read
        self.cache_creation_input_tokens = cache_write


class _FakeContentBlock:
    def __init__(self, type_, **kw):
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeFinalMessage:
    def __init__(self, content, stop_reason, usage):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = usage


class _FakeStreamContext:
    def __init__(self, texts, final_message):
        self._texts = texts
        self._final_message = final_message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def text_stream(self):
        async def _gen():
            for t in self._texts:
                yield t
        return _gen()

    async def get_final_message(self):
        return self._final_message


class _FakeMessagesAPI:
    def __init__(self, stream_ctx):
        self._stream_ctx = stream_ctx
        self.last_kwargs = None

    def stream(self, **kwargs):
        self.last_kwargs = kwargs
        return self._stream_ctx


class _FakeAnthropicSDKClient:
    def __init__(self, stream_ctx):
        self.messages = _FakeMessagesAPI(stream_ctx)


@pytest.mark.asyncio
async def test_anthropic_llm_client_translates_sdk_stream_to_events():
    from app.agent.llm_client import AnthropicLLMClient

    final = _FakeFinalMessage(
        content=[_FakeContentBlock("text", text="Da lam xong"),
                 _FakeContentBlock("tool_use", id="t1", name="create_task", input={"title": "X"})],
        stop_reason="tool_use",
        usage=_FakeUsage(input_tokens=100, output_tokens=20, cache_read=80),
    )
    stream_ctx = _FakeStreamContext(texts=["Da ", "lam ", "xong"], final_message=final)
    sdk_client = _FakeAnthropicSDKClient(stream_ctx)

    client = AnthropicLLMClient(sdk_client, model="claude-haiku-4-5")
    events = [e async for e in client.stream(
        system="sys", messages=[{"role": "user", "content": "hi"}], tools=[])]

    assert [e.text for e in events[:-1]] == ["Da ", "lam ", "xong"]
    done = events[-1]
    assert done.stop_reason == "tool_use"
    assert done.tool_uses == [ToolUseBlock(id="t1", name="create_task", input={"title": "X"})]
    assert done.input_tokens == 100
    assert done.cache_read_tokens == 80
    assert sdk_client.messages.last_kwargs["model"] == "claude-haiku-4-5"
```

Thêm vào cuối `backend/tests/test_agent_publisher.py`:
```python
import json


class _FakeRedisPubSub:
    def __init__(self, messages):
        self._messages = messages
        self.subscribed_channels = []
        self.unsubscribed_channels = []

    async def subscribe(self, channel):
        self.subscribed_channels.append(channel)

    async def unsubscribe(self, channel):
        self.unsubscribed_channels.append(channel)

    async def listen(self):
        for m in self._messages:
            yield m


class _FakeRedis:
    def __init__(self, pubsub_messages=None):
        self.published = []
        self._pubsub = _FakeRedisPubSub(pubsub_messages or [])

    async def publish(self, channel, data):
        self.published.append((channel, data))

    def pubsub(self):
        return self._pubsub


@pytest.mark.asyncio
async def test_redis_event_publisher_publishes_json_to_conversation_channel():
    from app.agent.publisher import RedisEventPublisher

    redis = _FakeRedis()
    pub = RedisEventPublisher(redis)
    conv_id = uuid.uuid4()
    await pub.publish(conv_id, {"type": "token", "text": "hi"})

    channel, data = redis.published[0]
    assert channel == f"conv:{conv_id}"
    assert json.loads(data) == {"type": "token", "text": "hi"}


@pytest.mark.asyncio
async def test_redis_event_publisher_subscribe_yields_decoded_events():
    from app.agent.publisher import RedisEventPublisher

    conv_id = uuid.uuid4()
    messages = [
        {"type": "subscribe", "data": 1},
        {"type": "message", "data": json.dumps({"type": "token", "text": "a"})},
        {"type": "message", "data": json.dumps({"type": "request_done"})},
    ]
    redis = _FakeRedis(pubsub_messages=messages)
    pub = RedisEventPublisher(redis)

    received = [e async for e in pub.subscribe(conv_id)]
    assert received == [{"type": "token", "text": "a"}, {"type": "request_done"}]
    assert redis._pubsub.subscribed_channels == [f"conv:{conv_id}"]
    assert redis._pubsub.unsubscribed_channels == [f"conv:{conv_id}"]
```

(bổ sung `import uuid` ở đầu `test_agent_publisher.py` nếu chưa có — file Task 4 đã có sẵn).

Run: `pytest tests/test_agent_llm_client.py tests/test_agent_publisher.py -v` → FAIL (AttributeError/ImportError: AnthropicLLMClient, RedisEventPublisher chưa tồn tại).

- [ ] **Step 2: Implement**

Thêm vào cuối `backend/app/agent/llm_client.py` (bổ sung `from functools import lru_cache` vào đầu file):
```python
class AnthropicLLMClient(LLMClient):
    """Prod impl — bọc anthropic.AsyncAnthropic (inject qua constructor để test không cần network)."""

    def __init__(self, client, model: str, max_tokens: int = 4096):
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    async def stream(self, *, system: str, messages: list[dict],
                     tools: list[dict]) -> AsyncIterator[StreamEvent]:
        async with self._client.messages.stream(
            model=self._model, max_tokens=self._max_tokens,
            system=system, messages=messages, tools=tools,
        ) as stream:
            async for text in stream.text_stream:
                yield TextDelta(text=text)
            final = await stream.get_final_message()
        tool_uses = [
            ToolUseBlock(id=block.id, name=block.name, input=block.input)
            for block in final.content if block.type == "tool_use"
        ]
        usage = final.usage
        yield StreamDone(
            tool_uses=tool_uses, stop_reason=final.stop_reason,
            input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        )


@lru_cache
def get_llm_client() -> LLMClient:
    import anthropic

    from app.config import get_settings

    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return AnthropicLLMClient(client, model=settings.model_chat)
```

Thêm vào cuối `backend/app/agent/publisher.py` (bổ sung `import json` và `from functools import lru_cache` vào đầu file):
```python
class RedisEventPublisher(EventPublisher):
    def __init__(self, redis):
        self._redis = redis

    async def publish(self, conversation_id: uuid.UUID, event: dict) -> None:
        await self._redis.publish(f"conv:{conversation_id}", json.dumps(event, default=str))

    async def subscribe(self, conversation_id: uuid.UUID) -> AsyncIterator[dict]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(f"conv:{conversation_id}")
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                yield json.loads(message["data"])
        finally:
            await pubsub.unsubscribe(f"conv:{conversation_id}")


@lru_cache
def get_event_publisher() -> EventPublisher:
    import redis.asyncio as redis_asyncio

    from app.config import get_settings

    redis_client = redis_asyncio.from_url(get_settings().redis_url)
    return RedisEventPublisher(redis_client)
```

- [ ] **Step 3: Run toàn bộ → PASS (81)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): AnthropicLLMClient + RedisEventPublisher prod implementations"
```

---

### Task 6: Tool registry core + Project/Task tools (9 tool)

**Files:**
- Create: `backend/app/agent/tools.py`
- Test: `backend/tests/test_agent_tools_project_task.py`

**Interfaces:**
- Produces: `ToolSpec(name, description, input_model, handler, sensitive=False)` (`.input_schema` = JSON schema từ `input_model.model_json_schema()`); `TOOLS: dict[str, ToolSpec]`; `call_tool(db, actor, tool_name, tool_input: dict) -> dict` — parse `tool_input` qua `input_model`, gọi `handler(db, actor, parsed)`; lỗi `HTTPException` từ service → bọc thành `{"error": "forbidden"|"not_found"|"invalid_input", "message": "..."}" (tiếng Việt), KHÔNG raise ra ngoài; parse lỗi (thiếu field) → `{"error": "invalid_input", ...}`.
- Tool: `create_project`, `update_project`, `list_projects`, `create_task`, `update_task`, `list_tasks`, `get_task`, `assign_task`, `unassign_task`.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_agent_tools_project_task.py`:
```python
import pytest

from app.agent.tools import TOOLS, call_tool
from app.models import Project, Role, User, Workspace


async def _ceo(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    return ws, ceo


async def _employee(db, ws):
    e = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
            role=Role.employee)
    db.add(e)
    await db.flush()
    return e


@pytest.mark.asyncio
async def test_create_project_tool_success(db_session):
    ws, ceo = await _ceo(db_session)
    result = await call_tool(db_session, ceo, "create_project", {"name": "Website"})
    assert result["name"] == "Website"
    assert "error" not in result


@pytest.mark.asyncio
async def test_create_project_tool_forbidden_for_employee(db_session):
    ws, ceo = await _ceo(db_session)
    emp = await _employee(db_session, ws)
    result = await call_tool(db_session, emp, "create_project", {"name": "X"})
    assert result == {"error": "forbidden", "message": "Bạn không có quyền làm điều này."}


@pytest.mark.asyncio
async def test_create_task_tool_invalid_input_missing_title(db_session):
    ws, ceo = await _ceo(db_session)
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    await db_session.commit()
    result = await call_tool(db_session, ceo, "create_task", {"project_id": str(project.id)})
    assert result["error"] == "invalid_input"


@pytest.mark.asyncio
async def test_create_get_update_assign_unassign_task_tools_roundtrip(db_session):
    ws, ceo = await _ceo(db_session)
    emp = await _employee(db_session, ws)
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    await db_session.commit()

    created = await call_tool(db_session, ceo, "create_task",
                              {"project_id": str(project.id), "title": "Lam bao cao"})
    assert created["title"] == "Lam bao cao"
    task_id = created["id"]

    assigned = await call_tool(db_session, ceo, "assign_task",
                               {"task_id": task_id, "user_id": str(emp.id)})
    assert assigned["already_assigned"] is False

    fetched = await call_tool(db_session, emp, "get_task", {"task_id": task_id})
    assert str(emp.id) in fetched["assignee_ids"]

    updated = await call_tool(db_session, ceo, "update_task",
                              {"task_id": task_id, "percent": 50})
    assert updated["percent"] == 50

    unassigned = await call_tool(db_session, ceo, "unassign_task",
                                 {"task_id": task_id, "user_id": str(emp.id)})
    assert unassigned["unassigned"] is True


@pytest.mark.asyncio
async def test_list_projects_and_list_tasks_tools_take_no_args(db_session):
    ws, ceo = await _ceo(db_session)
    await call_tool(db_session, ceo, "create_project", {"name": "P1"})
    listed = await call_tool(db_session, ceo, "list_projects", {})
    assert len(listed["projects"]) == 1


def test_all_9_project_task_tools_registered():
    expected = {"create_project", "update_project", "list_projects", "create_task",
               "update_task", "list_tasks", "get_task", "assign_task", "unassign_task"}
    assert expected <= TOOLS.keys()
```

Run: `pytest tests/test_agent_tools_project_task.py -v` → FAIL (ModuleNotFoundError: app.agent.tools).

- [ ] **Step 2: Implement**

`backend/app/agent/tools.py`:
```python
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.schemas import ProjectCreateIn, ProjectPatchIn, TaskCreateIn, TaskPatchIn
from app.services import work_service


@dataclass
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[AsyncSession, User, BaseModel], Awaitable[dict]]
    sensitive: bool = False

    @property
    def input_schema(self) -> dict:
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return schema


TOOLS: dict[str, ToolSpec] = {}


def _register(name: str, description: str, input_model: type[BaseModel],
              handler: Callable, sensitive: bool = False) -> None:
    TOOLS[name] = ToolSpec(name=name, description=description, input_model=input_model,
                          handler=handler, sensitive=sensitive)


_ERROR_LABELS = {403: "forbidden", 404: "not_found", 422: "invalid_input"}
_ERROR_MESSAGES = {
    403: "Bạn không có quyền làm điều này.",
    404: "Không tìm thấy đối tượng được yêu cầu.",
    422: "Dữ liệu đầu vào không hợp lệ.",
}


async def call_tool(db: AsyncSession, actor: User, tool_name: str, tool_input: dict) -> dict:
    """Gọi 1 tool theo tên; lỗi service (HTTPException) bọc thành tool_result lỗi, không raise ra ngoài."""
    spec = TOOLS[tool_name]
    try:
        parsed = spec.input_model(**tool_input)
    except Exception as exc:
        return {"error": "invalid_input", "message": f"Dữ liệu đầu vào không hợp lệ: {exc}"}
    try:
        return await spec.handler(db, actor, parsed)
    except HTTPException as exc:
        label = _ERROR_LABELS.get(exc.status_code, "error")
        message = _ERROR_MESSAGES.get(exc.status_code, str(exc.detail))
        return {"error": label, "message": message}


class NoArgsIn(BaseModel):
    pass


class UpdateProjectToolIn(ProjectPatchIn):
    project_id: uuid.UUID


class GetTaskToolIn(BaseModel):
    task_id: uuid.UUID


class UpdateTaskToolIn(TaskPatchIn):
    task_id: uuid.UUID


class AssignTaskToolIn(BaseModel):
    task_id: uuid.UUID
    user_id: uuid.UUID


class UnassignTaskToolIn(BaseModel):
    task_id: uuid.UUID
    user_id: uuid.UUID


async def _create_project(db, actor, body: ProjectCreateIn) -> dict:
    project = await work_service.create_project(db, actor, **body.model_dump())
    return {"id": str(project.id), "name": project.name, "status": project.status}


async def _update_project(db, actor, body: UpdateProjectToolIn) -> dict:
    patch = body.model_dump(exclude={"project_id"}, exclude_unset=True)
    project = await work_service.update_project(db, actor, body.project_id, patch)
    return {"id": str(project.id), "name": project.name, "status": project.status}


async def _list_projects(db, actor, body: NoArgsIn) -> dict:
    projects = await work_service.list_projects(db, actor)
    return {"projects": [{"id": str(p.id), "name": p.name, "status": p.status} for p in projects]}


async def _create_task(db, actor, body: TaskCreateIn) -> dict:
    task = await work_service.create_task(db, actor, **body.model_dump())
    return {"id": str(task["id"]), "title": task["title"], "status": task["status"].value}


async def _update_task(db, actor, body: UpdateTaskToolIn) -> dict:
    patch = body.model_dump(exclude={"task_id"}, exclude_unset=True)
    task = await work_service.update_task(db, actor, body.task_id, patch)
    return {"id": str(task["id"]), "title": task["title"], "status": task["status"].value,
           "percent": task["percent"]}


async def _list_tasks(db, actor, body: NoArgsIn) -> dict:
    tasks = await work_service.list_tasks(db, actor)
    return {"tasks": [{"id": str(t["id"]), "title": t["title"], "status": t["status"].value,
                       "percent": t["percent"]} for t in tasks]}


async def _get_task(db, actor, body: GetTaskToolIn) -> dict:
    task = await work_service.get_task(db, actor, body.task_id)
    return {"id": str(task["id"]), "title": task["title"], "description": task["description"],
           "status": task["status"].value, "percent": task["percent"],
           "assignee_ids": [str(u) for u in task["assignee_ids"]]}


async def _assign_task(db, actor, body: AssignTaskToolIn) -> dict:
    created = await work_service.assign_task(db, actor, body.task_id, body.user_id)
    return {"task_id": str(body.task_id), "user_id": str(body.user_id), "already_assigned": not created}


async def _unassign_task(db, actor, body: UnassignTaskToolIn) -> dict:
    await work_service.unassign_task(db, actor, body.task_id, body.user_id)
    return {"task_id": str(body.task_id), "user_id": str(body.user_id), "unassigned": True}


_register("create_project", "Tạo project mới (chỉ CEO).", ProjectCreateIn, _create_project)
_register("update_project", "Sửa project theo id (chỉ CEO).", UpdateProjectToolIn, _update_project)
_register("list_projects", "Liệt kê project mà actor được thấy.", NoArgsIn, _list_projects)
_register("create_task", "Tạo task trong 1 project (chỉ CEO).", TaskCreateIn, _create_task)
_register("update_task", "Sửa task theo id (chỉ CEO).", UpdateTaskToolIn, _update_task)
_register("list_tasks", "Liệt kê task mà actor được thấy.", NoArgsIn, _list_tasks)
_register("get_task", "Xem chi tiết 1 task theo id.", GetTaskToolIn, _get_task)
_register("assign_task", "Gán 1 người vào task (chỉ CEO).", AssignTaskToolIn, _assign_task)
_register("unassign_task", "Bỏ gán 1 người khỏi task (chỉ CEO).", UnassignTaskToolIn, _unassign_task)
```

- [ ] **Step 3: Run toàn bộ → PASS (87)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): tool registry core + project/task tools (9)"
```

---

### Task 7: Progress/Comment/Skill tools (9 tool)

**Files:**
- Modify: `backend/app/agent/tools.py`
- Test: `backend/tests/test_agent_tools_progress_skill.py`

**Interfaces:**
- Tool: `add_task_update`, `list_task_updates`, `add_comment`, `list_comments`, `create_skill`, `add_skill_version`, `grant_skill`, `list_skills`, `use_skill`.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_agent_tools_progress_skill.py`:
```python
import pytest

from app.agent.tools import TOOLS, call_tool
from app.models import Project, Role, Task, User, Workspace


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    emp = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
              role=Role.employee)
    db.add(emp)
    await db.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db.add(project)
    await db.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="T", created_by=ceo.id)
    db.add(task)
    await db.flush()
    await db.commit()
    return ws, ceo, emp, task


@pytest.mark.asyncio
async def test_add_task_update_and_list_task_updates_tools(db_session):
    ws, ceo, emp, task = await _world(db_session)
    result = await call_tool(db_session, ceo, "add_task_update",
                             {"task_id": str(task.id), "content": "50%", "percent": 50})
    assert result["percent"] == 50

    listed = await call_tool(db_session, ceo, "list_task_updates", {"task_id": str(task.id)})
    assert len(listed["updates"]) == 1
    assert listed["updates"][0]["content"] == "50%"


@pytest.mark.asyncio
async def test_add_comment_and_list_comments_tools(db_session):
    ws, ceo, emp, task = await _world(db_session)
    result = await call_tool(db_session, ceo, "add_comment",
                             {"task_id": str(task.id), "content": "Nho deadline"})
    assert result["content"] == "Nho deadline"

    listed = await call_tool(db_session, ceo, "list_comments", {"task_id": str(task.id)})
    assert len(listed["comments"]) == 1


@pytest.mark.asyncio
async def test_skill_lifecycle_via_tools(db_session):
    ws, ceo, emp, task = await _world(db_session)
    created = await call_tool(db_session, ceo, "create_skill", {
        "name": "Skill A", "kind": "knowledge", "task_id": str(task.id), "content": "boi canh v1",
    })
    assert created["latest_version"] == 1
    skill_id = created["id"]

    versioned = await call_tool(db_session, ceo, "add_skill_version",
                                {"skill_id": skill_id, "content": "boi canh v2"})
    assert versioned["version"] == 2

    granted = await call_tool(db_session, ceo, "grant_skill",
                              {"skill_id": skill_id, "user_id": str(emp.id)})
    assert granted["already_granted"] is False

    listed = await call_tool(db_session, emp, "list_skills", {})
    assert len(listed["skills"]) == 1

    used = await call_tool(db_session, emp, "use_skill", {"skill_id": skill_id})
    assert used["version"] == 2
    assert used["task_state"]["id"] == str(task.id)


@pytest.mark.asyncio
async def test_use_skill_tool_forbidden_when_not_granted(db_session):
    ws, ceo, emp, task = await _world(db_session)
    created = await call_tool(db_session, ceo, "create_skill", {
        "name": "Skill B", "kind": "knowledge", "content": "boi canh",
    })
    result = await call_tool(db_session, emp, "use_skill", {"skill_id": created["id"]})
    assert result["error"] == "forbidden"


def test_all_9_progress_comment_skill_tools_registered():
    expected = {"add_task_update", "list_task_updates", "add_comment", "list_comments",
               "create_skill", "add_skill_version", "grant_skill", "list_skills", "use_skill"}
    assert expected <= TOOLS.keys()
```

Run: `pytest tests/test_agent_tools_progress_skill.py -v` → FAIL (KeyError: 'add_task_update').

- [ ] **Step 2: Implement**

Sửa import ở đầu `backend/app/agent/tools.py` (thay dòng `from app.schemas import ...` và `from app.services import work_service` hiện có bằng):
```python
from app.schemas import (
    CommentCreateIn, ProjectCreateIn, ProjectPatchIn, SkillCreateIn, SkillGrantIn,
    SkillVersionIn, TaskCreateIn, TaskPatchIn, TaskUpdateCreateIn,
)
from app.services import skill_service, work_service
```

Thêm vào cuối `backend/app/agent/tools.py`:
```python
class AddTaskUpdateToolIn(TaskUpdateCreateIn):
    task_id: uuid.UUID


class ListTaskUpdatesToolIn(BaseModel):
    task_id: uuid.UUID


class AddCommentToolIn(CommentCreateIn):
    task_id: uuid.UUID


class ListCommentsToolIn(BaseModel):
    task_id: uuid.UUID


class AddSkillVersionToolIn(SkillVersionIn):
    skill_id: uuid.UUID


class GrantSkillToolIn(SkillGrantIn):
    skill_id: uuid.UUID


class UseSkillToolIn(BaseModel):
    skill_id: uuid.UUID


def _skill_tool_out(skill: dict) -> dict:
    return {"id": str(skill["id"]), "name": skill["name"], "kind": skill["kind"].value,
           "task_id": str(skill["task_id"]) if skill["task_id"] else None,
           "latest_version": skill["latest_version"]}


async def _add_task_update(db, actor, body: AddTaskUpdateToolIn) -> dict:
    patch = body.model_dump(exclude={"task_id"})
    upd = await work_service.add_task_update(db, actor, body.task_id, **patch)
    return {"id": str(upd.id), "task_id": str(upd.task_id), "percent": upd.percent,
           "status": upd.status.value if upd.status else None}


async def _list_task_updates(db, actor, body: ListTaskUpdatesToolIn) -> dict:
    updates = await work_service.list_task_updates(db, actor, body.task_id)
    return {"updates": [{"id": str(u.id), "author_id": str(u.author_id), "content": u.content,
                         "percent": u.percent, "created_at": u.created_at.isoformat()}
                        for u in updates]}


async def _add_comment(db, actor, body: AddCommentToolIn) -> dict:
    comment = await work_service.add_comment(db, actor, body.task_id, body.content)
    return {"id": str(comment.id), "task_id": str(comment.task_id), "content": comment.content}


async def _list_comments(db, actor, body: ListCommentsToolIn) -> dict:
    comments = await work_service.list_comments(db, actor, body.task_id)
    return {"comments": [{"id": str(c.id), "author_id": str(c.author_id), "content": c.content,
                          "created_at": c.created_at.isoformat()} for c in comments]}


async def _create_skill(db, actor, body: SkillCreateIn) -> dict:
    skill = await skill_service.create_skill(db, actor, **body.model_dump())
    return _skill_tool_out(skill)


async def _add_skill_version(db, actor, body: AddSkillVersionToolIn) -> dict:
    version = await skill_service.add_version(db, actor, body.skill_id, body.content)
    return {"skill_id": str(body.skill_id), "version": version}


async def _grant_skill(db, actor, body: GrantSkillToolIn) -> dict:
    created = await skill_service.grant_skill(db, actor, body.skill_id, body.user_id)
    return {"skill_id": str(body.skill_id), "user_id": str(body.user_id),
           "already_granted": not created}


async def _list_skills(db, actor, body: NoArgsIn) -> dict:
    skills = await skill_service.list_skills(db, actor)
    return {"skills": [_skill_tool_out(s) for s in skills]}


async def _use_skill(db, actor, body: UseSkillToolIn) -> dict:
    return await skill_service.use_skill(db, actor, body.skill_id)


_register("add_task_update", "Cập nhật tiến độ 1 task (% và/hoặc trạng thái).",
          AddTaskUpdateToolIn, _add_task_update)
_register("list_task_updates", "Lịch sử cập nhật tiến độ của 1 task, mới nhất trước.",
          ListTaskUpdatesToolIn, _list_task_updates)
_register("add_comment", "Thêm bình luận vào 1 task.", AddCommentToolIn, _add_comment)
_register("list_comments", "Liệt kê bình luận của 1 task.", ListCommentsToolIn, _list_comments)
_register("create_skill", "Tạo skill mới kèm nội dung version 1 (chỉ CEO).",
          SkillCreateIn, _create_skill)
_register("add_skill_version", "Thêm version nội dung mới cho skill (chỉ CEO).",
          AddSkillVersionToolIn, _add_skill_version)
_register("grant_skill", "Cấp quyền dùng skill cho 1 người (chỉ CEO).",
          GrantSkillToolIn, _grant_skill)
_register("list_skills", "Liệt kê skill actor được thấy/được cấp.", NoArgsIn, _list_skills)
_register("use_skill", "Dùng skill: lấy nội dung version mới nhất + trạng thái task sống.",
          UseSkillToolIn, _use_skill)
```

- [ ] **Step 3: Run toàn bộ → PASS (92)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): progress/comment/skill tools (9)"
```

---

### Task 8: Account tools (3 tool) + `SENSITIVE_TOOLS`

**Files:**
- Modify: `backend/app/agent/tools.py`
- Test: `backend/tests/test_agent_tools_account.py`

**Interfaces:**
- Produces: `SENSITIVE_TOOLS: frozenset[str]` — suy ra tự động từ `spec.sensitive` của mọi tool đã đăng ký (không liệt kê tay).
- Tool: `create_invite`, `lock_user` (sensitive), `unlock_user` (sensitive).

- [ ] **Step 1: Viết test fail**

`backend/tests/test_agent_tools_account.py`:
```python
import pytest

from app.agent.tools import SENSITIVE_TOOLS, TOOLS, call_tool
from app.models import Role, User, UserStatus, Workspace


async def _ceo(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    return ws, ceo


@pytest.mark.asyncio
async def test_create_invite_tool(db_session):
    ws, ceo = await _ceo(db_session)
    result = await call_tool(db_session, ceo, "create_invite", {"role": "manager"})
    assert result["role"] == "manager"
    assert "token" in result


@pytest.mark.asyncio
async def test_lock_and_unlock_user_tools(db_session):
    ws, ceo = await _ceo(db_session)
    emp = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
              role=Role.employee)
    db_session.add(emp)
    await db_session.flush()
    await db_session.commit()

    locked = await call_tool(db_session, ceo, "lock_user", {"target_id": str(emp.id)})
    assert locked == {"user_id": str(emp.id), "locked": True}
    await db_session.refresh(emp)
    assert emp.status == UserStatus.locked

    unlocked = await call_tool(db_session, ceo, "unlock_user", {"target_id": str(emp.id)})
    assert unlocked == {"user_id": str(emp.id), "locked": False}


@pytest.mark.asyncio
async def test_lock_root_ceo_tool_is_forbidden(db_session):
    ws, ceo = await _ceo(db_session)
    result = await call_tool(db_session, ceo, "lock_user", {"target_id": str(ceo.id)})
    assert result["error"] == "forbidden"


def test_lock_and_unlock_are_marked_sensitive():
    assert SENSITIVE_TOOLS == {"lock_user", "unlock_user"}
    assert TOOLS["create_invite"].sensitive is False
```

Run: `pytest tests/test_agent_tools_account.py -v` → FAIL (KeyError: 'create_invite').

- [ ] **Step 2: Implement**

Sửa dòng `from app.models import User` ở đầu `backend/app/agent/tools.py` thành `from app.models import Role, User`, và thêm `from app.services import auth_service` vào dòng import service hiện có (`from app.services import auth_service, skill_service, work_service`).

Thêm vào cuối `backend/app/agent/tools.py`:
```python
class CreateInviteToolIn(BaseModel):
    role: Role
    manager_id: uuid.UUID | None = None


class LockUserToolIn(BaseModel):
    target_id: uuid.UUID


class UnlockUserToolIn(BaseModel):
    target_id: uuid.UUID


async def _create_invite(db, actor, body: CreateInviteToolIn) -> dict:
    invite = await auth_service.create_invite(db, actor=actor, role=body.role,
                                              manager_id=body.manager_id)
    return {"token": invite.token, "role": invite.role.value,
           "expires_at": invite.expires_at.isoformat()}


async def _lock_user(db, actor, body: LockUserToolIn) -> dict:
    await auth_service.lock_user(db, actor, body.target_id)
    return {"user_id": str(body.target_id), "locked": True}


async def _unlock_user(db, actor, body: UnlockUserToolIn) -> dict:
    await auth_service.unlock_user(db, actor, body.target_id)
    return {"user_id": str(body.target_id), "locked": False}


_register("create_invite", "Tạo lời mời vào workspace kèm vai trò (chỉ CEO).",
          CreateInviteToolIn, _create_invite)
_register("lock_user", "Khóa tài khoản 1 người — đăng xuất khỏi mọi thiết bị "
          "(chỉ CEO, hành động nhạy cảm, cần xác nhận).", LockUserToolIn, _lock_user,
          sensitive=True)
_register("unlock_user", "Mở khóa tài khoản 1 người (chỉ CEO, hành động nhạy cảm, cần xác nhận).",
          UnlockUserToolIn, _unlock_user, sensitive=True)


SENSITIVE_TOOLS: frozenset[str] = frozenset(
    name for name, spec in TOOLS.items() if spec.sensitive
)
```

- [ ] **Step 3: Run toàn bộ → PASS (96)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): account tools (create_invite/lock_user/unlock_user) + SENSITIVE_TOOLS"
```

---

### Task 9: Agent loop — luồng chính (stream, tool_use, hoàn tất)

**Files:**
- Create: `backend/app/agent/loop.py`
- Test: `backend/tests/test_agent_loop_basic.py`

**Interfaces:**
- Produces: `SYSTEM_PROMPT: str` (đóng băng, không timestamp/tên user); `run_agent_loop(db, req: ChatRequest, llm: LLMClient, publisher: EventPublisher) -> None` — nạp history từ `messages`, gọi `llm.stream()`, publish `token` cho từng `TextDelta`; hết `TextDelta` gặp `StreamDone`: nếu `stop_reason != "tool_use"` → lưu `Message(assistant)` + `UsageLog`, `status=done`, publish `request_done`, return. Nếu có tool nhạy cảm (`name in SENSITIVE_TOOLS`) trong `tool_uses` → `status=awaiting_confirmation`, lưu `pending_action`, publish `confirmation_required`, return (KHÔNG thực thi tool). Ngược lại → thực thi mọi tool qua `call_tool`, lưu `Message(user, tool_result)`, lặp lại (gọi Claude tiếp) tới khi `end_turn`.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_agent_loop_basic.py`:
```python
import pytest
from sqlalchemy import select

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta, ToolUseBlock
from app.agent.loop import run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    ChatRequest, Conversation, Message, MessageRole, Project, Role, User, UserStatus, Workspace,
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


def _make_request(ws, conv, ceo, content="xin chao"):
    return ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                       content=content, queue_position=1.0)


@pytest.mark.asyncio
async def test_text_only_response_completes_request(db_session):
    ws, ceo, conv = await _world(db_session)
    req = _make_request(ws, conv, ceo)
    db_session.add(req)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[[
        TextDelta(text="Chao "), TextDelta(text="ban"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=10, output_tokens=3),
    ]])
    pub = FakeEventPublisher()

    await run_agent_loop(db_session, req, llm, pub)

    assert req.status.value == "done"
    assert req.result_summary == "Chao ban"
    tokens = [e for _, e in pub.events if e["type"] == "token"]
    assert [t["text"] for t in tokens] == ["Chao ", "ban"]
    assert any(e["type"] == "request_done" for _, e in pub.events)


@pytest.mark.asyncio
async def test_non_sensitive_tool_executes_and_loop_continues(db_session):
    ws, ceo, conv = await _world(db_session)
    req = _make_request(ws, conv, ceo, content="tao project Website")
    db_session.add(req)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="create_project",
                                            input={"name": "Website"})],
                    stop_reason="tool_use", input_tokens=20, output_tokens=8)],
        [TextDelta(text="Da tao xong."),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=15, output_tokens=4)],
    ])
    pub = FakeEventPublisher()

    await run_agent_loop(db_session, req, llm, pub)

    assert req.status.value == "done"
    project = (await db_session.execute(select(Project))).scalar_one()
    assert project.name == "Website"
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_sensitive_tool_pauses_for_confirmation_without_executing(db_session):
    ws, ceo, conv = await _world(db_session)
    target = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
                 role=Role.employee)
    db_session.add(target)
    await db_session.flush()
    req = _make_request(ws, conv, ceo, content="khoa tai khoan e@a.vn")
    db_session.add(req)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="lock_user",
                                            input={"target_id": str(target.id)})],
                    stop_reason="tool_use", input_tokens=12, output_tokens=6)],
    ])
    pub = FakeEventPublisher()

    await run_agent_loop(db_session, req, llm, pub)

    assert req.status.value == "awaiting_confirmation"
    assert req.pending_action["tool_name"] == "lock_user"
    await db_session.refresh(target)
    assert target.status == UserStatus.active
    assert any(e["type"] == "confirmation_required" for _, e in pub.events)
    assert len(llm.calls) == 1
```

Run: `pytest tests/test_agent_loop_basic.py -v` → FAIL (ModuleNotFoundError: app.agent.loop).

- [ ] **Step 2: Implement**

`backend/app/agent/loop.py`:
```python
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_client import LLMClient, StreamDone, TextDelta
from app.agent.publisher import EventPublisher
from app.agent.tools import SENSITIVE_TOOLS, TOOLS, call_tool
from app.config import get_settings
from app.models import ChatRequest, ChatRequestStatus, Message, MessageRole, UsageLog, User

SYSTEM_PROMPT = (
    "Ban la tro ly AI quan ly cong viec. Thuc hien yeu cau cua nguoi dung bang cach "
    "goi tool phu hop. Neu tool tra ve error, hay bao lai ro rang cho nguoi dung, "
    "khong tu suy dien hoac chon doi tuong thay the."
)


def _tool_specs_for_api() -> list[dict]:
    return [{"name": name, "description": spec.description, "input_schema": spec.input_schema}
           for name, spec in TOOLS.items()]


async def _load_history(db: AsyncSession, conversation_id: uuid.UUID) -> list[dict]:
    rows = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    return [{"role": m.role.value, "content": m.content} for m in rows.scalars()]


async def run_agent_loop(db: AsyncSession, req: ChatRequest, llm: LLMClient,
                        publisher: EventPublisher) -> None:
    """Chạy agent loop cho 1 chat_request tới khi end_turn hoặc awaiting_confirmation."""
    req.status = ChatRequestStatus.running
    req.started_at = datetime.now(timezone.utc)
    await db.commit()

    actor = await db.get(User, req.user_id)

    while True:
        history = await _load_history(db, req.conversation_id)
        text_parts: list[str] = []
        done: StreamDone | None = None
        async for event in llm.stream(system=SYSTEM_PROMPT, messages=history,
                                      tools=_tool_specs_for_api()):
            if isinstance(event, TextDelta):
                text_parts.append(event.text)
                await publisher.publish(req.conversation_id,
                                        {"type": "token", "chat_request_id": str(req.id),
                                         "text": event.text})
            else:
                done = event

        assistant_content: list[dict] = []
        if text_parts:
            assistant_content.append({"type": "text", "text": "".join(text_parts)})
        for tu in done.tool_uses:
            assistant_content.append({"type": "tool_use", "id": tu.id, "name": tu.name,
                                      "input": tu.input})
        db.add(Message(workspace_id=req.workspace_id, conversation_id=req.conversation_id,
                       chat_request_id=req.id, role=MessageRole.assistant,
                       content=assistant_content))
        db.add(UsageLog(workspace_id=req.workspace_id, chat_request_id=req.id,
                        model=get_settings().model_chat, input_tokens=done.input_tokens,
                        output_tokens=done.output_tokens,
                        cache_read_tokens=done.cache_read_tokens,
                        cache_write_tokens=done.cache_write_tokens))

        if done.stop_reason != "tool_use" or not done.tool_uses:
            req.status = ChatRequestStatus.done
            req.finished_at = datetime.now(timezone.utc)
            req.result_summary = "".join(text_parts)[:500]
            await db.commit()
            await publisher.publish(req.conversation_id,
                                    {"type": "request_done", "chat_request_id": str(req.id),
                                     "result_summary": req.result_summary})
            return

        first_sensitive = next((tu for tu in done.tool_uses if tu.name in SENSITIVE_TOOLS), None)
        if first_sensitive is not None:
            req.status = ChatRequestStatus.awaiting_confirmation
            req.pending_action = {"tool_name": first_sensitive.name,
                                  "tool_input": first_sensitive.input,
                                  "tool_use_id": first_sensitive.id}
            await db.commit()
            await publisher.publish(req.conversation_id,
                                    {"type": "confirmation_required", "chat_request_id": str(req.id),
                                     "tool_name": first_sensitive.name,
                                     "tool_input": first_sensitive.input})
            return

        tool_results = []
        for tu in done.tool_uses:
            result = await call_tool(db, actor, tu.name, tu.input)
            tool_results.append({"type": "tool_result", "tool_use_id": tu.id,
                                 "content": json.dumps(result, default=str)})
        db.add(Message(workspace_id=req.workspace_id, conversation_id=req.conversation_id,
                       chat_request_id=req.id, role=MessageRole.user, content=tool_results))
        await db.commit()
```

- [ ] **Step 3: Run toàn bộ → PASS (99)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): agent loop - stream/tool_use/completion/confirmation-pause"
```

---

### Task 10: Xử lý xác nhận hành động nhạy cảm (`resolve_confirmation`)

**Files:**
- Modify: `backend/app/agent/loop.py`
- Test: `backend/tests/test_agent_loop_confirmation.py`

**Interfaces:**
- Produces: `resolve_confirmation(db, req: ChatRequest, approved: bool) -> None` — approve: thực thi tool đang `pending_action` qua `call_tool` (quyền được **check lại** lúc này); deny: tool_result lỗi `user_denied`. Cả 2 trường hợp: lưu `Message(user, tool_result)`, xóa `pending_action`, `status=queued` (để `run_agent_loop` chạy lại lượt kế tiếp và thấy tool_result này trong history — không cần logic "resume" riêng).

- [ ] **Step 1: Viết test fail**

`backend/tests/test_agent_loop_confirmation.py`:
```python
import json

import pytest
from sqlalchemy import select

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.loop import resolve_confirmation, run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, Role, User, UserStatus, Workspace,
)


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    target = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
                  role=Role.employee)
    db.add_all([ceo, target])
    await db.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db.add(conv)
    await db.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="khoa e@a.vn", queue_position=1.0,
                      status=ChatRequestStatus.awaiting_confirmation,
                      pending_action={"tool_name": "lock_user",
                                     "tool_input": {"target_id": str(target.id)},
                                     "tool_use_id": "t1"})
    db.add(req)
    await db.flush()
    await db.commit()
    return ws, ceo, target, conv, req


@pytest.mark.asyncio
async def test_resolve_confirmation_approved_executes_tool_and_requeues(db_session):
    ws, ceo, target, conv, req = await _world(db_session)

    await resolve_confirmation(db_session, req, approved=True)

    await db_session.refresh(target)
    assert target.status == UserStatus.locked
    assert req.status == ChatRequestStatus.queued
    assert req.pending_action is None

    msgs = (await db_session.execute(select(Message))).scalars().all()
    tool_result = [m for m in msgs if m.content[0]["type"] == "tool_result"][0]
    assert json.loads(tool_result.content[0]["content"])["locked"] is True


@pytest.mark.asyncio
async def test_resolve_confirmation_denied_does_not_execute_tool(db_session):
    ws, ceo, target, conv, req = await _world(db_session)

    await resolve_confirmation(db_session, req, approved=False)

    await db_session.refresh(target)
    assert target.status == UserStatus.active
    assert req.status == ChatRequestStatus.queued
    msgs = (await db_session.execute(select(Message))).scalars().all()
    tool_result = [m for m in msgs if m.content[0]["type"] == "tool_result"][0]
    assert json.loads(tool_result.content[0]["content"])["error"] == "user_denied"


@pytest.mark.asyncio
async def test_run_agent_loop_completes_after_confirmation_resolved(db_session):
    ws, ceo, target, conv, req = await _world(db_session)
    await resolve_confirmation(db_session, req, approved=True)

    llm = FakeLLMClient(turns=[[
        TextDelta(text="Da khoa tai khoan."),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=8, output_tokens=4),
    ]])
    pub = FakeEventPublisher()
    await run_agent_loop(db_session, req, llm, pub)

    assert req.status == ChatRequestStatus.done
    sent_messages = llm.calls[0]["messages"]
    assert any(
        isinstance(block, dict) and block.get("type") == "tool_result"
        for msg in sent_messages for block in msg["content"]
    )
```

Run: `pytest tests/test_agent_loop_confirmation.py -v` → FAIL (ImportError: resolve_confirmation).

- [ ] **Step 2: Implement — thêm vào cuối `backend/app/agent/loop.py`**

```python
async def resolve_confirmation(db: AsyncSession, req: ChatRequest, approved: bool) -> None:
    """Xử lý xác nhận (hoặc từ chối) hành động nhạy cảm đang chờ; đưa request về
    queued để lần chạy run_agent_loop tiếp theo tự thấy tool_result trong history."""
    if req.pending_action is None:
        raise ValueError("no_pending_action")
    actor = await db.get(User, req.user_id)
    action = req.pending_action
    if approved:
        result = await call_tool(db, actor, action["tool_name"], action["tool_input"])
    else:
        result = {"error": "user_denied", "message": "Người dùng từ chối xác nhận hành động này."}
    db.add(Message(workspace_id=req.workspace_id, conversation_id=req.conversation_id,
                   chat_request_id=req.id, role=MessageRole.user,
                   content=[{"type": "tool_result", "tool_use_id": action["tool_use_id"],
                            "content": json.dumps(result, default=str)}]))
    req.pending_action = None
    req.status = ChatRequestStatus.queued
    await db.commit()
```

- [ ] **Step 3: Run toàn bộ → PASS (102)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): resolve_confirmation - approve/deny sensitive tool, requeue"
```

---

### Task 11: Dừng (cancel) + xử lý lỗi hạ tầng trong agent loop

**Files:**
- Modify: `backend/app/agent/loop.py`
- Test: `backend/tests/test_agent_loop_cancel_error.py`

**Interfaces:**
- Sửa `run_agent_loop` — thêm tham số `is_cancelled: Callable[[uuid.UUID], Awaitable[bool]] | None = None` (mặc định không bao giờ hủy — giữ tương thích các test Task 9/10 không truyền tham số này). Check `is_cancelled(req.id)` trước mỗi lượt gọi Claude VÀ trước khi xử lý mỗi event stream — thấy `True` → `status=cancelled`, publish `status_update`, dừng ngay, giữ nguyên token đã stream trước đó. Toàn bộ thân hàm bọc `try/except Exception` — lỗi hạ tầng (429, DB...) → `status=failed`, ghi `error`, publish `request_failed`, **không raise ra ngoài** (để `process_conversation`, Task 12, tự chuyển sang request kế tiếp).

- [ ] **Step 1: Viết test fail**

`backend/tests/test_agent_loop_cancel_error.py`:
```python
import pytest

from app.agent.llm_client import FakeLLMClient, LLMClient, StreamDone, TextDelta
from app.agent.loop import run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Role, User, Workspace,
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
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="xin chao", queue_position=1.0)
    db.add(req)
    await db.flush()
    db.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                   role=MessageRole.user, content=[{"type": "text", "text": "xin chao"}]))
    await db.commit()
    return req


@pytest.mark.asyncio
async def test_cancelled_before_first_call_stops_immediately(db_session):
    req = await _world(db_session)
    llm = FakeLLMClient(turns=[])  # không được gọi
    pub = FakeEventPublisher()

    async def always_cancelled(_id):
        return True

    await run_agent_loop(db_session, req, llm, pub, is_cancelled=always_cancelled)

    assert req.status == ChatRequestStatus.cancelled
    assert len(llm.calls) == 0
    assert any(e["status"] == "cancelled" for _, e in pub.events)


@pytest.mark.asyncio
async def test_cancelled_mid_stream_keeps_partial_tokens_and_stops(db_session):
    req = await _world(db_session)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="Dang "), TextDelta(text="lam"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])
    pub = FakeEventPublisher()
    calls = {"n": 0}

    async def cancel_on_third_check(_id):
        # 3 lần check trước khi hủy: (1) đầu while, (2) trước token "Dang ", (3) trước token "lam" -> True
        calls["n"] += 1
        return calls["n"] > 2

    await run_agent_loop(db_session, req, llm, pub, is_cancelled=cancel_on_third_check)

    assert req.status == ChatRequestStatus.cancelled
    tokens = [e for _, e in pub.events if e["type"] == "token"]
    assert len(tokens) == 1
    assert tokens[0]["text"] == "Dang "


@pytest.mark.asyncio
async def test_llm_error_marks_request_failed_without_raising(db_session):
    req = await _world(db_session)

    class _RaisingLLMClient(LLMClient):
        async def stream(self, *, system, messages, tools):
            raise RuntimeError("rate_limited_429")
            yield  # pragma: no cover - giữ hàm là generator

    pub = FakeEventPublisher()
    await run_agent_loop(db_session, req, _RaisingLLMClient(), pub)

    assert req.status == ChatRequestStatus.failed
    assert "rate_limited_429" in req.error
    assert any(e["type"] == "request_failed" for _, e in pub.events)
```

Run: `pytest tests/test_agent_loop_cancel_error.py -v` → FAIL (`run_agent_loop() got an unexpected keyword argument 'is_cancelled'`).

- [ ] **Step 2: Implement**

Sửa đầu `backend/app/agent/loop.py` (thêm `from typing import Awaitable, Callable` vào import), và thay **toàn bộ** hàm `run_agent_loop` hiện có bằng bản sau (thêm `is_cancelled` + bọc try/except):
```python
async def _never_cancelled(_request_id: uuid.UUID) -> bool:
    return False


async def run_agent_loop(
    db: AsyncSession, req: ChatRequest, llm: LLMClient, publisher: EventPublisher,
    is_cancelled: Callable[[uuid.UUID], Awaitable[bool]] | None = None,
) -> None:
    """Chạy agent loop cho 1 chat_request tới khi end_turn / awaiting_confirmation /
    cancelled / failed. Không bao giờ raise — mọi lỗi hạ tầng chuyển thành status=failed."""
    check_cancelled = is_cancelled or _never_cancelled
    req.status = ChatRequestStatus.running
    req.started_at = datetime.now(timezone.utc)
    await db.commit()

    actor = await db.get(User, req.user_id)

    async def _cancel_and_exit() -> None:
        req.status = ChatRequestStatus.cancelled
        req.finished_at = datetime.now(timezone.utc)
        await db.commit()
        await publisher.publish(req.conversation_id,
                                {"type": "status_update", "chat_request_id": str(req.id),
                                 "status": "cancelled"})

    try:
        while True:
            if await check_cancelled(req.id):
                await _cancel_and_exit()
                return

            history = await _load_history(db, req.conversation_id)
            text_parts: list[str] = []
            done: StreamDone | None = None
            async for event in llm.stream(system=SYSTEM_PROMPT, messages=history,
                                          tools=_tool_specs_for_api()):
                if await check_cancelled(req.id):
                    await _cancel_and_exit()
                    return
                if isinstance(event, TextDelta):
                    text_parts.append(event.text)
                    await publisher.publish(req.conversation_id,
                                            {"type": "token", "chat_request_id": str(req.id),
                                             "text": event.text})
                else:
                    done = event

            assistant_content: list[dict] = []
            if text_parts:
                assistant_content.append({"type": "text", "text": "".join(text_parts)})
            for tu in done.tool_uses:
                assistant_content.append({"type": "tool_use", "id": tu.id, "name": tu.name,
                                          "input": tu.input})
            db.add(Message(workspace_id=req.workspace_id, conversation_id=req.conversation_id,
                           chat_request_id=req.id, role=MessageRole.assistant,
                           content=assistant_content))
            db.add(UsageLog(workspace_id=req.workspace_id, chat_request_id=req.id,
                            model=get_settings().model_chat, input_tokens=done.input_tokens,
                            output_tokens=done.output_tokens,
                            cache_read_tokens=done.cache_read_tokens,
                            cache_write_tokens=done.cache_write_tokens))

            if done.stop_reason != "tool_use" or not done.tool_uses:
                req.status = ChatRequestStatus.done
                req.finished_at = datetime.now(timezone.utc)
                req.result_summary = "".join(text_parts)[:500]
                await db.commit()
                await publisher.publish(req.conversation_id,
                                        {"type": "request_done", "chat_request_id": str(req.id),
                                         "result_summary": req.result_summary})
                return

            first_sensitive = next((tu for tu in done.tool_uses if tu.name in SENSITIVE_TOOLS),
                                   None)
            if first_sensitive is not None:
                req.status = ChatRequestStatus.awaiting_confirmation
                req.pending_action = {"tool_name": first_sensitive.name,
                                      "tool_input": first_sensitive.input,
                                      "tool_use_id": first_sensitive.id}
                await db.commit()
                await publisher.publish(req.conversation_id,
                                        {"type": "confirmation_required",
                                         "chat_request_id": str(req.id),
                                         "tool_name": first_sensitive.name,
                                         "tool_input": first_sensitive.input})
                return

            tool_results = []
            for tu in done.tool_uses:
                result = await call_tool(db, actor, tu.name, tu.input)
                tool_results.append({"type": "tool_result", "tool_use_id": tu.id,
                                     "content": json.dumps(result, default=str)})
            db.add(Message(workspace_id=req.workspace_id, conversation_id=req.conversation_id,
                           chat_request_id=req.id, role=MessageRole.user, content=tool_results))
            await db.commit()
    except Exception as exc:
        req.status = ChatRequestStatus.failed
        req.error = str(exc)
        req.finished_at = datetime.now(timezone.utc)
        await db.commit()
        await publisher.publish(req.conversation_id,
                                {"type": "request_failed", "chat_request_id": str(req.id),
                                 "error": str(exc)})
```

- [ ] **Step 3: Run toàn bộ → PASS (105)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): agent loop - cancel flag + infra error handling"
```

---

### Task 12: Worker entrypoint — `process_conversation` + `WorkerSettings`

**Files:**
- Create: `backend/app/agent/worker.py`
- Test: `backend/tests/test_worker.py`

**Interfaces:**
- Produces: `process_conversation(ctx: dict, conversation_id: uuid.UUID) -> None` — arq job; lặp: lấy `chat_requests` `queued` có `queue_position` nhỏ nhất của conversation, chạy `run_agent_loop`, lặp tới khi hết `queued` (`ctx` chứa `session_factory`, `llm_client`, `event_publisher`, `is_cancelled` — set trong `_startup`, inject trực tiếp trong test). `enqueue_conversation(arq_pool, conversation_id) -> Any` — `arq_pool.enqueue_job("process_conversation", conversation_id, _job_id=f"conv:{conversation_id}")`. `WorkerSettings` (class arq đọc khi chạy `arq app.agent.worker.WorkerSettings`) — `functions=[process_conversation]`, `redis_settings` từ `settings.redis_url`.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_worker.py`:
```python
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.publisher import FakeEventPublisher
from app.agent.worker import WorkerSettings, enqueue_conversation, process_conversation
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Role, User, Workspace,
)


@pytest.mark.asyncio
async def test_process_conversation_runs_queued_requests_in_order_then_stops(engine, db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    other_conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add_all([conv, other_conv])
    await db_session.flush()

    req1 = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                       content="mot", queue_position=1.0)
    req2 = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                       content="hai", queue_position=2.0)
    other_req = ChatRequest(workspace_id=ws.id, conversation_id=other_conv.id, user_id=ceo.id,
                            content="khac conversation", queue_position=1.0)
    db_session.add_all([req1, req2, other_req])
    await db_session.flush()
    for req in (req1, req2, other_req):
        db_session.add(Message(workspace_id=ws.id, conversation_id=req.conversation_id,
                               chat_request_id=req.id, role=MessageRole.user,
                               content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[
        [TextDelta(text="tra loi 1"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
        [TextDelta(text="tra loi 2"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
    ])
    pub = FakeEventPublisher()

    async def never_cancelled(_id):
        return False

    ctx = {
        "session_factory": async_sessionmaker(engine, expire_on_commit=False),
        "llm_client": llm,
        "event_publisher": pub,
        "is_cancelled": never_cancelled,
    }

    await process_conversation(ctx, conv.id)

    await db_session.refresh(req1)
    await db_session.refresh(req2)
    await db_session.refresh(other_req)
    assert req1.status == ChatRequestStatus.done
    assert req2.status == ChatRequestStatus.done
    assert other_req.status == ChatRequestStatus.queued  # conversation khác không bị đụng tới
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_enqueue_conversation_uses_conversation_scoped_job_id():
    class _FakePool:
        def __init__(self):
            self.calls = []

        async def enqueue_job(self, name, *args, **kwargs):
            self.calls.append((name, args, kwargs))
            return "job-handle"

    pool = _FakePool()
    conv_id = uuid.uuid4()
    result = await enqueue_conversation(pool, conv_id)

    assert result == "job-handle"
    name, args, kwargs = pool.calls[0]
    assert name == "process_conversation"
    assert args == (conv_id,)
    assert kwargs["_job_id"] == f"conv:{conv_id}"


def test_worker_settings_registers_process_conversation():
    assert process_conversation in WorkerSettings.functions
    assert WorkerSettings.redis_settings is not None
```

Run: `pytest tests/test_worker.py -v` → FAIL (ModuleNotFoundError: app.agent.worker).

- [ ] **Step 2: Implement**

`backend/app/agent/worker.py`:
```python
from __future__ import annotations

import uuid

from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.llm_client import get_llm_client
from app.agent.loop import run_agent_loop
from app.agent.publisher import get_event_publisher
from app.config import get_settings
from app.models import ChatRequest, ChatRequestStatus


async def process_conversation(ctx: dict, conversation_id: uuid.UUID) -> None:
    """arq job: xử lý lần lượt mọi chat_request `queued` của 1 conversation tới khi hết."""
    session_factory = ctx["session_factory"]
    llm = ctx["llm_client"]
    publisher = ctx["event_publisher"]
    is_cancelled = ctx["is_cancelled"]

    while True:
        async with session_factory() as db:
            req = (await db.execute(
                select(ChatRequest).where(
                    ChatRequest.conversation_id == conversation_id,
                    ChatRequest.status == ChatRequestStatus.queued,
                ).order_by(ChatRequest.queue_position.asc()).limit(1)
            )).scalar_one_or_none()
            if req is None:
                return
            await run_agent_loop(db, req, llm, publisher, is_cancelled=is_cancelled)


async def enqueue_conversation(arq_pool, conversation_id: uuid.UUID):
    return await arq_pool.enqueue_job("process_conversation", conversation_id,
                                      _job_id=f"conv:{conversation_id}")


async def _is_cancelled_redis(ctx: dict, request_id: uuid.UUID) -> bool:
    return bool(await ctx["redis"].exists(f"cancel:{request_id}"))


async def _startup(ctx: dict) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    ctx["engine"] = engine
    ctx["session_factory"] = async_sessionmaker(engine, expire_on_commit=False)
    ctx["llm_client"] = get_llm_client()
    ctx["event_publisher"] = get_event_publisher()
    import redis.asyncio as redis_asyncio
    ctx["redis"] = redis_asyncio.from_url(settings.redis_url)
    ctx["is_cancelled"] = lambda request_id: _is_cancelled_redis(ctx, request_id)


async def _shutdown(ctx: dict) -> None:
    await ctx["engine"].dispose()
    await ctx["redis"].close()


class WorkerSettings:
    functions = [process_conversation]
    on_startup = _startup
    on_shutdown = _shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
```

- [ ] **Step 3: Run toàn bộ → PASS (108)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): arq worker - process_conversation loop + WorkerSettings"
```

---

### Task 13: REST — conversations + gửi tin nhắn (enqueue)

**Files:**
- Create: `backend/app/api/chat.py`
- Modify: `backend/app/schemas.py`, `backend/app/main.py`
- Test: `backend/tests/test_chat_api.py`

**Interfaces:**
- `POST /api/v1/conversations {title?}` → 201 `ConversationOut`. `GET /api/v1/conversations` → list `ConversationOut` của **chính actor** (`user_id == actor.id`), mới nhất trước.
- `POST /api/v1/conversations/{id}/messages {content}` → 201 `ChatRequestOut` (status=`queued`) — insert `chat_requests` + `messages(role=user)`, `queue_position` = max hiện có của conversation +1, gọi `enqueue_conversation(arq_pool, conversation_id)`. Conversation không thuộc actor/khác workspace → 404.
- `get_arq_pool(request: Request)` — đọc `request.app.state.arq_pool` (khởi tạo lúc `startup`, Task này thêm event `startup`/`shutdown` vào `main.py`); test override bằng pool giả.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_chat_api.py`:
```python
import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.chat import get_arq_pool
from app.db import get_db
from app.main import create_app
from tests.conftest import _ceo_headers, _invite_and_join


class _FakeArqPool:
    def __init__(self):
        self.enqueued = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.enqueued.append((name, args, kwargs))
        return "job"


@pytest.fixture
async def chat_client(engine):
    app = create_app()
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            yield session

    fake_pool = _FakeArqPool()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_arq_pool] = lambda: fake_pool
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, fake_pool


@pytest.mark.asyncio
async def test_create_and_list_own_conversations(chat_client):
    client, _ = chat_client
    ceo_h = await _ceo_headers(client)
    created = await client.post("/api/v1/conversations", headers=ceo_h,
                                json={"title": "Cong viec"})
    assert created.status_code == 201
    listed = await client.get("/api/v1/conversations", headers=ceo_h)
    assert [c["title"] for c in listed.json()] == ["Cong viec"]


@pytest.mark.asyncio
async def test_send_message_enqueues_job_and_creates_queued_request(chat_client):
    client, fake_pool = chat_client
    ceo_h = await _ceo_headers(client)
    conv = (await client.post("/api/v1/conversations", headers=ceo_h, json={})).json()

    resp = await client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=ceo_h,
                             json={"content": "tao task X"})
    assert resp.status_code == 201
    assert resp.json()["status"] == "queued"
    assert len(fake_pool.enqueued) == 1
    name, args, kwargs = fake_pool.enqueued[0]
    assert name == "process_conversation"
    assert kwargs["_job_id"] == f"conv:{conv['id']}"


@pytest.mark.asyncio
async def test_send_message_to_others_conversation_404(chat_client):
    client, _ = chat_client
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    conv = (await client.post("/api/v1/conversations", headers=ceo_h, json={})).json()

    m1_headers = {"Authorization": f"Bearer {m1['access_token']}"}
    resp = await client.post(f"/api/v1/conversations/{conv['id']}/messages",
                             headers=m1_headers, json={"content": "x"})
    assert resp.status_code == 404
```

Run: `pytest tests/test_chat_api.py -v` → FAIL (ModuleNotFoundError: app.api.chat).

- [ ] **Step 2: Implement**

Thêm vào `backend/app/schemas.py` (bổ sung import `from app.models import ChatRequestStatus` vào dòng import model hiện có):
```python
class ConversationCreateIn(BaseModel):
    title: str | None = None


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class MessageSendIn(BaseModel):
    content: str


class ChatRequestOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    status: ChatRequestStatus
    content: str
    created_at: dt.datetime

    model_config = {"from_attributes": True}
```

`backend/app/api/chat.py`:
```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.worker import enqueue_conversation
from app.db import get_db
from app.deps import get_current_user
from app.models import ChatRequest, Conversation, Message, MessageRole, User
from app.schemas import ChatRequestOut, ConversationCreateIn, ConversationOut, MessageSendIn

router = APIRouter(prefix="/api/v1/conversations", tags=["chat"])


async def get_arq_pool(request: Request):
    return request.app.state.arq_pool


async def _get_owned_conversation_or_404(db: AsyncSession, actor: User,
                                         conversation_id: uuid.UUID) -> Conversation:
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.workspace_id != actor.workspace_id or conv.user_id != actor.id:
        raise HTTPException(404, "conversation_not_found")
    return conv


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(body: ConversationCreateIn,
                              actor: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    conv = Conversation(workspace_id=actor.workspace_id, user_id=actor.id, title=body.title)
    db.add(conv)
    await db.commit()
    return conv


@router.get("", response_model=list[ConversationOut])
async def list_conversations(actor: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(Conversation).where(
        Conversation.workspace_id == actor.workspace_id, Conversation.user_id == actor.id,
    ).order_by(Conversation.created_at.desc()))
    return list(rows.scalars())


@router.post("/{conversation_id}/messages", response_model=ChatRequestOut, status_code=201)
async def send_message(conversation_id: uuid.UUID, body: MessageSendIn,
                       actor: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db),
                       arq_pool=Depends(get_arq_pool)):
    conv = await _get_owned_conversation_or_404(db, actor, conversation_id)
    max_pos = (await db.execute(select(func.max(ChatRequest.queue_position)).where(
        ChatRequest.conversation_id == conv.id))).scalar()
    req = ChatRequest(workspace_id=actor.workspace_id, conversation_id=conv.id,
                      user_id=actor.id, content=body.content,
                      queue_position=(max_pos or 0.0) + 1.0)
    db.add(req)
    await db.flush()
    db.add(Message(workspace_id=actor.workspace_id, conversation_id=conv.id,
                   chat_request_id=req.id, role=MessageRole.user,
                   content=[{"type": "text", "text": body.content}]))
    await db.commit()
    await enqueue_conversation(arq_pool, conv.id)
    return req
```

`backend/app/main.py` — sửa thành (thêm import `chat`, mount router, thêm 2 event handler):
```python
from fastapi import FastAPI

from app.api import auth, chat, invites, projects, skills, tasks, users
from app.config import assert_safe_config, get_settings


def create_app() -> FastAPI:
    assert_safe_config(get_settings())
    app = FastAPI(title="AI Assistant API", version="0.1.0", docs_url="/docs")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    @app.on_event("startup")
    async def _startup_arq_pool():
        from arq import create_pool
        from arq.connections import RedisSettings
        app.state.arq_pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))

    @app.on_event("shutdown")
    async def _shutdown_arq_pool():
        if getattr(app.state, "arq_pool", None) is not None:
            await app.state.arq_pool.close()

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(invites.router)
    app.include_router(projects.router)
    app.include_router(tasks.router)
    app.include_router(skills.router)
    app.include_router(chat.router)
    return app


app = create_app()
```

- [ ] **Step 3: Run toàn bộ → PASS (111)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): REST - conversations + send-message (enqueue)"
```

---

### Task 14: REST — xác nhận / dừng-hủy / sắp-xếp-lại / sửa hàng đợi

**Files:**
- Modify: `backend/app/api/chat.py`, `backend/app/schemas.py`
- Test: `backend/tests/test_chat_queue_api.py`

**Interfaces:**
- Router mới `chat_requests_router` (`prefix=/api/v1/chat-requests`), mount thêm trong `main.py`.
- `POST /api/v1/chat-requests/{id}/confirm {approved}` → 200 `ChatRequestOut` — chỉ actor sở hữu request; `status != awaiting_confirmation` → 409; gọi `resolve_confirmation` rồi `enqueue_conversation` lại.
- `PATCH /api/v1/chat-requests/{id} {content}` → 200 `ChatRequestOut` — chỉ sửa được khi `status == queued` (khác → 409); đồng bộ luôn `messages` (role=user) gắn với request.
- `POST /api/v1/chat-requests/{id}/cancel` → 204 — `queued` → set `cancelled` trực tiếp; `running` → set Redis key `cancel:{id}` (TTL 300s) qua `get_redis()` (mới, `lru_cache`, đọc `settings.redis_url`; test override bằng double giả).
- `POST /api/v1/chat-requests/{id}/reorder {before_id?}` → 200 `ChatRequestOut` — chỉ khi `status == queued`; `before_id=null` = đưa lên đầu hàng đợi (position nhỏ hơn min hiện có); `before_id` = uuid khác → chèn ngay trước request đó (fractional index, không renumber cả hàng đợi); `before_id` không thuộc hàng đợi `queued` hiện tại → 404.
- `POST /api/v1/conversations/{conversation_id}/stop-all` → 204 (trên `router` conversations) — hủy mọi `queued`, set cờ Redis cho request `running` (nếu có).

- [ ] **Step 1: Viết test fail**

`backend/tests/test_chat_queue_api.py`:
```python
import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.chat import get_arq_pool, get_redis
from app.db import get_db
from app.main import create_app
from app.models import ChatRequest, ChatRequestStatus, Conversation, Message, User, UserStatus
from tests.conftest import _ceo_headers


class _FakeArqPool:
    def __init__(self):
        self.enqueued = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.enqueued.append((name, args, kwargs))
        return "job"


class _FakeRedis:
    def __init__(self):
        self.set_calls = []

    async def set(self, key, value, ex=None):
        self.set_calls.append((key, value, ex))


@pytest.fixture
async def queue_client(engine):
    app = create_app()
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            yield session

    fake_pool = _FakeArqPool()
    fake_redis = _FakeRedis()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_arq_pool] = lambda: fake_pool
    app.dependency_overrides[get_redis] = lambda: fake_redis
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, fake_pool, fake_redis, maker


@pytest.mark.asyncio
async def test_confirm_approved_executes_and_requeues(queue_client):
    client, fake_pool, fake_redis, maker = queue_client
    ceo_h = await _ceo_headers(client)
    me = (await client.get("/api/v1/users/me", headers=ceo_h)).json()

    async with maker() as db:
        ceo = await db.get(User, uuid.UUID(me["id"]))
        target = User(workspace_id=ceo.workspace_id, email="e@a.vn", password_hash="x",
                     full_name="E", role="employee")
        db.add(target)
        await db.flush()
        conv = Conversation(workspace_id=ceo.workspace_id, user_id=ceo.id)
        db.add(conv)
        await db.flush()
        req = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                          user_id=ceo.id, content="khoa e", queue_position=1.0,
                          status=ChatRequestStatus.awaiting_confirmation,
                          pending_action={"tool_name": "lock_user",
                                         "tool_input": {"target_id": str(target.id)},
                                         "tool_use_id": "t1"})
        db.add(req)
        await db.commit()
        req_id, target_id = req.id, target.id

    resp = await client.post(f"/api/v1/chat-requests/{req_id}/confirm", headers=ceo_h,
                             json={"approved": True})
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    assert len(fake_pool.enqueued) == 1

    async with maker() as db:
        target = await db.get(User, target_id)
        assert target.status == UserStatus.locked


@pytest.mark.asyncio
async def test_confirm_when_not_awaiting_returns_409(queue_client):
    client, *_, maker = queue_client
    ceo_h = await _ceo_headers(client)
    me = (await client.get("/api/v1/users/me", headers=ceo_h)).json()

    async with maker() as db:
        ceo = await db.get(User, uuid.UUID(me["id"]))
        conv = Conversation(workspace_id=ceo.workspace_id, user_id=ceo.id)
        db.add(conv)
        await db.flush()
        req = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                          user_id=ceo.id, content="x", queue_position=1.0)
        db.add(req)
        await db.commit()
        req_id = req.id

    resp = await client.post(f"/api/v1/chat-requests/{req_id}/confirm", headers=ceo_h,
                             json={"approved": True})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_cancel_queued_request_marks_cancelled(queue_client):
    client, *_, maker = queue_client
    ceo_h = await _ceo_headers(client)
    me = (await client.get("/api/v1/users/me", headers=ceo_h)).json()

    async with maker() as db:
        ceo = await db.get(User, uuid.UUID(me["id"]))
        conv = Conversation(workspace_id=ceo.workspace_id, user_id=ceo.id)
        db.add(conv)
        await db.flush()
        req = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                          user_id=ceo.id, content="x", queue_position=1.0)
        db.add(req)
        await db.commit()
        req_id = req.id

    resp = await client.post(f"/api/v1/chat-requests/{req_id}/cancel", headers=ceo_h)
    assert resp.status_code == 204

    async with maker() as db:
        req = await db.get(ChatRequest, req_id)
        assert req.status == ChatRequestStatus.cancelled


@pytest.mark.asyncio
async def test_cancel_running_request_sets_redis_flag(queue_client):
    client, fake_pool, fake_redis, maker = queue_client
    ceo_h = await _ceo_headers(client)
    me = (await client.get("/api/v1/users/me", headers=ceo_h)).json()

    async with maker() as db:
        ceo = await db.get(User, uuid.UUID(me["id"]))
        conv = Conversation(workspace_id=ceo.workspace_id, user_id=ceo.id)
        db.add(conv)
        await db.flush()
        req = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                          user_id=ceo.id, content="x", queue_position=1.0,
                          status=ChatRequestStatus.running)
        db.add(req)
        await db.commit()
        req_id = req.id

    resp = await client.post(f"/api/v1/chat-requests/{req_id}/cancel", headers=ceo_h)
    assert resp.status_code == 204
    assert fake_redis.set_calls == [(f"cancel:{req_id}", "1", 300)]


@pytest.mark.asyncio
async def test_reorder_to_front_then_before_sibling(queue_client):
    client, *_, maker = queue_client
    ceo_h = await _ceo_headers(client)
    me = (await client.get("/api/v1/users/me", headers=ceo_h)).json()

    async with maker() as db:
        ceo = await db.get(User, uuid.UUID(me["id"]))
        conv = Conversation(workspace_id=ceo.workspace_id, user_id=ceo.id)
        db.add(conv)
        await db.flush()
        r1 = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                         user_id=ceo.id, content="1", queue_position=1.0)
        r2 = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                         user_id=ceo.id, content="2", queue_position=2.0)
        r3 = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                         user_id=ceo.id, content="3", queue_position=3.0)
        db.add_all([r1, r2, r3])
        await db.commit()
        r1_id, r2_id, r3_id = r1.id, r2.id, r3.id

    resp = await client.post(f"/api/v1/chat-requests/{r3_id}/reorder", headers=ceo_h, json={})
    assert resp.status_code == 200
    async with maker() as db:
        rows = (await db.execute(select(ChatRequest)
                                 .where(ChatRequest.id.in_([r1_id, r2_id, r3_id]))
                                 .order_by(ChatRequest.queue_position.asc()))).scalars().all()
        assert [r.id for r in rows] == [r3_id, r1_id, r2_id]

    resp2 = await client.post(f"/api/v1/chat-requests/{r2_id}/reorder", headers=ceo_h,
                              json={"before_id": str(r3_id)})
    assert resp2.status_code == 200
    async with maker() as db:
        rows = (await db.execute(select(ChatRequest)
                                 .where(ChatRequest.id.in_([r1_id, r2_id, r3_id]))
                                 .order_by(ChatRequest.queue_position.asc()))).scalars().all()
        assert [r.id for r in rows] == [r2_id, r3_id, r1_id]


@pytest.mark.asyncio
async def test_edit_queued_request_updates_content_and_linked_message(queue_client):
    client, *_, maker = queue_client
    ceo_h = await _ceo_headers(client)
    conv = (await client.post("/api/v1/conversations", headers=ceo_h, json={})).json()
    sent = await client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=ceo_h,
                             json={"content": "ban dau"})
    req_id = sent.json()["id"]

    resp = await client.patch(f"/api/v1/chat-requests/{req_id}", headers=ceo_h,
                              json={"content": "da sua"})
    assert resp.status_code == 200
    assert resp.json()["content"] == "da sua"

    async with maker() as db:
        msg = (await db.execute(select(Message).where(
            Message.chat_request_id == uuid.UUID(req_id)))).scalar_one()
        assert msg.content == [{"type": "text", "text": "da sua"}]


@pytest.mark.asyncio
async def test_stop_all_cancels_queued_and_flags_running(queue_client):
    client, fake_pool, fake_redis, maker = queue_client
    ceo_h = await _ceo_headers(client)
    me = (await client.get("/api/v1/users/me", headers=ceo_h)).json()

    async with maker() as db:
        ceo = await db.get(User, uuid.UUID(me["id"]))
        conv = Conversation(workspace_id=ceo.workspace_id, user_id=ceo.id)
        db.add(conv)
        await db.flush()
        r_running = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                                user_id=ceo.id, content="dang chay", queue_position=1.0,
                                status=ChatRequestStatus.running)
        r_queued = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                               user_id=ceo.id, content="cho", queue_position=2.0)
        db.add_all([r_running, r_queued])
        await db.commit()
        conv_id, running_id, queued_id = conv.id, r_running.id, r_queued.id

    resp = await client.post(f"/api/v1/conversations/{conv_id}/stop-all", headers=ceo_h)
    assert resp.status_code == 204

    async with maker() as db:
        queued = await db.get(ChatRequest, queued_id)
        assert queued.status == ChatRequestStatus.cancelled
    assert fake_redis.set_calls == [(f"cancel:{running_id}", "1", 300)]
```

Run: `pytest tests/test_chat_queue_api.py -v` → FAIL (404 do route chưa tồn tại).

- [ ] **Step 2: Implement**

Thêm vào `backend/app/schemas.py`:
```python
class ConfirmIn(BaseModel):
    approved: bool


class ChatRequestEditIn(BaseModel):
    content: str


class ReorderIn(BaseModel):
    before_id: uuid.UUID | None = None
```

Thêm vào đầu `backend/app/api/chat.py` (mở rộng import hiện có thành):
```python
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import resolve_confirmation
from app.agent.worker import enqueue_conversation
from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, User
from app.schemas import (
    ChatRequestEditIn, ChatRequestOut, ConfirmIn, ConversationCreateIn, ConversationOut,
    MessageSendIn, ReorderIn,
)

chat_requests_router = APIRouter(prefix="/api/v1/chat-requests", tags=["chat"])


@lru_cache
def get_redis():
    import redis.asyncio as redis_asyncio
    return redis_asyncio.from_url(get_settings().redis_url)
```

Thêm vào cuối `backend/app/api/chat.py`:
```python
async def _get_own_request_or_404(db: AsyncSession, actor: User,
                                  request_id: uuid.UUID) -> ChatRequest:
    req = await db.get(ChatRequest, request_id)
    if req is None or req.workspace_id != actor.workspace_id or req.user_id != actor.id:
        raise HTTPException(404, "request_not_found")
    return req


@router.post("/{conversation_id}/stop-all", status_code=204)
async def stop_all(conversation_id: uuid.UUID, actor: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db), redis=Depends(get_redis)):
    conv = await _get_owned_conversation_or_404(db, actor, conversation_id)
    rows = await db.execute(select(ChatRequest).where(
        ChatRequest.conversation_id == conv.id,
        ChatRequest.status.in_([ChatRequestStatus.queued, ChatRequestStatus.running]),
    ))
    for req in rows.scalars():
        if req.status == ChatRequestStatus.queued:
            req.status = ChatRequestStatus.cancelled
        else:
            await redis.set(f"cancel:{req.id}", "1", ex=300)
    await db.commit()
    return Response(status_code=204)


@chat_requests_router.post("/{request_id}/confirm", response_model=ChatRequestOut)
async def confirm_request(request_id: uuid.UUID, body: ConfirmIn,
                          actor: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db),
                          arq_pool=Depends(get_arq_pool)):
    req = await _get_own_request_or_404(db, actor, request_id)
    if req.status != ChatRequestStatus.awaiting_confirmation:
        raise HTTPException(409, "not_awaiting_confirmation")
    await resolve_confirmation(db, req, approved=body.approved)
    await enqueue_conversation(arq_pool, req.conversation_id)
    return req


@chat_requests_router.patch("/{request_id}", response_model=ChatRequestOut)
async def edit_request(request_id: uuid.UUID, body: ChatRequestEditIn,
                       actor: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    req = await _get_own_request_or_404(db, actor, request_id)
    if req.status != ChatRequestStatus.queued:
        raise HTTPException(409, "not_queued")
    req.content = body.content
    msg = (await db.execute(select(Message).where(
        Message.chat_request_id == req.id, Message.role == MessageRole.user
    ))).scalar_one_or_none()
    if msg is not None:
        msg.content = [{"type": "text", "text": body.content}]
    await db.commit()
    return req


@chat_requests_router.post("/{request_id}/cancel", status_code=204)
async def cancel_request(request_id: uuid.UUID, actor: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db), redis=Depends(get_redis)):
    req = await _get_own_request_or_404(db, actor, request_id)
    if req.status == ChatRequestStatus.queued:
        req.status = ChatRequestStatus.cancelled
        await db.commit()
    elif req.status == ChatRequestStatus.running:
        await redis.set(f"cancel:{req.id}", "1", ex=300)
    return Response(status_code=204)


@chat_requests_router.post("/{request_id}/reorder", response_model=ChatRequestOut)
async def reorder_request(request_id: uuid.UUID, body: ReorderIn,
                          actor: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    req = await _get_own_request_or_404(db, actor, request_id)
    if req.status != ChatRequestStatus.queued:
        raise HTTPException(409, "not_queued")
    siblings = (await db.execute(
        select(ChatRequest).where(ChatRequest.conversation_id == req.conversation_id,
                                  ChatRequest.status == ChatRequestStatus.queued,
                                  ChatRequest.id != req.id)
        .order_by(ChatRequest.queue_position.asc())
    )).scalars().all()
    if body.before_id is None:
        req.queue_position = (siblings[0].queue_position - 1.0) if siblings else 1.0
    else:
        idx = next((i for i, s in enumerate(siblings) if s.id == body.before_id), None)
        if idx is None:
            raise HTTPException(404, "before_request_not_found")
        before_pos = siblings[idx].queue_position
        prev_pos = siblings[idx - 1].queue_position if idx > 0 else before_pos - 2.0
        req.queue_position = (prev_pos + before_pos) / 2
    await db.commit()
    return req
```

Sửa `backend/app/main.py` — import module `chat` đã có sẵn từ Task 13 (`from app.api import auth, chat, invites, projects, skills, tasks, users`), không cần đổi dòng import. Chỉ thêm 1 dòng `app.include_router(chat.chat_requests_router)` ngay sau `app.include_router(chat.router)`.

- [ ] **Step 3: Run toàn bộ → PASS (118)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): REST - confirm/cancel/reorder/edit chat_requests + stop-all"
```

---

### Task 15: WebSocket streaming — `/ws/conversations/{id}`

**Files:**
- Create: `backend/app/api/ws.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_ws.py`

**Interfaces:**
- Produces: `WebSocketAuthError` (exception); `authorize_ws(db, token, conversation_id) -> Conversation` — decode JWT (claim `ws` = workspace_id, theo `app/security.py`), load conversation, khớp `workspace_id`+`user_id` → trả về; sai bất kỳ điều gì → raise `WebSocketAuthError`. `stream_events(send_json, subscription: AsyncIterator[dict]) -> None` — forward tuần tự mọi event từ `subscription` qua `send_json` (hàm thuần, không phụ thuộc `WebSocket` thật). `@router.websocket("/ws/conversations/{conversation_id}")` — route mỏng: `authorize_ws` → sai thì `close(code=4401)`; đúng thì `accept()` rồi `stream_events(websocket.send_json, publisher.subscribe(conversation_id))`.
- **Lưu ý phạm vi test:** route WebSocket thật KHÔNG có integration test qua socket thật trong plan này — `TestClient` của Starlette chạy app trong thread/event-loop riêng, xung đột với engine SQLite `StaticPool` dùng chung của bộ test hiện tại (aiosqlite gắn theo loop tạo ra nó). Toàn bộ logic có giá trị (auth, forward event) đã được tách thành `authorize_ws`/`stream_events` thuần và test đầy đủ; route chỉ còn là dây nối mỏng.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_ws.py`:
```python
import pytest

from app import security
from app.api.ws import WebSocketAuthError, authorize_ws, stream_events
from app.models import Conversation, Role, User, Workspace


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


@pytest.mark.asyncio
async def test_authorize_ws_accepts_owner_token(db_session):
    ws, ceo, conv = await _world(db_session)
    token = security.create_access_token(user_id=str(ceo.id), workspace_id=str(ws.id),
                                         role=ceo.role.value)
    result = await authorize_ws(db_session, token, conv.id)
    assert result.id == conv.id


@pytest.mark.asyncio
async def test_authorize_ws_rejects_invalid_token(db_session):
    ws, ceo, conv = await _world(db_session)
    with pytest.raises(WebSocketAuthError):
        await authorize_ws(db_session, "not-a-real-token", conv.id)


@pytest.mark.asyncio
async def test_authorize_ws_rejects_conversation_of_another_user(db_session):
    ws, ceo, conv = await _world(db_session)
    other = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
                role=Role.employee)
    db_session.add(other)
    await db_session.flush()
    await db_session.commit()
    token = security.create_access_token(user_id=str(other.id), workspace_id=str(ws.id),
                                         role=other.role.value)
    with pytest.raises(WebSocketAuthError):
        await authorize_ws(db_session, token, conv.id)  # conv thuộc ceo, không phải other


@pytest.mark.asyncio
async def test_stream_events_forwards_every_event_in_order():
    async def fake_subscription():
        yield {"type": "token", "text": "a"}
        yield {"type": "request_done"}

    sent = []

    async def fake_send_json(event):
        sent.append(event)

    await stream_events(fake_send_json, fake_subscription())

    assert sent == [{"type": "token", "text": "a"}, {"type": "request_done"}]
```

Run: `pytest tests/test_ws.py -v` → FAIL (ModuleNotFoundError: app.api.ws).

- [ ] **Step 2: Implement**

`backend/app/api/ws.py`:
```python
from __future__ import annotations

import uuid
from typing import AsyncIterator, Awaitable, Callable

import jwt
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.agent.publisher import EventPublisher, get_event_publisher
from app.db import get_db
from app.models import Conversation

router = APIRouter()


class WebSocketAuthError(Exception):
    pass


async def authorize_ws(db: AsyncSession, token: str, conversation_id: uuid.UUID) -> Conversation:
    """Giải mã token + xác nhận conversation thuộc đúng user/workspace.
    Raise WebSocketAuthError nếu bất kỳ bước nào không hợp lệ."""
    try:
        payload = security.decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
        workspace_id = uuid.UUID(payload["ws"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise WebSocketAuthError("invalid_token") from exc
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.workspace_id != workspace_id or conv.user_id != user_id:
        raise WebSocketAuthError("conversation_not_found")
    return conv


async def stream_events(send_json: Callable[[dict], Awaitable[None]],
                        subscription: AsyncIterator[dict]) -> None:
    """Chuyển tiếp event từ subscription ra send_json — hàm thuần, test không cần WebSocket thật."""
    async for event in subscription:
        await send_json(event)


@router.websocket("/ws/conversations/{conversation_id}")
async def conversation_ws(
    websocket: WebSocket, conversation_id: uuid.UUID, token: str = Query(...),
    db: AsyncSession = Depends(get_db),
    publisher: EventPublisher = Depends(get_event_publisher),
):
    try:
        await authorize_ws(db, token, conversation_id)
    except WebSocketAuthError:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    try:
        await stream_events(websocket.send_json, publisher.subscribe(conversation_id))
    except WebSocketDisconnect:
        pass
```

Sửa `backend/app/main.py` — thêm `ws` vào import (`from app.api import auth, chat, invites, projects, skills, tasks, users, ws`) và thêm `app.include_router(ws.router)` sau `app.include_router(chat.chat_requests_router)`.

- [ ] **Step 3: Run toàn bộ → PASS (122)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): websocket streaming - auth + event forwarding"
```

---

### Task 16: Docker worker service + migration Postgres + export contract

**Files:**
- Modify: `backend/docker-compose.yml`
- Create: migration mới qua alembic autogenerate

**Interfaces:**
- Service `worker` mới trong `docker-compose.yml`: cùng `build: .`, `command: arq app.agent.worker.WorkerSettings`, `depends_on: [postgres, redis]`, cùng biến môi trường `DATABASE_URL`/`JWT_SECRET` như `api` + `REDIS_URL: redis://redis:6379` (trong mạng docker, không phải host `localhost` — Redis host-mapped port 6379 giữ nguyên như hiện có, không đổi như Postgres).
- Migration `"chat agent core"` tạo 4 bảng mới (`conversations`, `chat_requests`, `messages`, `usage_log`); `alembic upgrade head` chạy sạch trên Postgres dev.
- `openapi.json` regenerate ở repo root (contract mới cho FE: `/api/v1/conversations`, `/api/v1/chat-requests`).

- [ ] **Step 1: Thêm service `worker` vào `backend/docker-compose.yml`**

Sửa `backend/docker-compose.yml` — thêm service `worker` (giữ nguyên `api`/`postgres`/`redis` hiện có), và thêm `REDIS_URL` vào `environment` của cả `api` lẫn `worker`:
```yaml
services:
  api:
    build: .
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql+asyncpg://app:app@postgres:5432/app
      JWT_SECRET: ${JWT_SECRET:-dev-secret}
      REDIS_URL: redis://redis:6379
    depends_on: [postgres, redis]
  worker:
    build: .
    command: ["arq", "app.agent.worker.WorkerSettings"]
    environment:
      DATABASE_URL: postgresql+asyncpg://app:app@postgres:5432/app
      JWT_SECRET: ${JWT_SECRET:-dev-secret}
      REDIS_URL: redis://redis:6379
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
    depends_on: [postgres, redis]
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: app
    volumes: ["pgdata:/var/lib/postgresql/data"]
    ports: ["5433:5432"]
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
volumes:
  pgdata:
```

- [ ] **Step 2: Sinh và áp migration**

```powershell
Set-Location "d:\8. AI\ai-assistant\backend"
docker compose up -d postgres redis
.venv\Scripts\alembic.exe revision --autogenerate -m "chat agent core"
.venv\Scripts\alembic.exe upgrade head
docker compose exec postgres psql -U app -d app -c "\dt"
```
Expected: 21 bảng (17 cũ + 4 mới + `alembic_version`). Đọc lại file migration sinh ra: đủ `conversations`, `chat_requests`, `messages`, `usage_log`.

- [ ] **Step 3: Export openapi + full suite**

```powershell
.venv\Scripts\python.exe scripts\export_openapi.py
.venv\Scripts\python.exe -m pytest tests/ -v
```
Expected: `openapi.json` chứa paths mới (`/api/v1/conversations`, `/api/v1/chat-requests/...`); **122 passed**.

- [ ] **Step 4: Commit**

```bash
git add backend/ openapi.json
git commit -m "feat(be): worker docker service, chat/agent core migration, refresh openapi contract"
```

---

## Self-review (đã chạy)

- **Spec coverage (thiết kế 2026-07-09-chat-agent-core-design.md §1–6):** §2 data model (conversation/chat_request/message/usage_log) ✅ T1; §3 runtime (enqueue dedupe theo `_job_id`, worker loop, agent loop, xác nhận 2 bước, dừng/hủy, WS) ✅ T3–T5, T9–T12, T15; §4 tool layer (21 tool, `input_schema` từ Pydantic, format lỗi) ✅ T6–T8; §5 testing (`FakeLLMClient`/`FakeEventPublisher`, không cần API key/Redis thật) ✅ xuyên suốt T3–T15; §6 infra/config (`anthropic`/`arq`/`redis`, `docker-compose` worker, `model_chat`) ✅ T2, T16. Ngoài phạm vi (đã chốt lúc brainstorm): `generate_report`/Excel (Plan 4), `send_email` (chưa có OAuth), voice/dashboard/tìm kiếm/báo cáo định kỳ, lệnh tường minh "tiếp tục công việc" sau mất mạng.
- **Placeholder scan:** không có TBD/`...` ngoài JSON minh họa response; mọi step code đều đầy đủ, không có "tương tự Task N".
- **Type consistency:** `run_agent_loop`/`resolve_confirmation`/`process_conversation` dùng thống nhất `ChatRequest`, `ChatRequestStatus`, `MessageRole` xuyên suốt T9–T14; `EventPublisher.subscribe()`/`publish()` chữ ký khớp giữa `FakeEventPublisher` (T4) và `RedisEventPublisher` (T5) và nơi dùng (`loop.py`, `ws.py`); `LLMClient.stream()` trả `AsyncIterator[TextDelta | StreamDone]` nhất quán giữa `FakeLLMClient` (T3), `AnthropicLLMClient` (T5), và `run_agent_loop` (T9/T11); `ToolSpec`/`TOOLS`/`SENSITIVE_TOOLS`/`call_tool` định nghĩa 1 lần ở T6, dùng lại nguyên vẹn ở T7, T8, T9 (`loop.py` import `SENSITIVE_TOOLS`, `TOOLS`, `call_tool` — không định nghĩa lại).
- **Đếm test:** 71 (baseline) → T1:72 → T2:73 → T3:75 → T4:78 → T5:81 → T6:87 → T7:92 → T8:96 → T9:99 → T10:102 → T11:105 → T12:108 → T13:111 → T14:118 → T15:122 → T16:122 (không thêm test, chỉ hạ tầng/migration).
