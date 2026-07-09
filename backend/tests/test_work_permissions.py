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
