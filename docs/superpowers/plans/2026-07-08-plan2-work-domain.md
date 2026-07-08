# Plan 2 — Domain Công việc & Skill (MVP Backend)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm domain công việc (projects/tasks/updates/comments) và skill 2 lớp (nội dung có version + trạng thái task sống) với REST CRUD theo đúng ma trận quyền — nền dữ liệu cho agent tools ở Plan 3.

**Architecture:** Mở rộng monolith Plan 1: models mới trong `app/models.py`, quyền mở rộng trong `app/permissions.py`, business logic trong `app/services/work_service.py` + `skill_service.py`, routers mới. Mọi bảng có `workspace_id`, mọi query lọc workspace. Task 1 xử lý 3 hardening carry-over từ final review Plan 1.

**Tech Stack:** như Plan 1 (FastAPI, SQLAlchemy 2.0 async, pytest + SQLite StaticPool).

## Global Constraints

- Mọi bảng mới có `workspace_id` NOT NULL FK `workspaces.id`; mọi query lọc theo workspace của actor.
- Ma trận quyền (funtional-plan §3): **CEO** tạo/sửa project & task, gán người, tạo/sửa/cấp skill (chỉ CEO sửa nội dung skill); **Manager** xem task được phân (mình + nhân viên trực thuộc + project mình phụ trách), cập nhật tiến độ của mình & nhân viên dưới quyền; **Employee** xem/cập nhật task của chính mình. Vượt quyền → 403. Khác workspace → 404 (không lộ tồn tại).
- Bình luận trong task KHÔNG bị giới hạn bởi ma trận nhân viên ⇎ nhân viên (đã chốt ở funtional-plan §6.4) — ai thấy task đều đọc/viết comment được.
- Skill 2 lớp: nội dung CEO soạn có version tăng dần; `use_skill` trả nội dung version mới nhất + trạng thái sống của task; ghi `skill_usage_log` kèm version.
- Danh tính từ JWT (`get_current_user`); quyền ở service layer; TDD; mỗi task một commit; không commit secrets.
- Chạy lệnh trong `backend/`; Windows PowerShell: `Set-Location "d:\8. AI\ai-assistant\backend"` rồi `.venv\Scripts\python.exe -m pytest tests/ -v`.
- Suite hiện tại: **38 passed** — không được làm hỏng test cũ.

## Cấu trúc file (mới/sửa)

```
backend/app/
  models.py           # sửa: thêm domain + skill models
  permissions.py      # sửa: visible_task_ids, visible_project_ids, can_update_progress
  schemas.py          # sửa: thêm schemas domain + skill
  deps.py             # sửa (Task 1): HTTPBearer
  config.py           # sửa (Task 1): env field + fail-fast
  services/
    auth_service.py   # sửa (Task 1): normalize email
    work_service.py   # mới: project/task/update/comment logic
    skill_service.py  # mới: skill logic
  api/
    projects.py       # mới
    tasks.py          # mới (kèm updates, comments, assignees)
    skills.py         # mới
backend/tests/
  conftest.py         # sửa (Task 1): chuyển helpers dùng chung vào đây
  test_hardening.py   # mới (Task 1)
  test_work_models.py, test_work_permissions.py, test_projects.py,
  test_tasks.py, test_task_updates.py, test_comments.py, test_skills.py  # mới
```

---

### Task 1: Hardening carry-over từ Plan 1

3 việc final review Plan 1 khuyến nghị làm sớm + dọn test helpers.

**Files:**
- Modify: `backend/app/services/auth_service.py`, `backend/app/deps.py`, `backend/app/config.py`, `backend/app/main.py`, `backend/tests/conftest.py`, `backend/tests/test_invites.py`, `backend/tests/test_permissions.py`, `backend/tests/test_lock.py`
- Test: `backend/tests/test_hardening.py` (mới)

**Interfaces:**
- Consumes: toàn bộ auth Plan 1.
- Produces: (a) email luôn lowercase khi ghi/tra cứu; (b) `deps.get_current_user` dùng `HTTPBearer` → openapi.json có security scheme `bearerAuth`; (c) `config.assert_safe_config(settings)` raise `RuntimeError` khi `env="production"` mà `jwt_secret` là default — gọi trong `create_app()`; (d) helpers `SIGNUP`, `_ceo_headers`, `_invite_and_join` sống trong `tests/conftest.py`, các test file import từ `tests.conftest`.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_hardening.py`:
```python
import pytest

from app.config import Settings, assert_safe_config
from tests.conftest import SIGNUP


@pytest.mark.asyncio
async def test_email_case_insensitive_login(client):
    await client.post("/api/v1/auth/signup-workspace", json={**SIGNUP, "email": "CEO@A.vn"})
    resp = await client.post("/api/v1/auth/login", json={
        "email": "ceo@a.vn", "password": SIGNUP["password"],
        "device_uuid": "d", "device_name": "",
    })
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_duplicate_email_case_insensitive_409(client):
    await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    resp = await client.post("/api/v1/auth/signup-workspace",
                             json={**SIGNUP, "email": SIGNUP["email"].upper()})
    assert resp.status_code == 409


def test_prod_config_fail_fast():
    with pytest.raises(RuntimeError):
        assert_safe_config(Settings(env="production"))
    assert_safe_config(Settings(env="production", jwt_secret="x" * 48))  # ok
    assert_safe_config(Settings())  # dev ok


def test_openapi_has_bearer_scheme():
    from app.main import create_app
    spec = create_app().openapi()
    schemes = spec.get("components", {}).get("securitySchemes", {})
    assert any(s.get("scheme") == "bearer" for s in schemes.values())
```

Chuyển helpers vào `backend/tests/conftest.py` (thêm vào cuối file hiện có):
```python
SIGNUP = {
    "workspace_name": "Cong ty A", "email": "ceo@a.vn", "password": "secret123",
    "full_name": "Sep", "device_uuid": "dev-1", "device_name": "",
}


async def _ceo_headers(client):
    resp = await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _invite_and_join(client, headers, role, email, manager_id=None):
    inv = await client.post("/api/v1/invites", headers=headers,
                            json={"role": role, "manager_id": manager_id})
    assert inv.status_code == 201, inv.text
    join = await client.post("/api/v1/auth/signup-invite", json={
        "token": inv.json()["token"], "email": email, "password": "pw123456",
        "full_name": email, "device_uuid": "d-" + email, "device_name": "",
    })
    assert join.status_code == 201, join.text
    return join.json()
```
Trong `test_invites.py`: xóa định nghĩa SIGNUP/_ceo_headers/_invite_and_join, thay bằng `from tests.conftest import SIGNUP, _ceo_headers, _invite_and_join`. Trong `test_permissions.py` và `test_lock.py`: đổi `from tests.test_invites import ...` thành `from tests.conftest import ...`.

Run: `pytest tests/test_hardening.py -v` → FAIL.

- [ ] **Step 2: Implement**

`backend/app/config.py` — thêm field + hàm:
```python
class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///:memory:"
    jwt_secret: str = "dev-secret-change-me"
    access_ttl_minutes: int = 15
    refresh_ttl_days: int = 30
    env: str = "dev"

    model_config = {"env_file": ".env"}


_DEFAULT_SECRETS = {"dev-secret-change-me", "dev-secret", ""}


def assert_safe_config(s: Settings) -> None:
    if s.env == "production" and (s.jwt_secret in _DEFAULT_SECRETS or len(s.jwt_secret) < 32):
        raise RuntimeError("unsafe jwt_secret in production - set a >=32 char JWT_SECRET")
```

Trong `create_app()` (main.py), dòng đầu: `assert_safe_config(get_settings())` (import từ app.config).

`backend/app/deps.py` — chuyển sang HTTPBearer:
```python
import uuid

