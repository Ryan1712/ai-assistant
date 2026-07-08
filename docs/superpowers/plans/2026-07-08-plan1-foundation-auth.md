# Plan 1 — Nền tảng & Auth (MVP Backend)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng backend FastAPI chạy được với multi-tenant workspace, đăng ký qua invite, JWT + log thiết bị, khóa tài khoản, permission layer — nền cho Plan 2 (domain) và Plan 3 (chat agent).

**Architecture:** Monolith FastAPI async + Postgres (SQLAlchemy 2.0 async, mọi bảng có `workspace_id`), auth JWT 2 lớp (access 15' + refresh xoay vòng lưu DB), quyền kiểm tra ở service layer. Test bằng pytest + httpx với SQLite in-memory.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, asyncpg (prod) / aiosqlite (test), PyJWT, bcrypt, pydantic-settings, pytest + pytest-asyncio + httpx.

## Global Constraints

- Mọi bảng (trừ `workspaces`) có cột `workspace_id` NOT NULL, FK về `workspaces.id`.
- Mọi route nằm dưới prefix `/api/v1`.
- Access token TTL **15 phút**; refresh token TTL **30 ngày**, xoay vòng (dùng 1 lần).
- Vai trò: `ceo` / `manager` / `employee`. Người tạo workspace là **CEO gốc** (`is_root=True`) — không ai khóa được; chỉ CEO gốc khóa/mở được tài khoản vai trò `ceo`.
- Danh tính luôn lấy từ JWT của phiên — không bao giờ từ tham số client tự khai.
- Chạy lệnh trong thư mục `backend/`. Windows PowerShell: kích hoạt venv bằng `.venv\Scripts\activate`.

---

## Cấu trúc file (đích đến của plan này)

```
backend/
  requirements.txt
  .env.example
  docker-compose.yml
  scripts/export_openapi.py
  app/
    __init__.py
    main.py              # app factory, mount routers
    config.py            # Settings (pydantic-settings)
    db.py                # engine, session, Base, get_db
    models.py            # toàn bộ ORM models của plan này
    schemas.py           # Pydantic request/response
    security.py          # bcrypt + JWT
    permissions.py       # role & hierarchy checks
    deps.py              # get_current_user, require_roles
    services/
      __init__.py
      auth_service.py    # signup/login/refresh/lock logic
    api/
      __init__.py
      auth.py            # /auth/*
      invites.py         # /invites
      users.py           # /users/*
  tests/
    conftest.py
    test_health.py
    test_security.py
    test_auth.py
    test_invites.py
    test_permissions.py
    test_lock.py
```

---

### Task 1: Scaffold + health endpoint + test harness + repo hygiene

**Files:**
- Create: `backend/requirements.txt`, `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/main.py`, `backend/tests/conftest.py`, `backend/tests/test_health.py`, `backend/.env.example`
- Create (repo root): `.gitignore`, `CLAUDE.md`, `.github/workflows/ci.yml`

**Interfaces:**
- Produces: `create_app() -> FastAPI` trong `app/main.py`; `Settings` trong `app/config.py` (fields: `database_url: str`, `jwt_secret: str`, `access_ttl_minutes: int = 15`, `refresh_ttl_days: int = 30`); fixture pytest `client` (httpx AsyncClient).

- [ ] **Step 1: Tạo venv + requirements**

`backend/requirements.txt`:
```
fastapi==0.115.*
uvicorn[standard]==0.30.*
sqlalchemy[asyncio]==2.0.*
asyncpg==0.29.*
aiosqlite==0.20.*
pydantic-settings==2.*
PyJWT==2.*
bcrypt==4.*
pytest==8.*
pytest-asyncio==0.24.*
httpx==0.27.*
```

Run:
```powershell
cd backend; python -m venv .venv; .venv\Scripts\activate; pip install -r requirements.txt
```
Expected: cài đặt thành công, không lỗi.

- [ ] **Step 2: Viết test fail cho /health**

`backend/tests/test_health.py`:
```python
import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

`backend/tests/conftest.py`:
```python
import pytest
import httpx

from app.main import create_app


@pytest.fixture
async def client():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

Thêm vào `backend/pytest.ini` (tạo mới):
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

Run: `pytest tests/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app'` hoặc `create_app` chưa tồn tại.

- [ ] **Step 3: Implement config + app factory**

`backend/app/__init__.py`: (file rỗng)

`backend/app/config.py`:
```python
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///:memory:"
    jwt_secret: str = "dev-secret-change-me"
    access_ttl_minutes: int = 15
    refresh_ttl_days: int = 30

    model_config = {"env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`backend/app/main.py`:
```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="AI Assistant API", version="0.1.0", docs_url="/docs")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
```

`backend/.env.example`:
```
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app
JWT_SECRET=change-me-in-prod
```

- [ ] **Step 4: Run test → PASS**

Run: `pytest tests/test_health.py -v`
Expected: PASS.

- [ ] **Step 5: Repo hygiene — .gitignore + CLAUDE.md + CI**

`.gitignore` (repo root):
```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
.env
*.sqlite3
```

`CLAUDE.md` (repo root):
```markdown
# AI Assistant — Trợ lý AI Quản lý Công việc (SaaS)

App mobile chat-first: CEO/manager/nhân viên điều hành công việc bằng cách nhắn cho AI.
Đội 2 dev: BE (Python, kiêm AI/LLM) + FE (React Native/Expo).

## Tài liệu nguồn (đọc trước khi làm việc lớn)
- Spec chức năng: `funtional-plan.md` (tên file cố ý giữ nguyên, đừng "sửa chính tả")
- Thiết kế BE: `docs/superpowers/specs/2026-07-08-backend-architecture-design.md`
- Plans: `docs/superpowers/plans/`

## Lệnh thường dùng (chạy trong `backend/`)
- Kích hoạt venv (Windows): `.venv\Scripts\activate`
- Test: `pytest tests/ -v`
- Chạy dev: `uvicorn app.main:app --reload` → Swagger tại http://localhost:8000/docs
- Hạ tầng local: `docker compose up -d postgres redis`
- Migration: `alembic revision --autogenerate -m "..."` rồi `alembic upgrade head`
- Export contract cho FE: `python scripts/export_openapi.py` (ghi `openapi.json` ở repo root)

