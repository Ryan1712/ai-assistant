import io
import uuid as uuid_mod
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.tools import SENSITIVE_TOOLS, TOOLS
from app.api.voice_notes import get_arq_pool as voice_get_arq_pool
from app.db import get_db
from app.main import create_app
from app.models import (
    Attachment, EmailMessage, Task, TaskAssignee, TaskComment, TaskUpdate, VoiceNote,
)
from tests.conftest import _ceo_headers, _invite_and_join


class _FakeArqPool:
    async def enqueue_job(self, name, *args, **kwargs):
        return "job"


@pytest.fixture
async def client(engine):
    # Override client mac dinh cua conftest: them fake arq pool vi co test upload
    # voice note (endpoint do doc app.state.arq_pool khi enqueue transcribe).
    app = create_app()
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[voice_get_arq_pool] = lambda: _FakeArqPool()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


async def _project(client, ceo_h, **kw):
    resp = await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P", **kw})
    return resp.json()["id"]


async def _task(client, ceo_h, pid, title="T"):
    r = await client.post("/api/v1/tasks", headers=ceo_h,
                          json={"project_id": pid, "title": title})
    return r.json()["id"]


@pytest.mark.asyncio
async def test_ceo_xoa_task_cascade_het_row_con(client, db_session, storage_dir):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    pid = await _project(client, ceo_h)
    tid = await _task(client, ceo_h, pid)

    # Dung du lieu con: assignee, update, comment, attachment (file that tren dia)
    await client.post(f"/api/v1/tasks/{tid}/assignees", headers=ceo_h,
                      json={"user_id": m1["user"]["id"]})
    await client.post(f"/api/v1/tasks/{tid}/updates", headers=_h(m1),
                      json={"content": "dang lam", "percent": 30})
    await client.post(f"/api/v1/tasks/{tid}/comments", headers=ceo_h,
                      json={"content": "trao doi"})
    up = await client.post(f"/api/v1/tasks/{tid}/attachments", headers=ceo_h,
                           files={"file": ("f.pdf", io.BytesIO(b"pdf"), "application/pdf")})
    assert up.status_code == 201, up.text
    att = await db_session.get(Attachment, uuid_mod.UUID(up.json()["id"]))
    att_path = Path(att.file_path)
    assert att_path.is_file()

    r = await client.delete(f"/api/v1/tasks/{tid}", headers=ceo_h)
    assert r.status_code == 204

    assert (await client.get(f"/api/v1/tasks/{tid}", headers=ceo_h)).status_code == 404
    tid_u = uuid_mod.UUID(tid)
    for model in (TaskAssignee, TaskUpdate, TaskComment, Attachment):
        rows = (await db_session.execute(select(model).where(
            model.task_id == tid_u))).scalars().all()
        assert rows == [], f"{model.__name__} chua bi xoa"
    assert not att_path.exists()


@pytest.mark.asyncio
async def test_xoa_task_go_link_voice_note_va_email(client, db_session, storage_dir):
    ceo_h = await _ceo_headers(client)
    pid = await _project(client, ceo_h)
    tid = await _task(client, ceo_h, pid)

    up = await client.post("/api/v1/voice-notes", headers=ceo_h,
                           files={"file": ("a.m4a", io.BytesIO(b"x"), "audio/m4a")},
                           data={"task_id": tid})
    assert up.status_code == 201, up.text
    vid = uuid_mod.UUID(up.json()["id"])

    r = await client.delete(f"/api/v1/tasks/{tid}", headers=ceo_h)
    assert r.status_code == 204

    note = await db_session.get(VoiceNote, vid)
    assert note is not None  # ghi am con nguyen — chi go link
    assert note.task_id is None


@pytest.mark.asyncio
async def test_khong_phai_ceo_khong_xoa_duoc(client, db_session):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    pid = await _project(client, ceo_h)
    tid = await _task(client, ceo_h, pid)

    assert (await client.delete(f"/api/v1/tasks/{tid}", headers=_h(m1))).status_code == 403
    assert (await client.delete(f"/api/v1/projects/{pid}", headers=_h(m1))).status_code == 403
    # van con nguyen
    assert (await client.get(f"/api/v1/tasks/{tid}", headers=ceo_h)).status_code == 200