import jwt as pyjwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.db import get_db
from app.models import User, UserStatus

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(401, "missing_token")
    try:
        payload = security.decode_access_token(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (pyjwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(401, "invalid_token")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(401, "user_not_found")
    if user.status == UserStatus.locked:
        raise HTTPException(403, "account_locked")
    return user
```

`backend/app/services/auth_service.py` — chuẩn hóa email tại MỌI cửa vào (4 chỗ): đầu `signup_workspace`, `login`, `signup_invite`, `request_unlock` thêm `email = email.strip().lower()`.

- [ ] **Step 3: Run toàn bộ → PASS** (`pytest tests/ -v`, kỳ vọng **42 passed** = 38 cũ + 4 mới), rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): hardening - email normalize, HTTPBearer scheme, prod secret fail-fast, shared test helpers"
```

---

### Task 2: Domain models — project/task/assignee/update/comment

**Files:**
- Modify: `backend/app/models.py`
- Test: `backend/tests/test_work_models.py`

**Interfaces:**
- Produces (models — mọi bảng có workspace_id, id UUID pk, created_at):
  - Enum `TaskStatus` (todo/in_progress/blocked/done), `TaskPriority` (low/medium/high).
  - `Project(id, workspace_id, name, goal, status[str, default "active"], deadline?, owner_id?→users, created_by→users, created_at)`
  - `Task(id, workspace_id, project_id→projects, title, description, status[TaskStatus, default todo], percent[int, default 0], deadline?, priority[TaskPriority, default medium], created_by, created_at)`
  - `TaskAssignee(id, workspace_id, task_id, user_id)` — unique (task_id, user_id)
  - `TaskUpdate(id, workspace_id, task_id, author_id, content, percent?, status?[TaskStatus], created_at)`
  - `TaskComment(id, workspace_id, task_id, author_id, content, created_at)`

- [ ] **Step 1: Viết test fail**

`backend/tests/test_work_models.py`:
```python
import pytest
from sqlalchemy import select

from app.models import (
    Project, Role, Task, TaskAssignee, TaskPriority, TaskStatus, User, Workspace,
)


@pytest.mark.asyncio
async def test_project_task_assignee_roundtrip(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    u = User(workspace_id=ws.id, email="c@a.vn", password_hash="x",
             full_name="C", role=Role.ceo, is_root=True)
    db_session.add(u)
    await db_session.flush()
    p = Project(workspace_id=ws.id, name="P1", created_by=u.id)
    db_session.add(p)
    await db_session.flush()
    t = Task(workspace_id=ws.id, project_id=p.id, title="T1", created_by=u.id)
    db_session.add(t)
    await db_session.flush()
    db_session.add(TaskAssignee(workspace_id=ws.id, task_id=t.id, user_id=u.id))
    await db_session.commit()

    found = (await db_session.execute(select(Task))).scalar_one()
    assert found.status == TaskStatus.todo
    assert found.percent == 0
    assert found.priority == TaskPriority.medium
```

Run → FAIL.

- [ ] **Step 2: Implement — thêm vào cuối `backend/app/models.py`**

(bổ sung import: `Integer, Text, UniqueConstraint` từ sqlalchemy)
```python
class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"


class TaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    goal: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.todo)
    percent: Mapped[int] = mapped_column(Integer, default=0)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    priority: Mapped[TaskPriority] = mapped_column(Enum(TaskPriority), default=TaskPriority.medium)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TaskAssignee(Base):
    __tablename__ = "task_assignees"
    __table_args__ = (UniqueConstraint("task_id", "user_id", name="uq_task_assignee"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TaskUpdate(Base):
    __tablename__ = "task_updates"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text, default="")
    percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[TaskStatus | None] = mapped_column(Enum(TaskStatus), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TaskComment(Base):
    __tablename__ = "task_comments"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
```

- [ ] **Step 3: Run toàn bộ → PASS (43)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): domain models - project/task/assignee/update/comment"
```

---

### Task 3: Mở rộng permission layer cho domain

**Files:**
- Modify: `backend/app/permissions.py`
- Test: `backend/tests/test_work_permissions.py`

**Interfaces:**
- Produces (thêm vào `app/permissions.py`):
  - `direct_report_ids(db, actor) -> list[uuid.UUID]` — id nhân viên có manager_id == actor.id (cùng workspace).
  - `visible_task_ids(db, actor) -> set[uuid.UUID]`: CEO = mọi task workspace; manager = task gán cho mình/nhân viên trực thuộc ∪ task thuộc project mình là owner; employee = task gán cho mình.
  - `visible_project_ids(db, actor) -> set[uuid.UUID]`: CEO = tất cả; khác = project chứa visible task ∪ (manager) project owner_id == mình.
  - `can_update_progress(db, actor, task) -> bool`: CEO cùng workspace = True; manager/employee = task được gán cho mình hoặc (manager) cho nhân viên trực thuộc. **Nghiêm theo assignment, không tính project-owner.**
  - `get_visible_task_or_404(db, actor, task_id) -> Task` — load task, khác workspace hoặc ngoài visible → 404.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_work_permissions.py` — dựng bằng ORM trực tiếp (nhanh, không qua API):
```python
import pytest

from app import permissions
from app.models import (
    Project, Role, Task, TaskAssignee, User, Workspace,
)


async def _world(db):
    """ws: ceo, m1(+e1), m2(+e2); P1 owner=m1; t_e1 gán e1; t_m2 gán m2; t_free không gán (thuộc P1)."""
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()

    def mk(email, role, mgr=None, root=False):
        return User(workspace_id=ws.id, email=email, password_hash="x",
                    full_name=email, role=role, manager_id=mgr, is_root=root)

    ceo = mk("c@a.vn", Role.ceo, root=True)
    db.add(ceo); await db.flush()
    m1 = mk("m1@a.vn", Role.manager); m2 = mk("m2@a.vn", Role.manager)
    db.add_all([m1, m2]); await db.flush()
    e1 = mk("e1@a.vn", Role.employee, mgr=m1.id); e2 = mk("e2@a.vn", Role.employee, mgr=m2.id)
    db.add_all([e1, e2]); await db.flush()

    p1 = Project(workspace_id=ws.id, name="P1", owner_id=m1.id, created_by=ceo.id)
    db.add(p1); await db.flush()
    t_e1 = Task(workspace_id=ws.id, project_id=p1.id, title="t_e1", created_by=ceo.id)
    t_m2 = Task(workspace_id=ws.id, project_id=p1.id, title="t_m2", created_by=ceo.id)
    t_free = Task(workspace_id=ws.id, project_id=p1.id, title="t_free", created_by=ceo.id)
    db.add_all([t_e1, t_m2, t_free]); await db.flush()
    db.add_all([
        TaskAssignee(workspace_id=ws.id, task_id=t_e1.id, user_id=e1.id),
        TaskAssignee(workspace_id=ws.id, task_id=t_m2.id, user_id=m2.id),
    ])
    await db.commit()
    return ceo, m1, m2, e1, e2, t_e1, t_m2, t_free


@pytest.mark.asyncio
async def test_visible_task_matrix(db_session):
    ceo, m1, m2, e1, e2, t_e1, t_m2, t_free = await _world(db_session)
    assert await permissions.visible_task_ids(db_session, ceo) == {t_e1.id, t_m2.id, t_free.id}
    # m1: t_e1 (nhân viên e1) + toàn bộ task của P1 (owner) => cả 3
    assert await permissions.visible_task_ids(db_session, m1) == {t_e1.id, t_m2.id, t_free.id}
    # m2: chỉ task mình được gán
    assert await permissions.visible_task_ids(db_session, m2) == {t_m2.id}
    assert await permissions.visible_task_ids(db_session, e1) == {t_e1.id}
    assert await permissions.visible_task_ids(db_session, e2) == set()


@pytest.mark.asyncio
async def test_can_update_progress_matrix(db_session):
    ceo, m1, m2, e1, e2, t_e1, t_m2, t_free = await _world(db_session)
    assert await permissions.can_update_progress(db_session, ceo, t_free)
    assert await permissions.can_update_progress(db_session, e1, t_e1)
    assert not await permissions.can_update_progress(db_session, e2, t_e1)
    assert await permissions.can_update_progress(db_session, m1, t_e1)   # nhân viên trực thuộc
    assert not await permissions.can_update_progress(db_session, m1, t_m2)  # m2 không thuộc m1
    assert not await permissions.can_update_progress(db_session, m1, t_free)  # owner-project KHÔNG đủ để update


@pytest.mark.asyncio
async def test_get_visible_task_or_404(db_session):
    from fastapi import HTTPException
    ceo, m1, m2, e1, e2, t_e1, t_m2, t_free = await _world(db_session)
    ok = await permissions.get_visible_task_or_404(db_session, e1, t_e1.id)
    assert ok.id == t_e1.id
    with pytest.raises(HTTPException) as exc:
        await permissions.get_visible_task_or_404(db_session, e1, t_m2.id)
    assert exc.value.status_code == 404
```

Run → FAIL.

- [ ] **Step 2: Implement — thêm vào `backend/app/permissions.py`**

(bổ sung import: `Project, Task, TaskAssignee` từ app.models)
```python
async def direct_report_ids(db: AsyncSession, actor: User) -> list[uuid.UUID]:
    rows = await db.execute(select(User.id).where(
        User.workspace_id == actor.workspace_id, User.manager_id == actor.id,
    ))
    return list(rows.scalars())


async def _assigned_task_ids(db: AsyncSession, actor: User, user_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    rows = await db.execute(select(TaskAssignee.task_id).where(
        TaskAssignee.workspace_id == actor.workspace_id,
        TaskAssignee.user_id.in_(user_ids),
    ))
    return set(rows.scalars())


async def visible_task_ids(db: AsyncSession, actor: User) -> set[uuid.UUID]:
    if actor.role == Role.ceo:
        rows = await db.execute(select(Task.id).where(Task.workspace_id == actor.workspace_id))
        return set(rows.scalars())
    uids = [actor.id]
    if actor.role == Role.manager:
        uids += await direct_report_ids(db, actor)
    ids = await _assigned_task_ids(db, actor, uids)
    if actor.role == Role.manager:
        owned = await db.execute(
            select(Task.id).join(Project, Task.project_id == Project.id).where(
                Task.workspace_id == actor.workspace_id, Project.owner_id == actor.id,
            )
        )
        ids |= set(owned.scalars())
    return ids


async def visible_project_ids(db: AsyncSession, actor: User) -> set[uuid.UUID]:
    if actor.role == Role.ceo:
        rows = await db.execute(select(Project.id).where(Project.workspace_id == actor.workspace_id))
        return set(rows.scalars())
    task_ids = await visible_task_ids(db, actor)
    ids: set[uuid.UUID] = set()
    if task_ids:
        rows = await db.execute(select(Task.project_id).where(Task.id.in_(task_ids)))
        ids = set(rows.scalars())
    if actor.role == Role.manager:
        rows = await db.execute(select(Project.id).where(
            Project.workspace_id == actor.workspace_id, Project.owner_id == actor.id,
        ))
        ids |= set(rows.scalars())
    return ids


async def can_update_progress(db: AsyncSession, actor: User, task: Task) -> bool:
    if task.workspace_id != actor.workspace_id:
        return False
    if actor.role == Role.ceo:
        return True
    uids = [actor.id]
    if actor.role == Role.manager:
        uids += await direct_report_ids(db, actor)
    assigned = await db.execute(select(TaskAssignee.id).where(
        TaskAssignee.task_id == task.id, TaskAssignee.user_id.in_(uids),
    ))
    return assigned.first() is not None


async def get_visible_task_or_404(db: AsyncSession, actor: User, task_id: uuid.UUID) -> Task:
    task = await db.get(Task, task_id)
    if task is None or task.workspace_id != actor.workspace_id:
        raise HTTPException(404, "task_not_found")
    if actor.role != Role.ceo and task.id not in await visible_task_ids(db, actor):
        raise HTTPException(404, "task_not_found")
    return task
```

- [ ] **Step 3: Run toàn bộ → PASS (46)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): work-domain permissions - task/project visibility + progress-update matrix"
```

---

### Task 4: Projects API

**Files:**
- Create: `backend/app/services/work_service.py`, `backend/app/api/projects.py`
- Modify: `backend/app/schemas.py`, `backend/app/main.py`
- Test: `backend/tests/test_projects.py`

**Interfaces:**
- `POST /api/v1/projects` (CEO) body `{name, goal?, deadline?, owner_id?}` → 201 ProjectOut. `owner_id` phải là user cùng workspace (422 nếu sai).
- `GET /api/v1/projects` → list ProjectOut theo `visible_project_ids`.
- `PATCH /api/v1/projects/{id}` (CEO) partial `{name?, goal?, status?, deadline?, owner_id?}` → 200; khác workspace → 404.
- Service: `work_service.create_project(db, actor, **fields)`, `update_project(db, actor, project_id, patch: dict)`, `list_projects(db, actor)`.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_projects.py`:
```python
import pytest

from tests.conftest import _ceo_headers, _invite_and_join


def _h(joined):
    return {"Authorization": f"Bearer {joined['access_token']}"}


@pytest.mark.asyncio
async def test_ceo_creates_and_patches_project(client):
    ceo_h = await _ceo_headers(client)
    resp = await client.post("/api/v1/projects", headers=ceo_h,
                             json={"name": "Website", "goal": "Ra mat Q4"})
    assert resp.status_code == 201
    pid = resp.json()["id"]
    patch = await client.patch(f"/api/v1/projects/{pid}", headers=ceo_h,
                               json={"status": "paused"})
    assert patch.status_code == 200
    assert patch.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_non_ceo_cannot_create_project(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    resp = await client.post("/api/v1/projects", headers=_h(m1), json={"name": "X"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_project_owner_validated(client):
    import uuid as uuid_mod
    ceo_h = await _ceo_headers(client)
    resp = await client.post("/api/v1/projects", headers=ceo_h,
                             json={"name": "X", "owner_id": str(uuid_mod.uuid4())})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_project_visibility(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    await client.post("/api/v1/projects", headers=ceo_h,
                      json={"name": "P-owned", "owner_id": m1["user"]["id"]})
    await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P-hidden"})

    ceo_sees = {p["name"] for p in (await client.get("/api/v1/projects", headers=ceo_h)).json()}
    assert ceo_sees == {"P-owned", "P-hidden"}
    m1_sees = {p["name"] for p in (await client.get("/api/v1/projects", headers=_h(m1))).json()}
    assert m1_sees == {"P-owned"}
```

