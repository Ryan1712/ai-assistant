# Gắn project cho conversation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho phép gắn/đổi `project_id` (tùy chọn) vào 1 conversation đang mở, để khi AI gọi `create_task` mà người dùng không chỉ rõ project khác, tự dùng project đã gắn làm mặc định — theo đúng spec `docs/superpowers/specs/2026-08-05-conversation-project-scope-design.md`.

**Architecture:** Thêm cột `project_id` (nullable FK → `projects.id`, `ondelete="SET NULL"`) vào `Conversation`. Mở rộng `PATCH /api/v1/conversations/{id}` nhận thêm `project_id` tùy chọn cùng payload đổi tên (không tách route). `run_agent_loop` (đã có sẵn `conv` object trong scope vòng lặp) tiêm 1 đoạn hướng dẫn vào system prompt khi `conv.project_id` có giá trị — không sửa logic tool `create_task`. FE mở rộng modal sửa tên có sẵn thêm phần chọn project, và hiện badge tên project ở header màn hình chat.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, Postgres, pytest-asyncio (BE); React Native/Expo, TypeScript (FE).

## Global Constraints

- Gắn project là **tùy chọn**, mặc định không gắn gì — không đổi hành vi cũ khi `project_id` là `None`.
- Chỉ ảnh hưởng **duy nhất** hành vi `create_task` không chỉ rõ project — KHÔNG động vào `list_tasks`, `get_project_health`, hay tool đọc khác.
- Nếu project bị xóa, conversation tự động gỡ về `project_id = NULL` (đã có sẵn qua `ondelete="SET NULL"`, không cần code thêm).
- KHÔNG thêm cơ chế "tạo conversation mới thủ công" — spec đã loại bỏ hướng này vì phá vỡ bất biến "≤1 conversation sống".
- FE: dùng token từ `frontend/src/ui/theme.ts` (`colors`, `radius`, `spacing`, `fonts`), không hardcode hex/spacing — theo `frontend/AGENTS.md`.
- TDD bắt buộc cho phần BE: test trước, thấy fail đúng lý do, rồi mới code.
- Mỗi task 1 commit riêng (CLAUDE.md).
- `python scripts/export_openapi.py` sau khi route ổn định (Task 3).

---

### Task 1: Migration + model `Conversation.project_id`

**Files:**
- Modify: `backend/app/models.py` (class `Conversation`, dòng ~373-395)
- Create: migration Alembic mới qua `alembic revision --autogenerate`
- Test: `backend/tests/test_conversation_project_scope.py` (mới)

**Interfaces:**
- Produces: `Conversation.project_id: uuid.UUID | None` — dùng ở Task 2 (schema), Task 3 (API), Task 4 (system prompt).

- [ ] **Step 1: Viết test thất bại xác nhận cột `project_id` tồn tại (mặc định None)**

```python
# backend/tests/test_conversation_project_scope.py
"""PO #2 (2026-08-08): gắn project cho conversation đang mở. Xem
docs/superpowers/specs/2026-08-05-conversation-project-scope-design.md.

Hành vi ON DELETE SET NULL KHÔNG có test tự động ở tầng model — đã thử bật
PRAGMA foreign_keys=ON cho SQLite test nhưng lộ ra 32 test KHÁC trong suite
đang dùng workspace_id/user_id ngẫu nhiên (không tạo record thật), sửa hết là
việc lớn ngoài phạm vi. Hành vi SET NULL xác nhận qua migration Alembic áp
lên Postgres dev thật (Step 5-6) — Postgres luôn enforce FK, đủ tin cậy."""
import uuid

import pytest

from app.models import Conversation


async def _mk_conv(db, project_id=None):
    ws, user = uuid.uuid4(), uuid.uuid4()
    conv = Conversation(workspace_id=ws, user_id=user, project_id=project_id)
    db.add(conv)
    await db.flush()
    return conv, ws


@pytest.mark.asyncio
async def test_conversation_project_id_nullable_default_none(db_session):
    conv, _ = await _mk_conv(db_session)
    await db_session.commit()
    assert conv.project_id is None
```

- [ ] **Step 2: Chạy test, xác nhận fail vì `project_id` chưa tồn tại**

Run: `cd backend && python -m pytest tests/test_conversation_project_scope.py -v`
Expected: FAIL với `TypeError: 'project_id' is an invalid keyword argument for Conversation` (hoặc lỗi tương đương).

