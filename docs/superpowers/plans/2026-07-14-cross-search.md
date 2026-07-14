# Tìm kiếm xuyên suốt — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans hoặc superpowers:subagent-driven-development để thực thi plan này task-by-task. Checkbox (`- [ ]`) để tracking.

**Goal:** CEO/manager/nhân viên gõ 1 từ khóa (qua chat hoặc REST) và nhận về task/note/ghi âm/người/skill liên quan, mỗi nhóm đã lọc đúng theo quyền hiển thị của họ.

**Architecture:** 1 service mới `app/services/search_service.py` với 5 hàm con (mỗi entity 1 hàm), mỗi hàm tái dùng nguyên logic phân quyền đã có (`visible_task_ids`, `visible_user_ids`, author-scoping của note/voice note, CEO/SkillGrant của skill) + `ILIKE` substring không phân biệt hoa/thường trên field text liên quan. 1 REST endpoint `GET /api/v1/search?q=...` + 1 tool chat `search` — cả hai chỉ gọi `search_service.search()`, không thêm logic phân quyền mới. Không có model/migration mới.

**Tech Stack:** BE như cũ (FastAPI + SQLAlchemy async). Không thêm dependency.

**Spec thiết kế:** [docs/superpowers/specs/2026-07-14-cross-search-design.md](../specs/2026-07-14-cross-search-design.md)

## Global Constraints (CLAUDE.md)
- Mọi bảng (trừ `workspaces`) có `workspace_id`; mọi query phải lọc theo workspace.
- Quyền kiểm tra ở **service layer**, không bao giờ ở prompt/model.
- Danh tính (`actor`) lấy từ JWT phiên đăng nhập — không bao giờ từ tham số client hay model.
- Route dưới `/api/v1`. Đổi API contract = chạy lại `export_openapi.py` cho FE.
- TDD: test trước, code sau; mỗi task một commit.
- Không commit secrets.

---

### Task 1: `search_service.py` — service layer đầy đủ (TDD)

**Files:**
- Create: `backend/app/services/search_service.py`
- Test: `backend/tests/test_search_service.py`

**Interfaces:**
- Produces: `async def search(db: AsyncSession, actor: User, q: str) -> dict` trả về
  `{"tasks": [...], "notes": [...], "voice_notes": [...], "users": [...], "skills": [...]}`.
  Task 2 (REST) và Task 3 (tool) sau đó đều chỉ gọi hàm `search()` này, không viết lại logic.
- Consumes: `app.permissions.visible_task_ids(db, actor) -> set[uuid.UUID]`,
  `app.permissions.visible_user_ids(db, actor) -> list[uuid.UUID]` (đã có sẵn, không sửa).

- [ ] **Step 1: Viết file test thất bại**

Tạo `backend/tests/test_search_service.py`:

