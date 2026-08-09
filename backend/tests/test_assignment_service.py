"""suggest_assignee (spec docs/superpowers/specs/2026-08-09-suggest-assignee-design.md):
gợi ý người phù hợp khi giao task, ưu tiên khớp chuyên môn ngữ nghĩa, tie-break
bằng số task đang làm dở (ít hơn = rảnh hơn). Fallback về người rảnh nhất
toàn workspace nếu không ai khớp chuyên môn."""
import pytest

from app.models import Project, Role, Task, TaskAssignee, TaskStatus, User, Workspace
from app.services import assignment_service, auth_service, embedding_service


async def _mk_ceo(db, ws):
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    return ceo


async def _mk_employee_with_expertise(db, ws, name, expertise):
    user = User(workspace_id=ws.id, full_name=name, role=Role.employee,
               expertise_notes=expertise)
    db.add(user)
    await db.flush()
    await embedding_service.index_employee_expertise(db, ws.id, user)
    return user


@pytest.mark.asyncio
async def test_suggest_assignee_khop_dung_chuyen_mon(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = await _mk_ceo(db_session, ws)
    designer = await _mk_employee_with_expertise(
        db_session, ws, "Duy Linh", "design, figma, giao dien nguoi dung")
    backend_dev = await _mk_employee_with_expertise(
        db_session, ws, "Nam", "backend python, database, api")
    await db_session.commit()

    result = await assignment_service.suggest_assignee(
        db_session, ceo, task_title="Thiet ke lai giao dien trang chu",
        task_description="Can lam moi UI/UX trang chu bang Figma")

    assert len(result["suggestions"]) >= 1
    top = result["suggestions"][0]
    assert top["user_id"] == str(designer.id)
    assert "Duy Linh" in top["reason"] or top["full_name"] == "Duy Linh"


@pytest.mark.asyncio
async def test_suggest_assignee_tie_break_bang_so_task_dang_lam(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = await _mk_ceo(db_session, ws)
    busy = await _mk_employee_with_expertise(db_session, ws, "Busy Dev", "python backend api")
    free = await _mk_employee_with_expertise(db_session, ws, "Free Dev", "python backend api")
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    # busy có 3 task dang lam, free co 0
    for i in range(3):
        t = Task(workspace_id=ws.id, project_id=project.id, title=f"T{i}",
                 status=TaskStatus.in_progress, created_by=ceo.id)
        db_session.add(t)
        await db_session.flush()
        db_session.add(TaskAssignee(workspace_id=ws.id, task_id=t.id, user_id=busy.id))
    await db_session.commit()

    result = await assignment_service.suggest_assignee(
        db_session, ceo, task_title="Viet API moi", task_description="backend python")

    top_ids = [s["user_id"] for s in result["suggestions"][:2]]
    assert str(free.id) in top_ids
    # free phải đứng trước busy nếu cả 2 cùng lọt top (score gần bằng nhau)
    if str(busy.id) in top_ids:
        assert top_ids.index(str(free.id)) < top_ids.index(str(busy.id))


@pytest.mark.asyncio
async def test_suggest_assignee_fallback_khi_khong_ai_khop_chuyen_mon(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = await _mk_ceo(db_session, ws)
    emp1 = await _mk_employee_with_expertise(db_session, ws, "E1", "ke toan")
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    t = Task(workspace_id=ws.id, project_id=project.id, title="T",
             status=TaskStatus.in_progress, created_by=ceo.id)
    db_session.add(t)
    await db_session.flush()
    db_session.add(TaskAssignee(workspace_id=ws.id, task_id=t.id, user_id=emp1.id))
    emp2 = await _mk_employee_with_expertise(db_session, ws, "E2", "hanh chinh")
    await db_session.commit()

    result = await assignment_service.suggest_assignee(
        db_session, ceo,
        task_title="Nghien cuu machine learning va deep learning cho san pham AI",
        task_description="")

    assert len(result["suggestions"]) == 1
    # emp2 ranh hon (0 task) nen duoc chon lam fallback
    assert result["suggestions"][0]["user_id"] == str(emp2.id)
    assert "rảnh" in result["suggestions"][0]["reason"].lower()


@pytest.mark.asyncio
async def test_suggest_assignee_khong_tu_goi_y_chinh_actor(db_session):
    """Fix round (final whole-branch review, Finding 2): nếu CEO tự set
    expertise_notes khớp đúng nội dung task đang hỏi, CEO KHÔNG được xuất
    hiện trong suggestions -- suggest_assignee gợi ý NHÂN VIÊN để giao việc,
    không tự gợi ý chính người đang hỏi."""
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = await _mk_ceo(db_session, ws)
    ceo.expertise_notes = "design, figma, giao dien nguoi dung"
    db_session.add(ceo)
    await db_session.commit()
    await embedding_service.index_employee_expertise(db_session, ws.id, ceo)

    result = await assignment_service.suggest_assignee(
        db_session, ceo, task_title="Thiet ke lai giao dien trang chu",
        task_description="Can lam moi UI/UX trang chu bang Figma")

    suggested_ids = [s["user_id"] for s in result["suggestions"]]
    assert str(ceo.id) not in suggested_ids


@pytest.mark.asyncio
async def test_suggest_assignee_requires_ceo(db_session):
    from fastapi import HTTPException

    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    manager = User(workspace_id=ws.id, email="m@a.vn", password_hash="x", full_name="M",
                   role=Role.manager)
    db_session.add(manager)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await assignment_service.suggest_assignee(db_session, manager, task_title="T")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_suggest_assignee_workspace_khong_co_nhan_vien(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = await _mk_ceo(db_session, ws)
    await db_session.commit()

    result = await assignment_service.suggest_assignee(db_session, ceo, task_title="T")
    assert result["suggestions"] == []