## Quy ước bất di bất dịch
- Mọi bảng (trừ `workspaces`) có `workspace_id`; mọi query phải lọc theo workspace.
- Quyền kiểm tra ở **service layer** (`app/permissions.py`), không bao giờ ở prompt/model.
- Danh tính (`actor`) lấy từ JWT phiên đăng nhập — không bao giờ từ tham số client hay model.
- Model LLM lấy từ config theo loại tác vụ — không hardcode model ID.
- Route dưới `/api/v1`. Đổi API contract = chạy lại export_openapi cho FE.
- TDD: test trước, code sau; mỗi task một commit.
- Không commit secrets; dùng `.env` (đã gitignore).

## Bài học (bổ sung khi Claude/dev làm sai điều gì đáng nhớ)
- (trống)
```

`.github/workflows/ci.yml`:
```yaml
name: CI
on:
  push:
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: pytest tests/ -v
```

Run: `git add .gitignore CLAUDE.md .github/` rồi kiểm tra `git status` không còn `.venv/` hay `.env` trong danh sách theo dõi.
Expected: chỉ các file nguồn được stage.

- [ ] **Step 6: Commit**

```bash
git add backend/ .gitignore CLAUDE.md .github/
git commit -m "feat(be): scaffold FastAPI app + test harness + repo hygiene (CLAUDE.md, CI)"
```

---

### Task 2: DB layer + models multi-tenant

**Files:**
- Create: `backend/app/db.py`, `backend/app/models.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_models.py` (tạo mới)

**Interfaces:**
- Produces: `Base`, `get_db()` (async dependency) trong `app/db.py`. Models: `Workspace(id, name)`, `User(id, workspace_id, email, password_hash, full_name, role, manager_id, is_root, status)`, `Device(id, workspace_id, user_id, device_uuid, device_name, last_login_at)`, `LoginEvent(id, workspace_id, user_id, device_uuid, device_name, created_at)`, `Invite(id, workspace_id, token, role, manager_id, created_by, expires_at, used_at)`, `RefreshToken(id, workspace_id, user_id, token_hash, expires_at, revoked_at)`, `Notification(id, workspace_id, recipient_id, type, payload, read_at, created_at)`. Enum: `Role` (`ceo|manager|employee`), `UserStatus` (`active|locked`).
- Consumes: `Settings` (Task 1).

- [ ] **Step 1: Viết test fail**

`backend/tests/test_models.py`:
```python
import pytest
from sqlalchemy import select

from app.models import Workspace, User, Role, UserStatus


@pytest.mark.asyncio
async def test_create_workspace_and_root_ceo(db_session):
    ws = Workspace(name="Cong ty A")
    db_session.add(ws)
    await db_session.flush()

    user = User(
        workspace_id=ws.id, email="ceo@a.vn", password_hash="x",
        full_name="Sep", role=Role.ceo, is_root=True,
    )
    db_session.add(user)
    await db_session.commit()

    found = (await db_session.execute(select(User).where(User.email == "ceo@a.vn"))).scalar_one()
    assert found.workspace_id == ws.id
    assert found.status == UserStatus.active
    assert found.is_root is True
```

Thêm fixtures DB vào `backend/tests/conftest.py` (thay toàn bộ nội dung):
```python
import pytest
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db import Base, get_db
from app.main import create_app


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_session(engine):
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest.fixture
async def client(engine):
    app = create_app()
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

Run: `pytest tests/test_models.py -v` → Expected: FAIL (chưa có `app.db` / `app.models`).

- [ ] **Step 2: Implement db.py + models.py**

`backend/app/db.py`:
```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_maker = None


def get_engine():
    global _engine, _maker
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url)
        _maker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def get_db():
    get_engine()
    async with _maker() as session:
        yield session
```

`backend/app/models.py`:
```python
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, ForeignKey, DateTime, Enum, JSON, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    ceo = "ceo"
    manager = "manager"
    employee = "employee"


class UserStatus(str, enum.Enum):
    active = "active"
    locked = "locked"


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role))
    manager_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_root: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus), default=UserStatus.active)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    device_uuid: Mapped[str] = mapped_column(String(64))
    device_name: Mapped[str] = mapped_column(String(255), default="")
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LoginEvent(Base):
    __tablename__ = "login_events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    device_uuid: Mapped[str] = mapped_column(String(64))
    device_name: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Invite(Base):
    __tablename__ = "invites"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    role: Mapped[Role] = mapped_column(Enum(Role))
    manager_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
```

- [ ] **Step 3: Run → PASS**

Run: `pytest tests/ -v` → Expected: PASS cả test_health + test_models.

- [ ] **Step 4: Commit**

```bash
git add backend/
git commit -m "feat(be): db layer + multi-tenant models (workspace/user/device/invite/refresh/notification)"
```

---

### Task 3: Security core — bcrypt + JWT

**Files:**
- Create: `backend/app/security.py`
- Test: `backend/tests/test_security.py`

**Interfaces:**
- Produces: `hash_password(p: str) -> str`; `verify_password(p: str, h: str) -> bool`; `create_access_token(*, user_id: str, workspace_id: str, role: str) -> str`; `decode_access_token(token: str) -> dict` (raise `jwt.InvalidTokenError` nếu sai/hết hạn; payload có keys `sub`, `ws`, `role`, `exp`); `new_refresh_token() -> tuple[str, str]` (trả `(token_plain, token_sha256_hex)`).

- [ ] **Step 1: Viết test fail**