Run → FAIL.

- [ ] **Step 2: Implement**

Thêm vào `backend/app/schemas.py` (đầu file đã có `import datetime as dt`, `import uuid`):
```python
class ProjectCreateIn(BaseModel):
    name: str
    goal: str = ""
    deadline: dt.datetime | None = None
    owner_id: uuid.UUID | None = None


class ProjectPatchIn(BaseModel):
    name: str | None = None
    goal: str | None = None
    status: str | None = None
    deadline: dt.datetime | None = None
    owner_id: uuid.UUID | None = None


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    goal: str
    status: str
    deadline: dt.datetime | None
    owner_id: uuid.UUID | None

    model_config = {"from_attributes": True}
```

`backend/app/services/work_service.py`:
```python
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, User
from app.permissions import require_ceo, visible_project_ids


async def _validate_owner(db: AsyncSession, actor: User, owner_id) -> None:
    if owner_id is None:
        return
    owner = await db.get(User, owner_id)
    if owner is None or owner.workspace_id != actor.workspace_id:
        raise HTTPException(422, "invalid_owner")


async def create_project(db: AsyncSession, actor: User, *, name: str, goal: str = "",
                         deadline=None, owner_id=None) -> Project:
    require_ceo(actor)
    await _validate_owner(db, actor, owner_id)
    project = Project(workspace_id=actor.workspace_id, name=name, goal=goal,
                      deadline=deadline, owner_id=owner_id, created_by=actor.id)
    db.add(project)
    await db.commit()
    return project


async def update_project(db: AsyncSession, actor: User, project_id: uuid.UUID,
                         patch: dict) -> Project:
    require_ceo(actor)
    project = await db.get(Project, project_id)
    if project is None or project.workspace_id != actor.workspace_id:
        raise HTTPException(404, "project_not_found")
    if "owner_id" in patch:
        await _validate_owner(db, actor, patch["owner_id"])
    for key, value in patch.items():
        setattr(project, key, value)
    await db.commit()
    return project


async def list_projects(db: AsyncSession, actor: User) -> list[Project]:
    ids = await visible_project_ids(db, actor)
    if not ids:
        return []
    rows = await db.execute(select(Project).where(Project.id.in_(ids)))
    return list(rows.scalars())
```

