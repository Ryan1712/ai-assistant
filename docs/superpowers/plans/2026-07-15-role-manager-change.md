# Đổi vai trò / đổi manager (người vẫn đang làm việc) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans hoặc superpowers:subagent-driven-development để thực thi plan này task-by-task. Checkbox (`- [ ]`) để tracking.

**Goal:** CEO đổi role (employee/manager/ceo) và/hoặc đổi manager của 1 người **đang hoạt động** qua chat hoặc REST — nếu người đó rời khỏi vai trò manager mà đang có direct report/owned project thì bàn giao cho 1 successor, nhưng KHÔNG đụng tới task đang được giao của chính họ.

**Architecture:** 1 hàm service mới `auth_service.change_role()` cạnh `offboard_user()` đã có — tái dùng ý tưởng successor của offboarding cho `User.manager_id`/`Project.owner_id`, nhưng độc lập hoàn toàn với `lock_user`/`offboard_user` (không khóa tài khoản, không đụng `TaskAssignee`). REST endpoint + tool chat mới bọc quanh hàm này, không có bảng/migration mới.

**Tech Stack:** BE như cũ (FastAPI + SQLAlchemy async). Không thêm dependency.

**Spec thiết kế:** [docs/superpowers/specs/2026-07-15-role-manager-change-design.md](../specs/2026-07-15-role-manager-change-design.md)

## Global Constraints (CLAUDE.md + spec)

- workspace_id lọc mọi query; quyền kiểm tra ở service layer (viết `_check_role_change_permission` riêng, không sửa `_check_lock_permission` của offboarding); actor từ JWT; TDD, mỗi task 1 commit; đổi API contract → chạy lại `export_openapi.py`.
- **KHÔNG đụng `TaskAssignee`** — khác biệt cốt lõi so với `offboard_user`, vì người này vẫn đang làm việc.
- **`new_manager_id` phải là 1 người có `role == Role.manager`** trong cùng workspace — giữ đúng ràng buộc đã có ở `create_invite`.
- **`successor_id` chỉ bắt buộc khi target rời khỏi role `manager` VÀ đang có direct report hoặc owned project** — không bắt buộc trong mọi trường hợp đổi role.
- **Không đổi `is_root`** — không có tham số nào đụng tới cờ này; root CEO bất biến (403 `cannot_change_root_ceo`).
- **Đổi liên quan CEO (target hiện là CEO, hoặc `new_role == ceo`) chỉ root CEO gọi được** — mở rộng so với `_check_lock_permission` (helper cũ không xét role đích).
- **Không có FE** cho tính năng này (giống `lock_user`/`offboard_user`).

---

### Task 1: `auth_service.change_role()` — lõi nghiệp vụ (TDD)

**Files:**
- Modify: `backend/app/services/auth_service.py` (thêm `_check_role_change_permission` + `change_role`, không cần import mới — `Role`, `Project`, `User`, `UserStatus`, `update`, `select`, `notify`, `HTTPException` đã có sẵn trong file)
- Test: `backend/tests/test_change_role_service.py` (mới)

**Interfaces:**
- Produces: `change_role(db: AsyncSession, actor: User, target_id: UUID, *, new_role: Role | None = None, new_manager_id: UUID | None = None, successor_id: UUID | None = None) -> dict` với shape `{"role": str, "manager_id": str | None, "successor_id": str | None, "reports_reassigned": int, "projects_reassigned": int}`. Task 2 (REST) và Task 3 (tool) đều gọi thẳng hàm này với đúng chữ ký trên.
- Consumes: `require_ceo()` (`app.permissions`, đã import sẵn trong `auth_service.py`), `notify()` đã có sẵn — không sửa các hàm này.

- [ ] **Step 1: Viết test `backend/tests/test_change_role_service.py`**