`backend/tests/test_security.py`:
```python
import jwt
import pytest

from app import security


def test_password_hash_roundtrip():
    h = security.hash_password("s3cret")
    assert h != "s3cret"
    assert security.verify_password("s3cret", h)
    assert not security.verify_password("wrong", h)


def test_jwt_roundtrip():
    token = security.create_access_token(user_id="u1", workspace_id="w1", role="ceo")
    payload = security.decode_access_token(token)
    assert payload["sub"] == "u1"
    assert payload["ws"] == "w1"
    assert payload["role"] == "ceo"


def test_jwt_tampered_rejected():
    token = security.create_access_token(user_id="u1", workspace_id="w1", role="ceo")
    with pytest.raises(jwt.InvalidTokenError):
        security.decode_access_token(token + "x")


def test_refresh_token_pair():
    plain, hashed = security.new_refresh_token()
    assert len(plain) >= 32
    assert hashed != plain and len(hashed) == 64  # sha256 hex
```

Run: `pytest tests/test_security.py -v` → FAIL (`app.security` chưa có).

- [ ] **Step 2: Implement**

`backend/app/security.py`:
```python
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode(), h.encode())
    except ValueError:
        return False


def create_access_token(*, user_id: str, workspace_id: str, role: str) -> str:
    s = get_settings()
    payload = {
        "sub": user_id,
        "ws": workspace_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=s.access_ttl_minutes),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])


def new_refresh_token() -> tuple[str, str]:
    plain = secrets.token_urlsafe(32)
    return plain, hashlib.sha256(plain.encode()).hexdigest()


def hash_refresh_token(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()
```

- [ ] **Step 3: Run → PASS**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): security core - bcrypt password + JWT access + refresh token helpers"
```

---

### Task 4: Signup workspace (CEO gốc) + Login (kèm log thiết bị)

**Files:**
- Create: `backend/app/schemas.py`, `backend/app/services/__init__.py`, `backend/app/services/auth_service.py`, `backend/app/api/__init__.py`, `backend/app/api/auth.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Consumes: models (Task 2), security (Task 3).
- Produces:
  - `POST /api/v1/auth/signup-workspace` body `{workspace_name, email, password, full_name, device_uuid, device_name}` → 201 `{access_token, refresh_token, user: {id, email, full_name, role, is_root}}`
  - `POST /api/v1/auth/login` body `{email, password, device_uuid, device_name}` → 200 cùng shape; 401 nếu sai; 403 `{"detail": "account_locked"}` nếu `status=locked`.
  - Service: `auth_service.signup_workspace(db, ...) -> tuple[User, str, str]`, `auth_service.login(db, ...) -> tuple[User, str, str]` (user, access, refresh). Mỗi login upsert `Device` (theo user_id + device_uuid) và ghi `LoginEvent`.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_auth.py`:
```python
import pytest
from sqlalchemy import select

from app.models import Device, LoginEvent

SIGNUP = {
    "workspace_name": "Cong ty A", "email": "ceo@a.vn", "password": "secret123",
    "full_name": "Sep", "device_uuid": "dev-1", "device_name": "iPhone Sep",
}


@pytest.mark.asyncio
async def test_signup_workspace_creates_root_ceo(client):
    resp = await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    assert resp.status_code == 201
    data = resp.json()
    assert data["user"]["role"] == "ceo"
    assert data["user"]["is_root"] is True
    assert data["access_token"] and data["refresh_token"]


@pytest.mark.asyncio
async def test_login_ok_and_logs_device(client, db_session):
    await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    resp = await client.post("/api/v1/auth/login", json={
        "email": "ceo@a.vn", "password": "secret123",
        "device_uuid": "dev-2", "device_name": "iPad",
    })
    assert resp.status_code == 200
    devices = (await db_session.execute(select(Device))).scalars().all()
    assert {d.device_uuid for d in devices} == {"dev-1", "dev-2"}
    events = (await db_session.execute(select(LoginEvent))).scalars().all()
    assert len(events) == 2  # signup cũng tính là 1 lần đăng nhập


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    resp = await client.post("/api/v1/auth/login", json={
        "email": "ceo@a.vn", "password": "WRONG", "device_uuid": "d", "device_name": "",
    })
    assert resp.status_code == 401
```

Run: `pytest tests/test_auth.py -v` → FAIL (404 vì route chưa có).

- [ ] **Step 2: Implement schemas + service + router**

`backend/app/schemas.py`:
```python
import uuid

from pydantic import BaseModel, EmailStr


class SignupWorkspaceIn(BaseModel):
    workspace_name: str
    email: EmailStr
    password: str
    full_name: str
    device_uuid: str
    device_name: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    device_uuid: str
    device_name: str = ""


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_root: bool

    model_config = {"from_attributes": True}


class AuthOut(BaseModel):
    access_token: str
    refresh_token: str
    user: UserOut
```

(Lưu ý: `EmailStr` cần `pip install email-validator` — thêm dòng `email-validator==2.*` vào `requirements.txt` và cài.)

`backend/app/services/__init__.py`: (rỗng)

`backend/app/services/auth_service.py`:
```python
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.config import get_settings
from app.models import (
    Device, LoginEvent, RefreshToken, Role, User, UserStatus, Workspace,
)


async def _issue_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    access = security.create_access_token(
        user_id=str(user.id), workspace_id=str(user.workspace_id), role=user.role.value,
    )
    plain, hashed = security.new_refresh_token()
    db.add(RefreshToken(
        workspace_id=user.workspace_id, user_id=user.id, token_hash=hashed,
        expires_at=datetime.now(timezone.utc) + timedelta(days=get_settings().refresh_ttl_days),
    ))
    return access, plain


async def _log_device(db: AsyncSession, user: User, device_uuid: str, device_name: str) -> None:
    now = datetime.now(timezone.utc)
    device = (await db.execute(
        select(Device).where(Device.user_id == user.id, Device.device_uuid == device_uuid)
    )).scalar_one_or_none()
    if device:
        device.device_name = device_name or device.device_name
        device.last_login_at = now
    else:
        db.add(Device(
            workspace_id=user.workspace_id, user_id=user.id,
            device_uuid=device_uuid, device_name=device_name, last_login_at=now,
        ))
    db.add(LoginEvent(
        workspace_id=user.workspace_id, user_id=user.id,
        device_uuid=device_uuid, device_name=device_name,
    ))


