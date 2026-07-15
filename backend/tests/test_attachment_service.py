import uuid

import pytest
from fastapi import HTTPException

from app.models import Project, Role, Task, TaskAssignee, User, Workspace
from app.services import attachment_service


async def _seed(db):
    """Workspace A: mgr so huu project (thay quyen qua project ownership),
    emp duoc gan vao task (tac gia attachment), outsider la manager khac khong lien quan."""
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="ceo@a.vn", password_hash="x", full_name="Sep",
              role=Role.ceo, is_root=True)
    mgr = User(workspace_id=ws.id, email="mgr@a.vn", password_hash="x", full_name="Quan Ly",
              role=Role.manager)
    outsider = User(workspace_id=ws.id, email="out@a.vn", password_hash="x",
                    full_name="Nguoi Ngoai", role=Role.manager)
    db.add_all([ceo, mgr, outsider])
    await db.flush()
    emp = User(workspace_id=ws.id, email="emp@a.vn", password_hash="x", full_name="Nhan Vien",
              role=Role.employee, manager_id=mgr.id)
    db.add(emp)
    await db.flush()
    project = Project(workspace_id=ws.id, name="Website", created_by=ceo.id, owner_id=mgr.id)
    db.add(project)
    await db.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="Viet hop dong",
               created_by=ceo.id)
    db.add(task)
    await db.flush()
    db.add(TaskAssignee(workspace_id=ws.id, task_id=task.id, user_id=emp.id))
    await db.commit()
    return ws, ceo, mgr, emp, outsider, task


@pytest.mark.asyncio
async def test_upload_success_stores_file_and_metadata(db_session, storage_dir):
    ws, ceo, mgr, emp, outsider, task = await _seed(db_session)
    out = await attachment_service.create_attachment(
        db_session, emp, task.id, filename="Hop_dong_A.pdf", data=b"%PDF-fake-bytes")
    assert out["original_filename"] == "Hop_dong_A.pdf"
    assert out["task_id"] == str(task.id)
    assert out["author_id"] == str(emp.id)
    assert out["file_size"] == len(b"%PDF-fake-bytes")

    files = list((storage_dir / "attachments").rglob("*.pdf"))
    assert len(files) == 1
    assert "Hop_dong_A" not in files[0].name  # ten file thuc la uuid, khong dung ten client gui


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_extension(db_session, storage_dir):
    ws, ceo, mgr, emp, outsider, task = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await attachment_service.create_attachment(
            db_session, emp, task.id, filename="virus.exe", data=b"x")
    assert exc.value.status_code == 422
    assert exc.value.detail == "unsupported_file_format"


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(db_session, storage_dir):
    ws, ceo, mgr, emp, outsider, task = await _seed(db_session)
    big = b"x" * (20 * 1024 * 1024 + 1)
    with pytest.raises(HTTPException) as exc:
        await attachment_service.create_attachment(
            db_session, emp, task.id, filename="big.pdf", data=big)
    assert exc.value.status_code == 422
    assert exc.value.detail == "file_too_large"


@pytest.mark.asyncio
async def test_upload_task_not_visible_404(db_session, storage_dir):
    ws, ceo, mgr, emp, outsider, task = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await attachment_service.create_attachment(
            db_session, outsider, task.id, filename="a.pdf", data=b"x")
    assert exc.value.status_code == 404
    assert exc.value.detail == "task_not_found"


@pytest.mark.asyncio
async def test_list_attachments_for_task(db_session, storage_dir):
    ws, ceo, mgr, emp, outsider, task = await _seed(db_session)
    await attachment_service.create_attachment(
        db_session, emp, task.id, filename="a.pdf", data=b"a")
    await attachment_service.create_attachment(
        db_session, emp, task.id, filename="b.pdf", data=b"b")
    listed = await attachment_service.list_attachments(db_session, mgr, task.id)
    assert len(listed) == 2
    assert {a["original_filename"] for a in listed} == {"a.pdf", "b.pdf"}


@pytest.mark.asyncio
async def test_download_visible_to_non_author_via_task_visibility(db_session, storage_dir):
    ws, ceo, mgr, emp, outsider, task = await _seed(db_session)
    out = await attachment_service.create_attachment(
        db_session, emp, task.id, filename="a.pdf", data=b"noi dung")
    path = await attachment_service.get_file_path(db_session, mgr, uuid.UUID(out["id"]))
    assert path.read_bytes() == b"noi dung"


@pytest.mark.asyncio
async def test_download_rejects_when_task_not_visible(db_session, storage_dir):
    ws, ceo, mgr, emp, outsider, task = await _seed(db_session)
    out = await attachment_service.create_attachment(
        db_session, emp, task.id, filename="a.pdf", data=b"x")
    with pytest.raises(HTTPException) as exc:
        await attachment_service.get_file_path(db_session, outsider, uuid.UUID(out["id"]))
    assert exc.value.status_code == 404
    assert exc.value.detail == "task_not_found"


@pytest.mark.asyncio
async def test_download_rejects_cross_workspace_attachment_id(db_session, storage_dir):
    ws, ceo, mgr, emp, outsider, task = await _seed(db_session)
    out = await attachment_service.create_attachment(
        db_session, emp, task.id, filename="a.pdf", data=b"x")
    other_ws = Workspace(name="B")
    db_session.add(other_ws)
    await db_session.flush()
    other_user = User(workspace_id=other_ws.id, email="other@b.vn", password_hash="x",
                      full_name="Khac Workspace", role=Role.ceo, is_root=True)
    db_session.add(other_user)
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await attachment_service.get_file_path(db_session, other_user, uuid.UUID(out["id"]))
    assert exc.value.status_code == 404
    assert exc.value.detail == "attachment_not_found"