`backend/app/api/projects.py`:
```python
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import ProjectCreateIn, ProjectOut, ProjectPatchIn
from app.services import work_service

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreateIn,
                         actor: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    return await work_service.create_project(db, actor, **body.model_dump())


@router.get("", response_model=list[ProjectOut])
async def list_projects(actor: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    return await work_service.list_projects(db, actor)


@router.patch("/{project_id}", response_model=ProjectOut)
async def patch_project(project_id: uuid.UUID, body: ProjectPatchIn,
                        actor: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    return await work_service.update_project(
        db, actor, project_id, body.model_dump(exclude_unset=True))
```

Trong `main.py`: import + `app.include_router(projects.router)`.

- [ ] **Step 3: Run toàn bộ → PASS (50)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): projects API - CEO create/patch, visibility-scoped listing"
```

---

### Task 5: Tasks API — tạo/sửa/gán (CEO) + xem theo quyền + notification khi gán

**Files:**
- Create: `backend/app/api/tasks.py`
- Modify: `backend/app/schemas.py`, `backend/app/services/work_service.py`, `backend/app/main.py`
- Test: `backend/tests/test_tasks.py`

**Interfaces:**
- `POST /api/v1/tasks` (CEO) body `{project_id, title, description?, deadline?, priority?}` → 201 TaskOut. project khác workspace/không tồn tại → 404.
- `GET /api/v1/tasks` → list TaskOut theo `visible_task_ids`. `GET /api/v1/tasks/{id}` → TaskOut (kèm `assignee_ids`); ngoài quyền → 404.
- `PATCH /api/v1/tasks/{id}` (CEO) partial `{title?, description?, status?, percent?, deadline?, priority?}`.
- `POST /api/v1/tasks/{id}/assignees` (CEO) `{user_id}` → 201; user khác workspace → 422; gán trùng → 200 idempotent; tạo `Notification(type="task_assigned", recipient=assignee, payload={task_id, title})`.
- `DELETE /api/v1/tasks/{id}/assignees/{user_id}` (CEO) → 204.
- Service: `create_task`, `update_task`, `assign_task`, `unassign_task`, `list_tasks`, `get_task` (kèm assignee_ids), helper `_task_out(db, task) -> dict`.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_tasks.py`:
```python
import pytest
from sqlalchemy import select

from app.models import Notification
from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


async def _project(client, ceo_h, **kw):
    resp = await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P", **kw})
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_ceo_creates_task_and_assigns(client, db_session):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    pid = await _project(client, ceo_h)

    t = await client.post("/api/v1/tasks", headers=ceo_h,
                          json={"project_id": pid, "title": "Lam bao cao"})
    assert t.status_code == 201
    tid = t.json()["id"]

    a = await client.post(f"/api/v1/tasks/{tid}/assignees", headers=ceo_h,
                          json={"user_id": e1["user"]["id"]})
    assert a.status_code == 201
    # idempotent
    a2 = await client.post(f"/api/v1/tasks/{tid}/assignees", headers=ceo_h,
                           json={"user_id": e1["user"]["id"]})
    assert a2.status_code == 200
    # notification cho người được gán
    notes = (await db_session.execute(select(Notification).where(
        Notification.type == "task_assigned"))).scalars().all()
    assert len(notes) == 1
    assert str(notes[0].recipient_id) == e1["user"]["id"]

    detail = await client.get(f"/api/v1/tasks/{tid}", headers=_h(e1))
    assert detail.status_code == 200
    assert e1["user"]["id"] in detail.json()["assignee_ids"]


@pytest.mark.asyncio
async def test_non_ceo_cannot_create_or_assign(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    pid = await _project(client, ceo_h)
    r = await client.post("/api/v1/tasks", headers=_h(m1),
                          json={"project_id": pid, "title": "X"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_task_visibility_404_outside_scope(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    pid = await _project(client, ceo_h)
    t = await client.post("/api/v1/tasks", headers=ceo_h,
                          json={"project_id": pid, "title": "T"})
    tid = t.json()["id"]
    # e1 chưa được gán -> không thấy
    assert (await client.get(f"/api/v1/tasks/{tid}", headers=_h(e1))).status_code == 404
    assert (await client.get("/api/v1/tasks", headers=_h(e1))).json() == []


@pytest.mark.asyncio
async def test_assign_cross_workspace_user_422(client):
    ceo_h = await _ceo_headers(client)
    pid = await _project(client, ceo_h)
    t = await client.post("/api/v1/tasks", headers=ceo_h,
                          json={"project_id": pid, "title": "T"})
    tid = t.json()["id"]
    b = await client.post("/api/v1/auth/signup-workspace", json={
        "workspace_name": "B", "email": "ceo@b.vn", "password": "secret123",
        "full_name": "B", "device_uuid": "db", "device_name": "",
    })
    r = await client.post(f"/api/v1/tasks/{tid}/assignees", headers=ceo_h,
                          json={"user_id": b.json()["user"]["id"]})
    assert r.status_code == 422
```

Run → FAIL.

- [ ] **Step 2: Implement**

Thêm vào `backend/app/schemas.py` (import `TaskPriority, TaskStatus` từ app.models):
```python
class TaskCreateIn(BaseModel):
    project_id: uuid.UUID
    title: str
    description: str = ""
    deadline: dt.datetime | None = None
    priority: TaskPriority = TaskPriority.medium


class TaskPatchIn(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    percent: int | None = Field(None, ge=0, le=100)
    deadline: dt.datetime | None = None
    priority: TaskPriority | None = None


class TaskOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str
    status: TaskStatus
    percent: int
    deadline: dt.datetime | None
    priority: TaskPriority
    assignee_ids: list[uuid.UUID] = []


class AssigneeIn(BaseModel):
    user_id: uuid.UUID
```
(bổ sung `from pydantic import BaseModel, EmailStr, Field`)

Thêm vào `backend/app/services/work_service.py` (import thêm `Notification, Task, TaskAssignee` và `get_visible_task_or_404, visible_task_ids`):
```python
async def _assignee_ids(db: AsyncSession, task_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await db.execute(select(TaskAssignee.user_id).where(TaskAssignee.task_id == task_id))
    return list(rows.scalars())


async def _task_out(db: AsyncSession, task: Task) -> dict:
    return {
        "id": task.id, "project_id": task.project_id, "title": task.title,
        "description": task.description, "status": task.status, "percent": task.percent,
        "deadline": task.deadline, "priority": task.priority,
        "assignee_ids": await _assignee_ids(db, task.id),
    }


async def create_task(db: AsyncSession, actor: User, *, project_id: uuid.UUID,
                      title: str, description: str = "", deadline=None,
                      priority=None) -> dict:
    require_ceo(actor)
    project = await db.get(Project, project_id)
    if project is None or project.workspace_id != actor.workspace_id:
        raise HTTPException(404, "project_not_found")
    task = Task(workspace_id=actor.workspace_id, project_id=project_id, title=title,
                description=description, deadline=deadline, created_by=actor.id,
                **({"priority": priority} if priority else {}))
    db.add(task)
    await db.commit()
    return await _task_out(db, task)


async def update_task(db: AsyncSession, actor: User, task_id: uuid.UUID, patch: dict) -> dict:
    require_ceo(actor)
    task = await db.get(Task, task_id)
    if task is None or task.workspace_id != actor.workspace_id:
        raise HTTPException(404, "task_not_found")
    for key, value in patch.items():
        setattr(task, key, value)
    await db.commit()
    return await _task_out(db, task)


async def assign_task(db: AsyncSession, actor: User, task_id: uuid.UUID,
                      user_id: uuid.UUID) -> bool:
    """Trả về True nếu tạo assignment mới, False nếu đã tồn tại (idempotent)."""
    require_ceo(actor)
    task = await db.get(Task, task_id)
    if task is None or task.workspace_id != actor.workspace_id:
        raise HTTPException(404, "task_not_found")
    target = await db.get(User, user_id)
    if target is None or target.workspace_id != actor.workspace_id:
        raise HTTPException(422, "invalid_assignee")
    existing = await db.execute(select(TaskAssignee.id).where(
        TaskAssignee.task_id == task_id, TaskAssignee.user_id == user_id))
    if existing.first() is not None:
        return False
    db.add(TaskAssignee(workspace_id=actor.workspace_id, task_id=task_id, user_id=user_id))
    db.add(Notification(workspace_id=actor.workspace_id, recipient_id=user_id,
                        type="task_assigned",
                        payload={"task_id": str(task_id), "title": task.title}))
    await db.commit()
    return True


async def unassign_task(db: AsyncSession, actor: User, task_id: uuid.UUID,
                        user_id: uuid.UUID) -> None:
    require_ceo(actor)
    task = await db.get(Task, task_id)
    if task is None or task.workspace_id != actor.workspace_id:
        raise HTTPException(404, "task_not_found")
    row = (await db.execute(select(TaskAssignee).where(
        TaskAssignee.task_id == task_id, TaskAssignee.user_id == user_id,
    ))).scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()


async def list_tasks(db: AsyncSession, actor: User) -> list[dict]:
    ids = await visible_task_ids(db, actor)
    if not ids:
        return []
    rows = await db.execute(select(Task).where(Task.id.in_(ids)))
    return [await _task_out(db, t) for t in rows.scalars()]


async def get_task(db: AsyncSession, actor: User, task_id: uuid.UUID) -> dict:
    task = await get_visible_task_or_404(db, actor, task_id)
    return await _task_out(db, task)
```