```python
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import Project, Role, Task, TaskAssignee, User, UserStatus, Workspace
from app.services import auth_service


async def _seed(db):
    """Workspace A: root CEO + mgr (manager, co 1 direct report emp + so huu 1 project)
    + mgr2 (manager khac, ung vien lam new_manager_id/successor) + ceo2 (CEO khong root)."""
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="ceo@a.vn", password_hash="x", full_name="Sep",
              role=Role.ceo, is_root=True)
    mgr = User(workspace_id=ws.id, email="mgr@a.vn", password_hash="x", full_name="Quan Ly",
              role=Role.manager)
    mgr2 = User(workspace_id=ws.id, email="mgr2@a.vn", password_hash="x", full_name="Quan Ly 2",
               role=Role.manager)
    ceo2 = User(workspace_id=ws.id, email="ceo2@a.vn", password_hash="x", full_name="CEO 2",
               role=Role.ceo, is_root=False)
    db.add_all([ceo, mgr, mgr2, ceo2])
    await db.flush()
    emp = User(workspace_id=ws.id, email="emp@a.vn", password_hash="x", full_name="Nhan Vien",
              role=Role.employee, manager_id=mgr.id)
    db.add(emp)
    await db.flush()
    project = Project(workspace_id=ws.id, name="Website", created_by=ceo.id, owner_id=mgr.id)
    db.add(project)
    await db.commit()
    return ws, ceo, mgr, mgr2, emp, ceo2, project


@pytest.mark.asyncio
async def test_non_ceo_cannot_change_role(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, emp, mgr2.id, new_role=Role.employee)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_promote_employee_to_manager(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    result = await auth_service.change_role(db_session, ceo, emp.id, new_role=Role.manager)
    assert result["role"] == "manager"
    assert result["reports_reassigned"] == 0
    assert result["projects_reassigned"] == 0
    await db_session.refresh(emp)
    assert emp.role == Role.manager


@pytest.mark.asyncio
async def test_change_manager_only(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    result = await auth_service.change_role(db_session, ceo, emp.id, new_manager_id=mgr2.id)
    assert result["role"] == "employee"
    assert result["manager_id"] == str(mgr2.id)
    await db_session.refresh(emp)
    assert emp.manager_id == mgr2.id
    assert emp.role == Role.employee


@pytest.mark.asyncio
async def test_demote_manager_with_dependents_requires_successor(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo, mgr.id, new_role=Role.employee,
                                       new_manager_id=mgr2.id)
    assert exc.value.status_code == 422
    assert exc.value.detail == "successor_required"


@pytest.mark.asyncio
async def test_demote_manager_new_manager_and_successor_are_independent(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    mgr3 = User(workspace_id=ws.id, email="mgr3@a.vn", password_hash="x", full_name="Quan Ly 3",
               role=Role.manager)
    db_session.add(mgr3)
    await db_session.commit()

    result = await auth_service.change_role(db_session, ceo, mgr.id, new_role=Role.employee,
                                            new_manager_id=mgr3.id, successor_id=mgr2.id)
    assert result["manager_id"] == str(mgr3.id)
    assert result["successor_id"] == str(mgr2.id)
    assert result["reports_reassigned"] == 1
    assert result["projects_reassigned"] == 1
    await db_session.refresh(mgr)
    assert mgr.manager_id == mgr3.id
    await db_session.refresh(emp)
    assert emp.manager_id == mgr2.id
    await db_session.refresh(project)
    assert project.owner_id == mgr2.id


@pytest.mark.asyncio
async def test_demote_manager_keeps_own_task_assignments(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    task = Task(workspace_id=ws.id, project_id=project.id, title="Sua loi", created_by=ceo.id)
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskAssignee(workspace_id=ws.id, task_id=task.id, user_id=mgr.id))
    await db_session.commit()

    await auth_service.change_role(db_session, ceo, mgr.id, new_role=Role.employee,
                                   new_manager_id=mgr2.id, successor_id=mgr2.id)

    assignees = (await db_session.execute(
        select(TaskAssignee).where(TaskAssignee.task_id == task.id))).scalars().all()
    assert [a.user_id for a in assignees] == [mgr.id]


@pytest.mark.asyncio
async def test_leaving_manager_without_dependents_no_successor_needed(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    result = await auth_service.change_role(db_session, ceo, mgr2.id, new_role=Role.employee,
                                            new_manager_id=mgr.id)
    assert result["reports_reassigned"] == 0
    assert result["projects_reassigned"] == 0


@pytest.mark.asyncio
async def test_employee_role_without_any_manager_rejected(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo, ceo2.id, new_role=Role.employee)
    assert exc.value.status_code == 422
    assert exc.value.detail == "employee_requires_manager"


@pytest.mark.asyncio
async def test_new_manager_must_have_manager_role(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo, emp.id, new_manager_id=ceo2.id)
    assert exc.value.status_code == 422
    assert exc.value.detail == "invalid_manager"


@pytest.mark.asyncio
async def test_new_manager_cannot_be_self(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo, mgr.id, new_manager_id=mgr.id)
    assert exc.value.status_code == 422
    assert exc.value.detail == "invalid_manager"


@pytest.mark.asyncio
async def test_no_change_requested(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo, mgr.id)
    assert exc.value.status_code == 422
    assert exc.value.detail == "no_change_requested"


@pytest.mark.asyncio
async def test_root_ceo_role_is_immutable(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo, ceo.id, new_role=Role.manager)
    assert exc.value.status_code == 403
    assert exc.value.detail == "cannot_change_root_ceo"


@pytest.mark.asyncio
async def test_non_root_ceo_cannot_change_another_ceo(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    ceo3 = User(workspace_id=ws.id, email="ceo3@a.vn", password_hash="x", full_name="CEO 3",
               role=Role.ceo, is_root=False)
    db_session.add(ceo3)
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo2, ceo3.id, new_role=Role.manager)
    assert exc.value.status_code == 403
    assert exc.value.detail == "only_root_can_change_ceo"


@pytest.mark.asyncio
async def test_non_root_ceo_cannot_promote_employee_to_ceo(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo2, emp.id, new_role=Role.ceo)
    assert exc.value.status_code == 403
    assert exc.value.detail == "only_root_can_change_ceo"


@pytest.mark.asyncio
async def test_root_ceo_can_promote_employee_to_ceo(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    result = await auth_service.change_role(db_session, ceo, mgr2.id, new_role=Role.ceo)
    assert result["role"] == "ceo"
    await db_session.refresh(mgr2)
    assert mgr2.role == Role.ceo


@pytest.mark.asyncio
async def test_successor_not_found_or_cross_workspace(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    other_ws = Workspace(name="B")
    db_session.add(other_ws)
    await db_session.flush()
    other_user = User(workspace_id=other_ws.id, email="other@b.vn", password_hash="x",
                      full_name="Khac Workspace", role=Role.manager)
    db_session.add(other_user)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo, mgr.id, new_role=Role.employee,
                                       new_manager_id=mgr2.id, successor_id=other_user.id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_successor_same_as_target_rejected(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo, mgr.id, new_role=Role.employee,
                                       new_manager_id=mgr2.id, successor_id=mgr.id)
    assert exc.value.status_code == 422
    assert exc.value.detail == "invalid_successor"


@pytest.mark.asyncio
async def test_locked_successor_rejected(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    mgr2.status = UserStatus.locked
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo, mgr.id, new_role=Role.employee,
                                       new_manager_id=mgr2.id, successor_id=mgr2.id)
    assert exc.value.status_code == 422
    assert exc.value.detail == "invalid_successor"
```

