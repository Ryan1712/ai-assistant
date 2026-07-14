# Offboarding (khóa + bàn giao khi nghỉ việc) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans hoặc superpowers:subagent-driven-development để thực thi plan này task-by-task. Checkbox (`- [ ]`) để tracking.

**Goal:** CEO cho 1 người nghỉ việc qua chat hoặc REST → tài khoản bị khóa (đăng xuất mọi thiết bị) và toàn bộ task/project/direct-report của họ tự động chuyển sang 1 người kế thừa do CEO chỉ định.

**Architecture:** 1 hàm service mới `auth_service.offboard_user()` gọi thẳng `lock_user()` đã có (tái dùng permission + khóa + revoke token + notify), sau đó reassign `TaskAssignee`/`Project.owner_id`/`User.manager_id` nếu có `successor_id`. REST endpoint + tool chat mới bọc quanh hàm này, không có bảng/migration mới.

**Tech Stack:** BE như cũ (FastAPI + SQLAlchemy async). Không thêm dependency.

**Spec thiết kế:** [docs/superpowers/specs/2026-07-14-offboarding-design.md](../specs/2026-07-14-offboarding-design.md)

## Global Constraints (CLAUDE.md + spec)

- workspace_id lọc mọi query; quyền kiểm tra ở service layer (đã có sẵn qua `_check_lock_permission`, không viết rule quyền mới); actor từ JWT; TDD, mỗi task 1 commit; đổi API contract → chạy lại `export_openapi.py`.
- **Không transfer `SkillGrant`** — ngoài phạm vi.
- **Chỉ 1 successor cho tất cả** (task + project + direct report) — không chia nhỏ theo loại.
- **Chỉ 1 notify() tóm tắt cho successor** — không thông báo riêng từng direct report bị đổi manager.
- **Không có FE** cho tính năng này (giống `lock_user`/`unlock_user` — admin action hiếm dùng, chỉ REST/tool).
- `offboard_user` phải **idempotent** như `lock_user` — gọi trên user đã bị khóa từ trước vẫn chạy được, không lỗi.

---

### Task 1: `auth_service.offboard_user()` — lõi nghiệp vụ (TDD)

**Files:**
- Modify: `backend/app/services/auth_service.py` (thêm import `Project`, `TaskAssignee`; thêm hàm `offboard_user`)
- Test: `backend/tests/test_offboard_service.py` (mới)

**Interfaces:**
- Produces: `offboard_user(db: AsyncSession, actor: User, target_id: UUID, successor_id: UUID | None = None) -> dict` với shape `{"locked": bool, "successor_id": str | None, "tasks_reassigned": int, "projects_reassigned": int, "reports_reassigned": int}`. Task 2 (REST) và Task 3 (tool) đều gọi thẳng hàm này với đúng chữ ký trên.
- Consumes: `lock_user()`, `_check_lock_permission()`, `notify()` đã có sẵn trong `auth_service.py` — không sửa các hàm này.

- [ ] **Step 1: Viết test `backend/tests/test_offboard_service.py`**