async def signup_workspace(
    db: AsyncSession, *, workspace_name: str, email: str, password: str,
    full_name: str, device_uuid: str, device_name: str,
) -> tuple[User, str, str]:
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "email_taken")
    ws = Workspace(name=workspace_name)
    db.add(ws)
    await db.flush()
    user = User(
        workspace_id=ws.id, email=email, password_hash=security.hash_password(password),
        full_name=full_name, role=Role.ceo, is_root=True,
    )
    db.add(user)
    await db.flush()
    await _log_device(db, user, device_uuid, device_name)
    access, refresh = await _issue_tokens(db, user)
    await db.commit()
    return user, access, refresh


async def login(
    db: AsyncSession, *, email: str, password: str, device_uuid: str, device_name: str,
) -> tuple[User, str, str]:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if not user or not security.verify_password(password, user.password_hash):
        raise HTTPException(401, "invalid_credentials")
    if user.status == UserStatus.locked:
        raise HTTPException(403, "account_locked")
    await _log_device(db, user, device_uuid, device_name)
    access, refresh = await _issue_tokens(db, user)
    await db.commit()
    return user, access, refresh
```

`backend/app/api/__init__.py`: (rỗng)

`backend/app/api/auth.py`:
```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import AuthOut, LoginIn, SignupWorkspaceIn
from app.services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/signup-workspace", response_model=AuthOut, status_code=201)
async def signup_workspace(body: SignupWorkspaceIn, db: AsyncSession = Depends(get_db)):
    user, access, refresh = await auth_service.signup_workspace(db, **body.model_dump())
    return AuthOut(access_token=access, refresh_token=refresh, user=user)


@router.post("/login", response_model=AuthOut)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    user, access, refresh = await auth_service.login(db, **body.model_dump())
    return AuthOut(access_token=access, refresh_token=refresh, user=user)
```

Sửa `backend/app/main.py` — mount router:
```python
from fastapi import FastAPI

from app.api import auth


def create_app() -> FastAPI:
    app = FastAPI(title="AI Assistant API", version="0.1.0", docs_url="/docs")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    app.include_router(auth.router)
    return app


app = create_app()
```

- [ ] **Step 3: Run → PASS**

Run: `pytest tests/ -v` → Expected: PASS toàn bộ.

- [ ] **Step 4: Commit**

```bash
git add backend/
git commit -m "feat(be): signup workspace (root CEO) + login with device logging"
```

---

### Task 5: get_current_user + refresh rotation + logout

**Files:**
- Create: `backend/app/deps.py`
- Modify: `backend/app/api/auth.py`, `backend/app/schemas.py`
- Test: thêm vào `backend/tests/test_auth.py`

**Interfaces:**
- Produces:
  - Dependency `get_current_user(db, authorization: str) -> User` — đọc header `Authorization: Bearer <access>`, decode JWT, load User; 401 nếu token sai/hết hạn; **403 `account_locked` nếu user.status=locked** (chặn ngay cả khi access token còn hạn).
  - `POST /api/v1/auth/refresh` body `{refresh_token}` → 200 `{access_token, refresh_token}` (xoay vòng: token cũ bị revoke, dùng lại token cũ → 401).
  - `POST /api/v1/auth/logout` body `{refresh_token}` → 204, revoke token đó.
  - `GET /api/v1/users/me` → UserOut (đặt tạm trong auth.py, chuyển sang users.py ở Task 7).

- [ ] **Step 1: Viết test fail** (thêm vào cuối `test_auth.py`)

```python
async def _signup(client):
    resp = await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    return resp.json()


@pytest.mark.asyncio
async def test_me_requires_valid_token(client):
    data = await _signup(client)
    ok = await client.get("/api/v1/users/me",
                          headers={"Authorization": f"Bearer {data['access_token']}"})
    assert ok.status_code == 200
    assert ok.json()["email"] == "ceo@a.vn"
    bad = await client.get("/api/v1/users/me", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotation(client):
    data = await _signup(client)
    old = data["refresh_token"]
    r1 = await client.post("/api/v1/auth/refresh", json={"refresh_token": old})
    assert r1.status_code == 200
    assert r1.json()["refresh_token"] != old
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": old})
    assert r2.status_code == 401  # token cũ đã bị revoke


@pytest.mark.asyncio
async def test_logout_revokes(client):
    data = await _signup(client)
    resp = await client.post("/api/v1/auth/logout", json={"refresh_token": data["refresh_token"]})
    assert resp.status_code == 204
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert r.status_code == 401
```

Run → FAIL.

- [ ] **Step 2: Implement**

Thêm vào `backend/app/schemas.py`:
```python
class RefreshIn(BaseModel):
    refresh_token: str


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str
```

`backend/app/deps.py`:
```python
import uuid

import jwt as pyjwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.db import get_db
from app.models import User, UserStatus


async def get_current_user(
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing_token")
    try:
        payload = security.decode_access_token(authorization.removeprefix("Bearer "))
    except pyjwt.InvalidTokenError:
        raise HTTPException(401, "invalid_token")
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise HTTPException(401, "user_not_found")
    if user.status == UserStatus.locked:
        raise HTTPException(403, "account_locked")
    return user
```

Thêm vào `backend/app/services/auth_service.py`:
```python
async def rotate_refresh(db: AsyncSession, refresh_plain: str) -> tuple[User, str, str]:
    now = datetime.now(timezone.utc)
    hashed = security.hash_refresh_token(refresh_plain)
    row = (await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hashed)
    )).scalar_one_or_none()
    if row is None or row.revoked_at is not None or row.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(401, "invalid_refresh_token")
    user = await db.get(User, row.user_id)
    if user is None or user.status == UserStatus.locked:
        raise HTTPException(403, "account_locked")
    row.revoked_at = now
    access, new_refresh = await _issue_tokens(db, user)
    await db.commit()
    return user, access, new_refresh


async def revoke_refresh(db: AsyncSession, refresh_plain: str) -> None:
    hashed = security.hash_refresh_token(refresh_plain)
    row = (await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hashed)
    )).scalar_one_or_none()
    if row and row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        await db.commit()
```

Thêm route vào `backend/app/api/auth.py`:
```python
from fastapi import Response