- [ ] **Step 2: Chạy test — xác nhận FAIL**

Run: `cd backend && pytest tests/test_change_role_service.py -v`
Expected: FAIL — `AttributeError: module 'app.services.auth_service' has no attribute 'change_role'` (hoặc tương đương, vì hàm chưa tồn tại).

- [ ] **Step 3: Implement `_check_role_change_permission` + `change_role` trong `backend/app/services/auth_service.py`**

Thêm 2 hàm mới **ngay sau** `offboard_user` (trước `request_unlock`):

```python
def _check_role_change_permission(actor: User, target: User, new_role: Role | None) -> None:
    require_ceo(actor)
    if target.is_root:
        raise HTTPException(403, "cannot_change_root_ceo")
    if target.role == Role.ceo or new_role == Role.ceo:
        if not actor.is_root:
            raise HTTPException(403, "only_root_can_change_ceo")


async def change_role(db: AsyncSession, actor: User, target_id: uuid_mod.UUID, *,
                      new_role: Role | None = None,
                      new_manager_id: uuid_mod.UUID | None = None,
                      successor_id: uuid_mod.UUID | None = None) -> dict:
    if new_role is None and new_manager_id is None:
        raise HTTPException(422, "no_change_requested")

    target = await db.get(User, target_id)
    if target is None or target.workspace_id != actor.workspace_id:
        raise HTTPException(404, "user_not_found")
    _check_role_change_permission(actor, target, new_role)

    if new_manager_id is not None:
        if new_manager_id == target_id:
            raise HTTPException(422, "invalid_manager")
        manager = await db.get(User, new_manager_id)
        if (manager is None or manager.workspace_id != actor.workspace_id
                or manager.role != Role.manager):
            raise HTTPException(422, "invalid_manager")

    resulting_role = new_role if new_role is not None else target.role
    resulting_manager_id = new_manager_id if new_manager_id is not None else target.manager_id
    if resulting_role == Role.employee and resulting_manager_id is None:
        raise HTTPException(422, "employee_requires_manager")

    reports_reassigned = 0
    projects_reassigned = 0
    leaving_manager = (new_role is not None and target.role == Role.manager
                       and new_role != Role.manager)

    if leaving_manager:
        has_reports = (await db.execute(select(User.id).where(
            User.workspace_id == actor.workspace_id, User.manager_id == target_id))).first()
        has_projects = (await db.execute(select(Project.id).where(
            Project.workspace_id == actor.workspace_id, Project.owner_id == target_id))).first()

        if has_reports or has_projects:
            if successor_id is None:
                raise HTTPException(422, "successor_required")
            successor = await db.get(User, successor_id)
            if successor is None or successor.workspace_id != actor.workspace_id:
                raise HTTPException(404, "user_not_found")
            if successor.id == target_id or successor.status == UserStatus.locked:
                raise HTTPException(422, "invalid_successor")

            result = await db.execute(update(User).where(
                User.workspace_id == actor.workspace_id, User.manager_id == target_id,
                User.id != successor_id,
            ).values(manager_id=successor_id))
            reports_reassigned = result.rowcount or 0

            result = await db.execute(update(Project).where(
                Project.workspace_id == actor.workspace_id, Project.owner_id == target_id
            ).values(owner_id=successor_id))
            projects_reassigned = result.rowcount or 0

            await notify(db, workspace_id=actor.workspace_id, recipient_id=successor_id,
                        type="management_handoff",
                        payload={"from_user": str(target_id),
                                 "reports_reassigned": reports_reassigned,
                                 "projects_reassigned": projects_reassigned})

    if new_role is not None:
        target.role = new_role
    if new_manager_id is not None:
        target.manager_id = new_manager_id

    await notify(db, workspace_id=actor.workspace_id, recipient_id=target_id,
                type="role_changed",
                payload={"role": target.role.value,
                         "manager_id": str(target.manager_id) if target.manager_id else None})
    await db.commit()

    return {"role": target.role.value,
            "manager_id": str(target.manager_id) if target.manager_id else None,
            "successor_id": str(successor_id) if successor_id else None,
            "reports_reassigned": reports_reassigned,
            "projects_reassigned": projects_reassigned}
```