```python
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import Project, Role, Task, TaskAssignee, User, UserStatus, Workspace
from app.services import auth_service


async def _seed(db):
    """Workspace A: CEO root + manager (owner project, giao 1 task, co 1 direct report)
    + employee bao cao manager + successor (con hoat dong)."""
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="ceo@a.vn", password_hash="x", full_name="Sep",
              role=Role.ceo, is_root=True)
    mgr = User(workspace_id=ws.id, email="mgr@a.vn", password_hash="x", full_name="Quan Ly",
              role=Role.manager)
    successor = User(workspace_id=ws.id, email="ke-thua@a.vn", password_hash="x",
                     full_name="Nguoi Ke Thua", role=Role.manager)
    db.add_all([ceo, mgr, successor])
    await db.flush()
    emp = User(workspace_id=ws.id, email="emp@a.vn", password_hash="x", full_name="Nhan Vien",
              role=Role.employee, manager_id=mgr.id)
    db.add(emp)
    await db.flush()
    project = Project(workspace_id=ws.id, name="Website", created_by=ceo.id, owner_id=mgr.id)
    db.add(project)
    await db.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="Sua loi", created_by=ceo.id)
    db.add(task)
    await db.flush()
    db.add(TaskAssignee(workspace_id=ws.id, task_id=task.id, user_id=mgr.id))
    await db.commit()
    return ws, ceo, mgr, emp, successor, project, task


@pytest.mark.asyncio
async def test_non_ceo_cannot_offboard(db_session):
    _, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.offboard_user(db_session, emp, mgr.id)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_offboard_without_successor_only_locks(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    result = await auth_service.offboard_user(db_session, ceo, mgr.id)
    assert result == {"locked": True, "successor_id": None, "tasks_reassigned": 0,
                      "projects_reassigned": 0, "reports_reassigned": 0}
    await db_session.refresh(mgr)
    assert mgr.status == UserStatus.locked
    await db_session.refresh(project)
    assert project.owner_id == mgr.id


@pytest.mark.asyncio
async def test_offboard_with_successor_reassigns_everything(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    result = await auth_service.offboard_user(db_session, ceo, mgr.id, successor.id)
    assert result == {"locked": True, "successor_id": str(successor.id), "tasks_reassigned": 1,
                      "projects_reassigned": 1, "reports_reassigned": 1}

    await db_session.refresh(mgr)
    assert mgr.status == UserStatus.locked
    await db_session.refresh(project)
    assert project.owner_id == successor.id
    await db_session.refresh(emp)
    assert emp.manager_id == successor.id

    assignees = (await db_session.execute(
        select(TaskAssignee).where(TaskAssignee.task_id == task.id))).scalars().all()
    assert [a.user_id for a in assignees] == [successor.id]


@pytest.mark.asyncio
async def test_offboard_does_not_duplicate_existing_successor_assignment(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    db_session.add(TaskAssignee(workspace_id=ws.id, task_id=task.id, user_id=successor.id))
    await db_session.commit()

    result = await auth_service.offboard_user(db_session, ceo, mgr.id, successor.id)
    assert result["tasks_reassigned"] == 1

    assignees = (await db_session.execute(
        select(TaskAssignee).where(TaskAssignee.task_id == task.id))).scalars().all()
    assert [a.user_id for a in assignees] == [successor.id]


@pytest.mark.asyncio
async def test_successor_not_found_or_cross_workspace(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    other_ws = Workspace(name="B")
    db_session.add(other_ws)
    await db_session.flush()
    other_user = User(workspace_id=other_ws.id, email="other@b.vn", password_hash="x",
                      full_name="Khac Workspace", role=Role.manager)
    db_session.add(other_user)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await auth_service.offboard_user(db_session, ceo, mgr.id, other_user.id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_successor_same_as_target_is_rejected(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.offboard_user(db_session, ceo, mgr.id, mgr.id)
    assert exc.value.status_code == 422
    assert exc.value.detail == "invalid_successor"


@pytest.mark.asyncio
async def test_locked_successor_is_rejected(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    successor.status = UserStatus.locked
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await auth_service.offboard_user(db_session, ceo, mgr.id, successor.id)
    assert exc.value.status_code == 422
    assert exc.value.detail == "invalid_successor"


@pytest.mark.asyncio
async def test_root_ceo_cannot_be_offboarded(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.offboard_user(db_session, ceo, ceo.id)
    assert exc.value.status_code == 403
    assert exc.value.detail == "cannot_lock_root_ceo"


@pytest.mark.asyncio
async def test_non_root_ceo_cannot_offboard_another_ceo(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    ceo2 = User(workspace_id=ws.id, email="ceo2@a.vn", password_hash="x", full_name="CEO 2",
               role=Role.ceo, is_root=False)
    ceo3 = User(workspace_id=ws.id, email="ceo3@a.vn", password_hash="x", full_name="CEO 3",
               role=Role.ceo, is_root=False)
    db_session.add_all([ceo2, ceo3])
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await auth_service.offboard_user(db_session, ceo2, ceo3.id)
    assert exc.value.status_code == 403
    assert exc.value.detail == "only_root_can_lock_ceo"


@pytest.mark.asyncio
async def test_offboard_is_idempotent_on_already_locked_user(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    await auth_service.offboard_user(db_session, ceo, mgr.id)
    result = await auth_service.offboard_user(db_session, ceo, mgr.id, successor.id)
    assert result["tasks_reassigned"] == 1
```