`backend/app/api/tasks.py`:
```python
import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import AssigneeIn, TaskCreateIn, TaskOut, TaskPatchIn
from app.services import work_service

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(body: TaskCreateIn, actor: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    return await work_service.create_task(db, actor, **body.model_dump())


@router.get("", response_model=list[TaskOut])
async def list_tasks(actor: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    return await work_service.list_tasks(db, actor)


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: uuid.UUID, actor: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    return await work_service.get_task(db, actor, task_id)


@router.patch("/{task_id}", response_model=TaskOut)
async def patch_task(task_id: uuid.UUID, body: TaskPatchIn,
                     actor: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    return await work_service.update_task(
        db, actor, task_id, body.model_dump(exclude_unset=True))


@router.post("/{task_id}/assignees")
async def assign(task_id: uuid.UUID, body: AssigneeIn,
                 actor: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    created = await work_service.assign_task(db, actor, task_id, body.user_id)
    return Response(status_code=201 if created else 200)


@router.delete("/{task_id}/assignees/{user_id}", status_code=204)
async def unassign(task_id: uuid.UUID, user_id: uuid.UUID,
                   actor: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    await work_service.unassign_task(db, actor, task_id, user_id)
    return Response(status_code=204)
```

Trong `main.py`: mount `tasks.router`.

- [ ] **Step 3: Run toàn bộ → PASS (54)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): tasks API - CEO create/patch/assign with notifications, visibility-scoped read"
```

---

### Task 6: Cập nhật tiến độ (task_updates) + đồng bộ task + notification

**Files:**
- Modify: `backend/app/schemas.py`, `backend/app/services/work_service.py`, `backend/app/api/tasks.py`
- Test: `backend/tests/test_task_updates.py`

**Interfaces:**
- `POST /api/v1/tasks/{id}/updates` body `{content?, percent?, status?}` → 201 TaskUpdateOut. Quyền theo `can_update_progress` (không đủ quyền nhưng thấy task → 403; không thấy → 404). percent/status có giá trị → đồng bộ vào `tasks` (nguồn chuẩn hiện tại; updates = lịch sử).
- `GET /api/v1/tasks/{id}/updates` → list theo thứ tự mới nhất trước; quyền = thấy task.
- Notification `type="task_update"` cho: mọi assignee của task (trừ tác giả) + manager của tác giả (nếu có) + CEO gốc — dedup, không tự gửi cho tác giả.
- Service: `add_task_update(db, actor, task_id, *, content, percent, status) -> TaskUpdate`, `list_task_updates(db, actor, task_id)`.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_task_updates.py`:
```python
import pytest
from sqlalchemy import select

from app.models import Notification, Task
from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


async def _setup(client):
    """CEO + m1 + e1(m1) + e2(m2); task gán e1."""
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    m2 = await _invite_and_join(client, ceo_h, "manager", "m2@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    e2 = await _invite_and_join(client, ceo_h, "employee", "e2@a.vn", m2["user"]["id"])
    pid = (await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P"})).json()["id"]
    tid = (await client.post("/api/v1/tasks", headers=ceo_h,
                             json={"project_id": pid, "title": "T"})).json()["id"]
    await client.post(f"/api/v1/tasks/{tid}/assignees", headers=ceo_h,
                      json={"user_id": e1["user"]["id"]})
    return ceo_h, m1, m2, e1, e2, tid


@pytest.mark.asyncio
async def test_assignee_updates_and_task_syncs(client, db_session):
    ceo_h, m1, m2, e1, e2, tid = await _setup(client)
    r = await client.post(f"/api/v1/tasks/{tid}/updates", headers=_h(e1),
                          json={"content": "da xong 50%", "percent": 50,
                                "status": "in_progress"})
    assert r.status_code == 201
    task = (await db_session.execute(select(Task))).scalar_one()
    assert task.percent == 50
    assert task.status.value == "in_progress"


@pytest.mark.asyncio
async def test_update_notifications_fanout(client, db_session):
    ceo_h, m1, m2, e1, e2, tid = await _setup(client)
    await client.post(f"/api/v1/tasks/{tid}/updates", headers=_h(e1),
                      json={"content": "update", "percent": 10})
    notes = (await db_session.execute(select(Notification).where(
        Notification.type == "task_update"))).scalars().all()
    recipients = {str(n.recipient_id) for n in notes}
    # manager cua tac gia + CEO goc (tac gia e1 la assignee duy nhat -> khong tu nhan)
    assert m1["user"]["id"] in recipients
    assert e1["user"]["id"] not in recipients
    assert len(recipients) == 2  # m1 + root CEO


@pytest.mark.asyncio
async def test_manager_updates_subordinate_task(client):
    ceo_h, m1, m2, e1, e2, tid = await _setup(client)
    assert (await client.post(f"/api/v1/tasks/{tid}/updates", headers=_h(m1),
                              json={"percent": 60})).status_code == 201


@pytest.mark.asyncio
async def test_unrelated_users_denied(client):
    ceo_h, m1, m2, e1, e2, tid = await _setup(client)
    # e2 khong thay task -> 404
    assert (await client.post(f"/api/v1/tasks/{tid}/updates", headers=_h(e2),
                              json={"percent": 1})).status_code == 404
    # m2 khong thay task (khong duoc gan, khong owner) -> 404
    assert (await client.get(f"/api/v1/tasks/{tid}/updates", headers=_h(m2))).status_code == 404


@pytest.mark.asyncio
async def test_list_updates_newest_first(client):
    ceo_h, m1, m2, e1, e2, tid = await _setup(client)
    await client.post(f"/api/v1/tasks/{tid}/updates", headers=_h(e1), json={"content": "1"})
    await client.post(f"/api/v1/tasks/{tid}/updates", headers=_h(e1), json={"content": "2"})
    lst = (await client.get(f"/api/v1/tasks/{tid}/updates", headers=_h(e1))).json()
    assert [u["content"] for u in lst] == ["2", "1"]
```

Run → FAIL.

- [ ] **Step 2: Implement**

Schemas:
```python
class TaskUpdateCreateIn(BaseModel):
    content: str = ""
    percent: int | None = Field(None, ge=0, le=100)
    status: TaskStatus | None = None


class TaskUpdateOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    author_id: uuid.UUID
    content: str
    percent: int | None
    status: TaskStatus | None
    created_at: dt.datetime

    model_config = {"from_attributes": True}
```

Service (import thêm `TaskUpdate` model, `can_update_progress`; alias tránh trùng tên schema không cần vì đây là models):
```python
async def _notify_task_update(db: AsyncSession, actor: User, task: Task) -> None:
    recipients: set[uuid.UUID] = set(await _assignee_ids(db, task.id))
    if actor.manager_id:
        recipients.add(actor.manager_id)
    root = (await db.execute(select(User.id).where(
        User.workspace_id == actor.workspace_id, User.is_root,
    ))).scalar_one_or_none()
    if root:
        recipients.add(root)
    recipients.discard(actor.id)
    for rid in recipients:
        db.add(Notification(workspace_id=actor.workspace_id, recipient_id=rid,
                            type="task_update",
                            payload={"task_id": str(task.id), "author_id": str(actor.id)}))


async def add_task_update(db: AsyncSession, actor: User, task_id: uuid.UUID, *,
                          content: str = "", percent=None, status=None) -> TaskUpdate:
    task = await get_visible_task_or_404(db, actor, task_id)
    if not await can_update_progress(db, actor, task):
        raise HTTPException(403, "forbidden")
    upd = TaskUpdate(workspace_id=actor.workspace_id, task_id=task.id, author_id=actor.id,
                     content=content, percent=percent, status=status)
    db.add(upd)
    if percent is not None:
        task.percent = percent
    if status is not None:
        task.status = status
    await _notify_task_update(db, actor, task)
    await db.commit()
    return upd


async def list_task_updates(db: AsyncSession, actor: User, task_id: uuid.UUID) -> list[TaskUpdate]:
    task = await get_visible_task_or_404(db, actor, task_id)
    rows = await db.execute(select(TaskUpdate).where(TaskUpdate.task_id == task.id)
                            .order_by(TaskUpdate.created_at.desc(), TaskUpdate.id.desc()))
    return list(rows.scalars())
```

