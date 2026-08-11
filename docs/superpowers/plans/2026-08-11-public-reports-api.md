# Public Reports API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho app mobile 9learning đọc report `published` từ backend `ai-assistant` qua header `X-App-Bundle-Id`, không cần đăng nhập, giới hạn vào 1 workspace cố định; đồng thời cho CEO quản trị (tạo/sửa/publish/xoá) report đó qua JWT bình thường.

**Architecture:** Model `PublicReport` mới, tách biệt hoàn toàn khỏi `Report`/`report_service.py` hiện có (khác bản chất: đây là nội dung CEO tự upload để công khai, không phải Excel tự sinh từ task). Một router `public_reports.py` gộp cả 2 nhóm endpoint (đọc qua bundle-id, ghi qua JWT+CEO), một service `public_report_service.py` chứa toàn bộ logic, một dependency mới `get_bundle_or_user` trong `deps.py`.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic — theo đúng pattern hiện có của `attachments.py`/`attachment_service.py` (lưu file local dưới `storage_dir`, tên file trên đĩa là uuid, không dùng tên gốc client gửi).

## Global Constraints

- Mọi bảng (trừ `workspaces`) có `workspace_id`; mọi query phải lọc theo workspace (CLAUDE.md).
- Quyền kiểm tra ở **service layer**, không bao giờ ở prompt/model (CLAUDE.md).
- Danh tính (`actor`) lấy từ JWT phiên đăng nhập — không bao giờ từ tham số client (CLAUDE.md).
- Route dưới `/api/v1`. Đổi API contract → chạy lại `python scripts/export_openapi.py` cho FE (CLAUDE.md).
- TDD: test trước, code sau; mỗi task một commit (CLAUDE.md).
- Không commit secrets; dùng `.env` (đã gitignore) (CLAUDE.md).
- Endpoint đọc qua bundle-id chỉ lộ report `status=published`; `draft` không bao giờ lộ qua kênh không-đăng-nhập (spec).
- `PUBLIC_REPORT_WORKSPACE_ID` là giá trị **cấu hình qua env**, không bao giờ do client truyền chọn workspace (spec).
- `PUBLIC_APP_BUNDLE_IDS` rỗng (mặc định) = tính năng tắt hoàn toàn — request qua bundle-id header phải 401 khi tắt (spec).
- Không thêm rate-limit hay secret riêng ngoài bundle-id; không hỗ trợ nhiều workspace qua bundle-id; không làm UI quản trị trên mobile app (spec, "Ngoài phạm vi").
- File path trên đĩa dùng uuid sinh mới, không dùng tên client gửi (theo pattern `attachment_service.py`).

---

## File Structure

- **Modify** `backend/app/models.py` — thêm enum `PublicReportStatus` + class `PublicReport`.
- **Modify** `backend/app/config.py` — thêm `public_app_bundle_ids: str = ""` và `public_report_workspace_id: str = ""`.
- **Modify** `backend/.env.example` — ghi chú 2 biến trên (comment, để trống mặc định = tắt).
- **Create** `backend/alembic/versions/<rev>_public_reports_table.py` — migration tạo bảng `public_reports`.
- **Modify** `backend/app/deps.py` — thêm `PublicReportScope` (dataclass) + dependency `get_bundle_or_user`.
- **Create** `backend/app/services/public_report_service.py` — toàn bộ logic đọc (list/get/content, lọc published+workspace cố định) và ghi (create/update/publish/unpublish/delete, CEO).
- **Modify** `backend/app/schemas.py` — thêm `PublicReportOut`, `CreatePublicReportIn`, `UpdatePublicReportIn`.
- **Create** `backend/app/api/public_reports.py` — router, đăng ký cả endpoint đọc (bundle-id/JWT) và ghi (CEO/JWT).
- **Modify** `backend/app/main.py` — `app.include_router(public_reports.router)`.
- **Create** `backend/tests/test_public_report_service.py` — unit test service layer.
- **Create** `backend/tests/test_public_reports_api.py` — integration test qua HTTP (bundle-id + JWT CEO).

---

## Task 1: Model `PublicReport` + migration

**Files:**
- Modify: `backend/app/models.py` (thêm cuối file, sau class `ReportSchedule` khoảng dòng 590+, xem vị trí thật bằng `grep -n "^class ReportSchedule" -A 20 app/models.py` trước khi chèn)
- Create: `backend/alembic/versions/<rev>_public_reports_table.py`
- Test: `backend/tests/test_public_report_service.py` (phần model, Task 1 chỉ cần bảng migrate được — test đầy đủ ở Task 3)

**Interfaces:**
- Produces: `PublicReportStatus` (enum: `draft`, `published`), `PublicReport` model với các cột: `id: uuid.UUID`, `workspace_id: uuid.UUID`, `title: str`, `description: str | None`, `status: PublicReportStatus`, `content_type: str`, `file_path: str`, `size_bytes: int`, `created_by: uuid.UUID`, `created_at: datetime`, `updated_at: datetime`.

- [ ] **Step 1: Xem vị trí chèn trong models.py**

Run: `grep -n "^class ReportSchedule" -A 25 backend/app/models.py`