(`User.id != successor_id` trong update direct-report học từ bugfix `2b6ee87` của offboarding — tránh successor tự thành manager của chính mình khi successor cũng là 1 direct report của target.)

- [ ] **Step 4: Chạy test — xác nhận PASS**

Run: `cd backend && pytest tests/test_change_role_service.py -v`
Expected: 18 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth_service.py backend/tests/test_change_role_service.py
git commit -m "feat(be): auth_service.change_role - doi role/manager cho nguoi dang lam viec"
```

---

### Task 2: REST endpoint `POST /api/v1/users/{user_id}/change-role` (TDD)

**Files:**
- Modify: `backend/app/schemas.py` (thêm `ChangeRoleIn`)
- Modify: `backend/app/api/users.py` (thêm endpoint)
- Test: `backend/tests/test_change_role_api.py` (mới)

**Interfaces:**
- Consumes: `auth_service.change_role()` (Task 1) — chữ ký `(db, actor, target_id, *, new_role=None, new_manager_id=None, successor_id=None) -> dict` đã cố định, không đổi ở task này.
- Produces: response JSON đúng shape trả về từ `change_role()` — Task 3 (tool) trả cùng shape này.

- [ ] **Step 1: Viết test `backend/tests/test_change_role_api.py`**

```python
import pytest

from tests.conftest import _ceo_headers, _invite_and_join