@pytest.mark.asyncio
async def test_cross_workspace_404(client, db_session):
    ceo_h = await _ceo_headers(client)
    pid = await _project(client, ceo_h)
    tid = await _task(client, ceo_h, pid)

    # workspace B
    other = await client.post("/api/v1/auth/signup-workspace", json={
        "workspace_name": "B Co", "email": "ceo-b@b.vn", "password": "pw123456",
        "full_name": "CEO B", "device_uuid": "d-b", "device_name": "",
    })
    b_h = {"Authorization": f"Bearer {other.json()['access_token']}"}

    assert (await client.delete(f"/api/v1/tasks/{tid}", headers=b_h)).status_code == 404
    assert (await client.delete(f"/api/v1/projects/{pid}", headers=b_h)).status_code == 404


@pytest.mark.asyncio
async def test_ceo_xoa_project_keo_theo_tasks(client, db_session):
    ceo_h = await _ceo_headers(client)
    pid = await _project(client, ceo_h)
    t1 = await _task(client, ceo_h, pid, "t1")
    t2 = await _task(client, ceo_h, pid, "t2")

    r = await client.delete(f"/api/v1/projects/{pid}", headers=ceo_h)
    assert r.status_code == 204

    for tid in (t1, t2):
        row = await db_session.get(Task, uuid_mod.UUID(tid))
        assert row is None
    listed = (await client.get("/api/v1/projects", headers=ceo_h)).json()
    assert all(p["id"] != pid for p in listed)


def test_tools_dang_ky_va_nhay_cam():
    assert "delete_task" in TOOLS and "delete_project" in TOOLS
    assert "delete_task" in SENSITIVE_TOOLS and "delete_project" in SENSITIVE_TOOLS
    assert len(TOOLS) == 51  # 49 + delete_task + delete_project


@pytest.mark.asyncio
async def test_xoa_task_go_link_note_va_skill(client, db_session):
    """Final review phat hien: Note.task_id va Skill.task_id la FK khong ondelete —
    tren Postgres xoa task ma con note/skill link se IntegrityError (SQLite test
    khong bat duoc vi khong bat PRAGMA foreign_keys). Cascade phai null 2 link nay."""
    from app.models import Note, Skill

    ceo_h = await _ceo_headers(client)
    pid = await _project(client, ceo_h)
    tid = await _task(client, ceo_h, pid)
    tid_u = uuid_mod.UUID(tid)

    from app.models import SkillKind

    ceo_row = (await db_session.execute(select(Task).where(Task.id == tid_u))).scalar_one()
    ws = ceo_row.workspace_id
    note = Note(workspace_id=ws, author_id=ceo_row.created_by, content="ghi chu",
                task_id=tid_u)
    skill = Skill(workspace_id=ws, name="quy trinh", kind=SkillKind.knowledge,
                  created_by=ceo_row.created_by, task_id=tid_u)
    db_session.add_all([note, skill])
    await db_session.commit()

    r = await client.delete(f"/api/v1/tasks/{tid}", headers=ceo_h)
    assert r.status_code == 204

    await db_session.refresh(note)
    await db_session.refresh(skill)
    assert note.task_id is None      # note giu nguyen, chi go link
    assert skill.task_id is None     # skill giu nguyen, chi go link


@pytest.mark.asyncio
async def test_xoa_project_go_link_note_va_tat_lich_bao_cao(client, db_session):
    """Note.project_id null; ReportSchedule cua project bi xoa: null project_id VA
    active=False — null suong khong thi lich dang scoped-theo-project am tham thanh
    lich toan workspace, chay mai mai (final review)."""
    from app.models import Note, ReportSchedule

    ceo_h = await _ceo_headers(client)
    pid = await _project(client, ceo_h)
    pid_u = uuid_mod.UUID(pid)

    task_row_id = await _task(client, ceo_h, pid)
    t = await db_session.get(Task, uuid_mod.UUID(task_row_id))
    ws, ceo_id = t.workspace_id, t.created_by
    note = Note(workspace_id=ws, author_id=ceo_id, content="ghi chu project",
                project_id=pid_u)
    from datetime import datetime, timezone

    sched = ReportSchedule(workspace_id=ws, created_by=ceo_id, recipient_id=ceo_id,
                           project_id=pid_u, weekday=None, hour=8, minute=0,
                           next_run_at=datetime(2030, 1, 1, tzinfo=timezone.utc))
    db_session.add_all([note, sched])
    await db_session.commit()

    r = await client.delete(f"/api/v1/projects/{pid}", headers=ceo_h)
    assert r.status_code == 204

    await db_session.refresh(note)
    await db_session.refresh(sched)
    assert note.project_id is None
    assert sched.project_id is None
    assert sched.active is False
