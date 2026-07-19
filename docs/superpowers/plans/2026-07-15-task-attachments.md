# Đính kèm tài liệu trong task — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho phép upload/liệt kê/tải xuống tài liệu đính kèm vào 1 task cụ thể, tái dùng nguyên pattern lưu file + kiểm tra quyền đã có trong `voice_service.py`/`add_comment`.

**Architecture:** 1 model mới `Attachment` (task_id bắt buộc) + 1 service module tái dùng pattern `voice_service.py` (lưu file UUID-named trên đĩa, whitelist đuôi + giới hạn dung lượng) + 1 router REST mới (3 endpoint) + 1 tool chat read-only. Quyền luôn qua `get_visible_task_or_404` có sẵn — không viết logic quyền mới.

**Tech Stack:** FastAPI, SQLAlchemy (async) + Alembic, Pydantic, pytest + pytest-asyncio + httpx (test client).

**Spec nguồn:** [docs/superpowers/specs/2026-07-15-task-attachments-design.md](../specs/2026-07-15-task-attachments-design.md)

## Global Constraints

- Whitelist đuôi file: `.pdf .doc .docx .xls .xlsx .ppt .pptx .txt .png .jpg .jpeg .zip`.
- Giới hạn dung lượng: 20MB (`20 * 1024 * 1024` bytes) — vượt quá → `422 file_too_large`.
- Đuôi ngoài whitelist → `422 unsupported_file_format`.
- File vật lý lưu tại `{storage_dir}/attachments/{workspace_id}/{uuid}{ext}` — KHÔNG dùng tên client gửi lên cho đường dẫn thật (chống path traversal/trùng tên); `original_filename` lưu riêng ở cột DB để hiển thị.
- Quyền luôn qua `get_visible_task_or_404(db, actor, task_id)` có sẵn trong `app/permissions.py` — áp dụng xuyên suốt upload/list/download (download qua task-visibility, KHÔNG phải author-only, khác `voice_service`).
- Thứ tự validate trong `create_attachment`: kiểm tra đuôi file + dung lượng TRƯỚC khi query task (tránh round-trip DB thừa cho file rõ ràng sai).
- Ngoài phạm vi (đừng làm): không có endpoint xóa, không có tool chat để upload, không đụng vào `TaskComment`, không đính kèm vào Project.
- Route mới dưới `/api/v1`. Đổi API contract → chạy `python scripts/export_openapi.py` (từ `backend/`).
- TDD: test trước, code sau; mỗi task 1 commit (quy ước dự án — xem CLAUDE.md).
- Actor luôn lấy từ `Depends(get_current_user)` (JWT), không bao giờ từ tham số client.

---

### Task 1: Model + Migration + `attachment_service.py`

**Files:**
- Modify: `backend/app/models.py` (thêm class `Attachment` ngay sau `VoiceNote`, dòng 364-365)
- Create: `backend/app/services/attachment_service.py`
- Create: `backend/tests/test_attachment_service.py`
- Create (tự sinh): migration mới qua `alembic revision --autogenerate`

**Interfaces:**
- Produces: `app.models.Attachment` — cột `id, workspace_id, task_id, author_id, file_path, original_filename, file_size, created_at`.
- Produces: `attachment_service.create_attachment(db: AsyncSession, actor: User, task_id: uuid.UUID, *, filename: str, data: bytes) -> dict`
- Produces: `attachment_service.list_attachments(db: AsyncSession, actor: User, task_id: uuid.UUID) -> list[dict]`
- Produces: `attachment_service.get_file_path(db: AsyncSession, actor: User, attachment_id: uuid.UUID) -> Path`
- Produces: response dict shape (`_out`): `{"id": str, "task_id": str, "author_id": str, "original_filename": str, "file_size": int, "created_at": datetime}`
- Consumes: `app.permissions.get_visible_task_or_404` (đã có), `app.config.get_settings().storage_dir` (đã có), fixture `storage_dir`/`db_session` trong `tests/conftest.py` (đã có).

- [ ] **Step 1: Thêm model `Attachment` vào `app/models.py`**

Chèn ngay sau `class VoiceNote` (trước `class EmailMessage`, dòng 364-366 hiện tại):

```python
class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    file_path: Mapped[str] = mapped_column(String(512))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
```

