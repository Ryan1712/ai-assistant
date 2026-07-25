# Phase 6 (mảnh 1) — Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Khi CEO tạo workspace mới, cho họ 1 câu chào viết sẵn + 3 nút gợi ý bấm nhanh, gợi ý dẫn dắt ngắn khi công ty còn thiếu setup, và để AI tự bóc text danh sách công việc dán vào chat thành đề xuất tạo project+task hàng loạt.

**Architecture:** Seed message tạo ngay lúc `signup_workspace` (không gọi LLM). Coach block là 4 cờ tính lại mỗi lượt (tái dùng data Phase 1 sẵn có), tiêm vào system prompt động, chỉ cho CEO. Import text là 1 đoạn hướng dẫn thêm vào system prompt tĩnh, tái dùng nguyên `propose_actions` đã có.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy 2.0 async / Alembic; React Native (Expo SDK 57). Test: pytest + pytest-asyncio (SQLite in-memory) BE; `tsc --noEmit` FE.

## Global Constraints

- Mọi bảng (trừ `workspaces`) có `workspace_id`; mọi query lọc theo `actor.workspace_id`/`workspace_id`. (CLAUDE.md)
- Quyền kiểm ở service layer; actor luôn từ JWT (`get_current_user`), không từ client/model. (CLAUDE.md)
- Model LLM từ config, không hardcode model ID. (CLAUDE.md)
- Route dưới `/api/v1`. Đổi API contract → chạy lại `python scripts/export_openapi.py`. (CLAUDE.md)
- TDD: test trước, code sau; mỗi task một commit. (CLAUDE.md)
- KHÔNG dùng PowerShell `Get-Content|Set-Content` sửa file UTF-8 tiếng Việt — dùng Edit/Write. (CLAUDE.md)
- Onboarding chỉ áp dụng cho CEO lúc tạo workspace mới — KHÔNG áp dụng cho manager/employee kích hoạt qua `activate.tsx`. (spec §1)
- Coach block chỉ tiêm khi `actor.role == Role.ceo` — manager/employee không tạo được project/mời người nên gợi ý vô nghĩa với họ. (spec §4)
- `get_workload_summary` (spec gốc §10.1) KHÔNG xây — quyết định cũ giữ nguyên (dữ liệu đã có trong snapshot). (spec §0)
- Không xây chip/luồng riêng cho nhập file `.xlsx` thật — chỉ hỗ trợ dán text. (spec §1)
- Lệnh BE chạy trong `backend/` với venv `.venv` (Windows: `.venv\Scripts\activate`). Lệnh FE chạy trong `frontend/`.

---

## File Structure

**Tạo mới:**
- `backend/app/services/onboarding_service.py` — `get_coach_flags` + `render_coach_block`.
- `backend/alembic/versions/<rev>_message_is_seed_flag.py` — migration 1 cột.
- `backend/tests/test_onboarding_seed.py`, `backend/tests/test_onboarding_service.py`, `backend/tests/test_onboarding_coach_loop.py`.

**Sửa:**
- `backend/app/models.py` — `Message` +1 cột (`is_seed`).
- `backend/app/services/auth_service.py` — `signup_workspace` tạo `Conversation` + seed `Message`.
- `backend/app/agent/loop.py` — import `Role`, `onboarding_service`; `_build_system_prompt` thêm đoạn hướng dẫn import text; `run_agent_loop` tiêm coach block (CEO-only).
- `backend/app/schemas.py` — `MessageOut.is_seed`.
- `backend/openapi.json` (export lại).
- `frontend/src/api/chat.ts` — `Message.is_seed`.
- `frontend/app/main/chat.tsx` — `submit(overrideText?)`, dải 3 chip dưới seed message.

---

### Task 1: Migration + `Message.is_seed`

**Files:**
- Modify: `backend/app/models.py:404-421` (class `Message`)
- Create: `backend/alembic/versions/<rev>_message_is_seed_flag.py`
- Test: `backend/tests/test_onboarding_seed.py` (smoke cột — mở rộng ở Task 2)

**Interfaces:**
- Produces: `Message.is_seed: bool` (default `False`).

- [ ] **Step 1: Viết test cột mới tồn tại + default**