Routes (thêm vào `api/tasks.py`):
```python
from app.schemas import TaskUpdateCreateIn, TaskUpdateOut


@router.post("/{task_id}/updates", response_model=TaskUpdateOut, status_code=201)
async def add_update(task_id: uuid.UUID, body: TaskUpdateCreateIn,
                     actor: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    return await work_service.add_task_update(db, actor, task_id, **body.model_dump())


@router.get("/{task_id}/updates", response_model=list[TaskUpdateOut])
async def list_updates(task_id: uuid.UUID, actor: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    return await work_service.list_task_updates(db, actor, task_id)
```

- [ ] **Step 3: Run toàn bộ → PASS (59)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): task progress updates - history + task sync + notification fanout"
```

---

### Task 7: Bình luận trong task

**Files:**
- Modify: `backend/app/schemas.py`, `backend/app/services/work_service.py`, `backend/app/api/tasks.py`
- Test: `backend/tests/test_comments.py`

**Interfaces:**
- `POST /api/v1/tasks/{id}/comments` `{content}` → 201 CommentOut; `GET /api/v1/tasks/{id}/comments` → list cũ → mới. Quyền: **ai thấy task đều comment/đọc được** (kể cả 2 employee cùng task — ngoại lệ ma trận đã chốt). Ngoài quyền thấy → 404.
- Service: `add_comment(db, actor, task_id, content)`, `list_comments(db, actor, task_id)`.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_comments.py`:
```python
import pytest

from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


async def _task_with_two_employees(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    e2 = await _invite_and_join(client, ceo_h, "employee", "e2@a.vn", m1["user"]["id"])
    pid = (await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P"})).json()["id"]
    tid = (await client.post("/api/v1/tasks", headers=ceo_h,
                             json={"project_id": pid, "title": "T"})).json()["id"]
    for u in (e1, e2):
        await client.post(f"/api/v1/tasks/{tid}/assignees", headers=ceo_h,
                          json={"user_id": u["user"]["id"]})
    return ceo_h, e1, e2, tid


@pytest.mark.asyncio
async def test_two_employees_same_task_can_discuss(client):
    ceo_h, e1, e2, tid = await _task_with_two_employees(client)
    assert (await client.post(f"/api/v1/tasks/{tid}/comments", headers=_h(e1),
                              json={"content": "phan cua toi xong"})).status_code == 201
    lst = await client.get(f"/api/v1/tasks/{tid}/comments", headers=_h(e2))
    assert lst.status_code == 200
    assert lst.json()[0]["content"] == "phan cua toi xong"
    assert (await client.post(f"/api/v1/tasks/{tid}/comments", headers=_h(e2),
                              json={"content": "ok toi tiep"})).status_code == 201


@pytest.mark.asyncio
async def test_outsider_cannot_see_comments(client):
    ceo_h, e1, e2, tid = await _task_with_two_employees(client)
    m2 = await _invite_and_join(client, ceo_h, "manager", "m2@a.vn")
    assert (await client.get(f"/api/v1/tasks/{tid}/comments", headers=_h(m2))).status_code == 404
    assert (await client.post(f"/api/v1/tasks/{tid}/comments", headers=_h(m2),
                              json={"content": "x"})).status_code == 404
```

Run → FAIL.

- [ ] **Step 2: Implement**

Schemas:
```python
class CommentCreateIn(BaseModel):
    content: str


class CommentOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    author_id: uuid.UUID
    content: str
    created_at: dt.datetime

    model_config = {"from_attributes": True}
```

Service (import `TaskComment`):
```python
async def add_comment(db: AsyncSession, actor: User, task_id: uuid.UUID,
                      content: str) -> TaskComment:
    task = await get_visible_task_or_404(db, actor, task_id)
    comment = TaskComment(workspace_id=actor.workspace_id, task_id=task.id,
                          author_id=actor.id, content=content)
    db.add(comment)
    await db.commit()
    return comment


async def list_comments(db: AsyncSession, actor: User, task_id: uuid.UUID) -> list[TaskComment]:
    task = await get_visible_task_or_404(db, actor, task_id)
    rows = await db.execute(select(TaskComment).where(TaskComment.task_id == task.id)
                            .order_by(TaskComment.created_at.asc(), TaskComment.id.asc()))
    return list(rows.scalars())
```

Routes (api/tasks.py):
```python
from app.schemas import CommentCreateIn, CommentOut


@router.post("/{task_id}/comments", response_model=CommentOut, status_code=201)
async def add_comment(task_id: uuid.UUID, body: CommentCreateIn,
                      actor: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    return await work_service.add_comment(db, actor, task_id, body.content)


@router.get("/{task_id}/comments", response_model=list[CommentOut])
async def list_comments(task_id: uuid.UUID, actor: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    return await work_service.list_comments(db, actor, task_id)
```

- [ ] **Step 3: Run toàn bộ → PASS (61)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): task comments - visible-to-task participants, matrix exemption honored"
```

---

### Task 8: Skill models + API tạo/version/cấp quyền (CEO)

**Files:**
- Create: `backend/app/services/skill_service.py`, `backend/app/api/skills.py`
- Modify: `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/main.py`
- Test: `backend/tests/test_skills.py`

**Interfaces:**
- Models: `SkillKind` enum (profile/knowledge); `Skill(id, workspace_id, name, kind, task_id?→tasks, created_by, created_at)`; `SkillVersion(id, workspace_id, skill_id, version:int, content:Text, created_by, created_at)` unique (skill_id, version); `SkillGrant(id, workspace_id, skill_id, user_id, granted_by, created_at)` unique (skill_id, user_id); `SkillUsageLog(id, workspace_id, skill_id, version:int, user_id, used_at)`.
- `POST /api/v1/skills` (CEO) `{name, kind, task_id?, content}` → 201 SkillOut (tạo kèm version 1). task_id khác workspace → 404.
- `POST /api/v1/skills/{id}/versions` (CEO) `{content}` → 201 `{version}` (version = max+1).
- `POST /api/v1/skills/{id}/grants` (CEO) `{user_id}` → 201; user khác workspace → 422; trùng → 200.
- `GET /api/v1/skills` → CEO: tất cả; khác: skill được cấp. SkillOut có `latest_version`.
- Service: `create_skill`, `add_version`, `grant_skill`, `list_skills`, helper `_latest_version(db, skill_id) -> SkillVersion`.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_skills.py`:
```python
import pytest

from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


@pytest.mark.asyncio
async def test_ceo_creates_skill_with_v1_and_bumps_version(client):
    ceo_h = await _ceo_headers(client)
    r = await client.post("/api/v1/skills", headers=ceo_h,
                          json={"name": "Quy trinh bao cao", "kind": "knowledge",
                                "content": "Buoc 1..."})
    assert r.status_code == 201
    sid = r.json()["id"]
    assert r.json()["latest_version"] == 1
    v2 = await client.post(f"/api/v1/skills/{sid}/versions", headers=ceo_h,
                           json={"content": "Buoc 1 (sua)..."})
    assert v2.status_code == 201
    assert v2.json()["version"] == 2


@pytest.mark.asyncio
async def test_non_ceo_cannot_create_or_version(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    r = await client.post("/api/v1/skills", headers=_h(m1),
                          json={"name": "X", "kind": "knowledge", "content": "c"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_grant_and_list_visibility(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    s = await client.post("/api/v1/skills", headers=ceo_h,
                          json={"name": "S", "kind": "knowledge", "content": "c"})
    sid = s.json()["id"]
    g = await client.post(f"/api/v1/skills/{sid}/grants", headers=ceo_h,
                          json={"user_id": e1["user"]["id"]})
    assert g.status_code == 201
    assert len((await client.get("/api/v1/skills", headers=_h(e1))).json()) == 1
    assert (await client.get("/api/v1/skills", headers=_h(m1))).json() == []
    assert len((await client.get("/api/v1/skills", headers=ceo_h)).json()) == 1


@pytest.mark.asyncio
async def test_grant_cross_workspace_422(client):
    ceo_h = await _ceo_headers(client)
    s = await client.post("/api/v1/skills", headers=ceo_h,
                          json={"name": "S", "kind": "knowledge", "content": "c"})
    b = await client.post("/api/v1/auth/signup-workspace", json={
        "workspace_name": "B", "email": "ceo@b.vn", "password": "secret123",
        "full_name": "B", "device_uuid": "db", "device_name": "",
    })
    r = await client.post(f"/api/v1/skills/{s.json()['id']}/grants", headers=ceo_h,
                          json={"user_id": b.json()["user"]["id"]})
    assert r.status_code == 422
```