```python
import pytest

from app.models import (
    Note, Project, Role, Skill, SkillGrant, SkillKind, Task, TaskAssignee, User,
    VoiceNote, Workspace,
)
from app.services import search_service


async def _seed(db):
    """Workspace A: CEO + 1 manager + 1 nhan vien duoi quyen manager + 1 nhan vien khac
    (khong thuoc doi ai) + 1 project."""
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="ceo@a.vn", password_hash="x", full_name="Sep CEO",
              role=Role.ceo, is_root=True)
    mgr = User(workspace_id=ws.id, email="mgr@a.vn", password_hash="x", full_name="Quan Ly",
              role=Role.manager)
    db.add_all([ceo, mgr])
    await db.flush()
    emp = User(workspace_id=ws.id, email="emp@a.vn", password_hash="x", full_name="Nhan Vien",
              role=Role.employee, manager_id=mgr.id)
    other_emp = User(workspace_id=ws.id, email="other@a.vn", password_hash="x", full_name="Khac",
                     role=Role.employee)
    db.add_all([emp, other_emp])
    await db.flush()
    project = Project(workspace_id=ws.id, name="Website", created_by=ceo.id)
    db.add(project)
    await db.flush()
    return ws, ceo, mgr, emp, other_emp, project


@pytest.mark.asyncio
async def test_search_tasks_matches_case_insensitive_and_respects_visibility(db_session):
    ws, ceo, mgr, emp, other_emp, project = await _seed(db_session)
    t1 = Task(workspace_id=ws.id, project_id=project.id, title="Sua loi website",
             created_by=ceo.id)
    t2 = Task(workspace_id=ws.id, project_id=project.id, title="Viet tai lieu",
             created_by=ceo.id)
    db_session.add_all([t1, t2])
    await db_session.flush()
    db_session.add(TaskAssignee(workspace_id=ws.id, task_id=t1.id, user_id=emp.id))
    await db_session.commit()

    ceo_result = await search_service.search(db_session, ceo, "WEBSITE")
    assert [t["title"] for t in ceo_result["tasks"]] == ["Sua loi website"]

    emp_result = await search_service.search(db_session, emp, "WEBSITE")
    assert [t["title"] for t in emp_result["tasks"]] == ["Sua loi website"]

    other_result = await search_service.search(db_session, other_emp, "WEBSITE")
    assert other_result["tasks"] == []  # khong duoc giao task nay


@pytest.mark.asyncio
async def test_search_notes_only_own_note_never_others(db_session):
    ws, ceo, mgr, emp, other_emp, project = await _seed(db_session)
    db_session.add_all([
        Note(workspace_id=ws.id, author_id=emp.id, content="ghi chu ve website moi"),
        Note(workspace_id=ws.id, author_id=other_emp.id,
             content="ghi chu ve website cua nguoi khac"),
    ])
    await db_session.commit()

    emp_result = await search_service.search(db_session, emp, "website")
    assert [n["content"] for n in emp_result["notes"]] == ["ghi chu ve website moi"]

    ceo_result = await search_service.search(db_session, ceo, "website")
    assert ceo_result["notes"] == []  # CEO khong tao note nao nen khong thay gi, ke ca cua nguoi khac


@pytest.mark.asyncio
async def test_search_voice_notes_only_own(db_session):
    ws, ceo, mgr, emp, other_emp, project = await _seed(db_session)
    db_session.add_all([
        VoiceNote(workspace_id=ws.id, author_id=emp.id, file_path="a.m4a",
                 transcript="hop ve website hom nay"),
        VoiceNote(workspace_id=ws.id, author_id=other_emp.id, file_path="b.m4a",
                 transcript="hop ve website tuan sau"),
    ])
    await db_session.commit()

    emp_result = await search_service.search(db_session, emp, "website")
    assert [v["transcript"] for v in emp_result["voice_notes"]] == ["hop ve website hom nay"]


@pytest.mark.asyncio
async def test_search_users_respects_visible_user_ids(db_session):
    ws, ceo, mgr, emp, other_emp, project = await _seed(db_session)

    mgr_result = await search_service.search(db_session, mgr, "khac")
    assert mgr_result["users"] == []  # other_emp khong thuoc doi cua mgr

    ceo_result = await search_service.search(db_session, ceo, "khac")
    assert [u["full_name"] for u in ceo_result["users"]] == ["Khac"]


@pytest.mark.asyncio
async def test_search_skills_ceo_sees_all_others_only_granted(db_session):
    ws, ceo, mgr, emp, other_emp, project = await _seed(db_session)
    s1 = Skill(workspace_id=ws.id, name="Ky nang ban hang", kind=SkillKind.knowledge,
              created_by=ceo.id)
    s2 = Skill(workspace_id=ws.id, name="Ky nang ky thuat", kind=SkillKind.knowledge,
              created_by=ceo.id)
    db_session.add_all([s1, s2])
    await db_session.flush()
    db_session.add(SkillGrant(workspace_id=ws.id, skill_id=s1.id, user_id=emp.id,
                              granted_by=ceo.id))
    await db_session.commit()

    ceo_result = await search_service.search(db_session, ceo, "ky nang")
    assert len(ceo_result["skills"]) == 2

    emp_result = await search_service.search(db_session, emp, "ky nang")
    assert [s["name"] for s in emp_result["skills"]] == ["Ky nang ban hang"]


@pytest.mark.asyncio
async def test_search_workspace_isolation(db_session):
    ws, ceo, mgr, emp, other_emp, project = await _seed(db_session)
    ws2 = Workspace(name="B")
    db_session.add(ws2)
    await db_session.flush()
    ceo2 = User(workspace_id=ws2.id, email="ceo2@b.vn", password_hash="x", full_name="Sep B",
               role=Role.ceo, is_root=True)
    db_session.add(ceo2)
    await db_session.flush()
    project2 = Project(workspace_id=ws2.id, name="P2", created_by=ceo2.id)
    db_session.add(project2)
    await db_session.flush()
    db_session.add(Task(workspace_id=ws2.id, project_id=project2.id,
                        title="Website rieng cua B", created_by=ceo2.id))
    await db_session.commit()

    ceo_result = await search_service.search(db_session, ceo, "website")
    assert ceo_result["tasks"] == []  # task cua workspace B khong duoc thay du trung tu khoa


@pytest.mark.asyncio
async def test_search_limit_20_per_group(db_session):
    ws, ceo, mgr, emp, other_emp, project = await _seed(db_session)
    db_session.add_all([
        Task(workspace_id=ws.id, project_id=project.id, title=f"Website {i}", created_by=ceo.id)
        for i in range(25)
    ])
    await db_session.commit()

    result = await search_service.search(db_session, ceo, "website")
    assert len(result["tasks"]) == 20
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `cd backend && pytest tests/test_search_service.py -v`
Expected: FAIL với `ImportError: cannot import name 'search_service' from 'app.services'` (module chưa tồn tại)

- [ ] **Step 3: Viết `search_service.py`**

Tạo `backend/app/services/search_service.py`:

```python
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Note, Role, Skill, SkillGrant, Task, User, VoiceNote
from app.permissions import visible_task_ids, visible_user_ids