Tạo `backend/tests/test_onboarding_seed.py`:
```python
import uuid

from app.models import Conversation, Message, MessageRole


async def test_message_co_cot_is_seed_default_false(db_session):
    conv = Conversation(workspace_id=uuid.uuid4(), user_id=uuid.uuid4())
    db_session.add(conv)
    await db_session.flush()
    msg = Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                 role=MessageRole.assistant, content=[{"type": "text", "text": "chao"}])
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    assert msg.is_seed is False
```

- [ ] **Step 2: Chạy test — FAIL**

Run (trong `backend/`): `.venv\Scripts\python.exe -m pytest tests/test_onboarding_seed.py -v`
Expected: FAIL (`TypeError` hoặc lỗi cột không tồn tại — `Message` chưa có `is_seed`).

- [ ] **Step 3: Thêm cột vào model**

Trong `backend/app/models.py`, class `Message`, sau dòng `is_ack` (dòng 420, trước `created_at`):
```python
    is_ack: Mapped[bool] = mapped_column(Boolean, default=False)
    # Phase 6 (onboarding): câu chào viết sẵn lúc signup_workspace — KHÔNG gọi LLM.
    # Khác is_ack: message này VẪN vào lịch sử gửi model bình thường (ngữ cảnh hợp
    # lệ, không đứng giữa cặp tool_use/tool_result nào). Chỉ dùng để FE quyết định
    # có hiện dải chip gợi ý hay không (xem chat.tsx).
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
```

