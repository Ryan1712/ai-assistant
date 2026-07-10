# Plan 4 — Báo cáo & Xuất Excel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tool agent `generate_report` (tool thứ 22, CEO-only) tổng hợp task ra file `.xlsx` + endpoint `GET /api/v1/reports/{report_id}/download` để FE tải file — mảnh cuối của Giai đoạn 1 (MVP).

**Architecture:** Thêm 1 model `Report` (metadata + tóm tắt, nội dung chi tiết chỉ nằm trong file), 1 service `report_service.generate_report()` (permission + query + ghi file openpyxl), 1 tool đăng ký qua cơ chế `ToolSpec`/`call_tool` sẵn có từ Plan 3, 1 REST router trả `FileResponse`. File lưu tại `{settings.storage_dir}/{workspace_id}/{report_id}.xlsx`, share giữa `api`/`worker` qua named volume docker.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, openpyxl (dependency mới), pytest + httpx ASGITransport.

**Spec:** `docs/superpowers/specs/2026-07-10-report-excel-design.md`

## Global Constraints

- Mọi bảng mới có `workspace_id`; mọi query lọc theo `workspace_id == actor.workspace_id`.
- Quyền kiểm tra ở service layer (`require_ceo` từ `app/permissions.py`) — không ở prompt/model.
- `actor` luôn là `User` lấy từ JWT (`get_current_user`) — không từ tham số client.
- Route dưới `/api/v1`. Đổi contract ⇒ chạy lại `python scripts/export_openapi.py`.
- TDD: test trước, code sau; mỗi task một commit.
- Chỉ CEO tạo VÀ tải báo cáo. Endpoint download trả **404** (không phải 403) khi không phải CEO.
- Cột Excel cố định: **Tên task, Project, Trạng thái, % hoàn thành, Người phụ trách, Cập nhật mới nhất, Deadline**.
- File lưu: `{settings.storage_dir}/{workspace_id}/{report_id}.xlsx`; `storage_dir` mặc định `./storage/reports`.
- Tool `generate_report`: `sensitive=False`, mọi input field optional.
- 0 task khớp filter ⇒ vẫn tạo file (chỉ header), `summary.total = 0`, không lỗi.
- Mọi lệnh chạy trong `backend/` với venv đã kích hoạt (`.venv\Scripts\activate`).

## File Structure

| File | Vai trò |
|---|---|
| `backend/app/models.py` | Thêm model `Report` (Task 1) |
| `backend/app/config.py` | Thêm `storage_dir` (Task 1) |
| `backend/alembic/versions/c4d5e6f70812_reports.py` | Migration bảng `reports` (Task 1) |
| `backend/app/services/report_service.py` | Mới — `generate_report()` (Task 2) |
| `backend/requirements.txt` | Thêm `openpyxl` (Task 2) |
| `backend/tests/conftest.py` | Thêm fixture `storage_dir` (Task 2) |
| `backend/app/agent/tools.py` | Đăng ký tool `generate_report` (Task 3) |
| `backend/app/api/reports.py` | Mới — router download (Task 4) |
| `backend/app/main.py` | Mount router reports (Task 4) |
| `backend/docker-compose.yml` | Volume `reports_data` + `STORAGE_DIR` (Task 5) |
| `openapi.json` (repo root) | Regen contract cho FE (Task 5) |
| Tests | `tests/test_report_service.py`, `tests/test_agent_tools_report.py`, `tests/test_reports_api.py` |

---

### Task 1: Model `Report` + config `storage_dir` + migration

**Files:**
- Modify: `backend/app/models.py` (thêm class cuối file, sau `UsageLog`)
- Modify: `backend/app/config.py:14` (thêm field vào `Settings`)
- Create: `backend/alembic/versions/c4d5e6f70812_reports.py`
- Test: `backend/tests/test_report_service.py` (tạo mới, thêm test tiếp ở Task 2)