_LIMIT = 20


async def _search_tasks(db: AsyncSession, actor: User, q: str) -> list[dict]:
    ids = await visible_task_ids(db, actor)
    if not ids:
        return []
    rows = await db.execute(
        select(Task).where(
            Task.id.in_(ids),
            or_(Task.title.ilike(f"%{q}%"), Task.description.ilike(f"%{q}%")),
        ).order_by(Task.created_at.desc()).limit(_LIMIT)
    )
    return [{"id": str(t.id), "title": t.title, "status": t.status.value,
            "project_id": str(t.project_id)} for t in rows.scalars()]


async def _search_notes(db: AsyncSession, actor: User, q: str) -> list[dict]:
    rows = await db.execute(
        select(Note).where(
            Note.workspace_id == actor.workspace_id, Note.author_id == actor.id,
            Note.content.ilike(f"%{q}%"),
        ).order_by(Note.created_at.desc()).limit(_LIMIT)
    )
    return [{"id": str(n.id), "content": n.content, "note_date": n.note_date.isoformat()}
           for n in rows.scalars()]


async def _search_voice_notes(db: AsyncSession, actor: User, q: str) -> list[dict]:
    rows = await db.execute(
        select(VoiceNote).where(
            VoiceNote.workspace_id == actor.workspace_id, VoiceNote.author_id == actor.id,
            VoiceNote.transcript.ilike(f"%{q}%"),
        ).order_by(VoiceNote.created_at.desc()).limit(_LIMIT)
    )
    return [{"id": str(v.id), "transcript": v.transcript,
            "created_at": v.created_at.isoformat()} for v in rows.scalars()]