- [ ] **Step 3: Thêm cột `project_id` vào model**

Trong `backend/app/models.py`, class `Conversation`, thêm sau dòng `user_id`:

```python
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # PO #2 (2026-08-08): gắn project cho conversation đang mở -- KHÔNG phải lúc
    # "tạo mới" (app không có khái niệm đó, xem docstring module phía trên) mà
    # gắn/đổi bất kỳ lúc nào qua PATCH. Dùng làm default project cho create_task
    # khi user không chỉ rõ project khác (tiêm qua system prompt, xem
    # app/agent/loop.py). ondelete=SET NULL: project bị xóa -> conversation tự
    # gỡ về "không gắn project", không lỗi, không mất conversation (spec §Phạm vi).
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_conversation_project_scope.py -v`
Expected: PASS.

- [ ] **Step 5: Sinh migration Alembic**

Đảm bảo Postgres dev đang chạy (`docker compose up -d postgres redis` ở `backend/`), rồi:

```bash
cd backend
.venv\Scripts\activate
alembic revision --autogenerate -m "add project_id to conversations"
```

Mở file migration sinh ra ở `backend/alembic/versions/`, xác nhận có `op.add_column('conversations', sa.Column('project_id', sa.Uuid(), nullable=True))` và `op.create_foreign_key(..., 'conversations', 'projects', ['project_id'], ['id'], ondelete='SET NULL')`. Đây là migration đơn giản (thêm cột nullable, không cần backfill) — autogenerate nên đủ chính xác, nhưng đọc lại file để xác nhận trước khi áp dụng (bài học từ lần trước: autogenerate có thể bỏ sót chi tiết cho thay đổi phức tạp — lần này KHÔNG đổi PK nên rủi ro thấp hơn nhiều, chỉ cần xác nhận `ondelete='SET NULL'` có mặt).

- [ ] **Step 6: Áp migration lên Postgres dev, verify**

```bash
cd backend
.venv\Scripts\activate
alembic upgrade head
```

Verify: `docker compose exec postgres psql -U app -d app -c "\d conversations"` — cột `project_id` phải xuất hiện, kèm FK `conversations_project_id_fkey ... ON DELETE SET NULL`.

- [ ] **Step 7: Chạy lại test + full suite liên quan**

