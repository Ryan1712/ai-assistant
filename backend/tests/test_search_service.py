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