- [ ] **Step 2: Chạy test — xác nhận FAIL**

Run: `cd backend && pytest tests/test_offboard_service.py -v`
Expected: FAIL — `AttributeError: module 'app.services.auth_service' has no attribute 'offboard_user'` (hoặc tương đương, vì hàm chưa tồn tại).

- [ ] **Step 3: Thêm import + implement `offboard_user` trong `backend/app/services/auth_service.py`**

Sửa dòng import model (hiện tại):

```python
from app.models import (
    Device, Invite, LoginEvent, Notification, RefreshToken, Role, User, UserStatus, Workspace,
)
```

thành:

```python
from app.models import (
    Device, Invite, LoginEvent, Notification, Project, RefreshToken, Role, TaskAssignee,
    User, UserStatus, Workspace,
)
```

(Chỉ thêm `Project`, `TaskAssignee` — `Task` không cần thiết vì hàm mới chỉ query/update qua `TaskAssignee`, không đụng bảng `tasks` trực tiếp.)

Thêm hàm mới **ngay sau** `unlock_user` (trước `request_unlock`):

```python
async def offboard_user(db: AsyncSession, actor: User, target_id: uuid_mod.UUID,
                        successor_id: uuid_mod.UUID | None = None) -> dict:
    await lock_user(db, actor, target_id)

    tasks_reassigned = 0
    projects_reassigned = 0
    reports_reassigned = 0

    if successor_id is not None:
        successor = await db.get(User, successor_id)
        if successor is None or successor.workspace_id != actor.workspace_id:
            raise HTTPException(404, "user_not_found")
        if successor.id == target_id or successor.status == UserStatus.locked:
            raise HTTPException(422, "invalid_successor")

        rows = (await db.execute(
            select(TaskAssignee).where(TaskAssignee.user_id == target_id))).scalars().all()
        for row in rows:
            existing = await db.execute(select(TaskAssignee.id).where(
                TaskAssignee.task_id == row.task_id, TaskAssignee.user_id == successor_id))
            if existing.first() is None:
                db.add(TaskAssignee(workspace_id=actor.workspace_id, task_id=row.task_id,
                                    user_id=successor_id))
            await db.delete(row)
            tasks_reassigned += 1

        result = await db.execute(update(Project).where(
            Project.workspace_id == actor.workspace_id, Project.owner_id == target_id
        ).values(owner_id=successor_id))
        projects_reassigned = result.rowcount or 0

        result = await db.execute(update(User).where(
            User.workspace_id == actor.workspace_id, User.manager_id == target_id
        ).values(manager_id=successor_id))
        reports_reassigned = result.rowcount or 0

        await notify(db, workspace_id=actor.workspace_id, recipient_id=successor_id,
                    type="offboard_handoff",
                    payload={"from_user": str(target_id), "tasks_reassigned": tasks_reassigned,
                             "projects_reassigned": projects_reassigned,
                             "reports_reassigned": reports_reassigned})
        await db.commit()

    return {"locked": True, "successor_id": str(successor_id) if successor_id else None,
            "tasks_reassigned": tasks_reassigned, "projects_reassigned": projects_reassigned,
            "reports_reassigned": reports_reassigned}
```

- [ ] **Step 4: Chạy test — xác nhận PASS**

Run: `cd backend && pytest tests/test_offboard_service.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth_service.py backend/tests/test_offboard_service.py
git commit -m "feat(be): auth_service.offboard_user - khoa + ban giao khi nghi viec"
```

---

### Task 2: REST endpoint `POST /api/v1/users/{user_id}/offboard` (TDD)

**Files:**
- Modify: `backend/app/schemas.py` (thêm `OffboardIn`)
- Modify: `backend/app/api/users.py` (thêm endpoint)
- Test: `backend/tests/test_offboard_api.py` (mới)

**Interfaces:**
- Consumes: `auth_service.offboard_user()` (Task 1) — chữ ký `(db, actor, target_id, successor_id=None) -> dict` đã cố định, không đổi ở task này.
- Produces: response JSON đúng shape trả về từ `offboard_user()` — Task 3 (tool) trả cùng shape này.

- [ ] **Step 1: Viết test `backend/tests/test_offboard_api.py`**