from app.deps import get_current_user
from app.models import User
from app.schemas import RefreshIn, TokenPairOut, UserOut


@router.post("/refresh", response_model=TokenPairOut)
async def refresh(body: RefreshIn, db: AsyncSession = Depends(get_db)):
    _, access, new_refresh = await auth_service.rotate_refresh(db, body.refresh_token)
    return TokenPairOut(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=204)
async def logout(body: RefreshIn, db: AsyncSession = Depends(get_db)):
    await auth_service.revoke_refresh(db, body.refresh_token)
    return Response(status_code=204)


me_router = APIRouter(prefix="/api/v1/users", tags=["users"])


@me_router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
```

Trong `main.py` mount thêm: `app.include_router(auth.me_router)`.

- [ ] **Step 3: Run → PASS**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): current-user dependency + refresh token rotation + logout"
```

---

### Task 6: Invites — CEO mời, đăng ký qua invite

**Files:**
- Create: `backend/app/api/invites.py`
- Modify: `backend/app/schemas.py`, `backend/app/services/auth_service.py`, `backend/app/main.py`
- Test: `backend/tests/test_invites.py`

**Interfaces:**
- Produces:
  - `POST /api/v1/invites` (auth, chỉ `role=ceo`) body `{role, manager_id?}` → 201 `{token, expires_at}`. Rule: `role=employee` bắt buộc có `manager_id` trỏ tới user role `manager` cùng workspace → 422 nếu thiếu/sai. Invite hết hạn sau 7 ngày.
  - `POST /api/v1/auth/signup-invite` (public) body `{token, email, password, full_name, device_uuid, device_name}` → 201 AuthOut. Token sai/hết hạn/đã dùng → 400 `invalid_invite`. User mới vào đúng workspace, đúng role + manager của invite; invite đánh dấu `used_at`.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_invites.py`:
```python
import pytest

SIGNUP = {
    "workspace_name": "Cong ty A", "email": "ceo@a.vn", "password": "secret123",
    "full_name": "Sep", "device_uuid": "dev-1", "device_name": "",
}


async def _ceo_headers(client):
    resp = await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _invite_and_join(client, headers, role, email, manager_id=None):
    inv = await client.post("/api/v1/invites", headers=headers,
                            json={"role": role, "manager_id": manager_id})
    assert inv.status_code == 201, inv.text
    join = await client.post("/api/v1/auth/signup-invite", json={
        "token": inv.json()["token"], "email": email, "password": "pw123456",
        "full_name": email, "device_uuid": "d-" + email, "device_name": "",
    })
    assert join.status_code == 201, join.text
    return join.json()


@pytest.mark.asyncio
async def test_full_invite_flow(client):
    headers = await _ceo_headers(client)
    mgr = await _invite_and_join(client, headers, "manager", "m1@a.vn")
    emp = await _invite_and_join(client, headers, "employee", "e1@a.vn",
                                 manager_id=mgr["user"]["id"])
    assert emp["user"]["role"] == "employee"


@pytest.mark.asyncio
async def test_employee_invite_requires_manager(client):
    headers = await _ceo_headers(client)
    resp = await client.post("/api/v1/invites", headers=headers,
                             json={"role": "employee", "manager_id": None})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invite_single_use(client):
    headers = await _ceo_headers(client)
    inv = await client.post("/api/v1/invites", headers=headers,
                            json={"role": "manager", "manager_id": None})
    token = inv.json()["token"]
    body = {"token": token, "email": "m2@a.vn", "password": "pw123456",
            "full_name": "M2", "device_uuid": "d", "device_name": ""}
    assert (await client.post("/api/v1/auth/signup-invite", json=body)).status_code == 201
    body["email"] = "m3@a.vn"
    assert (await client.post("/api/v1/auth/signup-invite", json=body)).status_code == 400


@pytest.mark.asyncio
async def test_non_ceo_cannot_invite(client):
    headers = await _ceo_headers(client)
    mgr = await _invite_and_join(client, headers, "manager", "m1@a.vn")
    mgr_headers = {"Authorization": f"Bearer {mgr['access_token']}"}
    resp = await client.post("/api/v1/invites", headers=mgr_headers,
                             json={"role": "employee", "manager_id": None})
    assert resp.status_code == 403
```

Run → FAIL.

- [ ] **Step 2: Implement**

Thêm vào `backend/app/schemas.py`:
```python
import datetime as dt


class InviteCreateIn(BaseModel):
    role: str  # "ceo" | "manager" | "employee"
    manager_id: uuid.UUID | None = None


class InviteOut(BaseModel):
    token: str
    expires_at: dt.datetime


class SignupInviteIn(BaseModel):
    token: str
    email: EmailStr
    password: str
    full_name: str
    device_uuid: str
    device_name: str = ""
```

Thêm vào `backend/app/services/auth_service.py`:
```python
import secrets

from app.models import Invite


async def create_invite(
    db: AsyncSession, *, actor: User, role: str, manager_id=None,
) -> Invite:
    if actor.role != Role.ceo:
        raise HTTPException(403, "forbidden")
    role_enum = Role(role)
    if role_enum == Role.employee:
        manager = await db.get(User, manager_id) if manager_id else None
        if not manager or manager.role != Role.manager or manager.workspace_id != actor.workspace_id:
            raise HTTPException(422, "employee_invite_requires_manager")
    invite = Invite(
        workspace_id=actor.workspace_id, token=secrets.token_urlsafe(24),
        role=role_enum, manager_id=manager_id, created_by=actor.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invite)
    await db.commit()
    return invite