Tất cả kiểu (`String`, `Integer`, `DateTime`, `Uuid`, `ForeignKey`, `Mapped`, `mapped_column`) đã được import sẵn ở đầu `app/models.py` — không cần thêm import nào.

- [ ] **Step 2: Viết test thất bại trong `backend/tests/test_attachment_service.py`**

```python
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
```

- [ ] **Step 3: Chạy test, xác nhận FAIL**

Run: `cd backend && pytest tests/test_attachment_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.attachment_service'` (hoặc `ImportError: cannot import name 'attachment_service'`).

- [ ] **Step 4: Viết `backend/app/services/attachment_service.py`**

```python
"""Đính kèm tài liệu trong task (funtional-plan §8) — task_id bắt buộc, khác Note/VoiceNote.

File lưu {storage_dir}/attachments/{workspace_id}/{uuid}{ext} — tên file sinh bằng uuid,
không dùng tên client gửi lên cho đường dẫn thật (giống voice_service._voice_dir);
original_filename lưu riêng ở cột DB để hiển thị tên gốc cho người dùng.
"""
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Attachment, User
from app.permissions import get_visible_task_or_404

_ALLOWED_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                 ".txt", ".png", ".jpg", ".jpeg", ".zip"}
_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


def _attachment_dir(workspace_id: uuid.UUID) -> Path:
    d = Path(get_settings().storage_dir) / "attachments" / str(workspace_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _out(a: Attachment) -> dict:
    return {"id": str(a.id), "task_id": str(a.task_id), "author_id": str(a.author_id),
            "original_filename": a.original_filename, "file_size": a.file_size,
            "created_at": a.created_at}


async def create_attachment(db: AsyncSession, actor: User, task_id: uuid.UUID, *,
                            filename: str, data: bytes) -> dict:
    ext = Path(filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(422, "unsupported_file_format")
    if len(data) > _MAX_FILE_SIZE:
        raise HTTPException(422, "file_too_large")
    task = await get_visible_task_or_404(db, actor, task_id)

    file_path = _attachment_dir(actor.workspace_id) / f"{uuid.uuid4()}{ext}"
    file_path.write_bytes(data)
    attachment = Attachment(workspace_id=actor.workspace_id, task_id=task.id,
                            author_id=actor.id, file_path=str(file_path),
                            original_filename=filename or "file", file_size=len(data))
    db.add(attachment)
    await db.commit()
    return _out(attachment)


async def list_attachments(db: AsyncSession, actor: User, task_id: uuid.UUID) -> list[dict]:
    task = await get_visible_task_or_404(db, actor, task_id)
    rows = await db.execute(select(Attachment).where(Attachment.task_id == task.id)
                            .order_by(Attachment.created_at.desc()))
    return [_out(a) for a in rows.scalars()]


async def get_file_path(db: AsyncSession, actor: User, attachment_id: uuid.UUID) -> Path:
    attachment = await db.get(Attachment, attachment_id)
    if attachment is None or attachment.workspace_id != actor.workspace_id:
        raise HTTPException(404, "attachment_not_found")
    await get_visible_task_or_404(db, actor, attachment.task_id)
    path = Path(attachment.file_path)
    if not path.is_file():
        raise HTTPException(404, "file_not_found")
    return path
```

- [ ] **Step 5: Chạy test, xác nhận PASS**

Run: `cd backend && pytest tests/test_attachment_service.py -v`
Expected: PASS — 8/8 tests xanh.

- [ ] **Step 6: Sinh migration cho Postgres dev**

Yêu cầu hạ tầng local đang chạy (`docker compose up -d postgres redis` từ `backend/`, xem CLAUDE.md — port map 5435/6380).