async def _search_users(db: AsyncSession, actor: User, q: str) -> list[dict]:
    ids = await visible_user_ids(db, actor)
    if not ids:
        return []
    rows = await db.execute(
        select(User).where(
            User.id.in_(ids),
            or_(User.full_name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")),
        ).order_by(User.full_name.asc()).limit(_LIMIT)
    )
    return [{"id": str(u.id), "full_name": u.full_name, "email": u.email,
            "role": u.role.value} for u in rows.scalars()]


async def _search_skills(db: AsyncSession, actor: User, q: str) -> list[dict]:
    query = select(Skill).where(Skill.workspace_id == actor.workspace_id,
                                Skill.name.ilike(f"%{q}%"))
    if actor.role != Role.ceo:
        query = query.join(SkillGrant, SkillGrant.skill_id == Skill.id).where(
            SkillGrant.user_id == actor.id)
    rows = await db.execute(query.order_by(Skill.created_at.desc()).limit(_LIMIT))
    return [{"id": str(s.id), "name": s.name, "kind": s.kind.value} for s in rows.scalars()]


async def search(db: AsyncSession, actor: User, q: str) -> dict:
    return {
        "tasks": await _search_tasks(db, actor, q),
        "notes": await _search_notes(db, actor, q),
        "voice_notes": await _search_voice_notes(db, actor, q),
        "users": await _search_users(db, actor, q),
        "skills": await _search_skills(db, actor, q),
    }
```

- [ ] **Step 4: Chạy test để xác nhận qua**

Run: `cd backend && pytest tests/test_search_service.py -v`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/search_service.py backend/tests/test_search_service.py
git commit -m "feat(be): search_service - tim kiem xuyen suot task/note/voice/user/skill"
```

---

### Task 2: Schema + REST endpoint `GET /api/v1/search` (TDD)

**Files:**
- Modify: `backend/app/schemas.py` (thêm cuối file)
- Create: `backend/app/api/search.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_search_api.py`

**Interfaces:**
- Consumes: `search_service.search(db, actor, q) -> dict` (Task 1).
- Produces: schema `SearchOut` dùng lại ở Task 3 khi cần (không bắt buộc — tool trả dict thô).

- [ ] **Step 1: Viết test REST thất bại**

Tạo `backend/tests/test_search_api.py`:

```python
import pytest

from tests.conftest import _ceo_headers


@pytest.mark.asyncio
async def test_search_finds_own_task_and_note(client):
    headers = await _ceo_headers(client)
    p = (await client.post("/api/v1/projects", headers=headers, json={"name": "P"})).json()
    await client.post("/api/v1/tasks", headers=headers,
                      json={"project_id": p["id"], "title": "Sua loi website"})
    await client.post("/api/v1/notes", headers=headers, json={"content": "ghi chu website"})

    r = await client.get("/api/v1/search", headers=headers, params={"q": "website"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [t["title"] for t in body["tasks"]] == ["Sua loi website"]
    assert [n["content"] for n in body["notes"]] == ["ghi chu website"]
    assert body["voice_notes"] == [] and body["users"] == [] and body["skills"] == []


@pytest.mark.asyncio
async def test_search_empty_query_rejected(client):
    headers = await _ceo_headers(client)
    r = await client.get("/api/v1/search", headers=headers, params={"q": ""})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_search_cross_workspace_isolated(client):
    ceo_a = await _ceo_headers(client)
    p = (await client.post("/api/v1/projects", headers=ceo_a, json={"name": "P"})).json()
    await client.post("/api/v1/tasks", headers=ceo_a,
                      json={"project_id": p["id"], "title": "Bi mat cong ty A"})

    resp_b = await client.post("/api/v1/auth/signup-workspace", json={
        "workspace_name": "Cong ty B", "email": "ceo@b.vn", "password": "secret123",
        "full_name": "Sep B", "device_uuid": "dev-b", "device_name": "",
    })
    ceo_b = {"Authorization": f"Bearer {resp_b.json()['access_token']}"}

    r = await client.get("/api/v1/search", headers=ceo_b, params={"q": "bi mat"})
    assert r.status_code == 200
    assert r.json()["tasks"] == []
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `cd backend && pytest tests/test_search_api.py -v`
Expected: FAIL với `404 Not Found` (chưa có route `/api/v1/search`)

- [ ] **Step 3: Thêm schema vào `app/schemas.py`**

Thêm vào cuối `backend/app/schemas.py` (sau `ReportScheduleOut`):

```python
class SearchTaskOut(BaseModel):
    id: uuid.UUID
    title: str
    status: TaskStatus
    project_id: uuid.UUID


class SearchNoteOut(BaseModel):
    id: uuid.UUID
    content: str
    note_date: dt.date


class SearchVoiceNoteOut(BaseModel):
    id: uuid.UUID
    transcript: str
    created_at: dt.datetime


class SearchUserOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    role: str


class SearchSkillOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: SkillKind


class SearchOut(BaseModel):
    tasks: list[SearchTaskOut]
    notes: list[SearchNoteOut]
    voice_notes: list[SearchVoiceNoteOut]
    users: list[SearchUserOut]
    skills: list[SearchSkillOut]
```

`TaskStatus`, `SkillKind` đã được import sẵn ở đầu `schemas.py` (dùng cho các schema khác) — không cần thêm import.

- [ ] **Step 4: Tạo `app/api/search.py`**

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import SearchOut
from app.services import search_service

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.get("", response_model=SearchOut)
async def search(q: str = Query(min_length=1), actor: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    return await search_service.search(db, actor, q)
```

- [ ] **Step 5: Đăng ký router trong `app/main.py`**

Sửa `backend/app/main.py`:

```python
from app.api import (
    auth, chat, dashboard, devices, emails, instructions, invites, notes, portal,
    projects, report_schedules, reports, search, skills, subscription, tasks, users,
    voice_notes, workspace, ws,
)
```

Và thêm dòng (ngay sau `app.include_router(report_schedules.router)`):

```python
    app.include_router(search.router)
```

- [ ] **Step 6: Chạy test để xác nhận qua**

Run: `cd backend && pytest tests/test_search_api.py -v`
Expected: `3 passed`

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/api/search.py backend/app/main.py backend/tests/test_search_api.py
git commit -m "feat(be): REST GET /api/v1/search"
```

---

### Task 3: Tool chat `search` + migration openapi (TDD)

**Files:**
- Modify: `backend/app/agent/tools.py`
- Modify: `backend/tests/test_agent_tools_report.py` (bump đếm tool)
- Test: `backend/tests/test_agent_tools_search.py`
- Modify: `openapi.json` (regenerate, không sửa tay)

**Interfaces:**
- Consumes: `search_service.search(db, actor, q)` (Task 1).
- Produces: tool `"search"` đăng ký trong `TOOLS` (đọc bởi agent loop đã có từ Plan 3, không cần sửa gì ở đó).

- [ ] **Step 1: Viết test tool thất bại**

Tạo `backend/tests/test_agent_tools_search.py`:

```python
import pytest

from app.agent.tools import TOOLS, call_tool
from app.models import Role, User, Workspace


async def _ceo(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    await db.commit()
    return ws, ceo


def test_search_tool_registered_and_not_sensitive():
    assert "search" in TOOLS
    assert TOOLS["search"].sensitive is False
    assert len(TOOLS) == 39  # +search (2026-07-14)


@pytest.mark.asyncio
async def test_search_tool_returns_all_groups_empty_when_no_match(db_session):
    ws, ceo = await _ceo(db_session)

    result = await call_tool(db_session, ceo, "search", {"q": "khong ton tai"})
    assert result == {"tasks": [], "notes": [], "voice_notes": [], "users": [], "skills": []}


@pytest.mark.asyncio
async def test_search_tool_rejects_empty_query(db_session):
    ws, ceo = await _ceo(db_session)

    result = await call_tool(db_session, ceo, "search", {"q": ""})
    assert result["error"] == "invalid_input"
```

Sửa dòng cuối `backend/tests/test_agent_tools_report.py` (assertion đếm tool đã lỗi thời sau Task này):

```python
    assert len(TOOLS) == 39  # +list_users +3 report-schedule +search (2026-07-14)
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `cd backend && pytest tests/test_agent_tools_search.py tests/test_agent_tools_report.py -v`
Expected: FAIL — `test_search_tool_registered_and_not_sensitive` báo `"search" not in TOOLS`; `test_generate_report_registered_as_22nd_tool_not_sensitive` báo `38 != 39`.

- [ ] **Step 3: Thêm tool vào `app/agent/tools.py`**

Sửa dòng import pydantic đầu file (`backend/app/agent/tools.py` dòng 9):

```python
from pydantic import BaseModel, Field
```

Thêm import `search_service` vào khối import services (dòng 18-22):

```python
from app.services import (
    auth_service, dashboard_service, email_service, instruction_service, note_service,
    portal_service, report_schedule_service, report_service, search_service, skill_service,
    voice_service, work_service,
)
```

Thêm cuối file `backend/app/agent/tools.py`:

```python
class SearchToolIn(BaseModel):
    q: str = Field(min_length=1)


async def _search(db, actor, body: SearchToolIn) -> dict:
    return await search_service.search(db, actor, body.q)


_register("search", "Tim kiem xuyen suot theo tu khoa: task, note, ghi am, nguoi, skill "
          "(chi trong pham vi actor duoc thay). Dung khi user hoi 'tim ... lien quan toi X'.",
          SearchToolIn, _search)
```

- [ ] **Step 4: Chạy test để xác nhận qua**

Run: `cd backend && pytest tests/test_agent_tools_search.py tests/test_agent_tools_report.py -v`
Expected: `8 passed` (3 test mới trong `test_agent_tools_search.py` + 5 test có sẵn trong `test_agent_tools_report.py`)

- [ ] **Step 5: Chạy toàn bộ test suite + export openapi**

```bash
cd backend && pytest tests/ -q
python scripts/export_openapi.py
```

Expected: tất cả pass (251 test — 238 hiện tại + 7 ở Task 1 + 3 ở Task 2 + 3 tool mới ở Task 3), file `openapi.json` ở repo root được ghi đè.

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/tools.py backend/tests/test_agent_tools_search.py backend/tests/test_agent_tools_report.py openapi.json
git commit -m "feat(be): tool chat search + openapi"
```

---

## Ghi chú

- Không có migration DB — search chỉ đọc dữ liệu đã có qua model hiện hữu.
- Không làm FE cho tính năng này trong plan này (giống pattern Plan 9) — REST endpoint sẵn dùng ngay khi cần, tool chat đã đủ dùng qua chat ngay lập tức.
- Lịch sử chat (Message) và báo cáo (Report) cố ý ngoài phạm vi (xem spec §1) — có thể thêm sau bằng cách nối thêm 1 nhóm mới vào `search()` nếu cần, không phải thiết kế lại.