```python
import pytest

from tests.conftest import _ceo_headers, _invite_and_join


@pytest.mark.asyncio
async def test_employee_cannot_offboard_via_rest(client):
    ceo_h = await _ceo_headers(client)
    mgr = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    emp = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn",
                                 manager_id=mgr["user"]["id"])
    emp_h = {"Authorization": f"Bearer {emp['access_token']}"}

    r = await client.post(f"/api/v1/users/{mgr['user']['id']}/offboard", headers=emp_h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_offboard_without_successor_locks_only(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")

    r = await client.post(f"/api/v1/users/{m1['user']['id']}/offboard", headers=ceo_h, json={})
    assert r.status_code == 200, r.text
    assert r.json() == {"locked": True, "successor_id": None, "tasks_reassigned": 0,
                        "projects_reassigned": 0, "reports_reassigned": 0}

    login = await client.post("/api/v1/auth/login", json={
        "email": "m1@a.vn", "password": "pw123456", "device_uuid": "d", "device_name": "",
    })
    assert login.status_code == 403


@pytest.mark.asyncio
async def test_offboard_with_successor_reassigns_direct_report(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    m2 = await _invite_and_join(client, ceo_h, "manager", "m2@a.vn")
    await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", manager_id=m1["user"]["id"])

    r = await client.post(f"/api/v1/users/{m1['user']['id']}/offboard", headers=ceo_h,
                          json={"successor_id": m2["user"]["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["reports_reassigned"] == 1


@pytest.mark.asyncio
async def test_invalid_successor_returns_422(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")

    r = await client.post(f"/api/v1/users/{m1['user']['id']}/offboard", headers=ceo_h,
                          json={"successor_id": m1["user"]["id"]})
    assert r.status_code == 422
    assert r.json()["detail"] == "invalid_successor"
```

- [ ] **Step 2: Chạy test — xác nhận FAIL**

Run: `cd backend && pytest tests/test_offboard_api.py -v`
Expected: FAIL — `404 Not Found` cho route chưa tồn tại (assert `r.status_code == 403` sẽ fail vì thực tế là 404).

- [ ] **Step 3: Thêm `OffboardIn` vào `backend/app/schemas.py`**

Thêm vào cuối file:

```python
class OffboardIn(BaseModel):
    successor_id: uuid.UUID | None = None
```

- [ ] **Step 4: Thêm endpoint vào `backend/app/api/users.py`**

Sửa dòng import (hiện tại):

```python
from app.schemas import DeviceOut, UserOut
```

thành:

```python
from app.schemas import DeviceOut, OffboardIn, UserOut
```

Thêm endpoint mới **ngay sau** `unlock_user` (cuối file):

```python
@router.post("/{user_id}/offboard")
async def offboard_user(
    user_id: uuid.UUID,
    body: OffboardIn = OffboardIn(),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.offboard_user(db, actor, user_id, body.successor_id)
```

(Đặt tên hàm `offboard_user` trùng tên với `auth_service.offboard_user` — không xung đột vì khác module/namespace, giống cách `lock_user`/`unlock_user` đã trùng tên giữa router và service.)

- [ ] **Step 5: Chạy test — xác nhận PASS**

Run: `cd backend && pytest tests/test_offboard_api.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/api/users.py backend/tests/test_offboard_api.py
git commit -m "feat(be): REST POST /api/v1/users/{id}/offboard"
```

---

### Task 3: Tool chat `offboard_user` + openapi (TDD)

**Files:**
- Modify: `backend/app/agent/tools.py` (thêm tool)
- Modify: `backend/tests/test_agent_tools_report.py` (bump `len(TOOLS)`)
- Test: `backend/tests/test_agent_tools_offboard.py` (mới)

**Interfaces:**
- Consumes: `auth_service.offboard_user()` (Task 1).

- [ ] **Step 1: Kiểm tra số lượng tool hiện tại**

Run: `cd backend && grep -c "^_register(" app/agent/tools.py`
Expected: `39`. Nếu số này khác 39 (đã thay đổi từ lúc viết plan), STOP và báo cáo — đừng tự âm thầm điều chỉnh con số ở bước sau.