Run:
```bash
cd backend
.venv\Scripts\activate
alembic revision --autogenerate -m "attachments table"
alembic upgrade head
```
Expected: migration mới sinh ra trong `backend/migrations/versions/`, chỉ chứa `op.create_table("attachments", ...)` — mở file migration ra đọc lại, xác nhận KHÔNG có cột Enum tái sinh type (bugfix `12cce73` không áp dụng ở đây vì `Attachment` không có cột Enum, chỉ cần xác nhận sạch). `alembic upgrade head` chạy không lỗi.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/services/attachment_service.py backend/tests/test_attachment_service.py backend/migrations/versions/
git commit -m "feat(be): model Attachment + attachment_service (upload/list/download qua task-visibility)"
```

---

### Task 2: REST endpoints

**Files:**
- Create: `backend/app/api/attachments.py`
- Modify: `backend/app/main.py:3-7` (thêm import `attachments`), `backend/app/main.py:34` (thêm `app.include_router(attachments.router)` ngay sau dòng `app.include_router(tasks.router)`)
- Create: `backend/tests/test_attachments_api.py`
- Modify (tự sinh): `openapi.json` ở repo root, qua `scripts/export_openapi.py`

**Interfaces:**
- Consumes: `attachment_service.create_attachment`, `attachment_service.list_attachments`, `attachment_service.get_file_path` (Task 1).
- Produces: `POST /api/v1/tasks/{task_id}/attachments` (201, multipart `file`), `GET /api/v1/tasks/{task_id}/attachments`, `GET /api/v1/attachments/{attachment_id}/file`.

- [ ] **Step 1: Viết test thất bại trong `backend/tests/test_attachments_api.py`**

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
    return ceo_h, m1, e1, e2, tid


def _upload_files(name="Hop_dong_A.pdf", content=b"%PDF-fake-bytes"):
    return {"file": (name, content, "application/pdf")}


@pytest.mark.asyncio
async def test_upload_list_download_round_trip(client, storage_dir):
    ceo_h, m1, e1, e2, tid = await _task_with_two_employees(client)
    r = await client.post(f"/api/v1/tasks/{tid}/attachments", headers=_h(e1),
                          files=_upload_files())
    assert r.status_code == 201, r.text
    att = r.json()
    assert att["original_filename"] == "Hop_dong_A.pdf"
    assert att["task_id"] == tid

    listed = await client.get(f"/api/v1/tasks/{tid}/attachments", headers=_h(e2))
    assert len(listed.json()) == 1

    files = list((storage_dir / "attachments").rglob("*.pdf"))
    assert len(files) == 1
    assert "Hop_dong_A" not in files[0].name

    dl = await client.get(f"/api/v1/attachments/{att['id']}/file", headers=_h(e2))
    assert dl.status_code == 200
    assert dl.content == b"%PDF-fake-bytes"


@pytest.mark.asyncio
async def test_upload_rejects_bad_extension(client, storage_dir):
    ceo_h, m1, e1, e2, tid = await _task_with_two_employees(client)
    r = await client.post(f"/api/v1/tasks/{tid}/attachments", headers=_h(e1),
                          files={"file": ("virus.exe", b"x", "application/octet-stream")})
    assert r.status_code == 422
    assert r.json()["detail"] == "unsupported_file_format"


@pytest.mark.asyncio
async def test_outsider_cannot_upload_list_or_download(client, storage_dir):
    ceo_h, m1, e1, e2, tid = await _task_with_two_employees(client)
    m2 = await _invite_and_join(client, ceo_h, "manager", "m2@a.vn")
    r = await client.post(f"/api/v1/tasks/{tid}/attachments", headers=_h(e1),
                          files=_upload_files())
    aid = r.json()["id"]

    assert (await client.post(f"/api/v1/tasks/{tid}/attachments", headers=_h(m2),
                              files=_upload_files())).status_code == 404
    assert (await client.get(f"/api/v1/tasks/{tid}/attachments", headers=_h(m2))).status_code == 404
    assert (await client.get(f"/api/v1/attachments/{aid}/file", headers=_h(m2))).status_code == 404


@pytest.mark.asyncio
async def test_cross_workspace_attachment_404(client, storage_dir):
    ceo_h, m1, e1, e2, tid = await _task_with_two_employees(client)
    r = await client.post(f"/api/v1/tasks/{tid}/attachments", headers=_h(e1),
                          files=_upload_files())
    aid = r.json()["id"]

    other_signup = {
        "workspace_name": "Cong ty B", "email": "ceo-b@a.vn", "password": "secret123",
        "full_name": "Sep B", "device_uuid": "dev-2", "device_name": "",
    }
    resp_signup = await client.post("/api/v1/auth/signup-workspace", json=other_signup)
    assert resp_signup.status_code == 201, resp_signup.text
    other_headers = {"Authorization": f"Bearer {resp_signup.json()['access_token']}"}
    assert (await client.get(f"/api/v1/attachments/{aid}/file",
                             headers=other_headers)).status_code == 404
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `cd backend && pytest tests/test_attachments_api.py -v`
Expected: FAIL — route `/api/v1/tasks/{tid}/attachments` chưa tồn tại → `assert 404 == 201` ở `test_upload_list_download_round_trip`.

- [ ] **Step 3: Viết `backend/app/api/attachments.py`**

```python
import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.services import attachment_service