Run → FAIL.

- [ ] **Step 2: Implement**

Models (cuối `models.py`):
```python
class SkillKind(str, enum.Enum):
    profile = "profile"
    knowledge = "knowledge"


class Skill(Base):
    __tablename__ = "skills"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[SkillKind] = mapped_column(Enum(SkillKind))
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SkillVersion(Base):
    __tablename__ = "skill_versions"
    __table_args__ = (UniqueConstraint("skill_id", "version", name="uq_skill_version"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SkillGrant(Base):
    __tablename__ = "skill_grants"
    __table_args__ = (UniqueConstraint("skill_id", "user_id", name="uq_skill_grant"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    granted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SkillUsageLog(Base):
    __tablename__ = "skill_usage_log"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
```

Schemas (import `SkillKind`):
```python
class SkillCreateIn(BaseModel):
    name: str
    kind: SkillKind
    task_id: uuid.UUID | None = None
    content: str


class SkillVersionIn(BaseModel):
    content: str


class SkillGrantIn(BaseModel):
    user_id: uuid.UUID


class SkillOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: SkillKind
    task_id: uuid.UUID | None
    latest_version: int
```

`backend/app/services/skill_service.py`:
```python
import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Skill, SkillGrant, SkillVersion, Task, User
from app.permissions import require_ceo


async def _latest_version_num(db: AsyncSession, skill_id: uuid.UUID) -> int:
    row = await db.execute(select(func.max(SkillVersion.version))
                           .where(SkillVersion.skill_id == skill_id))
    return row.scalar() or 0


async def _get_skill_or_404(db: AsyncSession, actor: User, skill_id: uuid.UUID) -> Skill:
    skill = await db.get(Skill, skill_id)
    if skill is None or skill.workspace_id != actor.workspace_id:
        raise HTTPException(404, "skill_not_found")
    return skill


async def _skill_out(db: AsyncSession, skill: Skill) -> dict:
    return {"id": skill.id, "name": skill.name, "kind": skill.kind,
            "task_id": skill.task_id,
            "latest_version": await _latest_version_num(db, skill.id)}


async def create_skill(db: AsyncSession, actor: User, *, name: str, kind,
                       task_id=None, content: str) -> dict:
    require_ceo(actor)
    if task_id is not None:
        task = await db.get(Task, task_id)
        if task is None or task.workspace_id != actor.workspace_id:
            raise HTTPException(404, "task_not_found")
    skill = Skill(workspace_id=actor.workspace_id, name=name, kind=kind,
                  task_id=task_id, created_by=actor.id)
    db.add(skill)
    await db.flush()
    db.add(SkillVersion(workspace_id=actor.workspace_id, skill_id=skill.id,
                        version=1, content=content, created_by=actor.id))
    await db.commit()
    return await _skill_out(db, skill)


async def add_version(db: AsyncSession, actor: User, skill_id: uuid.UUID,
                      content: str) -> int:
    require_ceo(actor)
    skill = await _get_skill_or_404(db, actor, skill_id)
    version = await _latest_version_num(db, skill.id) + 1
    db.add(SkillVersion(workspace_id=actor.workspace_id, skill_id=skill.id,
                        version=version, content=content, created_by=actor.id))
    await db.commit()
    return version


async def grant_skill(db: AsyncSession, actor: User, skill_id: uuid.UUID,
                      user_id: uuid.UUID) -> bool:
    require_ceo(actor)
    skill = await _get_skill_or_404(db, actor, skill_id)
    target = await db.get(User, user_id)
    if target is None or target.workspace_id != actor.workspace_id:
        raise HTTPException(422, "invalid_grantee")
    existing = await db.execute(select(SkillGrant.id).where(
        SkillGrant.skill_id == skill.id, SkillGrant.user_id == user_id))
    if existing.first() is not None:
        return False
    db.add(SkillGrant(workspace_id=actor.workspace_id, skill_id=skill.id,
                      user_id=user_id, granted_by=actor.id))
    await db.commit()
    return True


async def list_skills(db: AsyncSession, actor: User) -> list[dict]:
    from app.models import Role
    if actor.role == Role.ceo:
        rows = await db.execute(select(Skill).where(Skill.workspace_id == actor.workspace_id))
    else:
        rows = await db.execute(
            select(Skill).join(SkillGrant, SkillGrant.skill_id == Skill.id).where(
                Skill.workspace_id == actor.workspace_id, SkillGrant.user_id == actor.id))
    return [await _skill_out(db, s) for s in rows.scalars()]
```

`backend/app/api/skills.py`:
```python
import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import SkillCreateIn, SkillGrantIn, SkillOut, SkillVersionIn
from app.services import skill_service

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


@router.post("", response_model=SkillOut, status_code=201)
async def create_skill(body: SkillCreateIn, actor: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    return await skill_service.create_skill(db, actor, **body.model_dump())


@router.get("", response_model=list[SkillOut])
async def list_skills(actor: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    return await skill_service.list_skills(db, actor)


@router.post("/{skill_id}/versions", status_code=201)
async def add_version(skill_id: uuid.UUID, body: SkillVersionIn,
                      actor: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    version = await skill_service.add_version(db, actor, skill_id, body.content)
    return {"version": version}


@router.post("/{skill_id}/grants")
async def grant(skill_id: uuid.UUID, body: SkillGrantIn,
                actor: User = Depends(get_current_user),
                db: AsyncSession = Depends(get_db)):
    created = await skill_service.grant_skill(db, actor, skill_id, body.user_id)
    return Response(status_code=201 if created else 200)
```

Mount trong `main.py`.

- [ ] **Step 3: Run toàn bộ → PASS (65)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): skills - CEO-only create/version/grant, grant-scoped listing"
```

---

### Task 9: use_skill — hợp nhất 2 lớp + usage log

**Files:**
- Modify: `backend/app/services/skill_service.py`, `backend/app/api/skills.py`, `backend/app/schemas.py`
- Test: thêm vào `backend/tests/test_skills.py`

**Interfaces:**
- `GET /api/v1/skills/{id}/use` → 200:
  ```json
  {"skill_id": "...", "name": "...", "kind": "knowledge", "version": 2,
   "content": "<nội dung version mới nhất>",
   "task_state": {"id": "...", "title": "...", "status": "in_progress", "percent": 50,
                   "deadline": null, "priority": "medium",
                   "assignees": ["e1@a.vn"],
                   "latest_updates": [{"author_id": "...", "content": "...", "percent": 50,
                                        "created_at": "..."}]}}
  ```
  `task_state=null` nếu skill không gắn task. `latest_updates` tối đa 5, mới nhất trước.
- Quyền: CEO hoặc user có grant; không grant → 403; khác workspace → 404. Mỗi lần use ghi `SkillUsageLog(skill_id, version, user_id)`.
- Service: `use_skill(db, actor, skill_id) -> dict`.

- [ ] **Step 1: Viết test fail** (thêm vào `test_skills.py`)

```python
from sqlalchemy import select as sa_select

from app.models import SkillUsageLog