async def signup_invite(
    db: AsyncSession, *, token: str, email: str, password: str,
    full_name: str, device_uuid: str, device_name: str,
) -> tuple[User, str, str]:
    now = datetime.now(timezone.utc)
    invite = (await db.execute(select(Invite).where(Invite.token == token))).scalar_one_or_none()
    if (invite is None or invite.used_at is not None
            or invite.expires_at.replace(tzinfo=timezone.utc) < now):
        raise HTTPException(400, "invalid_invite")
    if (await db.execute(select(User).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(409, "email_taken")
    user = User(
        workspace_id=invite.workspace_id, email=email,
        password_hash=security.hash_password(password), full_name=full_name,
        role=invite.role, manager_id=invite.manager_id,
    )
    db.add(user)
    await db.flush()
    invite.used_at = now
    await _log_device(db, user, device_uuid, device_name)
    access, refresh = await _issue_tokens(db, user)
    await db.commit()
    return user, access, refresh
```

`backend/app/api/invites.py`:
```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import InviteCreateIn, InviteOut
from app.services import auth_service

router = APIRouter(prefix="/api/v1/invites", tags=["invites"])


@router.post("", response_model=InviteOut, status_code=201)
async def create_invite(
    body: InviteCreateIn,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    invite = await auth_service.create_invite(
        db, actor=actor, role=body.role, manager_id=body.manager_id,
    )
    return invite
```

Thêm route public vào `backend/app/api/auth.py`:
```python
from app.schemas import SignupInviteIn


@router.post("/signup-invite", response_model=AuthOut, status_code=201)
async def signup_invite(body: SignupInviteIn, db: AsyncSession = Depends(get_db)):
    user, access, refresh = await auth_service.signup_invite(db, **body.model_dump())
    return AuthOut(access_token=access, refresh_token=refresh, user=user)
```

Trong `main.py` mount thêm: `app.include_router(invites.router)` (import `from app.api import auth, invites`).

- [ ] **Step 3: Run → PASS**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): invite flow - CEO invites with role+manager, single-use signup"
```

---

### Task 7: Permission layer + danh sách user theo quyền

**Files:**
- Create: `backend/app/permissions.py`, `backend/app/api/users.py`
- Modify: `backend/app/main.py` (mount users router; chuyển `/users/me` từ auth.py sang users.py)
- Test: `backend/tests/test_permissions.py`

**Interfaces:**
- Produces:
  - `permissions.visible_user_ids(db, actor) -> list[uuid.UUID]`: CEO → mọi user trong workspace; manager → chính mình + nhân viên có `manager_id == actor.id`; employee → chỉ chính mình.
  - `permissions.require_ceo(actor)` / `require_root_ceo(actor)`: raise `HTTPException(403)` nếu sai role. **Đây là hàm mà Plan 2/3 sẽ tái dùng trong mọi service** — quyền nằm ở service layer, không nằm ở prompt.
  - `GET /api/v1/users` (auth) → danh sách UserOut theo `visible_user_ids`.
  - `GET /api/v1/users/{user_id}/devices` (auth, chỉ CEO) → `[{device_uuid, device_name, last_login_at}]`.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_permissions.py`:
```python
import pytest

from tests.test_invites import SIGNUP, _ceo_headers, _invite_and_join


async def _team(client):
    """CEO + 2 manager + 2 employee (mỗi manager 1 nhân viên)."""
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    m2 = await _invite_and_join(client, ceo_h, "manager", "m2@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    e2 = await _invite_and_join(client, ceo_h, "employee", "e2@a.vn", m2["user"]["id"])
    def h(x): return {"Authorization": f"Bearer {x['access_token']}"}
    return ceo_h, h(m1), h(e1), h(e2)


@pytest.mark.asyncio
async def test_visibility_matrix(client):
    ceo_h, m1_h, e1_h, _ = await _team(client)

    all_users = (await client.get("/api/v1/users", headers=ceo_h)).json()
    assert len(all_users) == 5  # CEO thấy tất cả

    m1_sees = {u["email"] for u in (await client.get("/api/v1/users", headers=m1_h)).json()}
    assert m1_sees == {"m1@a.vn", "e1@a.vn"}  # manager: mình + nhân viên dưới quyền

    e1_sees = {u["email"] for u in (await client.get("/api/v1/users", headers=e1_h)).json()}
    assert e1_sees == {"e1@a.vn"}  # employee: chỉ mình


@pytest.mark.asyncio
async def test_devices_ceo_only(client):
    ceo_h, m1_h, _, _ = await _team(client)
    users = (await client.get("/api/v1/users", headers=ceo_h)).json()
    target = next(u for u in users if u["email"] == "m1@a.vn")

    ok = await client.get(f"/api/v1/users/{target['id']}/devices", headers=ceo_h)
    assert ok.status_code == 200 and len(ok.json()) >= 1

    denied = await client.get(f"/api/v1/users/{target['id']}/devices", headers=m1_h)
    assert denied.status_code == 403
```

Run → FAIL.

- [ ] **Step 2: Implement**

`backend/app/permissions.py`:
```python
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Role, User


def require_ceo(actor: User) -> None:
    if actor.role != Role.ceo:
        raise HTTPException(403, "forbidden")


def require_root_ceo(actor: User) -> None:
    if not actor.is_root:
        raise HTTPException(403, "forbidden")


async def visible_user_ids(db: AsyncSession, actor: User) -> list[uuid.UUID]:
    if actor.role == Role.ceo:
        rows = await db.execute(
            select(User.id).where(User.workspace_id == actor.workspace_id)
        )
        return list(rows.scalars())
    if actor.role == Role.manager:
        rows = await db.execute(
            select(User.id).where(
                User.workspace_id == actor.workspace_id,
                User.manager_id == actor.id,
            )
        )
        return [actor.id, *rows.scalars()]
    return [actor.id]
```

`backend/app/api/users.py`:
```python
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import permissions
from app.db import get_db
from app.deps import get_current_user
from app.models import Device, User
from app.schemas import DeviceOut, UserOut

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@router.get("", response_model=list[UserOut])
async def list_users(
    actor: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    ids = await permissions.visible_user_ids(db, actor)
    rows = await db.execute(select(User).where(User.id.in_(ids)))
    return list(rows.scalars())


@router.get("/{user_id}/devices", response_model=list[DeviceOut])
async def list_devices(
    user_id: uuid.UUID,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    permissions.require_ceo(actor)
    rows = await db.execute(select(Device).where(
        Device.user_id == user_id, Device.workspace_id == actor.workspace_id,
    ))
    return list(rows.scalars())
```

Thêm vào `backend/app/schemas.py`:
```python
class DeviceOut(BaseModel):
    device_uuid: str
    device_name: str
    last_login_at: dt.datetime

    model_config = {"from_attributes": True}
```

Trong `backend/app/api/auth.py`: **xóa** `me_router` và route `/users/me` (đã chuyển sang users.py). Trong `main.py`: `from app.api import auth, invites, users` và mount `users.router` (bỏ `auth.me_router`).

- [ ] **Step 3: Run toàn bộ → PASS** (`pytest tests/ -v`), rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): permission layer (role + hierarchy) + user listing + device log view"
```

---

### Task 8: Khóa / mở khóa tài khoản + yêu cầu mở khóa

**Files:**
- Modify: `backend/app/api/users.py`, `backend/app/api/auth.py`, `backend/app/services/auth_service.py`
- Test: `backend/tests/test_lock.py`

**Interfaces:**
- Produces:
  - `POST /api/v1/users/{user_id}/lock` (CEO) → 204. Rules: khóa user role `ceo` yêu cầu actor `is_root`; **không ai khóa được CEO gốc** (403 kể cả root tự khóa mình). Khóa = `status=locked` + revoke toàn bộ refresh token của user + ghi `Notification(type="account_locked")` cho user bị khóa.
  - `POST /api/v1/users/{user_id}/unlock` (CEO, cùng rule role) → 204, `status=active`.
  - `POST /api/v1/auth/unlock-request` (public) body `{email, device_uuid}` → 202 luôn (không lộ email tồn tại hay không); nếu email tồn tại và đang khóa → tạo `Notification(type="unlock_request")` cho **CEO gốc** của workspace đó.
  - Service: `auth_service.lock_user(db, actor, target_id)`, `unlock_user(...)`, `request_unlock(db, email, device_uuid)`.

- [ ] **Step 1: Viết test fail**

`backend/tests/test_lock.py`:
```python
import pytest
from sqlalchemy import select

from app.models import Notification, User
from tests.test_invites import SIGNUP, _ceo_headers, _invite_and_join


@pytest.mark.asyncio
async def test_lock_kicks_user_out(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    uid = m1["user"]["id"]

    assert (await client.post(f"/api/v1/users/{uid}/lock", headers=ceo_h)).status_code == 204

    # refresh token bị thu hồi
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": m1["refresh_token"]})
    assert r.status_code in (401, 403)
    # access token còn hạn cũng bị chặn
    me = await client.get("/api/v1/users/me",
                          headers={"Authorization": f"Bearer {m1['access_token']}"})
    assert me.status_code == 403
    # không đăng nhập lại được
    login = await client.post("/api/v1/auth/login", json={
        "email": "m1@a.vn", "password": "pw123456", "device_uuid": "d", "device_name": "",
    })
    assert login.status_code == 403


@pytest.mark.asyncio
async def test_unlock_restores_access(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    uid = m1["user"]["id"]
    await client.post(f"/api/v1/users/{uid}/lock", headers=ceo_h)
    assert (await client.post(f"/api/v1/users/{uid}/unlock", headers=ceo_h)).status_code == 204
    login = await client.post("/api/v1/auth/login", json={
        "email": "m1@a.vn", "password": "pw123456", "device_uuid": "d", "device_name": "",
    })
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_root_ceo_cannot_be_locked(client, db_session):
    ceo_h = await _ceo_headers(client)
    root = (await db_session.execute(select(User).where(User.is_root))).scalar_one()
    resp = await client.post(f"/api/v1/users/{root.id}/lock", headers=ceo_h)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_manager_cannot_lock(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    m2 = await _invite_and_join(client, ceo_h, "manager", "m2@a.vn")
    h = {"Authorization": f"Bearer {m1['access_token']}"}
    resp = await client.post(f"/api/v1/users/{m2['user']['id']}/lock", headers=h)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unlock_request_notifies_root_ceo(client, db_session):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    await client.post(f"/api/v1/users/{m1['user']['id']}/lock", headers=ceo_h)

    resp = await client.post("/api/v1/auth/unlock-request",
                             json={"email": "m1@a.vn", "device_uuid": "dev-x"})
    assert resp.status_code == 202
    # email không tồn tại → vẫn 202, không lộ thông tin
    resp2 = await client.post("/api/v1/auth/unlock-request",
                              json={"email": "ghost@a.vn", "device_uuid": "d"})
    assert resp2.status_code == 202

    notes = (await db_session.execute(
        select(Notification).where(Notification.type == "unlock_request")
    )).scalars().all()
    assert len(notes) == 1
    assert notes[0].payload["device_uuid"] == "dev-x"
```

Run → FAIL.

- [ ] **Step 2: Implement**

Thêm vào `backend/app/services/auth_service.py`:
```python
import uuid as uuid_mod

from sqlalchemy import update

from app.models import Notification
from app.permissions import require_ceo


def _check_lock_permission(actor: User, target: User) -> None:
    require_ceo(actor)
    if target.is_root:
        raise HTTPException(403, "cannot_lock_root_ceo")
    if target.role == Role.ceo and not actor.is_root:
        raise HTTPException(403, "only_root_can_lock_ceo")
    if target.workspace_id != actor.workspace_id:
        raise HTTPException(404, "user_not_found")


async def lock_user(db: AsyncSession, actor: User, target_id: uuid_mod.UUID) -> None:
    target = await db.get(User, target_id)
    if target is None:
        raise HTTPException(404, "user_not_found")
    _check_lock_permission(actor, target)
    target.status = UserStatus.locked
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == target.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    db.add(Notification(
        workspace_id=target.workspace_id, recipient_id=target.id,
        type="account_locked", payload={"by": str(actor.id)},
    ))
    await db.commit()


async def unlock_user(db: AsyncSession, actor: User, target_id: uuid_mod.UUID) -> None:
    target = await db.get(User, target_id)
    if target is None:
        raise HTTPException(404, "user_not_found")
    _check_lock_permission(actor, target)
    target.status = UserStatus.active
    await db.commit()


async def request_unlock(db: AsyncSession, *, email: str, device_uuid: str) -> None:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None or user.status != UserStatus.locked:
        return  # luôn im lặng — không lộ email tồn tại
    root = (await db.execute(select(User).where(
        User.workspace_id == user.workspace_id, User.is_root,
    ))).scalar_one_or_none()
    if root:
        db.add(Notification(
            workspace_id=user.workspace_id, recipient_id=root.id,
            type="unlock_request",
            payload={"user_id": str(user.id), "email": email, "device_uuid": device_uuid},
        ))
        await db.commit()
```

Thêm route vào `backend/app/api/users.py`:
```python
from fastapi import Response

from app.services import auth_service


@router.post("/{user_id}/lock", status_code=204)
async def lock_user(
    user_id: uuid.UUID,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await auth_service.lock_user(db, actor, user_id)
    return Response(status_code=204)


@router.post("/{user_id}/unlock", status_code=204)
async def unlock_user(
    user_id: uuid.UUID,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await auth_service.unlock_user(db, actor, user_id)
    return Response(status_code=204)
```

Thêm route public vào `backend/app/api/auth.py`:
```python
class UnlockRequestIn(BaseModel):  # đặt trong schemas.py, import sang
    email: EmailStr
    device_uuid: str
```
(khai báo `UnlockRequestIn` trong `schemas.py`, import vào auth.py)
```python
@router.post("/unlock-request", status_code=202)
async def unlock_request(body: UnlockRequestIn, db: AsyncSession = Depends(get_db)):
    await auth_service.request_unlock(db, email=body.email, device_uuid=body.device_uuid)
    return {"status": "accepted"}
```

- [ ] **Step 3: Run toàn bộ → PASS**, rồi **Commit**

```bash
git add backend/
git commit -m "feat(be): account lock/unlock (root CEO rules) + public unlock request"
```

---

### Task 9: Docker Compose + Alembic + export openapi.json

**Files:**
- Create: `backend/docker-compose.yml`, `backend/Dockerfile`, `backend/scripts/export_openapi.py`, `backend/alembic.ini`, `backend/alembic/` (init)
- Test: `backend/tests/test_openapi_export.py`

**Interfaces:**
- Produces: `docker compose up` chạy api + postgres + redis; `python scripts/export_openapi.py` ghi `openapi.json` ở repo root cho FE chạy orval; alembic migration đầu tiên.

- [ ] **Step 1: Test fail cho export script**

`backend/tests/test_openapi_export.py`:
```python
import json

from scripts.export_openapi import build_openapi


def test_openapi_contains_auth_routes():
    spec = build_openapi()
    paths = spec["paths"]
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/signup-invite" in paths
    assert "/api/v1/users/{user_id}/lock" in paths
    json.dumps(spec)  # serializable
```

Run: `pytest tests/test_openapi_export.py -v` → FAIL.

- [ ] **Step 2: Implement script**

`backend/scripts/export_openapi.py`:
```python
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.main import create_app  # noqa: E402


def build_openapi() -> dict:
    return create_app().openapi()


if __name__ == "__main__":
    out = pathlib.Path(__file__).resolve().parents[2] / "openapi.json"
    out.write_text(json.dumps(build_openapi(), indent=2), encoding="utf-8")
    print(f"Wrote {out}")
```

(Tạo `backend/scripts/__init__.py` rỗng để pytest import được.)

Run test → PASS.

- [ ] **Step 3: Dockerfile + Compose**

`backend/Dockerfile`:
```dockerfile
FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`backend/docker-compose.yml`:
```yaml
services:
  api:
    build: .
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql+asyncpg://app:app@postgres:5432/app
      JWT_SECRET: ${JWT_SECRET:-dev-secret}
    depends_on: [postgres, redis]
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: app
    volumes: ["pgdata:/var/lib/postgresql/data"]
    ports: ["5432:5432"]
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
volumes:
  pgdata:
```

(`worker` service sẽ thêm ở Plan 3.)

- [ ] **Step 4: Alembic init + migration đầu**

```powershell
pip install alembic; alembic init -t async alembic
```

Sửa `backend/alembic/env.py` — thay phần metadata:
```python
from app.db import Base
from app import models  # noqa: F401  (đăng ký toàn bộ bảng)
target_metadata = Base.metadata
```
Sửa `backend/alembic.ini`: `sqlalchemy.url = postgresql+asyncpg://app:app@localhost:5432/app`
(thêm `alembic==1.*` vào requirements.txt)

Run:
```powershell
docker compose up -d postgres
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```
Expected: migration tạo đủ 8 bảng, upgrade thành công.

- [ ] **Step 5: Smoke test bằng compose**

```powershell
docker compose up -d --build
curl http://localhost:8000/api/v1/health
```
Expected: `{"status":"ok"}`; mở `http://localhost:8000/docs` thấy Swagger đầy đủ endpoint.

- [ ] **Step 6: Commit**

```bash
git add backend/ openapi.json
git commit -m "feat(be): docker compose + alembic initial migration + openapi export for FE codegen"
```

---

## Self-review (đã chạy)

- **Spec coverage (phần thuộc Plan 1):** workspace/invite kiểu Slack ✅ (Task 4, 6) · JWT 2 lớp + log thiết bị ✅ (Task 3, 4, 5) · khóa/mở + CEO gốc bất khả khóa + unlock request ✅ (Task 8) · permission layer service-level ✅ (Task 7) · Swagger + openapi cho orval ✅ (Task 9) · Docker Compose ✅ (Task 9). Ngoài phạm vi Plan 1 (chủ đích): chat/agent (Plan 3), domain task/skill (Plan 2), báo cáo (Plan 4), usage_log/semaphore (Plan 3).
- **Type consistency:** `AuthOut`/`UserOut` dùng thống nhất Task 4→8; `visible_user_ids`/`require_ceo` khai báo Task 7, dùng lại Task 8; `hash_refresh_token` khai báo Task 3, dùng Task 5.
- **Placeholder scan:** không còn TBD/`...` ngoài danh sách liệt kê tool ví dụ.