Ghi lại dòng cuối cùng của `ReportSchedule` (kết thúc bằng `created_at`) để chèn class mới ngay sau đó.

- [ ] **Step 2: Thêm enum + model vào models.py**

Chèn ngay sau class `ReportSchedule` (giữ 2 dòng trống trước/sau theo style hiện có trong file):

```python
class PublicReportStatus(str, enum.Enum):
    draft = "draft"
    published = "published"


class PublicReport(Base):
    """Báo cáo công khai cho app mobile 9learning đọc qua bundle-id, không cần
    đăng nhập (funtional-plan §6.8, spec 2026-08-03-public-reports-api-design.md).
    Tách biệt hoàn toàn với Report/report_service.py — đó là Excel tự sinh từ
    task nội bộ, đây là nội dung CEO tự upload để công khai."""
    __tablename__ = "public_reports"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PublicReportStatus] = mapped_column(Enum(PublicReportStatus),
                                                        default=PublicReportStatus.draft)
    content_type: Mapped[str] = mapped_column(String(128))
    file_path: Mapped[str] = mapped_column(String(512))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now,
                                                  onupdate=_now)
```

Nếu `Text`, `Integer`, `String`, `Enum`, `DateTime`, `ForeignKey`, `Uuid`, `Mapped`, `mapped_column` chưa có trong import ở đầu `models.py`, kiểm tra bằng `grep -n "^from sqlalchemy" backend/app/models.py` — các model khác (`Attachment`, `Report`) đã dùng hết các kiểu này nên import sẵn có, không cần sửa thêm.

- [ ] **Step 3: Tạo migration**

Run (trong `backend/`, venv active):
```bash
alembic revision -m "public_reports_table"
```

Đổi `down_revision` thành head hiện tại (xác nhận lại bằng `alembic heads` — tại thời điểm viết plan này là `2fd8baf43c21`, nhưng Task 1 có thể chạy sau khi nhánh khác đã merge nên PHẢI check lại thực tế, không copy cứng giá trị này).

Sửa nội dung file migration vừa sinh thành:

```python
"""public_reports_table

Revision ID: <rev do alembic sinh>
Revises: <head thực tế lúc chạy>
Create Date: <do alembic sinh>

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '<rev do alembic sinh>'
down_revision: Union[str, Sequence[str], None] = '<head thực tế lúc chạy>'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'public_reports',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('draft', 'published', name='publicreportstatus'),
                  nullable=False),
        sa.Column('content_type', sa.String(length=128), nullable=False),
        sa.Column('file_path', sa.String(length=512), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_public_reports_workspace_id'), 'public_reports',
                    ['workspace_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_public_reports_workspace_id'), table_name='public_reports')
    op.drop_table('public_reports')
    sa.Enum(name='publicreportstatus').drop(op.get_bind(), checkfirst=True)
```

- [ ] **Step 4: Chạy migration lên DB dev và xác nhận**