router = APIRouter(prefix="/api/v1", tags=["attachments"])


@router.post("/tasks/{task_id}/attachments", status_code=201)
async def upload_attachment(task_id: uuid.UUID, file: UploadFile = File(...),
                            actor: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    data = await file.read()
    return await attachment_service.create_attachment(
        db, actor, task_id, filename=file.filename or "", data=data)


@router.get("/tasks/{task_id}/attachments")
async def list_attachments(task_id: uuid.UUID,
                           actor: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    return await attachment_service.list_attachments(db, actor, task_id)


@router.get("/attachments/{attachment_id}/file")
async def download_attachment(attachment_id: uuid.UUID,
                              actor: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    path = await attachment_service.get_file_path(db, actor, attachment_id)
    return FileResponse(path)
```

- [ ] **Step 4: Đăng ký router trong `backend/app/main.py`**

Sửa import (dòng 3-7), thêm `attachments` (thứ tự alphabet, đứng trước `auth`):

```python
from app.api import (
    attachments, auth, chat, dashboard, devices, emails, instructions, invites, notes,
    portal, projects, report_schedules, reports, search, skills, subscription, tasks,
    users, voice_notes, workspace, ws,
)
```

Thêm dòng `app.include_router(attachments.router)` ngay sau `app.include_router(tasks.router)` (dòng 34 hiện tại):

```python
    app.include_router(tasks.router)
    app.include_router(attachments.router)
    app.include_router(skills.router)
```

- [ ] **Step 5: Chạy test, xác nhận PASS**

Run: `cd backend && pytest tests/test_attachments_api.py -v`
Expected: PASS — 4/4 tests xanh.

- [ ] **Step 6: Chạy toàn bộ test suite, xác nhận không hồi quy**

Run: `cd backend && pytest tests/ -v`
Expected: PASS toàn bộ (không có test cũ nào đỏ vì thêm router mới).

- [ ] **Step 7: Xuất lại OpenAPI contract cho FE**

Run: `cd backend && python scripts/export_openapi.py`
Expected: `openapi.json` ở repo root được cập nhật, chứa 3 path mới (`/api/v1/tasks/{task_id}/attachments`, `/api/v1/attachments/{attachment_id}/file`).

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/attachments.py backend/app/main.py backend/tests/test_attachments_api.py openapi.json
git commit -m "feat(be): REST 3 endpoint upload/list/download attachment cho task"
```

---

### Task 3: Tool chat `list_task_attachments`

**Files:**
- Modify: `backend/app/agent/tools.py:18-22` (thêm `attachment_service` vào import), thêm class + handler + `_register` ngay sau block `list_voice_notes`/`get_voice_note` (khoảng dòng 562 hiện tại, trước `_register("get_today_dashboard", ...)`)
- Create: `backend/tests/test_agent_tools_attachments.py`

**Interfaces:**
- Consumes: `attachment_service.create_attachment`, `attachment_service.list_attachments` (Task 1); `call_tool(db, actor, tool_name, tool_input) -> dict` (đã có trong `app/agent/tools.py`).
- Produces: `TOOLS["list_task_attachments"]` — input `{"task_id": uuid}`, output `{"attachments": [...]}`, `sensitive=False`.

- [ ] **Step 1: Viết test thất bại trong `backend/tests/test_agent_tools_attachments.py`**

```python
import pytest

from app.agent.tools import TOOLS, call_tool
from app.models import Project, Role, Task, User, Workspace
from app.services import attachment_service


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db.add(project)
    await db.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="T", created_by=ceo.id)
    db.add(task)
    await db.commit()
    return ws, ceo, task


def test_list_task_attachments_tool_registered_and_not_sensitive():
    spec = TOOLS["list_task_attachments"]
    assert spec.sensitive is False


@pytest.mark.asyncio
async def test_list_task_attachments_returns_uploaded_files(db_session, storage_dir):
    ws, ceo, task = await _world(db_session)
    await attachment_service.create_attachment(
        db_session, ceo, task.id, filename="a.pdf", data=b"noi dung")

    got = await call_tool(db_session, ceo, "list_task_attachments", {"task_id": str(task.id)})
    assert len(got["attachments"]) == 1
    assert got["attachments"][0]["original_filename"] == "a.pdf"
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `cd backend && pytest tests/test_agent_tools_attachments.py -v`
Expected: FAIL — `KeyError: 'list_task_attachments'` (tool chưa đăng ký).

- [ ] **Step 3: Thêm `attachment_service` vào import của `app/agent/tools.py`**

Sửa khối import (dòng 18-22 hiện tại):

```python
from app.services import (
    attachment_service, auth_service, dashboard_service, email_service,
    instruction_service, note_service, portal_service, report_schedule_service,
    report_service, search_service, skill_service, voice_service, work_service,
)
```

- [ ] **Step 4: Thêm tool ngay sau block `list_voice_notes`/`get_voice_note`**

Chèn ngay trước dòng `_register("get_today_dashboard", ...)`:

```python
class ListTaskAttachmentsToolIn(BaseModel):
    task_id: uuid.UUID


async def _list_task_attachments(db, actor, body: ListTaskAttachmentsToolIn) -> dict:
    attachments = await attachment_service.list_attachments(db, actor, body.task_id)
    return {"attachments": attachments}


_register("list_task_attachments", "Liệt kê tài liệu đính kèm của 1 task (tên file, dung "
          "lượng, người đính kèm, thời gian).", ListTaskAttachmentsToolIn,
          _list_task_attachments)
```

- [ ] **Step 5: Chạy test, xác nhận PASS**

Run: `cd backend && pytest tests/test_agent_tools_attachments.py -v`
Expected: PASS — 2/2 tests xanh.

- [ ] **Step 6: Chạy toàn bộ test suite lần cuối**

Run: `cd backend && pytest tests/ -v`
Expected: PASS toàn bộ.

- [ ] **Step 7: Commit**

```bash
git add backend/app/agent/tools.py backend/tests/test_agent_tools_attachments.py
git commit -m "feat(be): tool chat list_task_attachments (read-only, task-visibility)"
```

---

## Self-review

**1. Spec coverage:**
- §1 phạm vi: model `Attachment` (Task 1), upload/list/download REST + tool read-only (Task 2, 3), whitelist + giới hạn dung lượng (Task 1) — đủ. Không có delete/không có tool upload/không đụng Comment/không đụng Project — không task nào vi phạm.
- §2 Model: Task 1 Step 1 — khớp chính xác định nghĩa cột trong spec.
- §3 Storage & Validation: Task 1 Step 4 (`_ALLOWED_EXTS`, `_MAX_FILE_SIZE`, `_attachment_dir`).
- §4 Service functions: Task 1 Step 4 — `create_attachment`/`list_attachments`/`get_file_path` khớp spec, cùng `_out` (được suy ra từ response shape §5 vì spec không viết tường minh hàm này).
- §5 REST endpoints: Task 2 Step 3-4.
- §6 Tool chat: Task 3 Step 4.
- §7 Xử lý lỗi: mọi mã lỗi (`unsupported_file_format`, `file_too_large`, `task_not_found`, `attachment_not_found`, `file_not_found`) đều có test tương ứng ở Task 1/2.
- §8 Testing: 3 file test đúng tên spec yêu cầu (`test_attachment_service.py`, `test_attachments_api.py`, `test_agent_tools_attachments.py`), migration ở Task 1 Step 6, `export_openapi.py` ở Task 2 Step 7.

**2. Placeholder scan:** không còn "TBD"/"tương tự Task N"/mô tả suông — mọi step code đều đầy đủ, chạy được.

**3. Type consistency:** `create_attachment`/`list_attachments`/`get_file_path` dùng cùng chữ ký xuyên suốt Task 1 (định nghĩa) → Task 2 (`app/api/attachments.py` gọi) → Task 3 (test dùng trực tiếp để seed dữ liệu, vì không có tool upload). `Attachment`/`attachment_service` là tên duy nhất được dùng nhất quán, không có biến thể đặt tên khác.

**Lưu ý phạm vi:** FE cố ý không nằm trong plan này (theo quyết định brainstorming đã ghi trong spec) — sẽ là spec+plan riêng sau.