Run: `cd backend && python -m pytest tests/test_conversation_project_scope.py tests/test_chat_api.py -v`
Expected: tất cả PASS, không phá gì hiện có.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/*.py backend/tests/test_conversation_project_scope.py
git commit -m "feat(conversations): them cot project_id nullable, FK projects ON DELETE SET NULL"
```

---

### Task 2: Schema `ConversationOut`/`ConversationRenameIn` + API PATCH mở rộng

**Files:**
- Modify: `backend/app/schemas.py` (`ConversationOut` dòng ~320-327, `ConversationRenameIn` dòng ~316-317)
- Modify: `backend/app/api/chat.py` (`rename_conversation` dòng ~134-142)
- Test: `backend/tests/test_conversation_project_scope.py` (mở rộng)

**Interfaces:**
- Consumes: `Conversation.project_id` từ Task 1.
- Produces: `ConversationOut.project_id: str | None`, `ConversationOut.project_name: str | None` — dùng ở Task 5 (FE).
- `PATCH /api/v1/conversations/{id}` body: `{title?: str, project_id?: uuid | null}` — cả 2 field optional, nhưng ít nhất phải gửi 1 trong 2 (giữ nguyên field còn lại nếu không gửi).

- [ ] **Step 1: Viết test thất bại cho PATCH nhận `project_id`**

Thêm vào `backend/tests/test_conversation_project_scope.py`:

```python
from tests.conftest import _ceo_headers


@pytest.mark.asyncio
async def test_patch_conversation_sets_project_id(client):
    ceo_h = await _ceo_headers(client)
    proj = (await client.post("/api/v1/projects", json={"name": "P1", "goal": "g"},
                              headers=ceo_h)).json()
    conv = (await client.get("/api/v1/conversations/active", headers=ceo_h)).json()

    resp = await client.patch(f"/api/v1/conversations/{conv['id']}",
                              json={"project_id": proj["id"]}, headers=ceo_h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == proj["id"]
    assert body["project_name"] == "P1"


@pytest.mark.asyncio
async def test_patch_conversation_unsets_project_id(client):
    ceo_h = await _ceo_headers(client)
    proj = (await client.post("/api/v1/projects", json={"name": "P1", "goal": "g"},
                              headers=ceo_h)).json()
    conv = (await client.get("/api/v1/conversations/active", headers=ceo_h)).json()
    await client.patch(f"/api/v1/conversations/{conv['id']}",
                       json={"project_id": proj["id"]}, headers=ceo_h)

    resp = await client.patch(f"/api/v1/conversations/{conv['id']}",
                              json={"project_id": None}, headers=ceo_h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] is None
    assert body["project_name"] is None


@pytest.mark.asyncio
async def test_patch_conversation_title_only_keeps_project_id(client):
    ceo_h = await _ceo_headers(client)
    proj = (await client.post("/api/v1/projects", json={"name": "P1", "goal": "g"},
                              headers=ceo_h)).json()
    conv = (await client.get("/api/v1/conversations/active", headers=ceo_h)).json()
    await client.patch(f"/api/v1/conversations/{conv['id']}",
                       json={"project_id": proj["id"]}, headers=ceo_h)

    resp = await client.patch(f"/api/v1/conversations/{conv['id']}",
                              json={"title": "Tên mới"}, headers=ceo_h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Tên mới"
    assert body["project_id"] == proj["id"]  # KHÔNG bị mất khi chỉ đổi title
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && python -m pytest tests/test_conversation_project_scope.py -v`
Expected: FAIL vì `ConversationRenameIn` chưa nhận `project_id` (Pydantic validation error hoặc `KeyError` khi đọc `body["project_id"]`/`body["project_name"]` — response hiện tại không có field này).

- [ ] **Step 3: Sửa schema `ConversationRenameIn` và `ConversationOut`**

Trong `backend/app/schemas.py`, đổi:

```python
class ConversationRenameIn(BaseModel):
    title: str
```

thành:

```python
class ConversationRenameIn(BaseModel):
    """PO #2: mở rộng nhận project_id cùng payload đổi tên, không tách route
    riêng (spec §Backend mục 2). Cả 2 field optional -- title=None nghĩa là
    'không đổi tên', project_id KHÔNG dùng None làm 'không đổi' mà dùng
    project_id_set để phân biệt 'gửi None để GỠ project' vs 'không gửi field
    này' (Pydantic field không có default riêng cho 'chưa gửi' vs 'gửi null'
    trừ khi dùng model_fields_set) -- đơn giản hơn: client LUÔN gửi project_id
    tường minh (kể cả null để gỡ), chỉ title là optional thật."""
    title: str | None = None
    project_id: uuid.UUID | None = None
```

Và đổi `ConversationOut`:

```python
class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str | None
    project_id: uuid.UUID | None = None
    project_name: str | None = None
    queue_held: bool = False
    archived_at: dt.datetime | None = None
    created_at: dt.datetime

    model_config = {"from_attributes": True}
```

Lưu ý: `ConversationOut` dùng `from_attributes=True` và trả thẳng ORM object ở nhiều route (`return conv`) — `project_name` KHÔNG phải cột trên `Conversation`, cần route tự set nó (Step 4) trước khi serialize, hoặc build dict thủ công.

- [ ] **Step 4: Sửa route `rename_conversation` để nhận `project_id` và trả kèm `project_name`**

Trong `backend/app/api/chat.py`, đổi:

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

thành:

```python
@router.patch("/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(conversation_id: uuid.UUID, body: ConversationRenameIn,
                              actor: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    """PO #2: cùng route nhận CẢ title lẫn project_id (spec §Backend mục 2) --
    "rename" trong tên hàm giữ nguyên để không đổi route path, dù giờ làm
    nhiều hơn đổi tên."""
    conv = await _get_owned_conversation_or_404(db, actor, conversation_id)
    if body.title is not None:
        conv.title = body.title
        conv.title_locked = True
    if "project_id" in body.model_fields_set:
        if body.project_id is not None:
            project = await db.get(Project, body.project_id)
            if project is None or project.workspace_id != actor.workspace_id:
                raise HTTPException(404, "project_not_found")
        conv.project_id = body.project_id
    await db.commit()
    project_name = None
    if conv.project_id is not None:
        project = await db.get(Project, conv.project_id)
        project_name = project.name if project else None
    return ConversationOut(
        id=conv.id, title=conv.title, project_id=conv.project_id,
        project_name=project_name, queue_held=conv.queue_held,
        archived_at=conv.archived_at, created_at=conv.created_at)
```

Kiểm tra `Project` và `HTTPException` đã import ở đầu `chat.py` — nếu chưa, thêm vào dòng import.

- [ ] **Step 5: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_conversation_project_scope.py -v`
Expected: PASS cả 5 test (2 từ Task 1 + 3 mới).

- [ ] **Step 6: Chạy test liên quan khác đảm bảo không phá gì (đặc biệt các nơi dùng `ConversationRenameIn`/gọi PATCH rename cũ)**

Run: `cd backend && python -m pytest tests/test_chat_api.py tests/test_conversation_title_service.py tests/test_conversation_active_timeline_api.py -v`
Expected: tất cả PASS — đặc biệt test cũ nào gọi PATCH chỉ với `{"title": "..."}` (không có `project_id`) vẫn phải hoạt động y hệt trước (đổi tên, không đụng `project_id`).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/api/chat.py backend/tests/test_conversation_project_scope.py
git commit -m "feat(conversations): PATCH nhan project_id, tra kem project_name"
```

---

### Task 3: List conversations trả kèm `project_id`/`project_name`

**Files:**
- Modify: `backend/app/api/chat.py` (`list_conversations` dòng ~85-90, `_create_conversation`/route tạo, `active_conversation` dòng ~95-102)
- Test: `backend/tests/test_conversation_project_scope.py` (mở rộng)

**Interfaces:**
- Consumes: `Conversation.project_id` (Task 1), `ConversationOut` (Task 2).
- Produces: mọi response trả `ConversationOut` (list, active, create) đều có `project_id`/`project_name` nhất quán.

- [ ] **Step 1: Viết test thất bại cho GET /conversations và GET /conversations/active trả kèm project_name**

```python
@pytest.mark.asyncio
async def test_list_conversations_includes_project_name(client):
    ceo_h = await _ceo_headers(client)
    proj = (await client.post("/api/v1/projects", json={"name": "P1", "goal": "g"},
                              headers=ceo_h)).json()
    conv = (await client.get("/api/v1/conversations/active", headers=ceo_h)).json()
    await client.patch(f"/api/v1/conversations/{conv['id']}",
                       json={"project_id": proj["id"]}, headers=ceo_h)

    listed = (await client.get("/api/v1/conversations", headers=ceo_h)).json()
    found = next(c for c in listed if c["id"] == conv["id"])
    assert found["project_name"] == "P1"

    active = (await client.get("/api/v1/conversations/active", headers=ceo_h)).json()
    assert active["project_name"] == "P1"
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && python -m pytest tests/test_conversation_project_scope.py::test_list_conversations_includes_project_name -v`
Expected: FAIL — `project_name` sẽ là `None` dù đã gắn (vì `list_conversations`/`active_conversation` hiện trả thẳng ORM object qua `response_model=ConversationOut`, Pydantic tự đọc `project_name` từ attribute không tồn tại trên `Conversation` → mặc định `None` do có `= None` trong schema, không lỗi nhưng SAI giá trị).

- [ ] **Step 3: Thêm helper build `ConversationOut` kèm `project_name`, dùng lại ở list/active**

Trong `backend/app/api/chat.py`, thêm hàm helper (đặt gần `_get_owned_conversation_or_404`):

```python
async def _conversation_out(db: AsyncSession, conv: Conversation) -> ConversationOut:
    """Build ConversationOut kèm project_name (denormalized, spec §Backend mục 3)
    -- Conversation model KHÔNG có cột project_name, phải tự join/lookup."""
    project_name = None
    if conv.project_id is not None:
        project = await db.get(Project, conv.project_id)
        project_name = project.name if project else None
    return ConversationOut(
        id=conv.id, title=conv.title, project_id=conv.project_id,
        project_name=project_name, queue_held=conv.queue_held,
        archived_at=conv.archived_at, created_at=conv.created_at)
```

Sửa `list_conversations`:

```python
@router.get("", response_model=list[ConversationOut])
async def list_conversations(actor: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(Conversation).where(
        Conversation.workspace_id == actor.workspace_id, Conversation.user_id == actor.id,
    ).order_by(Conversation.created_at.desc()))
    return [await _conversation_out(db, c) for c in rows.scalars()]
```

Sửa `active_conversation`:

```python
@router.get("/active", response_model=ConversationOut)
async def active_conversation(actor: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    from app.agent.llm_client import get_llm_client
    conv = await session_service.get_or_rotate_active_conversation(
        db, actor, get_llm_client)
    return await _conversation_out(db, conv)
```

Sửa `rename_conversation` (Task 2, Step 4) để dùng lại helper thay vì lặp code:

```python
@router.patch("/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(conversation_id: uuid.UUID, body: ConversationRenameIn,
                              actor: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    conv = await _get_owned_conversation_or_404(db, actor, conversation_id)
    if body.title is not None:
        conv.title = body.title
        conv.title_locked = True
    if "project_id" in body.model_fields_set:
        if body.project_id is not None:
            project = await db.get(Project, body.project_id)
            if project is None or project.workspace_id != actor.workspace_id:
                raise HTTPException(404, "project_not_found")
        conv.project_id = body.project_id
    await db.commit()
    return await _conversation_out(db, conv)
```

Kiểm tra `_create_conversation` (route POST tạo conversation, dòng ~73-82) — response_model cũng là `ConversationOut`, trả `return conv` (ORM trực tiếp, `project_id` luôn None lúc tạo nên không cần join, nhưng để nhất quán và tránh Pydantic serialize warning, đổi luôn:

```python
    conv = Conversation(workspace_id=actor.workspace_id, user_id=actor.id, title=body.title,
                        title_locked=body.title is not None)
    db.add(conv)
    await db.commit()
    return await _conversation_out(db, conv)
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_conversation_project_scope.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Export lại openapi.json (contract đổi — thêm field mới)**

```bash
cd backend
.venv\Scripts\activate
python scripts/export_openapi.py
```

- [ ] **Step 6: Chạy full suite backend**

Run: `cd backend && python -m pytest tests/ -q`
Expected: tất cả PASS, không phá gì hiện có (baseline trước task này: 838 passed, 0 failed, 4 skipped).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/chat.py openapi.json
git commit -m "feat(conversations): list/active/create tra kem project_name qua helper chung"
```

---

### Task 4: Tiêm hướng dẫn project vào system prompt (`run_agent_loop`)

**Files:**
- Modify: `backend/app/agent/loop.py` (vòng lặp `dynamic_parts`, dòng ~384-409)
- Test: `backend/tests/test_agent_loop_rag_context.py` (tham khảo pattern), tạo file mới `backend/tests/test_agent_loop_project_context.py`

**Interfaces:**
- Consumes: `conv.project_id` (Task 1), `conv` object đã có sẵn trong scope `run_agent_loop`.
- Produces: đoạn text `"# Project mặc định..."` xuất hiện trong system prompt khi `conv.project_id` có giá trị — model `create_task` không chỉ rõ project sẽ dùng project này (hành vi do model tuân theo hướng dẫn prompt, KHÔNG code cứng).

- [ ] **Step 1: Đọc `backend/tests/test_agent_loop_rag_context.py` đầy đủ (đã đọc lúc viết plan — pattern xác nhận: dùng `FakeLLMClient(turns=[[TextDelta(...), StreamDone(...)]])` từ `app.agent.llm_client`, `FakeEventPublisher()` từ `app.agent.publisher`, tạo `Workspace` tường minh qua helper `_world`, gọi `run_agent_loop(db, req, llm, publisher, ...)` không cần `tool_names`, đọc kết quả qua `llm.calls[0]["system"]` — CÓ THỂ là `list[dict]` (mỗi phần tử `{"text": ...}`) hoặc `str` thuần tùy có block động hay không)**

- [ ] **Step 2: Viết test thất bại xác nhận đoạn hướng dẫn project xuất hiện trong system prompt khi conv có `project_id`**

```python
# backend/tests/test_agent_loop_project_context.py
"""PO #2: run_agent_loop tiêm đoạn hướng dẫn project mặc định vào block động
của system prompt khi conversation.project_id có giá trị — cùng pattern
rag_context/example_context (xem test_agent_loop_rag_context.py)."""
import pytest

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.loop import run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import ChatRequest, Conversation, Project, Role, User, Workspace


async def _world(db, with_project: bool):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    project = None
    if with_project:
        project = Project(workspace_id=ws.id, name="Website Redesign", goal="")
        db.add(project)
        await db.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id,
                        project_id=project.id if project else None)
    db.add(conv)
    await db.flush()
    return ws, ceo, conv


async def _request(db, ws, conv, ceo, content="tao task moi"):
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content=content, queue_position=1.0)
    db.add(req)
    await db.commit()
    return req


def _system_text(system) -> str:
    return system if isinstance(system, str) else "\n".join(b["text"] for b in system)


@pytest.mark.asyncio
async def test_run_agent_loop_injects_project_default_when_conv_has_project_id(db_session):
    ws, ceo, conv = await _world(db_session, with_project=True)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    text = _system_text(llm.calls[0]["system"])
    assert "Website Redesign" in text
    assert "create_task" in text


@pytest.mark.asyncio
async def test_run_agent_loop_no_project_hint_when_conv_has_no_project(db_session):
    ws, ceo, conv = await _world(db_session, with_project=False)
    req = await _request(db_session, ws, conv, ceo, content="hello")
    llm = FakeLLMClient(turns=[[
        TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    text = _system_text(llm.calls[0]["system"])
    assert "Project mặc định" not in text
```

Nếu `FakeLLMClient`/`StreamDone`/`FakeEventPublisher` có signature khác khi đọc lại (Step 1), sửa test theo signature thật — đây là điểm duy nhất trong plan chưa 100% khóa cứng, vì phụ thuộc đọc file tại thời điểm thực thi.

- [ ] **Step 3: Chạy test, xác nhận fail đúng lý do**

Run: `cd backend && python -m pytest tests/test_agent_loop_project_context.py -v`
Expected: FAIL vì `"Website Redesign"` không có trong `captured_system` (chưa code tiêm đoạn hướng dẫn).

- [ ] **Step 4: Thêm đoạn tiêm project vào `dynamic_parts`**

Trong `backend/app/agent/loop.py`, ngay sau đoạn `if coach_block:` (dòng ~407-408, trước dòng `if conv is not None and conv.rolling_summary:`), thêm:

```python
            if conv is not None and conv.project_id is not None:
                project = await db.get(Project, conv.project_id)
                if project is not None:
                    dynamic_parts.append(
                        f"# Project mặc định cho cuộc trò chuyện này\n"
                        f"Cuộc trò chuyện này đang gắn với project '{project.name}' — khi tạo "
                        f"task mới (create_task) mà người dùng KHÔNG chỉ rõ project khác, dùng "
                        f"project này làm mặc định. Các yêu cầu khác (xem/hỏi về project/task "
                        f"khác) vẫn xử lý bình thường, không bị giới hạn vào project này.")
```

Kiểm tra `Project` đã import ở đầu `loop.py` — nếu chưa, thêm `Project` vào dòng `from app.models import (...)`.

- [ ] **Step 5: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_agent_loop_project_context.py -v`
Expected: PASS cả 2 test.

- [ ] **Step 6: Chạy test liên quan `loop.py` để đảm bảo không phá gì**

Run: `cd backend && python -m pytest tests/test_agent_loop_rag_context.py tests/test_agent_loop_example_context.py tests/test_agent_loop_cancel_error.py -v`
Expected: tất cả PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/agent/loop.py backend/tests/test_agent_loop_project_context.py
git commit -m "feat(agent): tiem huong dan project mac dinh vao system prompt khi conversation co project_id"
```

---

### Task 5: FE — API client + modal chọn project + badge ở header chat

**Files:**
- Modify: `frontend/src/api/chat.ts` (`Conversation` type, `renameConversation`)
- Modify: `frontend/app/main/conversations.tsx` (modal sửa tên, thêm picker project)
- Modify: `frontend/app/main/chat.tsx` (header, badge project)

**Interfaces:**
- Consumes: `ConversationOut.project_id`/`project_name` (BE Task 2/3), `listProjects()` (`frontend/src/api/projects.ts`, đã có sẵn).
- Produces: `updateConversation(id, {title?, project_id?})` — hàm mới thay `renameConversation` (giữ `renameConversation` như alias mỏng để không phá chỗ gọi cũ nếu có, hoặc đổi tên tất cả chỗ gọi — quyết định ở Step 2 dựa trên số lượng chỗ gọi thực tế).

- [ ] **Step 1: Đọc `frontend/DESIGN.md` đầy đủ trước khi thêm UI mới (bắt buộc theo AGENTS.md)**

- [ ] **Step 2: Kiểm tra mọi nơi gọi `renameConversation` để quyết định đổi tên hay giữ**

Run: `grep -rn "renameConversation" frontend/`

Nếu chỉ có 1 chỗ gọi (trong `conversations.tsx`), đổi thẳng tên hàm thành `updateConversation` và sửa chỗ gọi. Nếu có nhiều chỗ, cân nhắc giữ `renameConversation(id, title)` nguyên như cũ và thêm hàm mới `updateConversationProject(id, projectId)` riêng để giảm rủi ro — quyết định cụ thể dựa trên kết quả grep thật, không đoán trước.

- [ ] **Step 3: Cập nhật `frontend/src/api/chat.ts`**

Đổi `Conversation` type:

```typescript
export type Conversation = {
  id: string;
  title: string | null;
  project_id: string | null;
  project_name: string | null;
  queue_held: boolean;
  archived_at: string | null;
  created_at: string;
};
```

Đổi (hoặc thêm mới, tùy kết quả Step 2) hàm update:

```typescript
export const updateConversation = (
  conversationId: string,
  body: { title?: string; project_id?: string | null },
) =>
  apiFetch<Conversation>(`/api/v1/conversations/${conversationId}`, {
    method: "PATCH",
    body,
  });
```

Nếu giữ `renameConversation` cho tương thích ngược, viết nó dựa trên `updateConversation`:

```typescript
export const renameConversation = (conversationId: string, title: string) =>
  updateConversation(conversationId, { title });
```

- [ ] **Step 4: Thêm import `listProjects`/`Project` và state chọn project vào `frontend/app/main/conversations.tsx`**

Thêm import:

```typescript
import { listProjects, Project } from "../../src/api/projects";
import { updateConversation } from "../../src/api/chat";
```

Thêm state (cạnh state `editing`/`draft` hiện có, dòng ~97-101):

```typescript
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [draftProjectId, setDraftProjectId] = useState<string | null>(null);
```

Load danh sách project 1 lần khi mở màn hình (thêm `useEffect` cạnh cái load `listConversations` hiện có):

```typescript
  useEffect(() => {
    listProjects().then(setProjects).catch(() => setProjects([]));
  }, []);
```

- [ ] **Step 5: Sửa `openEdit`/`saveEdit` để đọc/ghi `project_id`**

```typescript
  const openEdit = (c: Conversation) => {
    setDraft(c.title ?? "");
    setDraftProjectId(c.project_id ?? null);
    setEditError(null);
    setEditing(c);
  };

  const saveEdit = async () => {
    if (!editing) return;
    const title = draft.trim();
    if (!title) return;
    setEditBusy(true);
    setEditError(null);
    try {
      const updated = await updateConversation(editing.id, {
        title,
        project_id: draftProjectId,
      });
      setConversations((prev) =>
        prev
          ? prev.map((x) => (x.id === editing.id ? updated : x))
          : prev,
      );
      setEditing(null);
    } catch (e: any) {
      setEditError(String(e?.message ?? e));
    } finally {
      setEditBusy(false);
    }
  };
```

- [ ] **Step 6: Thêm UI chọn project trong modal (sau `<Field>` đổi tên, trước `<ErrorText>`, dòng ~202-203)**

Dùng danh sách chip/nút đơn giản (nhất quán "pill" theo DESIGN.md — radius 999), không cần thư viện picker mới:

```tsx
            <Text style={styles.pickerLabel}>Project (tùy chọn)</Text>
            <View style={styles.projectChips}>
              <TouchableOpacity
                style={[
                  styles.projectChip,
                  draftProjectId === null && styles.projectChipActive,
                ]}
                onPress={() => setDraftProjectId(null)}
              >
                <Text
                  style={[
                    styles.projectChipText,
                    draftProjectId === null && styles.projectChipTextActive,
                  ]}
                >
                  Không gắn
                </Text>
              </TouchableOpacity>
              {(projects ?? []).map((p) => (
                <TouchableOpacity
                  key={p.id}
                  style={[
                    styles.projectChip,
                    draftProjectId === p.id && styles.projectChipActive,
                  ]}
                  onPress={() => setDraftProjectId(p.id)}
                >
                  <Text
                    style={[
                      styles.projectChipText,
                      draftProjectId === p.id && styles.projectChipTextActive,
                    ]}
                  >
                    {p.name}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
```

Thêm style tương ứng (dùng token `colors`/`radius`/`spacing` từ `theme.ts`, cạnh `styles.modalTitle`):

```typescript
  pickerLabel: {
    fontFamily: fonts.semibold,
    fontSize: 13,
    color: colors.textSecondary,
    marginBottom: spacing.xs,
  },
  projectChips: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.xs,
    marginBottom: spacing.sm,
  },
  projectChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceAlt,
  },
  projectChipActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  projectChipText: {
    fontFamily: fonts.semibold,
    fontSize: 13,
    color: colors.textSecondary,
  },
  projectChipTextActive: {
    color: colors.onPrimary,
  },
```

Đọc `radius`, `fonts` đã import ở đầu file (dòng ~22) — xác nhận `radius.pill` tồn tại trong `theme.ts` trước khi dùng (đã grep xác nhận có ở Task chuẩn bị).

- [ ] **Step 7: Thêm badge project ở header `frontend/app/main/chat.tsx`**

Thêm state cạnh `conversationTitle` (dòng ~347):

```typescript
  const [conversationProjectName, setConversationProjectName] = useState<string | null>(null);
```

Cập nhật 2 chỗ set `conversationTitle` (dòng ~579, ~590) để cũng set project name:

```typescript
          setConversationTitle(conv.title);
          setConversationProjectName(conv.project_name);
```

```typescript
          setConversationTitle(active.title);
          setConversationProjectName(active.project_name);
```

Và reset ở đầu effect (cạnh `setConversationTitle(null)` dòng ~564):

```typescript
    setConversationProjectName(null);
```

Thêm badge trong header, ngay dưới `headerTitle` (sau dòng ~813, trong cùng `<View style={styles.header}>` — kiểm tra layout thật trước khi chèn, có thể cần bọc `headerTitle` + badge trong 1 `<View>` con để xếp dọc thay vì hàng ngang hiện có; đọc đủ 30 dòng context quanh dòng 800-825 trước khi sửa để không phá layout `flexDirection: row` hiện tại của `styles.header`):

```tsx
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle} numberOfLines={1}>
            {conversationTitle || "Trợ lý AI"}
          </Text>
          {conversationProjectName && (
            <Text style={styles.headerProjectBadge} numberOfLines={1}>
              📁 {conversationProjectName}
            </Text>
          )}
        </View>
```

(thay cho `<Text style={styles.headerTitle} ...>` đứng riêng hiện có — bọc trong `View` để xếp badge bên dưới). Thêm style `headerProjectBadge` cạnh `headerTitle` trong `StyleSheet.create` của `chat.tsx` (đọc style hiện có trước khi thêm, dùng `colors.textSecondary`, `fontSize` nhỏ hơn title).

- [ ] **Step 8: Chạy TypeScript check (không có test tự động FE theo cấu trúc repo hiện tại — xác nhận bằng compile)**

Run: `cd frontend && npx tsc --noEmit`
Expected: không lỗi type liên quan các file vừa sửa (lỗi có sẵn từ trước, nếu có, không thuộc phạm vi task này — chỉ xác nhận không có lỗi MỚI phát sinh từ thay đổi này).

- [ ] **Step 9: Dùng skill `run` để khởi động app, xác nhận trực quan modal + badge hoạt động (nếu môi trường cho phép — Android emulator theo memory `project-android-emulator-dev-loop`)**

- [ ] **Step 10: Commit**

```bash
git add frontend/src/api/chat.ts frontend/app/main/conversations.tsx frontend/app/main/chat.tsx
git commit -m "feat(fe): modal chon project cho conversation + badge o header chat"
```

---

## Self-Review Notes

- **Spec coverage:** đối chiếu "Việc cần làm (tổng quan)" trong spec (8 mục) — mục 1-5 là Task 1-4, mục 6 là Task 5, mục 7 (test) rải trong từng task tương ứng, mục 8 (export_openapi) ở Task 3 Step 5.
- **Placeholder scan:** không còn "TBD"/code rút gọn — mọi step có code đầy đủ, các chỗ cần "đọc code thật trước khi sửa" (Task 5 Step 2, 7) đều nêu rõ lý do (layout/số lượng chỗ gọi chưa xác định trước, không phải lười viết).
- **Type consistency:** `project_id: uuid.UUID | None` (BE) ↔ `project_id: string | null` (FE, qua JSON) nhất quán; `ConversationOut`/`Conversation` (FE type) đồng bộ field `project_id`/`project_name` giữa Task 2/3 (BE) và Task 5 (FE).
- **Đã verify trước khi chốt plan:** Task 4 test đã đối chiếu trực tiếp với `test_agent_loop_rag_context.py` thật (đọc đầy đủ lúc lập plan) — dùng đúng `FakeLLMClient`/`StreamDone`/`FakeEventPublisher`/helper `_world` tạo `Workspace` tường minh, không còn class/fixture tự bịa tên.