Run:
```bash
alembic upgrade head
alembic current
```
Expected: `alembic current` in ra đúng revision vừa tạo, không lỗi.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/*public_reports_table*.py
git commit -m "feat(public-reports): model PublicReport + migration"
```

---

## Task 2: Config `PUBLIC_APP_BUNDLE_IDS` / `PUBLIC_REPORT_WORKSPACE_ID`

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`

**Interfaces:**
- Produces: `Settings.public_app_bundle_ids: str` (mặc định `""`, danh sách phân tách dấu phẩy), `Settings.public_report_workspace_id: str` (mặc định `""`, UUID dạng chuỗi).

- [ ] **Step 1: Thêm field vào `Settings`**

Trong `backend/app/config.py`, thêm 2 dòng vào cuối class `Settings` (ngay trước `model_config = {...}`):

```python
    # Public Reports API cho app mobile 9learning đọc qua bundle-id, không đăng
    # nhập (funtional-plan 6.8, spec 2026-08-03-public-reports-api-design.md).
    # Rỗng = tính năng tắt hoàn toàn.
    public_app_bundle_ids: str = ""
    public_report_workspace_id: str = ""
```

- [ ] **Step 2: Ghi chú vào `.env.example`**

Thêm vào cuối `backend/.env.example`:

```
# --- Public Reports API (app mobile 9learning đọc report không cần đăng nhập) ---
# Rỗng (mặc định) = tính năng tắt hoàn toàn.
# PUBLIC_APP_BUNDLE_IDS=com.9learning.app,com.9learning.app.dev
# PUBLIC_REPORT_WORKSPACE_ID=00000000-0000-0000-0000-000000000000
```

- [ ] **Step 3: Xác nhận app khởi động không lỗi với giá trị mặc định**

Run: `python -c "from app.config import get_settings; s = get_settings(); print(s.public_app_bundle_ids, repr(s.public_report_workspace_id))"`
Expected: in ra `` (rỗng) và `''`, không lỗi.

- [ ] **Step 4: Commit**

```bash
git add backend/app/config.py backend/.env.example
git commit -m "feat(public-reports): config PUBLIC_APP_BUNDLE_IDS/PUBLIC_REPORT_WORKSPACE_ID"
```

---

## Task 3: Dependency `get_bundle_or_user`

**Files:**
- Modify: `backend/app/deps.py`
- Test: `backend/tests/test_public_report_service.py` (phần dependency — tạo file mới ở đây, sẽ mở rộng thêm ở Task 4)

**Interfaces:**
- Consumes: `Settings.public_app_bundle_ids`, `Settings.public_report_workspace_id` (Task 2); `get_current_user` (đã có, `deps.py`).
- Produces: dataclass `PublicReportScope(workspace_id: uuid.UUID, user: User | None)`; dependency callable `get_bundle_or_user(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: AsyncSession = Depends(get_db)) -> PublicReportScope`. Task 4/5 dùng `scope.workspace_id` để lọc query, `scope.user` chỉ khác `None` khi vào qua JWT (không dùng ở endpoint đọc nhưng để sẵn cho endpoint ghi tái dùng path chung nếu cần).

- [ ] **Step 1: Viết test cho dependency (qua service/router sẽ dựng ở bước sau — test dependency trực tiếp bằng cách gọi hàm)**

Tạo `backend/tests/test_public_report_service.py`:

```python
import uuid

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.deps import get_bundle_or_user


def _request(headers: dict) -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {"type": "http", "headers": raw_headers}
    return Request(scope)


@pytest.mark.asyncio
async def test_bundle_id_matches_allowlist_returns_fixed_workspace(monkeypatch, db_session):
    from app.config import get_settings
    ws_id = uuid.uuid4()
    monkeypatch.setattr(get_settings(), "public_app_bundle_ids", "com.9learning.app")
    monkeypatch.setattr(get_settings(), "public_report_workspace_id", str(ws_id))

    scope = await get_bundle_or_user(
        request=_request({"x-app-bundle-id": "com.9learning.app"}),
        creds=None, db=db_session)
    assert scope.workspace_id == ws_id
    assert scope.user is None


@pytest.mark.asyncio
async def test_bundle_id_not_in_allowlist_and_no_token_401(monkeypatch, db_session):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "public_app_bundle_ids", "com.9learning.app")
    monkeypatch.setattr(get_settings(), "public_report_workspace_id", str(uuid.uuid4()))

    with pytest.raises(HTTPException) as exc:
        await get_bundle_or_user(
            request=_request({"x-app-bundle-id": "com.other.app"}),
            creds=None, db=db_session)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_feature_disabled_when_allowlist_empty(monkeypatch, db_session):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "public_app_bundle_ids", "")
    monkeypatch.setattr(get_settings(), "public_report_workspace_id", "")

    with pytest.raises(HTTPException) as exc:
        await get_bundle_or_user(
            request=_request({"x-app-bundle-id": "com.9learning.app"}),
            creds=None, db=db_session)
    assert exc.value.status_code == 401
```

Kiểm tra `backend/tests/conftest.py` có fixture `db_session` chưa: `grep -n "def db_session" backend/tests/conftest.py`. Nếu KHÔNG có, dùng fixture `engine` có sẵn (xem cách `client` fixture dùng `async_sessionmaker(engine, ...)` ở `conftest.py:37-39`) để tự tạo session trong test thay vì giả định `db_session` tồn tại — sửa 3 test trên, thay tham số `db_session` bằng `engine` và mở session:
```python
    from sqlalchemy.ext.asyncio import async_sessionmaker
    async with async_sessionmaker(engine, expire_on_commit=False)() as db_session:
        ...  # gọi get_bundle_or_user(..., db=db_session) trong block này
```

- [ ] **Step 2: Chạy test, xác nhận fail vì `get_bundle_or_user` chưa tồn tại**

Run: `pytest tests/test_public_report_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_bundle_or_user'`

- [ ] **Step 3: Implement trong `deps.py`**

Thêm vào cuối `backend/app/deps.py`:

```python
import dataclasses

from fastapi import Request

from app.config import get_settings


@dataclasses.dataclass
class PublicReportScope:
    workspace_id: uuid.UUID
    user: User | None


async def get_bundle_or_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> PublicReportScope:
    settings = get_settings()
    bundle_id = request.headers.get("x-app-bundle-id")
    allowlist = {b.strip() for b in settings.public_app_bundle_ids.split(",") if b.strip()}
    if bundle_id and bundle_id in allowlist and settings.public_report_workspace_id:
        return PublicReportScope(
            workspace_id=uuid.UUID(settings.public_report_workspace_id), user=None)
    if creds is not None:
        user = await get_current_user(creds=creds, db=db)
        return PublicReportScope(workspace_id=user.workspace_id, user=user)
    raise HTTPException(401, "missing_token")
```

Lưu ý: `import dataclasses`, `Request` từ `fastapi`, và `get_settings` phải đặt ở đầu file cùng các import khác (không để rải giữa file) — di chuyển các dòng `import`/`from` lên đầu `deps.py` theo đúng vị trí quy ước Python, chỉ giữ định nghĩa `PublicReportScope`/`get_bundle_or_user` ở cuối.

- [ ] **Step 4: Chạy lại test, xác nhận pass**

Run: `pytest tests/test_public_report_service.py -v`
Expected: PASS (3 test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/deps.py backend/tests/test_public_report_service.py
git commit -m "feat(public-reports): dependency get_bundle_or_user"
```

---

## Task 4: Service `public_report_service.py` — đọc (list/get/content)

**Files:**
- Create: `backend/app/services/public_report_service.py`
- Test: `backend/tests/test_public_report_service.py` (mở rộng file Task 3)

**Interfaces:**
- Consumes: `PublicReport`, `PublicReportStatus` (Task 1); `PublicReportScope` (Task 3); `get_settings().storage_dir` (pattern giống `attachment_service._attachment_dir`).
- Produces: `async def list_published(db: AsyncSession, workspace_id: uuid.UUID) -> list[dict]`, `async def get_published(db: AsyncSession, workspace_id: uuid.UUID, report_id: uuid.UUID) -> dict` (raise `HTTPException(404, "public_report_not_found")` nếu không tồn tại/khác workspace/không published), `async def get_content_path(db: AsyncSession, workspace_id: uuid.UUID, report_id: uuid.UUID) -> tuple[Path, str]` (trả `(path, content_type)`, cùng điều kiện 404 như trên).

- [ ] **Step 1: Viết test cho list/get/content (thêm vào cuối `test_public_report_service.py`)**

```python
import datetime as dt

from app.models import PublicReport, PublicReportStatus


async def _make_report(db_session, workspace_id, status, *, file_bytes=b"hello",
                       content_type="text/plain"):
    from pathlib import Path
    import uuid as uuidlib
    from app.config import get_settings
    d = Path(get_settings().storage_dir) / "public_reports" / str(workspace_id)
    d.mkdir(parents=True, exist_ok=True)
    fp = d / f"{uuidlib.uuid4()}.txt"
    fp.write_bytes(file_bytes)
    report = PublicReport(workspace_id=workspace_id, title="R1", status=status,
                          content_type=content_type, file_path=str(fp),
                          size_bytes=len(file_bytes), created_by=uuidlib.uuid4())
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    return report


@pytest.mark.asyncio
async def test_list_published_excludes_draft(engine, storage_dir):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services import public_report_service
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ws = uuid.uuid4()
        await _make_report(db, ws, PublicReportStatus.published)
        await _make_report(db, ws, PublicReportStatus.draft)
        result = await public_report_service.list_published(db, ws)
        assert len(result) == 1


@pytest.mark.asyncio
async def test_list_published_excludes_other_workspace(engine, storage_dir):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services import public_report_service
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ws1, ws2 = uuid.uuid4(), uuid.uuid4()
        await _make_report(db, ws1, PublicReportStatus.published)
        result = await public_report_service.list_published(db, ws2)
        assert result == []


@pytest.mark.asyncio
async def test_get_published_404_on_draft(engine, storage_dir):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from fastapi import HTTPException
    from app.services import public_report_service
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ws = uuid.uuid4()
        report = await _make_report(db, ws, PublicReportStatus.draft)
        with pytest.raises(HTTPException) as exc:
            await public_report_service.get_published(db, ws, report.id)
        assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_content_path_returns_file(engine, storage_dir):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services import public_report_service
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ws = uuid.uuid4()
        report = await _make_report(db, ws, PublicReportStatus.published,
                                    file_bytes=b"content-x", content_type="text/plain")
        path, content_type = await public_report_service.get_content_path(db, ws, report.id)
        assert path.read_bytes() == b"content-x"
        assert content_type == "text/plain"
```

Cần thêm `import uuid` và `import pytest` nếu chưa có ở đầu file (đã có từ Task 3, kiểm tra trước khi thêm trùng). Fixture `engine` và `storage_dir` đã có sẵn trong `conftest.py` (dùng chung với `attachment_service`/`attachments_api` test).

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `pytest tests/test_public_report_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.public_report_service'`

- [ ] **Step 3: Implement `public_report_service.py`**

```python
"""Public Reports API (funtional-plan §6.8, spec 2026-08-03-public-reports-api-design.md).

Đọc: qua bundle-id (không đăng nhập), chỉ report status=published, giới hạn 1
workspace cố định (PUBLIC_REPORT_WORKSPACE_ID). Ghi: CEO qua JWT bình thường.
Tách biệt hoàn toàn với Report/report_service.py (Excel tự sinh từ task nội bộ).
"""
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import PublicReport, PublicReportStatus, User
from app.permissions import require_ceo

_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB, giống attachment_service


def _dir(workspace_id: uuid.UUID) -> Path:
    d = Path(get_settings().storage_dir) / "public_reports" / str(workspace_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _out(r: PublicReport) -> dict:
    return {"id": str(r.id), "title": r.title, "description": r.description,
            "status": r.status.value, "content_type": r.content_type,
            "size_bytes": r.size_bytes, "created_at": r.created_at,
            "updated_at": r.updated_at}


async def list_published(db: AsyncSession, workspace_id: uuid.UUID) -> list[dict]:
    rows = await db.execute(
        select(PublicReport).where(PublicReport.workspace_id == workspace_id,
                                   PublicReport.status == PublicReportStatus.published)
        .order_by(PublicReport.created_at.desc()))
    return [_out(r) for r in rows.scalars()]


async def _get_published_row(db: AsyncSession, workspace_id: uuid.UUID,
                             report_id: uuid.UUID) -> PublicReport:
    report = await db.get(PublicReport, report_id)
    if (report is None or report.workspace_id != workspace_id
            or report.status != PublicReportStatus.published):
        raise HTTPException(404, "public_report_not_found")
    return report


async def get_published(db: AsyncSession, workspace_id: uuid.UUID,
                        report_id: uuid.UUID) -> dict:
    report = await _get_published_row(db, workspace_id, report_id)
    return _out(report)


async def get_content_path(db: AsyncSession, workspace_id: uuid.UUID,
                           report_id: uuid.UUID) -> tuple[Path, str]:
    report = await _get_published_row(db, workspace_id, report_id)
    path = Path(report.file_path)
    if not path.is_file():
        raise HTTPException(404, "public_report_file_missing")
    return path, report.content_type
```

- [ ] **Step 4: Chạy lại test, xác nhận pass**

Run: `pytest tests/test_public_report_service.py -v`
Expected: PASS (7 test tổng)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/public_report_service.py backend/tests/test_public_report_service.py
git commit -m "feat(public-reports): service list/get/content published-only"
```

---

## Task 5: Service — ghi (create/update/publish/unpublish/delete, CEO)

**Files:**
- Modify: `backend/app/services/public_report_service.py`
- Test: `backend/tests/test_public_report_service.py`

**Interfaces:**
- Consumes: `require_ceo` (đã có, `permissions.py`); mọi hàm nhận `actor: User`.
- Produces: `async def create(db, actor: User, *, title: str, description: str | None, filename: str, content_type: str, data: bytes) -> dict`, `async def update_metadata(db, actor: User, report_id: uuid.UUID, *, title: str | None, description: str | None) -> dict`, `async def set_status(db, actor: User, report_id: uuid.UUID, status: PublicReportStatus) -> dict`, `async def delete(db, actor: User, report_id: uuid.UUID) -> None`. Mỗi hàm raise `HTTPException(404, "public_report_not_found")` nếu report không tồn tại/khác workspace của `actor`; `require_ceo(actor)` raise `403` nếu không phải CEO.

- [ ] **Step 1: Viết test (thêm vào cuối file test)**

```python
from app.models import Role


def _ceo_user(workspace_id):
    from app.models import User, UserStatus
    return User(id=uuid.uuid4(), workspace_id=workspace_id, email="ceo@x.vn",
               full_name="CEO", role=Role.ceo, status=UserStatus.active,
               password_hash="x", is_root=True)


def _manager_user(workspace_id):
    from app.models import User, UserStatus
    return User(id=uuid.uuid4(), workspace_id=workspace_id, email="m@x.vn",
               full_name="M", role=Role.manager, status=UserStatus.active,
               password_hash="x")


@pytest.mark.asyncio
async def test_create_defaults_to_draft(engine, storage_dir):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services import public_report_service
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ws = uuid.uuid4()
        ceo = _ceo_user(ws)
        out = await public_report_service.create(
            db, ceo, title="Q3 revenue", description=None, filename="q3.pdf",
            content_type="application/pdf", data=b"%PDF-x")
        assert out["status"] == "draft"


@pytest.mark.asyncio
async def test_create_rejects_non_ceo(engine, storage_dir):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from fastapi import HTTPException
    from app.services import public_report_service
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ws = uuid.uuid4()
        manager = _manager_user(ws)
        with pytest.raises(HTTPException) as exc:
            await public_report_service.create(
                db, manager, title="X", description=None, filename="a.pdf",
                content_type="application/pdf", data=b"x")
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_publish_then_unpublish(engine, storage_dir):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services import public_report_service
    from app.models import PublicReportStatus
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ws = uuid.uuid4()
        ceo = _ceo_user(ws)
        created = await public_report_service.create(
            db, ceo, title="X", description=None, filename="a.pdf",
            content_type="application/pdf", data=b"x")
        rid = uuid.UUID(created["id"])

        published = await public_report_service.set_status(
            db, ceo, rid, PublicReportStatus.published)
        assert published["status"] == "published"
        visible = await public_report_service.list_published(db, ws)
        assert len(visible) == 1

        unpublished = await public_report_service.set_status(
            db, ceo, rid, PublicReportStatus.draft)
        assert unpublished["status"] == "draft"
        visible_after = await public_report_service.list_published(db, ws)
        assert visible_after == []


@pytest.mark.asyncio
async def test_delete_removes_report(engine, storage_dir):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services import public_report_service
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ws = uuid.uuid4()
        ceo = _ceo_user(ws)
        created = await public_report_service.create(
            db, ceo, title="X", description=None, filename="a.pdf",
            content_type="application/pdf", data=b"x")
        rid = uuid.UUID(created["id"])
        await public_report_service.delete(db, ceo, rid)
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            await public_report_service.update_metadata(db, ceo, rid, title="Y",
                                                         description=None)


@pytest.mark.asyncio
async def test_cross_workspace_write_404(engine, storage_dir):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services import public_report_service
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ws1, ws2 = uuid.uuid4(), uuid.uuid4()
        ceo1 = _ceo_user(ws1)
        ceo2 = _ceo_user(ws2)
        created = await public_report_service.create(
            db, ceo1, title="X", description=None, filename="a.pdf",
            content_type="application/pdf", data=b"x")
        rid = uuid.UUID(created["id"])
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await public_report_service.update_metadata(db, ceo2, rid, title="Y",
                                                         description=None)
        assert exc.value.status_code == 404
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `pytest tests/test_public_report_service.py -v`
Expected: FAIL — `AttributeError: module 'app.services.public_report_service' has no attribute 'create'`

- [ ] **Step 3: Implement — thêm vào cuối `public_report_service.py`**

```python
async def create(db: AsyncSession, actor: User, *, title: str, description: str | None,
                 filename: str, content_type: str, data: bytes) -> dict:
    require_ceo(actor)
    if len(data) > _MAX_FILE_SIZE:
        raise HTTPException(422, "file_too_large")
    file_path = _dir(actor.workspace_id) / f"{uuid.uuid4()}{Path(filename or '').suffix}"
    file_path.write_bytes(data)
    report = PublicReport(workspace_id=actor.workspace_id, title=title,
                          description=description, status=PublicReportStatus.draft,
                          content_type=content_type, file_path=str(file_path),
                          size_bytes=len(data), created_by=actor.id)
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return _out(report)


async def _get_own_row(db: AsyncSession, actor: User, report_id: uuid.UUID) -> PublicReport:
    require_ceo(actor)
    report = await db.get(PublicReport, report_id)
    if report is None or report.workspace_id != actor.workspace_id:
        raise HTTPException(404, "public_report_not_found")
    return report


async def update_metadata(db: AsyncSession, actor: User, report_id: uuid.UUID, *,
                          title: str | None, description: str | None) -> dict:
    report = await _get_own_row(db, actor, report_id)
    if title is not None:
        report.title = title
    if description is not None:
        report.description = description
    await db.commit()
    await db.refresh(report)
    return _out(report)


async def set_status(db: AsyncSession, actor: User, report_id: uuid.UUID,
                     status: PublicReportStatus) -> dict:
    report = await _get_own_row(db, actor, report_id)
    report.status = status
    await db.commit()
    await db.refresh(report)
    return _out(report)


async def delete(db: AsyncSession, actor: User, report_id: uuid.UUID) -> None:
    report = await _get_own_row(db, actor, report_id)
    path = Path(report.file_path)
    if path.is_file():
        path.unlink()
    await db.delete(report)
    await db.commit()
```

- [ ] **Step 4: Chạy lại test, xác nhận pass**

Run: `pytest tests/test_public_report_service.py -v`
Expected: PASS (toàn bộ test trong file)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/public_report_service.py backend/tests/test_public_report_service.py
git commit -m "feat(public-reports): service create/update/publish/delete (CEO)"
```

---

## Task 6: Schemas Pydantic

**Files:**
- Modify: `backend/app/schemas.py`

**Interfaces:**
- Produces: `PublicReportOut(BaseModel)`, `UpdatePublicReportIn(BaseModel)`.

- [ ] **Step 1: Thêm vào `schemas.py`**

Thêm import `PublicReportStatus` vào dòng import model đầu file (`from app.models import (... , PublicReportStatus, ...)` — giữ thứ tự alphabet như các tên khác trong tuple đó).

Thêm cuối file:

```python
class PublicReportOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    status: PublicReportStatus
    content_type: str
    size_bytes: int
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = {"from_attributes": True}


class UpdatePublicReportIn(BaseModel):
    title: str | None = None
    description: str | None = None
```

Router dùng `response_model=PublicReportOut` nhưng service trả `dict` với `status` là `str` (`.value`) — FastAPI/Pydantic tự coerce chuỗi khớp giá trị enum về `PublicReportStatus` khi validate response, không cần đổi service.

- [ ] **Step 2: Xác nhận import không lỗi**

Run: `python -c "from app.schemas import PublicReportOut, UpdatePublicReportIn; print('ok')"`
Expected: in `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas.py
git commit -m "feat(public-reports): schemas PublicReportOut/UpdatePublicReportIn"
```

---

## Task 7: Router `public_reports.py` + đăng ký vào `main.py`

**Files:**
- Create: `backend/app/api/public_reports.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_public_reports_api.py`

**Interfaces:**
- Consumes: `get_bundle_or_user` (Task 3), `get_current_user` (đã có), `public_report_service.*` (Task 4/5), `PublicReportOut`/`UpdatePublicReportIn` (Task 6).
- Produces: router mount tại `/api/v1/public-reports` với các route liệt kê dưới đây — đây là contract API cuối cùng, FE/app 9learning gọi đúng các path này.

- [ ] **Step 1: Viết test API (file mới, mẫu lấy theo `tests/test_attachments_api.py`)**

```python
import uuid

import pytest

from tests.conftest import _ceo_headers


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


async def _ceo_with_headers(client):
    resp_headers = await _ceo_headers(client)
    me = await client.get("/api/v1/users/me", headers=resp_headers)
    return resp_headers, me.json()


@pytest.mark.asyncio
async def test_ceo_crud_and_publish_flow(client, storage_dir, monkeypatch):
    ceo_h, me = await _ceo_with_headers(client)
    ws_id = me["workspace_id"]

    r = await client.post("/api/v1/public-reports", headers=ceo_h,
                          data={"title": "Q3", "description": "desc"},
                          files={"file": ("q3.pdf", b"%PDF-x", "application/pdf")})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert r.json()["status"] == "draft"

    upd = await client.patch(f"/api/v1/public-reports/{rid}", headers=ceo_h,
                             json={"title": "Q3 updated"})
    assert upd.status_code == 200
    assert upd.json()["title"] == "Q3 updated"

    pub = await client.post(f"/api/v1/public-reports/{rid}/publish", headers=ceo_h)
    assert pub.status_code == 200
    assert pub.json()["status"] == "published"

    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "public_app_bundle_ids", "com.9learning.app")
    monkeypatch.setattr(get_settings(), "public_report_workspace_id", ws_id)

    listed = await client.get("/api/v1/public-reports",
                              headers={"X-App-Bundle-Id": "com.9learning.app"})
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    detail = await client.get(f"/api/v1/public-reports/{rid}",
                              headers={"X-App-Bundle-Id": "com.9learning.app"})
    assert detail.status_code == 200

    content = await client.get(f"/api/v1/public-reports/{rid}/content",
                               headers={"X-App-Bundle-Id": "com.9learning.app"})
    assert content.status_code == 200
    assert content.content == b"%PDF-x"

    unpub = await client.post(f"/api/v1/public-reports/{rid}/unpublish", headers=ceo_h)
    assert unpub.json()["status"] == "draft"
    listed_after = await client.get("/api/v1/public-reports",
                                    headers={"X-App-Bundle-Id": "com.9learning.app"})
    assert listed_after.json() == []

    dele = await client.delete(f"/api/v1/public-reports/{rid}", headers=ceo_h)
    assert dele.status_code == 204


@pytest.mark.asyncio
async def test_bundle_id_disabled_by_default_401(client, storage_dir):
    r = await client.get("/api/v1/public-reports",
                         headers={"X-App-Bundle-Id": "com.9learning.app"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_non_ceo_cannot_write(client, storage_dir):
    from tests.conftest import _invite_and_join
    ceo_h, me = await _ceo_with_headers(client)
    manager = await _invite_and_join(client, ceo_h, "manager", "m@a.vn")
    m_h = _h(manager)
    r = await client.post("/api/v1/public-reports", headers=m_h,
                          data={"title": "X"},
                          files={"file": ("a.pdf", b"x", "application/pdf")})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_bundle_id_never_leaks_draft(client, storage_dir, monkeypatch):
    ceo_h, me = await _ceo_with_headers(client)
    ws_id = me["workspace_id"]
    r = await client.post("/api/v1/public-reports", headers=ceo_h,
                          data={"title": "Draft only"},
                          files={"file": ("d.pdf", b"x", "application/pdf")})
    rid = r.json()["id"]

    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "public_app_bundle_ids", "com.9learning.app")
    monkeypatch.setattr(get_settings(), "public_report_workspace_id", ws_id)

    detail = await client.get(f"/api/v1/public-reports/{rid}",
                              headers={"X-App-Bundle-Id": "com.9learning.app"})
    assert detail.status_code == 404
```

Kiểm tra route thật của "current user" trước khi dùng: `grep -n "\"/api/v1/users/me\"\|'/api/v1/users/me'" backend/app/api/users.py`. Nếu route trả `workspace_id` khác tên field hoặc không tồn tại, thay `_ceo_with_headers` bằng cách lấy `workspace_id` từ JWT decode trực tiếp (`app.security.decode_access_token`) hoặc từ response `signup-workspace` nếu nó đã chứa `workspace_id` — kiểm tra bằng `grep -n "workspace_id" backend/app/api/auth.py` để xác nhận field thật trước khi viết test.

- [ ] **Step 2: Chạy test, xác nhận fail (module chưa tồn tại)**

Run: `pytest tests/test_public_reports_api.py -v`
Expected: FAIL — router chưa mount, 404 Not Found trên mọi request (hoặc `ModuleNotFoundError` nếu import trực tiếp router trong test — ở đây test chỉ gọi qua `client` nên sẽ là 404 thay vì exception).

- [ ] **Step 3: Implement router**

Create `backend/app/api/public_reports.py`:

```python
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import PublicReportScope, get_bundle_or_user, get_current_user
from app.models import PublicReportStatus, User
from app.schemas import PublicReportOut, UpdatePublicReportIn
from app.services import public_report_service

router = APIRouter(prefix="/api/v1/public-reports", tags=["public-reports"])


# --- Đọc: bundle-id (không đăng nhập) hoặc JWT --------------------------

@router.get("", response_model=list[PublicReportOut])
async def list_public_reports(scope: PublicReportScope = Depends(get_bundle_or_user),
                              db: AsyncSession = Depends(get_db)):
    return await public_report_service.list_published(db, scope.workspace_id)


@router.get("/{report_id}", response_model=PublicReportOut)
async def get_public_report(report_id: uuid.UUID,
                            scope: PublicReportScope = Depends(get_bundle_or_user),
                            db: AsyncSession = Depends(get_db)):
    return await public_report_service.get_published(db, scope.workspace_id, report_id)


@router.get("/{report_id}/content")
async def get_public_report_content(report_id: uuid.UUID,
                                    scope: PublicReportScope = Depends(get_bundle_or_user),
                                    db: AsyncSession = Depends(get_db)):
    path, content_type = await public_report_service.get_content_path(
        db, scope.workspace_id, report_id)
    return FileResponse(path, media_type=content_type, headers={
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


# --- Ghi: CEO qua JWT ----------------------------------------------------

@router.post("", response_model=PublicReportOut, status_code=201)
async def create_public_report(title: str = Form(...), description: str | None = Form(None),
                               file: UploadFile = File(...),
                               actor: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    data = await file.read()
    return await public_report_service.create(
        db, actor, title=title, description=description,
        filename=file.filename or "", content_type=file.content_type or "application/octet-stream",
        data=data)


@router.patch("/{report_id}", response_model=PublicReportOut)
async def update_public_report(report_id: uuid.UUID, body: UpdatePublicReportIn,
                               actor: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    return await public_report_service.update_metadata(
        db, actor, report_id, title=body.title, description=body.description)


@router.post("/{report_id}/publish", response_model=PublicReportOut)
async def publish_public_report(report_id: uuid.UUID,
                                actor: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    return await public_report_service.set_status(
        db, actor, report_id, PublicReportStatus.published)


@router.post("/{report_id}/unpublish", response_model=PublicReportOut)
async def unpublish_public_report(report_id: uuid.UUID,
                                  actor: User = Depends(get_current_user),
                                  db: AsyncSession = Depends(get_db)):
    return await public_report_service.set_status(
        db, actor, report_id, PublicReportStatus.draft)


@router.delete("/{report_id}", status_code=204)
async def delete_public_report(report_id: uuid.UUID,
                               actor: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    await public_report_service.delete(db, actor, report_id)
```

Lưu ý thứ tự route: `GET /{report_id}` và `POST ""`/`GET ""` không đụng độ path, nhưng đảm bảo route cụ thể hơn (`/{report_id}/content`, `/{report_id}/publish`) khai báo — FastAPI so path theo khai báo tĩnh trước động nên thứ tự ở trên không gây xung đột (không có 2 route cùng pattern tổng quát).

- [ ] **Step 4: Đăng ký router vào `main.py`**

Trong `backend/app/main.py`, thêm import và `include_router` theo đúng vị trí các router khác (gần `reports.router`):

```python
from app.api import public_reports  # thêm cùng nhóm import app.api.* hiện có
```

```python
    app.include_router(public_reports.router)
```

- [ ] **Step 5: Chạy lại test, xác nhận pass**

Run: `pytest tests/test_public_reports_api.py -v`
Expected: PASS (toàn bộ test trong file)

- [ ] **Step 6: Export lại OpenAPI contract**

Run (trong `backend/`): `python scripts/export_openapi.py`
Expected: `openapi.json` ở repo root được cập nhật, không lỗi.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/public_reports.py backend/app/main.py backend/tests/test_public_reports_api.py openapi.json
git commit -m "feat(public-reports): router + mount + openapi export"
```

---

## Task 8: Full suite + rà soát cuối

**Files:** không tạo/sửa file mới — chạy toàn bộ test suite hiện có để xác nhận không phá gì.

- [ ] **Step 1: Chạy toàn bộ test suite backend**

Run (trong `backend/`): `pytest tests/ -v`
Expected: tất cả PASS, không có test nào từ trước bị fail do thay đổi `models.py`/`deps.py`/`schemas.py`/`main.py`.

- [ ] **Step 2: Nếu có fail, sửa và re-run tới khi xanh hết**

(Không thêm bước cụ thể — nội dung fix phụ thuộc lỗi thực tế xuất hiện.)

- [ ] **Step 3: Commit nếu có sửa**

```bash
git add -A
git commit -m "fix(public-reports): full suite green"
```

---

## Spec Coverage Checklist (tự rà soát khi viết plan)

- Model `PublicReport` + enum → Task 1. ✅
- Config `PUBLIC_APP_BUNDLE_IDS`/`PUBLIC_REPORT_WORKSPACE_ID` → Task 2. ✅
- Dependency `get_bundle_or_user`, 401 khi tắt/không khớp → Task 3. ✅
- Service đọc (list/get/content), chỉ published, đúng workspace cố định → Task 4. ✅
- Service ghi (create/update/publish/unpublish/delete), CEO-only → Task 5. ✅
- Schemas Pydantic → Task 6. ✅
- Router `/api/v1/public-reports` (đọc không đăng nhập + ghi CEO), mount vào `main.py`, export OpenAPI → Task 7. ✅
- Test: bundle-id hợp lệ/không hợp lệ, tắt hoàn toàn khi env rỗng, không lộ draft, không lộ workspace khác, CEO CRUD, JWT vẫn hoạt động song song → rải trong Task 3/4/5/7, tổng hợp full suite ở Task 8. ✅
- "Ngoài phạm vi" (không rate-limit/secret riêng, không multi-workspace qua bundle-id, không UI mobile) → không có task nào vi phạm; không tạo thêm gì ngoài spec. ✅