- [ ] **Step 2: Viết test `backend/tests/test_agent_tools_offboard.py`**

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
    successor = User(workspace_id=ws.id, email="ke-thua@a.vn", password_hash="x",
                     full_name="Ke Thua", role=Role.manager)
    target = User(workspace_id=ws.id, email="target@a.vn", password_hash="x",
                  full_name="Nguoi Nghi", role=Role.manager)
    db.add_all([successor, target])
    await db.flush()
    await db.commit()
    return ws, ceo, successor, target


def test_offboard_user_tool_registered_and_sensitive():
    assert "offboard_user" in TOOLS
    assert TOOLS["offboard_user"].sensitive is True
    assert len(TOOLS) == 40  # +offboard_user (2026-07-14)


@pytest.mark.asyncio
async def test_offboard_user_tool_locks_and_reassigns(db_session):
    ws, ceo, successor, target = await _ceo(db_session)

    result = await call_tool(db_session, ceo, "offboard_user",
                             {"user_id": str(target.id), "successor_id": str(successor.id)})
    assert result["locked"] is True
    assert result["successor_id"] == str(successor.id)


@pytest.mark.asyncio
async def test_offboard_user_tool_wraps_forbidden_error(db_session):
    ws, ceo, successor, target = await _ceo(db_session)
    employee = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
                    role=Role.employee)
    db_session.add(employee)
    await db_session.commit()

    result = await call_tool(db_session, employee, "offboard_user", {"user_id": str(target.id)})
    assert result["error"] == "forbidden"
```

- [ ] **Step 3: Chạy test — xác nhận FAIL**

Run: `cd backend && pytest tests/test_agent_tools_offboard.py -v`
Expected: FAIL — `"offboard_user" not in TOOLS`.

- [ ] **Step 4: Thêm tool vào `backend/app/agent/tools.py`**

Thêm ngay sau hàm `_unlock_user` (trước dòng `_register("list_users", ...)`):

```python
class OffboardUserToolIn(BaseModel):
    user_id: uuid.UUID
    successor_id: uuid.UUID | None = None


async def _offboard_user(db, actor, body: OffboardUserToolIn) -> dict:
    return await auth_service.offboard_user(db, actor, body.user_id, body.successor_id)
```

Thêm `_register` **ngay sau** dòng đăng ký `unlock_user` hiện có (giữ nguyên 2 dòng `_register("lock_user", ...)`/`_register("unlock_user", ...)` y hệt, chỉ chèn thêm khối mới ngay sau):

```python
_register("offboard_user",
          "Cho 1 người nghỉ việc — khóa tài khoản (đăng xuất mọi thiết bị) và bàn giao toàn bộ "
          "task/project/nhân viên báo cáo trực tiếp (nếu có) cho 1 người kế thừa (chỉ CEO, hành "
          "động nhạy cảm - hệ thống TỰ hiện bước xác nhận khi gọi tool, cứ gọi ngay đừng hỏi trước).",
          OffboardUserToolIn, _offboard_user, sensitive=True)
```

- [ ] **Step 5: Cập nhật assertion số lượng tool trong `backend/tests/test_agent_tools_report.py`**

Tìm dòng cuối file (hiện `assert len(TOOLS) == 39  # ...`) và sửa thành:

```python
    assert len(TOOLS) == 40  # +offboard_user (2026-07-14)
```

- [ ] **Step 6: Chạy test — xác nhận PASS**

Run: `cd backend && pytest tests/test_agent_tools_offboard.py tests/test_agent_tools_report.py -v`
Expected: tất cả pass.

- [ ] **Step 7: Full suite + export openapi**

Run: `cd backend && pytest tests/ -q`
Expected: tất cả pass, output sạch (không có test nào fail vì đếm tool sai ở file khác — nếu có, tìm và sửa file đó y hệt Step 5, đừng đoán số).

Run: `cd backend && python scripts/export_openapi.py`
Expected: `Wrote .../openapi.json`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/agent/tools.py backend/tests/test_agent_tools_offboard.py backend/tests/test_agent_tools_report.py openapi.json
git commit -m "feat(be): tool chat offboard_user + openapi"
```

---

## Ghi chú

- Không có FE cho tính năng này (giống `lock_user`/`unlock_user`) — không cần plan FE riêng trừ khi sau này có yêu cầu.
- "Đổi vai trò" (role/manager change cho người vẫn đang làm việc) là tính năng khác, không nằm trong plan này — cần spec riêng nếu có yêu cầu.