async def _skill_on_task(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    pid = (await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P"})).json()["id"]
    tid = (await client.post("/api/v1/tasks", headers=ceo_h,
                             json={"project_id": pid, "title": "T"})).json()["id"]
    await client.post(f"/api/v1/tasks/{tid}/assignees", headers=ceo_h,
                      json={"user_id": e1["user"]["id"]})
    sid = (await client.post("/api/v1/skills", headers=ceo_h,
                             json={"name": "S", "kind": "knowledge", "task_id": tid,
                                   "content": "huong dan v1"})).json()["id"]
    await client.post(f"/api/v1/skills/{sid}/grants", headers=ceo_h,
                      json={"user_id": e1["user"]["id"]})
    return ceo_h, e1, tid, sid


@pytest.mark.asyncio
async def test_use_skill_composes_two_layers(client, db_session):
    ceo_h, e1, tid, sid = await _skill_on_task(client)
    # e1 cap nhat tien do -> task_state phai song
    await client.post(f"/api/v1/tasks/{tid}/updates", headers=_h(e1),
                      json={"content": "50% roi", "percent": 50, "status": "in_progress"})
    # CEO sua noi dung skill -> version 2
    await client.post(f"/api/v1/skills/{sid}/versions", headers=ceo_h,
                      json={"content": "huong dan v2"})

    used = await client.get(f"/api/v1/skills/{sid}/use", headers=_h(e1))
    assert used.status_code == 200
    data = used.json()
    assert data["version"] == 2
    assert data["content"] == "huong dan v2"
    assert data["task_state"]["percent"] == 50
    assert data["task_state"]["status"] == "in_progress"
    assert data["task_state"]["latest_updates"][0]["content"] == "50% roi"

    log = (await db_session.execute(sa_select(SkillUsageLog))).scalars().all()
    assert len(log) == 1
    assert log[0].version == 2


@pytest.mark.asyncio
async def test_use_skill_requires_grant(client):
    ceo_h, e1, tid, sid = await _skill_on_task(client)
    m2 = await _invite_and_join(client, ceo_h, "manager", "m2@a.vn")
    assert (await client.get(f"/api/v1/skills/{sid}/use", headers=_h(m2))).status_code == 403
    assert (await client.get(f"/api/v1/skills/{sid}/use", headers=ceo_h)).status_code == 200
```

Run → FAIL.

- [ ] **Step 2: Implement**

Thêm vào `skill_service.py` (import `Role, SkillUsageLog, TaskAssignee, TaskUpdate`):
```python
async def _task_state(db: AsyncSession, task: Task) -> dict:
    assignee_rows = await db.execute(
        select(User.email).join(TaskAssignee, TaskAssignee.user_id == User.id)
        .where(TaskAssignee.task_id == task.id))
    updates = await db.execute(
        select(TaskUpdate).where(TaskUpdate.task_id == task.id)
        .order_by(TaskUpdate.created_at.desc(), TaskUpdate.id.desc()).limit(5))
    return {
        "id": str(task.id), "title": task.title, "status": task.status.value,
        "percent": task.percent,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "priority": task.priority.value,
        "assignees": list(assignee_rows.scalars()),
        "latest_updates": [
            {"author_id": str(u.author_id), "content": u.content, "percent": u.percent,
             "created_at": u.created_at.isoformat()}
            for u in updates.scalars()
        ],
    }


async def use_skill(db: AsyncSession, actor: User, skill_id: uuid.UUID) -> dict:
    skill = await _get_skill_or_404(db, actor, skill_id)
    if actor.role != Role.ceo:
        granted = await db.execute(select(SkillGrant.id).where(
            SkillGrant.skill_id == skill.id, SkillGrant.user_id == actor.id))
        if granted.first() is None:
            raise HTTPException(403, "skill_not_granted")
    latest = (await db.execute(
        select(SkillVersion).where(SkillVersion.skill_id == skill.id)
        .order_by(SkillVersion.version.desc()).limit(1))).scalar_one()
    task_state = None
    if skill.task_id is not None:
        task = await db.get(Task, skill.task_id)
        if task is not None:
            task_state = await _task_state(db, task)
    db.add(SkillUsageLog(workspace_id=actor.workspace_id, skill_id=skill.id,
                         version=latest.version, user_id=actor.id))
    await db.commit()
    return {"skill_id": str(skill.id), "name": skill.name, "kind": skill.kind.value,
            "version": latest.version, "content": latest.content,
            "task_state": task_state}
```

Route (api/skills.py):
```python
@router.get("/{skill_id}/use")
async def use_skill(skill_id: uuid.UUID, actor: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    return await skill_service.use_skill(db, actor, skill_id)
```

- [ ] **Step 3: Run toàn bộ → PASS (67)**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): use_skill - two-layer compose (versioned content + live task state) with usage log"
```

---

### Task 10: Migration + fix port Postgres dev + export openapi

**Files:**
- Modify: `backend/docker-compose.yml`, `backend/alembic.ini`, `backend/.env.example`, `CLAUDE.md`
- Create: migration mới qua alembic autogenerate

**Interfaces:**
- Postgres dev map ra host port **5433** (máy dev có Postgres 18 native chiếm 5432); alembic.ini + .env.example trỏ 5433. Trong mạng docker, api vẫn nối `postgres:5432` (không đổi).
- Migration `"work domain + skills"` tạo 9 bảng mới; `alembic upgrade head` chạy sạch.
- `openapi.json` regenerate ở repo root (contract mới cho FE).

- [ ] **Step 1: Đổi port dev**

`backend/docker-compose.yml`: service postgres đổi `ports: ["5432:5432"]` → `ports: ["5433:5432"]`.
`backend/alembic.ini`: `sqlalchemy.url = postgresql+asyncpg://app:app@localhost:5433/app`.
`backend/.env.example`: `DATABASE_URL=postgresql+asyncpg://app:app@localhost:5433/app`.
`CLAUDE.md` mục "Lệnh thường dùng" thêm dòng: `- Postgres dev map host port 5433 (5432 bị Postgres bản Windows native chiếm)`.

- [ ] **Step 2: Sinh và áp migration**

```powershell
docker compose up -d postgres
alembic revision --autogenerate -m "work domain + skills"
alembic upgrade head
docker compose exec postgres psql -U app -d app -c "\dt"
```
Expected: 17 bảng (7 cũ + 9 mới + alembic_version). Đọc lại file migration sinh ra: đủ projects, tasks, task_assignees (uq_task_assignee), task_updates, task_comments, skills, skill_versions (uq_skill_version), skill_grants (uq_skill_grant), skill_usage_log.

- [ ] **Step 3: Export openapi + full suite**

```powershell
.venv\Scripts\python.exe scripts\export_openapi.py
.venv\Scripts\python.exe -m pytest tests/ -v
```
Expected: openapi.json chứa paths mới (/api/v1/projects, /api/v1/tasks, /api/v1/skills...); **67 passed**.

- [ ] **Step 4: Commit**

```bash
git add backend/ openapi.json CLAUDE.md
git commit -m "feat(be): migration for work domain + skills, dev postgres on 5433, refresh openapi contract"
```

---

## Self-review (đã chạy)

- **Spec coverage (Plan 2 scope):** projects/tasks/assignees CRUD theo quyền CEO ✅ (T4, T5) · task_updates lịch sử + sync + notification fanout ✅ (T6) · comments với ngoại lệ ma trận ✅ (T7) · skill 2 lớp: version CEO-only, grant, use hợp nhất live state, usage log kèm version ✅ (T8, T9) · hardening carry-over từ final review Plan 1 ✅ (T1) · migration + contract FE ✅ (T10). Ngoài scope (chủ đích): agent tools gọi các service này (Plan 3), báo cáo tổng hợp/Excel (Plan 4), voice/audit_log/usage_log LLM (Plan 3/4).
- **Type consistency:** `visible_task_ids` trả `set` (T3) — mọi chỗ dùng đều xử lý set ✅; `_task_out`/`_skill_out` trả dict khớp TaskOut/SkillOut ✅; helpers test import từ `tests.conftest` thống nhất T1 và được T4–T9 dùng ✅; `TaskUpdate` (model) vs `TaskUpdateCreateIn/TaskUpdateOut` (schema) không trùng tên ✅.
- **Placeholder scan:** không có TBD/`...` ngoài ví dụ JSON minh họa response.
- **Đếm test:** 38 → T1:42 → T2:43 → T3:46 → T4:50 → T5:54 → T6:59 → T7:61 → T8:65 → T9:67 → T10:67.