**Interfaces:**
- Consumes: `Base`, `_uuid`, `_now` sẵn có trong `app/models.py`.
- Produces: model `Report` (fields: `id, workspace_id, requested_by, kind, filters, summary, file_path, created_at`); `Settings.storage_dir: str = "./storage/reports"` — Task 2/4 đọc qua `get_settings().storage_dir`.

- [ ] **Step 1: Viết test fail**

Tạo `backend/tests/test_report_service.py`:

```python
import pytest

from app.config import Settings
from app.models import Report, Role, User, Workspace


def test_storage_dir_setting_default():
    assert Settings().storage_dir == "./storage/reports"


@pytest.mark.asyncio
async def test_report_model_roundtrip(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    report = Report(workspace_id=ws.id, requested_by=ceo.id,
                    filters={"status": "done"}, summary={"total": 0},
                    file_path=f"{ws.id}/x.xlsx")
    db_session.add(report)
    await db_session.commit()

    fetched = await db_session.get(Report, report.id)
    assert fetched.kind == "task_summary"
    assert fetched.filters == {"status": "done"}
    assert fetched.summary == {"total": 0}
    assert fetched.created_at is not None
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `pytest tests/test_report_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'Report' from 'app.models'`

- [ ] **Step 3: Thêm model + setting**

Cuối `backend/app/models.py` (sau class `UsageLog`):

```python
class Report(Base):
    __tablename__ = "reports"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(32), default="task_summary")
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    file_path: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
```

Trong `backend/app/config.py`, thêm 1 dòng vào class `Settings` (sau `model_chat`):

```python
    storage_dir: str = "./storage/reports"
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `pytest tests/test_report_service.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Tạo migration**

Nếu Postgres dev đang chạy (`docker compose up -d postgres` trong `backend/`):

```bash
alembic revision --autogenerate -m "reports"
alembic upgrade head
```

Kiểm tra file sinh ra khớp nội dung dưới (bảng `reports` + index `workspace_id`). Nếu KHÔNG có Postgres, tạo tay `backend/alembic/versions/c4d5e6f70812_reports.py` với nội dung:

```python
"""reports

Revision ID: c4d5e6f70812
Revises: 7615af4daf88
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f70812'
down_revision: Union[str, Sequence[str], None] = '7615af4daf88'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('reports',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('requested_by', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('filters', sa.JSON(), nullable=False),
    sa.Column('summary', sa.JSON(), nullable=False),
    sa.Column('file_path', sa.String(length=512), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_reports_workspace_id'), 'reports', ['workspace_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_reports_workspace_id'), table_name='reports')
    op.drop_table('reports')
```

(Tên file khi autogenerate sẽ có revision id ngẫu nhiên khác — chấp nhận, chỉ cần `down_revision = '7615af4daf88'`.)

- [ ] **Step 6: Chạy toàn bộ test cũ, xác nhận không vỡ gì**

Run: `pytest tests/ -v`
Expected: tất cả PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/config.py backend/alembic/versions/ backend/tests/test_report_service.py
git commit -m "feat(be): report model + storage_dir config"
```

---

### Task 2: `report_service.generate_report()` — query + ghi file Excel

**Files:**
- Create: `backend/app/services/report_service.py`
- Modify: `backend/requirements.txt` (thêm `openpyxl`)
- Modify: `backend/tests/conftest.py` (thêm fixture `storage_dir`)
- Test: `backend/tests/test_report_service.py` (bổ sung)

**Interfaces:**
- Consumes: `Report` model + `get_settings().storage_dir` (Task 1); `require_ceo` từ `app.permissions`; models `Task, Project, TaskAssignee, TaskUpdate, User, TaskStatus`.
- Produces:
  ```python
  async def generate_report(db: AsyncSession, actor: User, *,
                            project_id: uuid.UUID | None = None,
                            assignee_id: uuid.UUID | None = None,
                            date_from: date | None = None,
                            date_to: date | None = None,
                            status: TaskStatus | None = None) -> dict
  # trả: {"report_id": str, "summary": {"total": int, "todo": int, "in_progress": int,
  #        "blocked": int, "done": int}, "row_count": int, "filters_applied": dict}
  # raise HTTPException(403) nếu không phải CEO; HTTPException(404) nếu project_id/assignee_id
  # không tồn tại hoặc khác workspace.
  ```
  Fixture pytest `storage_dir` (conftest): monkeypatch `get_settings().storage_dir` = `tmp_path`, trả về `tmp_path` — Task 3/4 dùng lại.

- [ ] **Step 1: Cài openpyxl**

Thêm dòng vào `backend/requirements.txt` (cuối file):

```
openpyxl==3.1.*
```

Run: `pip install openpyxl==3.1.*`
Expected: `Successfully installed openpyxl-3.1.x` (kèm et-xmlfile)

- [ ] **Step 2: Thêm fixture `storage_dir` vào conftest**

Cuối `backend/tests/conftest.py`:

```python
@pytest.fixture
def storage_dir(tmp_path, monkeypatch):
    from app.config import get_settings
    # get_settings() là lru_cache — monkeypatch attr trên instance, tự hoàn nguyên sau test
    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path))
    return tmp_path
```

- [ ] **Step 3: Viết các test fail cho service**

Bổ sung vào `backend/tests/test_report_service.py` (giữ nguyên 2 test Task 1; cập nhật khối import đầu file thành):

```python
import uuid
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook
from sqlalchemy import select

from app.config import Settings
from app.models import (
    Project, Report, Role, Task, TaskAssignee, TaskStatus, TaskUpdate, User, Workspace,
)
from app.services import report_service
```

Rồi thêm helpers + tests:

```python
async def _seed(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="ceo@a.vn", password_hash="x", full_name="Sep",
              role=Role.ceo, is_root=True)
    emp = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="Nhan Vien",
              role=Role.employee)
    db.add_all([ceo, emp])
    await db.flush()
    project = Project(workspace_id=ws.id, name="Website", created_by=ceo.id)
    db.add(project)
    await db.flush()
    return ws, ceo, emp, project


async def _task(db, ws, project, ceo, title, status=TaskStatus.todo, percent=0):
    task = Task(workspace_id=ws.id, project_id=project.id, title=title,
                status=status, percent=percent, created_by=ceo.id)
    db.add(task)
    await db.flush()
    return task


@pytest.mark.asyncio
async def test_generate_report_writes_xlsx_and_summary(db_session, storage_dir):
    ws, ceo, emp, project = await _seed(db_session)
    t1 = await _task(db_session, ws, project, ceo, "Lam trang chu",
                     status=TaskStatus.in_progress, percent=40)
    await _task(db_session, ws, project, ceo, "Viet tai lieu", status=TaskStatus.done,
                percent=100)
    db_session.add(TaskAssignee(workspace_id=ws.id, task_id=t1.id, user_id=emp.id))
    db_session.add(TaskUpdate(workspace_id=ws.id, task_id=t1.id, author_id=emp.id,
                              content="da xong 40%", percent=40))
    await db_session.commit()

    result = await report_service.generate_report(db_session, ceo)

    assert result["row_count"] == 2
    assert result["summary"] == {"total": 2, "todo": 0, "in_progress": 1,
                                 "blocked": 0, "done": 1}
    report = await db_session.get(Report, uuid.UUID(result["report_id"]))
    assert report.workspace_id == ws.id
    assert report.requested_by == ceo.id
    assert report.summary == result["summary"]

    path = storage_dir / str(ws.id) / f"{result['report_id']}.xlsx"
    assert path.is_file()
    assert report.file_path == f"{ws.id}/{result['report_id']}.xlsx"
    sheet = load_workbook(path).active
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0] == ("Tên task", "Project", "Trạng thái", "% hoàn thành",
                       "Người phụ trách", "Cập nhật mới nhất", "Deadline")
    assert len(rows) == 3
    row1 = next(r for r in rows[1:] if r[0] == "Lam trang chu")
    assert row1[1] == "Website"
    assert row1[2] == "in_progress"
    assert row1[3] == 40
    assert row1[4] == "Nhan Vien"
    assert "da xong 40%" in row1[5]


@pytest.mark.asyncio
async def test_generate_report_forbidden_for_non_ceo(db_session, storage_dir):
    ws, ceo, emp, project = await _seed(db_session)
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await report_service.generate_report(db_session, emp)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_generate_report_unknown_project_404(db_session, storage_dir):
    ws, ceo, emp, project = await _seed(db_session)
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await report_service.generate_report(db_session, ceo, project_id=uuid.uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_generate_report_unknown_assignee_404(db_session, storage_dir):
    ws, ceo, emp, project = await _seed(db_session)
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await report_service.generate_report(db_session, ceo, assignee_id=uuid.uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_generate_report_filters(db_session, storage_dir):
    ws, ceo, emp, project = await _seed(db_session)
    other = Project(workspace_id=ws.id, name="App", created_by=ceo.id)
    db_session.add(other)
    await db_session.flush()
    t1 = await _task(db_session, ws, project, ceo, "T1", status=TaskStatus.done)
    await _task(db_session, ws, other, ceo, "T2", status=TaskStatus.todo)
    db_session.add(TaskAssignee(workspace_id=ws.id, task_id=t1.id, user_id=emp.id))
    await db_session.commit()

    by_project = await report_service.generate_report(db_session, ceo,
                                                      project_id=project.id)
    assert by_project["row_count"] == 1

    by_status = await report_service.generate_report(db_session, ceo,
                                                     status=TaskStatus.done)
    assert by_status["row_count"] == 1

    by_assignee = await report_service.generate_report(db_session, ceo,
                                                       assignee_id=emp.id)
    assert by_assignee["row_count"] == 1
    assert by_assignee["filters_applied"]["assignee_id"] == str(emp.id)

    future = date.today() + timedelta(days=7)
    by_date = await report_service.generate_report(db_session, ceo, date_from=future)
    assert by_date["row_count"] == 0


@pytest.mark.asyncio
async def test_generate_report_empty_still_creates_file(db_session, storage_dir):
    ws, ceo, emp, project = await _seed(db_session)
    await db_session.commit()
    result = await report_service.generate_report(db_session, ceo,
                                                  status=TaskStatus.blocked)
    assert result["summary"]["total"] == 0
    path = storage_dir / str(ws.id) / f"{result['report_id']}.xlsx"
    assert path.is_file()
    sheet = load_workbook(path).active
    assert len(list(sheet.iter_rows())) == 1  # chỉ header
```

- [ ] **Step 4: Chạy test, xác nhận fail**

Run: `pytest tests/test_report_service.py -v`
Expected: 2 test Task 1 PASS; các test mới FAIL — `ImportError: cannot import name 'report_service'`

- [ ] **Step 5: Viết service**

Tạo `backend/app/services/report_service.py`:

```python
import uuid
from datetime import date, datetime, time, timezone
from pathlib import Path

from fastapi import HTTPException
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Project, Report, Task, TaskAssignee, TaskStatus, TaskUpdate, User
from app.permissions import require_ceo

_HEADERS = ["Tên task", "Project", "Trạng thái", "% hoàn thành",
            "Người phụ trách", "Cập nhật mới nhất", "Deadline"]


async def _latest_update_cell(db: AsyncSession, task_id: uuid.UUID) -> str:
    latest = (await db.execute(
        select(TaskUpdate).where(TaskUpdate.task_id == task_id)
        .order_by(TaskUpdate.created_at.desc(), TaskUpdate.id.desc()).limit(1)
    )).scalar_one_or_none()
    if latest is None:
        return ""
    return f"{latest.content} ({latest.created_at.strftime('%d/%m/%Y %H:%M')})"


async def generate_report(db: AsyncSession, actor: User, *,
                          project_id: uuid.UUID | None = None,
                          assignee_id: uuid.UUID | None = None,
                          date_from: date | None = None,
                          date_to: date | None = None,
                          status: TaskStatus | None = None) -> dict:
    require_ceo(actor)
    if project_id is not None:
        project = await db.get(Project, project_id)
        if project is None or project.workspace_id != actor.workspace_id:
            raise HTTPException(404, "project_not_found")
    if assignee_id is not None:
        assignee = await db.get(User, assignee_id)
        if assignee is None or assignee.workspace_id != actor.workspace_id:
            raise HTTPException(404, "user_not_found")

    query = select(Task).where(Task.workspace_id == actor.workspace_id)
    if project_id is not None:
        query = query.where(Task.project_id == project_id)
    if assignee_id is not None:
        query = query.where(Task.id.in_(
            select(TaskAssignee.task_id).where(TaskAssignee.user_id == assignee_id)))
    if date_from is not None:
        query = query.where(Task.created_at >= datetime.combine(
            date_from, time.min, tzinfo=timezone.utc))
    if date_to is not None:
        query = query.where(Task.created_at <= datetime.combine(
            date_to, time.max, tzinfo=timezone.utc))
    if status is not None:
        query = query.where(Task.status == status)
    tasks = list((await db.execute(query.order_by(Task.created_at.asc()))).scalars())

    wb = Workbook()
    sheet = wb.active
    sheet.title = "Tasks"
    sheet.append(_HEADERS)
    summary = {"total": len(tasks), **{s.value: 0 for s in TaskStatus}}
    for task in tasks:
        summary[task.status.value] += 1
        project_row = await db.get(Project, task.project_id)
        assignee_names = (await db.execute(
            select(User.full_name).join(TaskAssignee, TaskAssignee.user_id == User.id)
            .where(TaskAssignee.task_id == task.id))).scalars()
        sheet.append([
            task.title,
            project_row.name if project_row else "",
            task.status.value,
            task.percent,
            ", ".join(assignee_names),
            await _latest_update_cell(db, task.id),
            task.deadline.strftime("%d/%m/%Y") if task.deadline else "",
        ])

    filters = {"project_id": str(project_id) if project_id else None,
               "assignee_id": str(assignee_id) if assignee_id else None,
               "date_from": date_from.isoformat() if date_from else None,
               "date_to": date_to.isoformat() if date_to else None,
               "status": status.value if status else None}
    report = Report(workspace_id=actor.workspace_id, requested_by=actor.id,
                    filters=filters, summary=summary, file_path="")
    db.add(report)
    await db.flush()
    report.file_path = f"{actor.workspace_id}/{report.id}.xlsx"

    out = Path(get_settings().storage_dir) / report.file_path
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)

    await db.commit()
    return {"report_id": str(report.id), "summary": summary,
            "row_count": len(tasks), "filters_applied": filters}
```

- [ ] **Step 6: Chạy test, xác nhận pass**

Run: `pytest tests/test_report_service.py -v`
Expected: PASS (8 passed)

- [ ] **Step 7: Chạy toàn bộ suite**

Run: `pytest tests/ -v`
Expected: tất cả PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/report_service.py backend/requirements.txt backend/tests/conftest.py backend/tests/test_report_service.py
git commit -m "feat(be): report_service.generate_report - excel export"
```

---

### Task 3: Tool agent `generate_report` (tool thứ 22)

**Files:**
- Modify: `backend/app/agent/tools.py` (thêm cuối file, trước khối `SENSITIVE_TOOLS`)
- Test: `backend/tests/test_agent_tools_report.py`

**Interfaces:**
- Consumes: `report_service.generate_report(db, actor, **kwargs) -> dict` (Task 2); `_register`, `call_tool`, `TOOLS` sẵn có trong `tools.py`; fixture `storage_dir` (Task 2).
- Produces: tool `"generate_report"` trong `TOOLS`, `sensitive=False`, input model `GenerateReportToolIn` (mọi field optional: `project_id`, `assignee_id`, `date_from`, `date_to`, `status`). Tool result = dict trả thẳng từ service (đã JSON-serializable) — FE đọc `report_id` từ tool_result trong message để hiện nút tải.

- [ ] **Step 1: Viết test fail**

Tạo `backend/tests/test_agent_tools_report.py`:

```python
import uuid

import pytest

from app.agent.tools import TOOLS, call_tool
from app.models import Project, Role, Task, TaskStatus, User, Workspace


async def _ceo(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    return ws, ceo


@pytest.mark.asyncio
async def test_generate_report_tool_success(db_session, storage_dir):
    ws, ceo = await _ceo(db_session)
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    db_session.add(Task(workspace_id=ws.id, project_id=project.id, title="T",
                        status=TaskStatus.done, created_by=ceo.id))
    await db_session.commit()

    result = await call_tool(db_session, ceo, "generate_report", {})
    assert "error" not in result
    assert result["row_count"] == 1
    assert result["summary"]["done"] == 1
    assert uuid.UUID(result["report_id"])  # id hợp lệ


@pytest.mark.asyncio
async def test_generate_report_tool_with_status_filter(db_session, storage_dir):
    ws, ceo = await _ceo(db_session)
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    db_session.add(Task(workspace_id=ws.id, project_id=project.id, title="T",
                        status=TaskStatus.todo, created_by=ceo.id))
    await db_session.commit()

    result = await call_tool(db_session, ceo, "generate_report", {"status": "done"})
    assert result["row_count"] == 0
    assert result["filters_applied"]["status"] == "done"


@pytest.mark.asyncio
async def test_generate_report_tool_forbidden_for_employee(db_session, storage_dir):
    ws, ceo = await _ceo(db_session)
    emp = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
              role=Role.employee)
    db_session.add(emp)
    await db_session.flush()
    result = await call_tool(db_session, emp, "generate_report", {})
    assert result == {"error": "forbidden", "message": "Bạn không có quyền làm điều này."}


@pytest.mark.asyncio
async def test_generate_report_tool_unknown_project_not_found(db_session, storage_dir):
    ws, ceo = await _ceo(db_session)
    result = await call_tool(db_session, ceo, "generate_report",
                             {"project_id": str(uuid.uuid4())})
    assert result["error"] == "not_found"


def test_generate_report_registered_as_22nd_tool_not_sensitive():
    assert "generate_report" in TOOLS
    assert TOOLS["generate_report"].sensitive is False
    assert len(TOOLS) == 22
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `pytest tests/test_agent_tools_report.py -v`
Expected: FAIL — `KeyError: 'generate_report'` (từ `call_tool`) và assert `"generate_report" in TOOLS` fail

- [ ] **Step 3: Đăng ký tool**

Trong `backend/app/agent/tools.py`:

Sửa dòng import datetime/models đầu file — thêm `date` và `TaskStatus`:

```python
from datetime import date
```

(đặt ngay sau `import uuid`), và đổi dòng import models thành:

```python
from app.models import Role, TaskStatus, User
```

Đổi dòng import services thành:

```python
from app.services import auth_service, report_service, skill_service, work_service
```

Thêm trước khối `SENSITIVE_TOOLS` (cuối file):

```python
class GenerateReportToolIn(BaseModel):
    project_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    status: TaskStatus | None = None


async def _generate_report(db, actor, body: GenerateReportToolIn) -> dict:
    return await report_service.generate_report(db, actor, **body.model_dump())


_register("generate_report",
          "Tạo báo cáo Excel tổng hợp task, filter tùy chọn theo project/người/khoảng "
          "thời gian/trạng thái (chỉ CEO). Trả về report_id + tóm tắt số liệu; "
          "file tải qua ứng dụng.", GenerateReportToolIn, _generate_report)
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `pytest tests/test_agent_tools_report.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Chạy toàn bộ suite (đề phòng test nào đó đếm tool)**

Run: `pytest tests/ -v`
Expected: tất cả PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/tools.py backend/tests/test_agent_tools_report.py
git commit -m "feat(be): agent tool generate_report (tool 22)"
```

---

### Task 4: REST `GET /api/v1/reports/{report_id}/download`

**Files:**
- Create: `backend/app/api/reports.py`
- Modify: `backend/app/main.py:3,30` (import + mount router)
- Test: `backend/tests/test_reports_api.py`

**Interfaces:**
- Consumes: `Report` model + `get_settings().storage_dir` (Task 1); `report_service.generate_report` (Task 2, dùng trong test để seed); `get_current_user` từ `app.deps`, `get_db` từ `app.db`; fixtures `client`, `db_session`, `storage_dir` + helpers `_ceo_headers`, `_invite_and_join` từ conftest.
- Produces: endpoint `GET /api/v1/reports/{report_id}/download` — 200 `FileResponse` xlsx attachment cho CEO cùng workspace; 404 mọi trường hợp khác (không tồn tại, khác workspace, không phải CEO, file mất).

- [ ] **Step 1: Viết test fail**

Tạo `backend/tests/test_reports_api.py`:

```python
import uuid

import pytest
from sqlalchemy import select

from app.models import User
from app.services import report_service
from tests.conftest import _ceo_headers, _invite_and_join

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _make_report(client, db_session):
    """Signup CEO qua API rồi tạo report qua service (cùng engine → cùng DB)."""
    headers = await _ceo_headers(client)
    ceo = (await db_session.execute(
        select(User).where(User.email == "ceo@a.vn"))).scalar_one()
    result = await report_service.generate_report(db_session, ceo)
    return headers, result["report_id"]


@pytest.mark.asyncio
async def test_ceo_downloads_xlsx(client, db_session, storage_dir):
    headers, report_id = await _make_report(client, db_session)
    resp = await client.get(f"/api/v1/reports/{report_id}/download", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == XLSX
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content[:2] == b"PK"  # magic bytes zip/xlsx


@pytest.mark.asyncio
async def test_non_ceo_gets_404(client, db_session, storage_dir):
    headers, report_id = await _make_report(client, db_session)
    emp = await _invite_and_join(client, headers, "employee", "e@a.vn")
    emp_headers = {"Authorization": f"Bearer {emp['access_token']}"}
    resp = await client.get(f"/api/v1/reports/{report_id}/download",
                            headers=emp_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unknown_report_404(client, storage_dir):
    headers = await _ceo_headers(client)
    resp = await client.get(f"/api/v1/reports/{uuid.uuid4()}/download", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_missing_file_on_disk_404(client, db_session, storage_dir):
    headers, report_id = await _make_report(client, db_session)
    for f in storage_dir.rglob("*.xlsx"):
        f.unlink()
    resp = await client.get(f"/api/v1/reports/{report_id}/download", headers=headers)
    assert resp.status_code == 404
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `pytest tests/test_reports_api.py -v`
Expected: FAIL — 404 route not found (endpoint chưa tồn tại) làm `test_ceo_downloads_xlsx` fail ở assert 200

- [ ] **Step 3: Viết router + mount**

Tạo `backend/app/api/reports.py`:

```python
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import Report, Role, User

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/{report_id}/download")
async def download_report(report_id: uuid.UUID,
                          actor: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    report = await db.get(Report, report_id)
    # 404 (không lộ tồn tại) cho cả: không có, khác workspace, không phải CEO
    if (report is None or report.workspace_id != actor.workspace_id
            or actor.role != Role.ceo):
        raise HTTPException(404, "report_not_found")
    path = Path(get_settings().storage_dir) / report.file_path
    if not path.is_file():
        raise HTTPException(404, "report_file_missing")
    return FileResponse(path, media_type=_XLSX,
                        filename=f"report-{report.id}.xlsx")
```

Trong `backend/app/main.py`, đổi dòng import api thành:

```python
from app.api import auth, chat, invites, projects, reports, skills, tasks, users, ws
```

và thêm sau `app.include_router(skills.router)`:

```python
    app.include_router(reports.router)
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `pytest tests/test_reports_api.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Chạy toàn bộ suite**

Run: `pytest tests/ -v`
Expected: tất cả PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/reports.py backend/app/main.py backend/tests/test_reports_api.py
git commit -m "feat(be): report download endpoint"
```

---

### Task 5: Hạ tầng — docker volume, gitignore, export OpenAPI contract

**Files:**
- Modify: `backend/docker-compose.yml` (volume `reports_data` + env `STORAGE_DIR` cho `api` và `worker`)
- Modify: `.gitignore` repo root (bỏ qua `backend/storage/`)
- Modify: `openapi.json` repo root (regen)

**Interfaces:**
- Consumes: `Settings.storage_dir` đọc env `STORAGE_DIR` tự động qua pydantic-settings (Task 1); route mới (Task 4).
- Produces: `api` và `worker` container cùng đọc/ghi `/data/reports`; `openapi.json` chứa `/api/v1/reports/{report_id}/download` cho FE.

- [ ] **Step 1: Sửa docker-compose.yml**

Thay toàn bộ `backend/docker-compose.yml` bằng:

```yaml
services:
  api:
    build: .
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql+asyncpg://app:app@postgres:5432/app
      JWT_SECRET: ${JWT_SECRET:-dev-secret}
      REDIS_URL: redis://redis:6379
      STORAGE_DIR: /data/reports
    volumes: ["reports_data:/data/reports"]
    depends_on: [postgres, redis]
  worker:
    build: .
    command: ["arq", "app.agent.worker.WorkerSettings"]
    environment:
      DATABASE_URL: postgresql+asyncpg://app:app@postgres:5432/app
      JWT_SECRET: ${JWT_SECRET:-dev-secret}
      REDIS_URL: redis://redis:6379
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
      STORAGE_DIR: /data/reports
    volumes: ["reports_data:/data/reports"]
    depends_on: [postgres, redis]
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: app
    volumes: ["pgdata:/var/lib/postgresql/data"]
    ports: ["5433:5432"]
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
volumes:
  pgdata:
  reports_data:
```

Run: `docker compose config --quiet`
Expected: không có output lỗi (YAML hợp lệ). Nếu docker không chạy trên máy, bỏ qua bước validate này.

- [ ] **Step 2: Gitignore thư mục storage dev**

Thêm dòng vào `.gitignore` ở repo root:

```
backend/storage/
```

- [ ] **Step 3: Export lại OpenAPI contract**

Run (trong `backend/`): `python scripts/export_openapi.py`
Expected: `Wrote d:\8. AI\ai-assistant\openapi.json`

Kiểm tra nhanh: `python -c "import json; spec=json.load(open('../openapi.json', encoding='utf-8')); assert '/api/v1/reports/{report_id}/download' in spec['paths']; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Chạy toàn bộ suite lần cuối**

Run: `pytest tests/ -v`
Expected: tất cả PASS

- [ ] **Step 5: Commit**

```bash
git add backend/docker-compose.yml .gitignore openapi.json
git commit -m "chore(be): reports volume + refresh openapi contract"
```

---

## Self-review (đã chạy khi viết plan)

- **Spec coverage:** §2 model → Task 1; §3 service+tool → Task 2, 3; §4 endpoint+storage → Task 1 (config), 4 (endpoint), 5 (volume); §5 bảng lỗi → test 403/404/empty ở Task 2-4, lỗi ghi file để nổi lên theo cơ chế Plan 3 (không code thêm — đúng spec); §6 testing → 3 file test đúng tên spec. Không có gap.
- **Placeholder scan:** không có TBD/"tương tự Task N"; mọi step code đều có code đầy đủ.
- **Type consistency:** `generate_report` signature ở Task 2 khớp cách gọi ở Task 3 (`**body.model_dump()` với đúng 5 key) và Task 4 test; `report.file_path` tương đối (`{ws_id}/{report_id}.xlsx`) nhất quán giữa service (ghi) và router (đọc, prepend `storage_dir`); fixture `storage_dir` khai báo Task 2, dùng Task 2/3/4.