@pytest.mark.asyncio
async def test_employee_cannot_change_role_via_rest(client):
    ceo_h = await _ceo_headers(client)
    mgr = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    emp = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn",
                                 manager_id=mgr["user"]["id"])
    emp_h = {"Authorization": f"Bearer {emp['access_token']}"}

    r = await client.post(f"/api/v1/users/{mgr['user']['id']}/change-role", headers=emp_h,
                          json={"new_role": "employee"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_change_manager_only_via_rest(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    m2 = await _invite_and_join(client, ceo_h, "manager", "m2@a.vn")
    emp = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn",
                                 manager_id=m1["user"]["id"])

    r = await client.post(f"/api/v1/users/{emp['user']['id']}/change-role", headers=ceo_h,
                          json={"new_manager_id": m2["user"]["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["manager_id"] == m2["user"]["id"]


@pytest.mark.asyncio
async def test_promote_employee_to_manager_via_rest(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    emp = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn",
                                 manager_id=m1["user"]["id"])

    r = await client.post(f"/api/v1/users/{emp['user']['id']}/change-role", headers=ceo_h,
                          json={"new_role": "manager"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "manager"


@pytest.mark.asyncio
async def test_demote_manager_with_dependents_requires_successor_via_rest(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    m2 = await _invite_and_join(client, ceo_h, "manager", "m2@a.vn")
    await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", manager_id=m1["user"]["id"])

    r = await client.post(f"/api/v1/users/{m1['user']['id']}/change-role", headers=ceo_h,
                          json={"new_role": "employee", "new_manager_id": m2["user"]["id"]})
    assert r.status_code == 422
    assert r.json()["detail"] == "successor_required"
```

- [ ] **Step 2: Chạy test — xác nhận FAIL**

Run: `cd backend && pytest tests/test_change_role_api.py -v`
Expected: FAIL — `404 Not Found` cho route chưa tồn tại (assert `r.status_code == 403` sẽ fail vì thực tế là 404).

- [ ] **Step 3: Thêm `ChangeRoleIn` vào `backend/app/schemas.py`**

Thêm vào cuối file:

```python
class ChangeRoleIn(BaseModel):
    new_role: Role | None = None
    new_manager_id: uuid.UUID | None = None
    successor_id: uuid.UUID | None = None
```

- [ ] **Step 4: Thêm endpoint vào `backend/app/api/users.py`**

Sửa dòng import (hiện tại):

```python
from app.schemas import DeviceOut, OffboardIn, UserOut
```

thành:

```python
from app.schemas import ChangeRoleIn, DeviceOut, OffboardIn, UserOut
```

Thêm endpoint mới **ngay sau** `offboard_user` (cuối file):

```python
@router.post("/{user_id}/change-role")
async def change_role(
    user_id: uuid.UUID,
    body: ChangeRoleIn = ChangeRoleIn(),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.change_role(db, actor, user_id, new_role=body.new_role,
                                          new_manager_id=body.new_manager_id,
                                          successor_id=body.successor_id)
```

(Đặt tên hàm `change_role` trùng tên với `auth_service.change_role` — không xung đột vì khác module/namespace, giống cách `offboard_user` đã trùng tên giữa router và service.)

- [ ] **Step 5: Chạy test — xác nhận PASS**

Run: `cd backend && pytest tests/test_change_role_api.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/api/users.py backend/tests/test_change_role_api.py
git commit -m "feat(be): REST POST /api/v1/users/{id}/change-role"
```

---

### Task 3: Tool chat `change_user_role` + openapi (TDD)

**Files:**
- Modify: `backend/app/agent/tools.py` (thêm tool)
- Modify: `backend/tests/test_agent_tools_report.py` (bump `len(TOOLS)`)
- Test: `backend/tests/test_agent_tools_change_role.py` (mới)

**Interfaces:**
- Consumes: `auth_service.change_role()` (Task 1).

- [ ] **Step 1: Kiểm tra số lượng tool hiện tại**

Run: `cd backend && grep -c "^_register(" app/agent/tools.py`
Expected: `40`. Nếu số này khác 40 (đã thay đổi từ lúc viết plan), STOP và báo cáo — đừng tự âm thầm điều chỉnh con số ở bước sau.

- [ ] **Step 2: Viết test `backend/tests/test_agent_tools_change_role.py`**

```python
import pytest

from app.agent.tools import TOOLS, call_tool
from app.models import Role, User, Workspace


async def _seed(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    mgr = User(workspace_id=ws.id, email="m@a.vn", password_hash="x", full_name="M",
              role=Role.manager)
    db.add_all([ceo, mgr])
    await db.flush()
    await db.commit()
    return ws, ceo, mgr


def test_change_user_role_tool_registered_and_sensitive():
    assert "change_user_role" in TOOLS
    assert TOOLS["change_user_role"].sensitive is True
    assert len(TOOLS) == 41  # +change_user_role (2026-07-15)


@pytest.mark.asyncio
async def test_change_user_role_tool_updates_manager(db_session):
    ws, ceo, mgr = await _seed(db_session)
    employee = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
                    role=Role.employee, manager_id=mgr.id)
    mgr2 = User(workspace_id=ws.id, email="m2@a.vn", password_hash="x", full_name="M2",
               role=Role.manager)
    db_session.add_all([employee, mgr2])
    await db_session.commit()

    result = await call_tool(db_session, ceo, "change_user_role",
                             {"user_id": str(employee.id), "new_manager_id": str(mgr2.id)})
    assert result["manager_id"] == str(mgr2.id)


@pytest.mark.asyncio
async def test_change_user_role_tool_wraps_forbidden_error(db_session):
    ws, ceo, mgr = await _seed(db_session)
    employee = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
                    role=Role.employee, manager_id=mgr.id)
    db_session.add(employee)
    await db_session.commit()

    result = await call_tool(db_session, employee, "change_user_role",
                             {"user_id": str(mgr.id), "new_role": "employee"})
    assert result["error"] == "forbidden"
```

- [ ] **Step 3: Chạy test — xác nhận FAIL**

Run: `cd backend && pytest tests/test_agent_tools_change_role.py -v`
Expected: FAIL — `"change_user_role" not in TOOLS`.

- [ ] **Step 4: Thêm tool vào `backend/app/agent/tools.py`**

Thêm ngay sau hàm `_offboard_user` (trước dòng `_register("list_users", ...)`):

```python
class ChangeUserRoleToolIn(BaseModel):
    user_id: uuid.UUID
    new_role: Role | None = None
    new_manager_id: uuid.UUID | None = None
    successor_id: uuid.UUID | None = None


async def _change_user_role(db, actor, body: ChangeUserRoleToolIn) -> dict:
    return await auth_service.change_role(db, actor, body.user_id, new_role=body.new_role,
                                          new_manager_id=body.new_manager_id,
                                          successor_id=body.successor_id)
```

Thêm `_register` **ngay sau** dòng đăng ký `offboard_user` hiện có (giữ nguyên khối `_register("offboard_user", ...)` y hệt, chỉ chèn thêm khối mới ngay sau):

```python
_register("change_user_role",
          "Đổi vai trò (employee/manager/ceo) và/hoặc đổi người quản lý trực tiếp của 1 người "
          "ĐANG làm việc (không khóa tài khoản, không đụng task đang được giao của họ). Nếu đổi "
          "khỏi vai trò manager mà người đó đang có nhân viên báo cáo hoặc đang sở hữu project, "
          "PHẢI cung cấp successor_id để bàn giao. Chỉ CEO gọi được; đổi liên quan tới vai trò CEO "
          "(thăng ai đó thành CEO, hoặc đổi role của 1 CEO khác) chỉ root CEO gọi được — hành động "
          "nhạy cảm, hệ thống TỰ hiện bước xác nhận khi gọi tool, cứ gọi ngay đừng hỏi trước.",
          ChangeUserRoleToolIn, _change_user_role, sensitive=True)
```

- [ ] **Step 5: Cập nhật assertion số lượng tool trong `backend/tests/test_agent_tools_report.py`**

Tìm dòng cuối file (hiện `assert len(TOOLS) == 40  # ...`) và sửa thành:

```python
    assert len(TOOLS) == 41  # +change_user_role (2026-07-15)
```

- [ ] **Step 6: Chạy test — xác nhận PASS**

Run: `cd backend && pytest tests/test_agent_tools_change_role.py tests/test_agent_tools_report.py -v`
Expected: tất cả pass.

- [ ] **Step 7: Full suite + export openapi**

Run: `cd backend && pytest tests/ -q`
Expected: tất cả pass, output sạch (không có test nào fail vì đếm tool sai ở file khác — nếu có, tìm và sửa file đó y hệt Step 5, đừng đoán số).

Run: `cd backend && python scripts/export_openapi.py`
Expected: `Wrote .../openapi.json`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/agent/tools.py backend/tests/test_agent_tools_change_role.py backend/tests/test_agent_tools_report.py openapi.json
git commit -m "feat(be): tool chat change_user_role + openapi"
```

---

## Ghi chú

- Không có FE cho tính năng này (giống `lock_user`/`offboard_user`) — không cần plan FE riêng trừ khi sau này có yêu cầu.
- Đây là mảnh cuối cùng của khoảng trống "Xử lý khi nhân sự nghỉ hoặc đổi vai trò" nêu ở funtional-plan.md §8 — sau plan này, cả 2 nhánh (nghỉ việc = offboarding, đổi vai trò = plan này) đều đã có.