- [ ] **Step 4: Chạy test — PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_onboarding_seed.py -v`
Expected: PASS.

- [ ] **Step 5: Tạo migration Alembic**

Chạy (trong `backend/`, cần `docker compose up -d postgres redis` trước):
```bash
alembic revision --autogenerate -m "message_is_seed_flag"
```
Mở file migration vừa sinh trong `backend/alembic/versions/`, xác nhận `down_revision = "b0e866329b4c"` (head hiện tại — migration `session_model_rolling_summary` của Phase 5). Nếu autogenerate bỏ sót, viết tay:
```python
def upgrade() -> None:
    op.add_column("messages", sa.Column("is_seed", sa.Boolean(),
                  server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("messages", "is_seed")
```

- [ ] **Step 6: Áp migration lên Postgres dev + commit**

```bash
alembic upgrade head
```
Expected: chạy sạch, không lỗi.
```bash
git add app/models.py alembic/versions/ tests/test_onboarding_seed.py
git commit -m "feat(be): them cot Message.is_seed cho onboarding (Phase 6)"
```

---

### Task 2: `signup_workspace` tạo Conversation + seed Message

**Files:**
- Modify: `backend/app/services/auth_service.py:1-18` (imports), `:53-77` (`signup_workspace`)
- Test: `backend/tests/test_onboarding_seed.py`

**Interfaces:**
- Consumes: `Message.is_seed` (Task 1).
- Produces: sau `signup_workspace`, workspace có đúng 1 `Conversation` (archived_at=None) chứa đúng 1 `Message(role=assistant, is_seed=True, chat_request_id=None)`.

- [ ] **Step 1: Viết test — signup tạo seed conversation + message**

Thêm vào `backend/tests/test_onboarding_seed.py`:
```python
from sqlalchemy import select

from app.models import ChatRequestStatus, Workspace
from app.services import auth_service


async def test_signup_workspace_seed_conversation_va_message(db_session):
    user, access, refresh = await auth_service.signup_workspace(
        db_session, workspace_name="Cong ty B", email="ceo2@a.vn",
        password="secret123", full_name="Sep 2",
        device_uuid="dev-onb-1", device_name="",
    )

    convs = (await db_session.execute(select(Conversation).where(
        Conversation.workspace_id == user.workspace_id))).scalars().all()
    assert len(convs) == 1
    assert convs[0].user_id == user.id
    assert convs[0].archived_at is None

    msgs = (await db_session.execute(select(Message).where(
        Message.conversation_id == convs[0].id))).scalars().all()
    assert len(msgs) == 1
    seed = msgs[0]
    assert seed.role == MessageRole.assistant
    assert seed.is_seed is True
    assert seed.chat_request_id is None
    assert seed.content[0]["type"] == "text"
    assert len(seed.content[0]["text"]) > 0
```
(`Conversation` đã import ở đầu file từ Task 1; thêm `ChatRequestStatus`/`Workspace` không thực sự cần cho test này — bỏ nếu không dùng, chỉ cần `select`, `auth_service`.)

- [ ] **Step 2: Chạy test — FAIL**

Run: `.venv\Scripts\python.exe -m pytest tests/test_onboarding_seed.py -v`
Expected: FAIL (`len(convs) == 0`).

- [ ] **Step 3: Sửa `signup_workspace`**

Trong `backend/app/services/auth_service.py`:

3a. Thêm import (dòng 12-15, gộp vào import `app.models` sẵn có):
```python
from app.models import (
    AccountEvent, Conversation, Device, Invite, LoginEvent, Message, MessageRole,
    Notification, Project, RefreshToken, Role, TaskAssignee, User, UserStatus, Workspace,
)
```

3b. Thêm hằng số câu chào (đầu file, sau `_DUMMY_HASH`):
```python
_SEED_MESSAGE_TEXT = (
    "Chào anh! Tôi là trợ lý điều hành — nhắn cho tôi để giao việc, tạo project, "
    "hỏi tiến độ... Anh có thể bắt đầu bằng 1 trong các gợi ý dưới đây, hoặc gõ "
    "thẳng điều anh cần."
)
```

3c. Trong `signup_workspace`, sau dòng `await _log_device(db, user, device_uuid, device_name)` và TRƯỚC `access, refresh = await _issue_tokens(db, user)`, thêm:
```python
    conv = Conversation(workspace_id=ws.id, user_id=user.id)
    db.add(conv)
    await db.flush()
    db.add(Message(workspace_id=ws.id, conversation_id=conv.id, role=MessageRole.assistant,
                   content=[{"type": "text", "text": _SEED_MESSAGE_TEXT}], is_seed=True))
```
(Nằm trong cùng transaction với tạo `Workspace`/`User` — nếu `commit()` sau đó fail vì email trùng, toàn bộ rollback cùng nhau, không cần xử lý riêng.)

- [ ] **Step 4: Chạy test — PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_onboarding_seed.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Regression auth**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth.py -v`
Expected: PASS (không hồi quy — `test_signup_workspace_creates_root_ceo` không kiểm tra conversation nên không bị ảnh hưởng).

- [ ] **Step 6: Commit**

```bash
git add app/services/auth_service.py tests/test_onboarding_seed.py
git commit -m "feat(be): signup_workspace tao seed conversation + message (Phase 6 onboarding)"
```

---

### Task 3: `onboarding_service.py` — coach flags

**Files:**
- Create: `backend/app/services/onboarding_service.py`
- Test: `backend/tests/test_onboarding_service.py`

**Interfaces:**
- Consumes: `snapshot_service.build_workspace_data(db, workspace_id, *, now=None) -> dict` (Phase 1, đã có — trả `data["projects"]` list dict có `task_total`, `data["users"]` list dict).
- Produces: `async def get_coach_flags(db, workspace_id) -> dict[str, bool]` (khóa: `has_projects`, `has_tasks`, `has_members`, `has_first_report`); `def render_coach_block(flags: dict[str, bool]) -> str | None` (None nếu đủ cả 4 cờ).

- [ ] **Step 1: Viết test coach flags**

Tạo `backend/tests/test_onboarding_service.py`:
```python
import uuid

from app.models import (
    Project, Report, Role, Task, TaskAssignee, TaskStatus, User, Workspace,
)
from app.services.onboarding_service import get_coach_flags, render_coach_block


async def _mk_ws_ceo(db):
    ws = Workspace(name="Cong ty C")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c3@a.vn", password_hash="x", full_name="C3",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    return ws, ceo


async def test_workspace_rong_het_ca_4_co_false(db_session):
    ws, ceo = await _mk_ws_ceo(db_session)
    await db_session.commit()
    flags = await get_coach_flags(db_session, ws.id)
    assert flags == {"has_projects": False, "has_tasks": False,
                     "has_members": False, "has_first_report": False}
    assert render_coach_block(flags) is not None


async def test_du_ca_4_moc_tra_none(db_session):
    ws, ceo = await _mk_ws_ceo(db_session)
    other = User(workspace_id=ws.id, email="m3@a.vn", password_hash="x", full_name="M3",
                role=Role.manager)
    db_session.add(other)
    await db_session.flush()
    proj = Project(workspace_id=ws.id, name="Du an X", created_by=ceo.id)
    db_session.add(proj)
    await db_session.flush()
    task = Task(workspace_id=ws.id, project_id=proj.id, title="Task 1",
               status=TaskStatus.todo, created_by=ceo.id)
    db_session.add(task)
    db_session.add(Report(workspace_id=ws.id, requested_by=ceo.id, file_path="x.xlsx"))
    await db_session.commit()

    flags = await get_coach_flags(db_session, ws.id)
    assert flags == {"has_projects": True, "has_tasks": True,
                     "has_members": True, "has_first_report": True}
    assert render_coach_block(flags) is None


async def test_co_project_nhung_chua_co_task(db_session):
    ws, ceo = await _mk_ws_ceo(db_session)
    proj = Project(workspace_id=ws.id, name="Du an rong", created_by=ceo.id)
    db_session.add(proj)
    await db_session.commit()

    flags = await get_coach_flags(db_session, ws.id)
    assert flags["has_projects"] is True
    assert flags["has_tasks"] is False
    block = render_coach_block(flags)
    assert block is not None
    assert "task" in block.lower() or "cong viec" in block.lower() or "công việc" in block
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `.venv\Scripts\python.exe -m pytest tests/test_onboarding_service.py -v`
Expected: FAIL (`ModuleNotFoundError: app.services.onboarding_service`).

- [ ] **Step 3: Viết `onboarding_service.py`**

Tạo `backend/app/services/onboarding_service.py`:
```python
"""Phase 6 (onboarding): coach block — gợi ý ngắn cho CEO khi workspace còn thiếu
setup cơ bản. 4 cờ tính lại mỗi lượt (KHÔNG cache, KHÔNG lưu trạng thái "đã tốt
nghiệp") — rẻ vì tái dùng phần lớn từ build_workspace_data (Phase 1), chỉ thêm
đúng 1 query mới cho has_first_report.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Report
from app.services import snapshot_service

_COACH_LABELS = {
    "has_projects": "tạo project đầu tiên",
    "has_tasks": "thêm task vào project",
    "has_members": "mời thêm nhân viên/quản lý",
    "has_first_report": "tạo báo cáo đầu tiên",
}


async def get_coach_flags(db: AsyncSession, workspace_id: uuid.UUID) -> dict[str, bool]:
    data = await snapshot_service.build_workspace_data(db, workspace_id)
    has_projects = len(data["projects"]) > 0
    has_tasks = any(p["task_total"] > 0 for p in data["projects"])
    has_members = len(data["users"]) > 1  # CEO tự thân đã nằm trong danh sách này
    has_first_report = (await db.execute(
        select(Report.id).where(Report.workspace_id == workspace_id).limit(1)
    )).scalar_one_or_none() is not None
    return {"has_projects": has_projects, "has_tasks": has_tasks,
           "has_members": has_members, "has_first_report": has_first_report}


def render_coach_block(flags: dict[str, bool]) -> str | None:
    """None nếu đủ cả 4 mốc — không có gì để gợi ý, khối tự biến mất khỏi system
    prompt (không cần code riêng để 'tắt hẳn')."""
    missing = [_COACH_LABELS[k] for k, v in flags.items() if not v]
    if not missing:
        return None
    items = ", ".join(missing)
    return (
        "# Gợi ý dẫn dắt (chỉ hiện với CEO chưa hoàn tất thiết lập)\n"
        f"Công ty còn thiếu: {items}. Sau câu trả lời chính, thêm ĐÚNG 1 câu ngắn "
        "gợi ý bước tiếp theo hợp lý (chọn 1 trong các việc còn thiếu ở trên, dựa "
        "theo ngữ cảnh câu hỏi vừa rồi). Không lặp lại gợi ý y hệt câu trước nếu "
        "ngữ cảnh không đổi."
    )
```

- [ ] **Step 4: Chạy test — PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_onboarding_service.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add app/services/onboarding_service.py tests/test_onboarding_service.py
git commit -m "feat(be): onboarding_service.get_coach_flags + render_coach_block (Phase 6)"
```

---

### Task 4: Tiêm coach block vào `run_agent_loop` (CEO-only) + hướng dẫn import text

**Files:**
- Modify: `backend/app/agent/loop.py` (imports dòng 18-22; `_build_system_prompt` dòng 58-113; `run_agent_loop` chỗ dựng `dynamic_parts` ~dòng 294-307)
- Test: `backend/tests/test_onboarding_coach_loop.py` (mới)

**Interfaces:**
- Consumes: `get_coach_flags`, `render_coach_block` (Task 3).
- Produces: `run_agent_loop` tiêm coach block vào system prompt CHỈ khi `actor.role == Role.ceo`; `_build_system_prompt` có thêm đoạn hướng dẫn "dán text danh sách công việc" cho MỌI actor.

- [ ] **Step 1: Viết test — coach block CEO-only + import-text guidance luôn có**

Tạo `backend/tests/test_onboarding_coach_loop.py`:
```python
import uuid

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.loop import _build_system_prompt, run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    ChatRequest, Conversation, Message, MessageRole, Project, Report, Role, Task,
    TaskStatus, User, Workspace,
)


async def _seed(db, role=Role.ceo):
    ws = Workspace(name="Cong ty D")
    db.add(ws)
    await db.flush()
    actor = User(workspace_id=ws.id, email="d@a.vn", password_hash="x", full_name="D",
                role=role, is_root=(role == Role.ceo))
    db.add(actor)
    await db.flush()
    return ws, actor


async def _run(db, ws, actor, content="xin chao"):
    conv = Conversation(workspace_id=ws.id, user_id=actor.id)
    db.add(conv)
    await db.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=actor.id,
                      content=content, queue_position=1.0)
    db.add(req)
    await db.flush()
    db.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                   role=MessageRole.user, content=[{"type": "text", "text": content}]))
    await db.commit()
    llm = FakeLLMClient(turns=[[TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)]])
    await run_agent_loop(db, req, llm, FakeEventPublisher())
    return llm.calls[0]["system"]


def _system_text(system):
    return system if isinstance(system, str) else "\n".join(
        b["text"] for b in system if b.get("type") == "text")


async def test_coach_block_hien_voi_ceo_workspace_rong(db_session):
    ws, ceo = await _seed(db_session, role=Role.ceo)
    system = await _run(db_session, ws, ceo)
    assert "Gợi ý dẫn dắt" in _system_text(system)


async def test_coach_block_khong_hien_voi_manager(db_session):
    ws, manager = await _seed(db_session, role=Role.manager)
    system = await _run(db_session, ws, manager)
    assert "Gợi ý dẫn dắt" not in _system_text(system)


async def test_coach_block_khong_hien_khi_du_setup(db_session):
    ws, ceo = await _seed(db_session, role=Role.ceo)
    proj = Project(workspace_id=ws.id, name="Du an", created_by=ceo.id)
    db_session.add(proj)
    await db_session.flush()
    db_session.add(Task(workspace_id=ws.id, project_id=proj.id, title="T1",
                        status=TaskStatus.todo, created_by=ceo.id))
    other = User(workspace_id=ws.id, email="mgr@a.vn", password_hash="x", full_name="M",
                role=Role.manager)
    db_session.add(other)
    db_session.add(Report(workspace_id=ws.id, requested_by=ceo.id, file_path="x.xlsx"))
    await db_session.commit()
    system = await _run(db_session, ws, ceo)
    assert "Gợi ý dẫn dắt" not in _system_text(system)


def test_system_prompt_tinh_co_huong_dan_import_text():
    actor = User(id=uuid.uuid4(), workspace_id=uuid.uuid4(), email="x@a.vn",
                password_hash="x", full_name="X", role=Role.ceo)
    prompt = _build_system_prompt(actor)
    assert "propose_actions" in prompt
    assert "dán" in prompt.lower() or "liệt kê nhiều công việc" in prompt
```

- [ ] **Step 2: Chạy test — FAIL**

Run: `.venv\Scripts\python.exe -m pytest tests/test_onboarding_coach_loop.py -v`
Expected: FAIL (coach block chưa xuất hiện; đoạn hướng dẫn import chưa có trong `_build_system_prompt`).

- [ ] **Step 3a: Thêm hướng dẫn import text vào `_build_system_prompt`**

Trong `backend/app/agent/loop.py`, cuối chuỗi trả về của `_build_system_prompt` (dòng 112, ngay trước dấu `)` đóng hàm, nối tiếp đoạn "biết chính xác cái gì cần làm lại."):
```python
        "biết chính xác cái gì cần làm lại.\n"
        "Khi người dùng dán 1 đoạn text dài liệt kê nhiều công việc (copy từ Excel/"
        "Word/ghi chú), tự nhận diện project + danh sách task + người phụ trách "
        "(nếu có nêu tên) từ nội dung đó, rồi gọi propose_actions MỘT LẦN gồm đủ "
        "create_project + N create_task + assign_task tương ứng — không hỏi lại "
        "từng dòng một, chỉ hỏi nếu tên người nhắc tới bị nhập nhằng "
        "(resolve_person)."
    )
```
(Đóng ngoặc `)` giữ nguyên vị trí cuối cùng — chỉ nối thêm 1 chuỗi trước dấu đóng.)

- [ ] **Step 3b: Import `Role`, `onboarding_service`**

Trong `backend/app/agent/loop.py`, sửa import (dòng 18-22):
```python
from app.models import (
    AgentTrace, ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole,
    Role, UsageLog, User,
)
from app.services import instruction_service, onboarding_service, snapshot_service
```

- [ ] **Step 3c: Tiêm coach block trong `run_agent_loop`**

Trong `backend/app/agent/loop.py`, sau khối:
```python
            if conv is not None and conv.rolling_summary:
                # Phase 5: tóm tắt hội thoại cũ — block ĐỘNG cuối, gần message nhất.
                dynamic_parts.append(
                    "# Tóm tắt hội thoại trước đó\n" + conv.rolling_summary)
```
thêm NGAY TRƯỚC khối đó (giữa `snapshot_text` và `rolling_summary`, để rolling_summary vẫn là block cuối "gần message nhất" như comment cũ mô tả):
```python
            if actor.role == Role.ceo:
                # Phase 6 (onboarding): gợi ý dẫn dắt — chỉ CEO có quyền tạo
                # project/mời người nên gợi ý này vô nghĩa với manager/employee.
                coach_flags = await onboarding_service.get_coach_flags(db, req.workspace_id)
                coach_block = onboarding_service.render_coach_block(coach_flags)
                if coach_block:
                    dynamic_parts.append(coach_block)
```
Vị trí chèn: NGAY SAU dòng `dynamic_parts.append(snapshot_text)` (trong khối `if snapshot_text:`), và TRƯỚC dòng `if conv is not None and conv.rolling_summary:`.

- [ ] **Step 4: Chạy test — PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_onboarding_coach_loop.py -v`
Expected: PASS toàn bộ 4 test.

- [ ] **Step 5: Regression loop + auth**

Run: `.venv\Scripts\python.exe -m pytest tests/test_loop_rolling_summary.py tests/test_load_history_queue.py tests/test_auth.py -v`
Expected: PASS (không hồi quy).

- [ ] **Step 6: Commit**

```bash
git add app/agent/loop.py tests/test_onboarding_coach_loop.py
git commit -m "feat(be): tiem coach block (CEO-only) + huong dan import text vao system prompt (Phase 6)"
```

---

### Task 5: `MessageOut.is_seed` + export OpenAPI

**Files:**
- Modify: `backend/app/schemas.py:400-407` (`MessageOut`)
- Modify: `backend/openapi.json` (export lại)
- Test: `backend/tests/test_onboarding_seed.py` (mở rộng — test API)

**Interfaces:**
- Consumes: `Message.is_seed` (Task 1).
- Produces: `MessageOut.is_seed: bool`.

- [ ] **Step 1: Viết test — seed message có `is_seed=true` qua API**

Thêm vào `backend/tests/test_onboarding_seed.py`:
```python
SIGNUP_API = {
    "workspace_name": "Cong ty E", "email": "ceo-e@a.vn", "password": "secret123",
    "full_name": "Sep E", "device_uuid": "dev-onb-2", "device_name": "",
}


async def test_seed_message_co_is_seed_true_qua_api(client):
    resp = await client.post("/api/v1/auth/signup-workspace", json=SIGNUP_API)
    assert resp.status_code == 201, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    active = await client.get("/api/v1/conversations/active", headers=headers)
    conv_id = active.json()["id"]
    msgs = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    assert msgs.status_code == 200
    body = msgs.json()
    assert len(body) == 1
    assert body[0]["is_seed"] is True
```
(Test này cần `client` fixture — thêm `import pytest` nếu file chưa có, và các test async trong file này chạy được nhờ `asyncio_mode = auto` trong `pytest.ini`, không cần decorator riêng.)

- [ ] **Step 2: Chạy test — FAIL**

Run: `.venv\Scripts\python.exe -m pytest tests/test_onboarding_seed.py::test_seed_message_co_is_seed_true_qua_api -v`
Expected: FAIL (`KeyError: 'is_seed'` — field chưa có trong response).

- [ ] **Step 3: Thêm field vào schema**

Trong `backend/app/schemas.py`, class `MessageOut`:
```python
class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    role: MessageRole
    content: list
    voice_note_id: uuid.UUID | None = None
    is_seed: bool = False
    created_at: dt.datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Chạy test — PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_onboarding_seed.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Export OpenAPI + commit**

```bash
python scripts/export_openapi.py
git add app/schemas.py tests/test_onboarding_seed.py ../openapi.json
git commit -m "feat(be): MessageOut.is_seed (Phase 6 onboarding)"
```
(Nếu `openapi.json` ở repo root, điều chỉnh đường dẫn `git add` cho đúng — xem cách Phase 5 Task 8 đã làm.)

---

### Task 6: FE — `Message.is_seed` + `submit(overrideText?)` + 3 chip

**Files:**
- Modify: `frontend/src/api/chat.ts:72-79` (`Message` type)
- Modify: `frontend/app/main/chat.tsx` (`Row` type dòng 42-46; `messagesToRows` dòng 134-154; `submit` dòng 387+; call site `onPress={submit}` dòng 743; render chip mới sau FlatList dòng 644)

**Interfaces:**
- Consumes: `MessageOut.is_seed` (Task 5).
- Produces: `Message.is_seed: boolean` (FE type); `submit(overrideText?: string)`; dải 3 chip render khi `rows.length===1 && rows[0].kind==="assistant" && rows[0].isSeed && !historyMode`.

- [ ] **Step 1: Thêm field `is_seed` vào FE type**

Trong `frontend/src/api/chat.ts`, sửa `Message` type:
```typescript
export type Message = {
  id: string;
  conversation_id: string | null;
  role: "user" | "assistant";
  content: ContentBlock[];
  voice_note_id: string | null;
  is_seed: boolean;
  created_at: string;
};
```

- [ ] **Step 2: `Row` type + `messagesToRows` truyền `isSeed`**

Trong `frontend/app/main/chat.tsx`, sửa `Row` type (dòng 42-46):
```typescript
type Row =
  | { key: string; kind: "user" | "assistant"; text: string; voiceNoteId?: string | null; isSeed?: boolean }
  | { key: string; kind: "streaming"; text: string }
  | { key: string; kind: "system"; text: string }
  | { key: string; kind: "failed"; text: string; retryContent: string | null };
```

Sửa `messagesToRows` (dòng 143-145), thêm `isSeed: m.is_seed`:
```typescript
    if (text)
      out.push({ key: m.id, kind: m.role === "user" ? "user" : "assistant", text,
                 voiceNoteId: m.voice_note_id, isSeed: m.is_seed });
```

- [ ] **Step 3: `submit` nhận `overrideText` tùy chọn**

Sửa chữ ký `submit` (dòng 387) và dòng dựng `content` (dòng 390):
```typescript
  const submit = async (overrideText?: string) => {
    if (archived) return;
    if (!conversationId) return;
    const content = (overrideText ?? input).trim()
      || (attachedAudio ? "Xử lý file ghi âm này giúp tôi" : "");
    if (!content) return;
    setInput("");
```
(Phần còn lại của hàm giữ nguyên — chỉ 2 dòng đầu đổi.)

**QUAN TRỌNG:** sửa call site nút Gửi (dòng 743) từ `onPress={submit}` thành `onPress={() => submit()}` — nếu để nguyên, React Native truyền `GestureResponderEvent` làm `overrideText`, phá luôn nút gửi bình thường:
```tsx
              <TouchableOpacity
                style={[styles.sendBtn, !canSend && styles.sendBtnOff]}
                onPress={() => submit()}
                disabled={!canSend}
                accessibilityLabel="Gửi"
              >
```

- [ ] **Step 4: Render dải 3 chip**

Thêm hằng số module-level (cạnh `mdStyles`, trước `export default function Chat()`):
```typescript
const ONBOARDING_CHIPS = ["Tạo project", "Xem công việc", "Xem thử làm được gì"];
```

Trong JSX, ngay sau thẻ đóng `<FlatList ... />` (dòng 644, TRƯỚC khối `{runningTool && ...}`), thêm:
```tsx
      {!historyMode && rows.length === 1 && rows[0].kind === "assistant" && rows[0].isSeed && (
        <View style={styles.onboardingChipsRow}>
          {ONBOARDING_CHIPS.map((label) => (
            <TouchableOpacity
              key={label}
              style={styles.onboardingChip}
              onPress={() => submit(label)}
            >
              <Text style={styles.onboardingChipText}>{label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
```

Thêm style (cạnh `loadOlder`/`loadOlderText`):
```typescript
  onboardingChipsRow: {
    flexDirection: "row", flexWrap: "wrap", gap: spacing.sm,
    paddingHorizontal: spacing.lg, paddingBottom: spacing.sm,
  },
  onboardingChip: {
    backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.borderStrong,
    borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
  },
  onboardingChipText: { color: colors.text, fontFamily: fonts.semibold, fontSize: 13 },
```

- [ ] **Step 5: Kiểm tra tsc**

Run (trong `frontend/`): `npx tsc --noEmit`
Expected: 0 lỗi.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/chat.ts frontend/app/main/chat.tsx
git commit -m "feat(fe): dai 3 chip onboarding duoi seed message (Phase 6)"
```

---

### Task 7: Verify toàn bộ + cập nhật docs

**Files:**
- Modify: `PROJECT_CONTEXT.md`

- [ ] **Step 1: Full pytest**

Run (trong `backend/`, sau `docker compose up -d postgres redis` + `alembic upgrade head`): `.venv\Scripts\python.exe -m pytest tests/ -v`
Expected: tất cả PASS (số test tăng so với 696 trước đó — xem `PROJECT_CONTEXT.md` mục 10; 0 fail). Nếu có fail, sửa trước khi tiếp.

- [ ] **Step 2: Full tsc**

Run (trong `frontend/`): `npx tsc --noEmit`
Expected: 0 lỗi.

- [ ] **Step 3: Smoke migration trên Postgres dev**

Run (trong `backend/`): `alembic upgrade head`
Expected: đã ở head (migration Task 1 đã áp), không lỗi.

- [ ] **Step 4: Cập nhật `PROJECT_CONTEXT.md`**

Cập nhật: mục 6 (thêm đoạn "Onboarding (Phase 6)" — seed message/chip/coach block/import text, ghi rõ CEO-only, `get_workload_summary` giữ quyết định không xây), mục 9 (thêm migration `message_is_seed_flag` + cột `Message.is_seed`), mục 13 (dòng tiến độ mới, ngày hôm nay). Đổi "Last verified"/"Verified against commit" sang commit HEAD mới. Dùng Edit/Write (KHÔNG PowerShell Set-Content).

- [ ] **Step 5: Commit docs**

```bash
git add PROJECT_CONTEXT.md
git commit -m "docs: PROJECT_CONTEXT.md - Phase 6 onboarding (seed message + chip + coach block + import text)"
```

---

## Self-Review

**1. Spec coverage:**
- Seed message (spec §2) → Task 1-2. ✔
- 3 chip (spec §3) → Task 6. ✔
- Coach block (spec §4) → Task 3-4. ✔
- Import text (spec §5) → Task 4 (Step 3a). ✔
- 10.1 không làm gì thêm (spec §0) → không có task, đúng chủ đích. ✔
- `MessageOut.is_seed` + export OpenAPI (spec §6) → Task 5. ✔
- FE `Message.is_seed` + chip UI (spec §6) → Task 6. ✔
- Test đầy đủ (spec §6) → mỗi task backend có test; FE verify bằng tsc. ✔
- Không làm 10.2/10.3/10.4, không xây `get_workload_summary`, không chip Excel, không upload `.xlsx`, không onboarding cho manager/employee (spec §7) → không có task nào cho các mục này. ✔

**2. Placeholder scan:** Không có TBD/TODO; mọi step có code đầy đủ.

**3. Type consistency:**
- `get_coach_flags(db, workspace_id) -> dict[str, bool]` — Task 3/4 khớp.
- `render_coach_block(flags: dict[str, bool]) -> str | None` — Task 3/4 khớp.
- `Message.is_seed: bool` (Task 1) → `MessageOut.is_seed: bool` (Task 5) → FE `Message.is_seed: boolean` (Task 6) — nhất quán.
- `submit(overrideText?: string)` — Task 6 định nghĩa + dùng nội bộ (chip + nút gửi), đã lưu ý sửa call site cũ `onPress={submit}` để tránh truyền nhầm event object.

Không phát hiện lệch tên/kiểu.
