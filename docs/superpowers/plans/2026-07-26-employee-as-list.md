# Nhân viên = tên trong danh sách công ty — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bỏ hẳn khái niệm "tài khoản/mời/kích hoạt" khỏi việc thêm nhân viên — chỉ CEO đăng nhập dùng app; người khác trong công ty chỉ là 1 record (tên bắt buộc + email tùy chọn) dùng để gán việc, không đăng nhập được.

**Architecture:** Đổi service `create_employee` (tạo tài khoản + mã kích hoạt) thành `add_employee` (chỉ tạo record không mật khẩu). Nới `User.email`/`password_hash` thành nullable ở DB. Tắt (comment-out, giữ code) route `/auth/activate` và `POST /invites` cũ; thêm route `POST /employees` mới. Đổi công cụ AI + mô tả tương ứng — đây là nơi sinh ra câu "mời vào hệ thống" mà CEO đang thấy.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (backend), Expo/React Native (frontend), pytest (TDD).

## Global Constraints

- Thêm nhân viên chỉ nhận **tên (bắt buộc) + email (tùy chọn)** — không vai trò, không quản lý, không mã kích hoạt.
- Chỉ CEO đăng nhập dùng app; mọi người khác không bao giờ đăng nhập được (dù có email).
- Không dùng chữ "mời / vào hệ thống / tài khoản / kích hoạt / đăng ký" khi nói về việc thêm nhân viên — dùng "danh sách nhân viên công ty".
- Comment-out code không còn dùng (route/màn hình) thay vì xóa — theo quy ước dự án (xem `CLAUDE.md`).
- Đổi API contract → chạy lại `python scripts/export_openapi.py`.
- Vai trò `manager` KHÔNG bị gỡ khỏi hệ thống phân quyền trong plan này (ngoài phạm vi — xem spec §5). Chỉ bỏ khả năng **tạo mới** người có thể đăng nhập.
- TDD: viết test thất bại trước, code sau; mỗi task 1 commit.
- Spec đầy đủ: `docs/superpowers/specs/2026-07-26-employee-as-list-design.md`.

---

## Bối cảnh quan trọng cho người thực thi (đọc trước khi bắt đầu)

**Vì sao không chỉ đổi 1 chỗ:** CEO báo lỗi "AI hỏi mời Duy Linh vào hệ thống". Nguyên nhân gốc là công cụ AI `create_employee` — mô tả và kết quả trả về của nó chứa đầy chữ "tạo tài khoản/mời/mã kích hoạt", nên model tự nhiên diễn đạt lại thành "mời vào hệ thống" dù resolver đã được sửa câu chữ ở phiên trước. Phải đổi cả **chuỗi**: model (DB) → service → tool AI → route REST → FE, nếu không sẽ còn sót chỗ nói sai.

**Rủi ro lớn nhất đã tìm ra và đã có giải pháp:** Fixture test `_invite_and_join` trong `tests/conftest.py` được **36 file test / 150 lần gọi** dùng để "tạo 1 manager/employee và đăng nhập luôn" (qua `POST /invites` rồi `POST /auth/activate`, trả về access_token thật). Nếu tắt `/auth/activate` mà không sửa fixture này trước, gần như toàn bộ test suite liên quan tới manager/employee sẽ vỡ hàng loạt — không phải vì code sai, mà vì cách setup test không còn đường vào. Giải pháp (Task 2): sửa fixture để **tạo User trực tiếp qua DB** (có mật khẩu, status active) rồi gọi `POST /auth/login` bình thường lấy token — giữ **nguyên chữ ký hàm** `_invite_and_join(client, headers, role, email, manager_id=None)` nên **0 file trong 36 file kia cần sửa gì**. Route `/auth/login` không bị đụng trong plan này nên vẫn hoạt động bình thường cho việc này.

**Thứ tự task được chọn có chủ đích:** Task 1 (nới nullable) là additive, không phá gì. Task 2 (sửa fixture) làm NGAY SAU đó và TRƯỚC KHI tắt bất kỳ route nào — lúc này route cũ `/invites`+`/activate` vẫn còn sống nên Task 2 tự nó không gây đỏ gì thêm, chỉ đổi cách fixture hoạt động nội bộ. Task 3–4 đổi service+tool (đây mới là chỗ sinh test đỏ, xử lý luôn trong cùng task). Task 5–6 mới tắt các route cũ — lúc này không còn ai (kể cả test) phụ thuộc chúng nữa nên tắt an toàn.

---

## Đã thỏa mãn từ trước — KHÔNG cần task riêng (đã kiểm tra lại code)

Spec §3.4 (system prompt) và §3.5 (`resolver_service.py` hint) đã được sửa ở phiên trước (commit
`c7d4639`, lúc fix lỗi "hỏi Duy Linh có tài khoản chưa"): `backend/app/agent/loop.py` đã có đoạn
*"Khi người dùng nhắc tên ai đó không có trong danh bạ công ty... nói rõ 'X chưa có trong danh sách
nhân viên'... KHÔNG hỏi kiểu 'X có tài khoản trong hệ thống chưa'"*, và
`backend/app/services/resolver_service.py::resolve_person` đã trả hint tương tự. Task 8 Step 4 sẽ
grep xác nhận không còn chữ "mời...hệ thống" sót lại — nếu grep đó fail, quay lại 2 file này sửa
tiếp trước khi coi plan hoàn thành.

---

### Task 1: Model — cho phép nhân viên không mật khẩu/email

**Files:**
- Modify: `backend/app/models.py:61-62` (cột `email`, `password_hash` của `User`)
- Modify: `backend/app/services/auth_service.py:91-108` (hàm `login`)
- Create: `backend/alembic/versions/<new>_employee_no_login.py`
- Test: `backend/tests/test_auth_service_login.py` (file mới)

**Interfaces:**
- Produces: `User.email: str | None`, `User.password_hash: str | None` — Task 3 dùng để tạo record không mật khẩu.
- Produces: `auth_service.login(...)` từ chối sạch (401) user có `password_hash IS NULL` thay vì lỗi hệ thống — Task 3's test dựa vào hành vi này.

- [ ] **Step 1: Viết test thất bại — login với password_hash=None phải trả 401, không phải lỗi 500**

Tạo file `backend/tests/test_auth_service_login.py`:

```python
import pytest
from fastapi import HTTPException

from app.models import Role, User, Workspace
from app.services import auth_service


@pytest.mark.asyncio
async def test_login_rejects_user_without_password_cleanly(db_session):
    """Nhân viên chỉ-có-tên (Task 3: add_employee) có password_hash=None. Nếu login()
    gọi thẳng security.verify_password(password, None) sẽ AttributeError (None không
    có .encode()) — lỗi hệ thống 500 thay vì từ chối sạch 401. Đây là defense-in-depth:
    record chỉ-tên TUYỆT ĐỐI không được đăng nhập, dù ai đó biết email và đoán đúng gì đó."""
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    nv = User(workspace_id=ws.id, email="nv@a.vn", password_hash=None,
             full_name="Nhan Vien", role=Role.employee)
    db_session.add(nv)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await auth_service.login(db_session, email="nv@a.vn", password="anything",
                                 device_uuid="d", device_name="")
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_credentials"
```

- [ ] **Step 2: Chạy test, xác nhận lỗi (fail vì AttributeError, không phải vì thiếu tính năng)**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_auth_service_login.py -v`
Expected: FAIL — traceback có `AttributeError: 'NoneType' object has no attribute 'encode'` (không phải `HTTPException`). Đây LÀ bug hiện tại, xác nhận trước khi sửa.

- [ ] **Step 3: Nới `User.email`/`password_hash` thành nullable trong model**

Trong `backend/app/models.py`, sửa 2 dòng (giữ nguyên vị trí, chỉ thêm `nullable=True`):

```python
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

- [ ] **Step 4: Thêm guard trong `login()` — từ chối sạch trước khi verify_password**

Trong `backend/app/services/auth_service.py`, sửa hàm `login` (dòng 91-108):

```python
async def login(
    db: AsyncSession, *, email: str, password: str, device_uuid: str, device_name: str,
) -> tuple[User, str, str]:
    email = email.strip().lower()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if not user or user.password_hash is None:
        # password_hash=None = record chỉ-tên (add_employee, Task 3) — KHÔNG bao giờ
        # đăng nhập được, dù email đúng. Chặn trước verify_password: None không có
        # .encode() -> AttributeError (lỗi hệ thống) thay vì từ chối sạch nếu không guard.
        security.verify_password(password, _DUMMY_HASH)
        raise HTTPException(401, "invalid_credentials")
    if not security.verify_password(password, user.password_hash):
        raise HTTPException(401, "invalid_credentials")
    if user.status == UserStatus.locked:
        raise HTTPException(403, "account_locked")
    if user.status == UserStatus.pending:
        raise HTTPException(403, "account_pending")
    await _log_device(db, user, device_uuid, device_name)
    access, refresh = await _issue_tokens(db, user)
    await db.commit()
    return user, access, refresh
```

- [ ] **Step 5: Chạy test, xác nhận pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_auth_service_login.py -v`
Expected: PASS

- [ ] **Step 6: Tạo migration nullable**

Run: `cd backend && .venv/Scripts/python.exe -m alembic revision -m "employee_no_login"`

Sửa file vừa sinh ra (`backend/alembic/versions/<hash>_employee_no_login.py`) — `down_revision` phải trỏ đúng head hiện tại `1a11430b62b9` (kiểm tra lại bằng `alembic heads` nếu có commit migration khác chen vào từ lúc viết plan):

```python
"""employee_no_login

Revision ID: <hash do alembic tu sinh>
Revises: 1a11430b62b9
Create Date: <do alembic tu sinh>

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '<hash do alembic tu sinh>'
down_revision: Union[str, Sequence[str], None] = '1a11430b62b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nhân viên = record chỉ-tên (add_employee, không tài khoản) không còn bắt buộc
    # có email/mật khẩu. Postgres cho phép nhiều NULL trên cột unique nên không xung
    # đột giữa nhiều nhân viên không-email.
    op.alter_column('users', 'email', existing_type=sa.String(255), nullable=True)
    op.alter_column('users', 'password_hash', existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('users', 'password_hash', existing_type=sa.String(255), nullable=False)
    op.alter_column('users', 'email', existing_type=sa.String(255), nullable=False)
```

- [ ] **Step 7: Chạy migration lên DB dev để xác nhận chạy sạch (không bắt buộc nếu chỉ chạy test SQLite, nhưng nên xác nhận cú pháp)**

Run: `cd backend && .venv/Scripts/python.exe -m alembic upgrade head`
Expected: chạy xong không lỗi, in ra revision mới là head.

- [ ] **Step 8: Chạy lại toàn bộ test liên quan auth để chắc không vỡ gì**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_auth_service_login.py tests/test_create_employee.py -v`
Expected: PASS hết (test_create_employee.py chưa đổi ở task này, vẫn phải xanh vì model chỉ NỚI ràng buộc, không đổi hành vi hiện có).

- [ ] **Step 9: Commit**

```bash
cd "d:\8. AI\ai-assistant"
git add backend/app/models.py backend/app/services/auth_service.py backend/alembic/versions backend/tests/test_auth_service_login.py
git commit -m "feat(auth): cho phép User không email/mật khẩu — nền tảng cho nhân viên chỉ-tên

User.email/password_hash nullable (migration mới). login() chặn sạch (401)
user password_hash=None trước khi gọi verify_password — tránh AttributeError
(None không có .encode()). Chuẩn bị cho add_employee (Task 3) tạo record
không tài khoản.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Test infra — fixture tạo user không qua route invite/activate

**Files:**
- Modify: `backend/tests/conftest.py:32-71` (fixture `client`, hàm `_invite_and_join`)

**Interfaces:**
- Consumes: `security.hash_password`, `security.decode_access_token` (`backend/app/security.py`), `User`/`Role`/`UserStatus` (`backend/app/models.py`).
- Produces: `_invite_and_join(client, headers, role, email, manager_id=None) -> dict` — **chữ ký và shape trả về giữ NGUYÊN** (dict có `access_token`, `refresh_token`, `user`) để 36 file test khác không cần sửa gì.

**Vì sao task này không có "test thất bại" kiểu thông thường:** đây là sửa hạ tầng test, không phải tính năng sản phẩm. Bằng chứng đúng/sai là chạy các file test ĐANG DÙNG fixture này — nếu chúng vẫn xanh y hệt trước khi sửa, nghĩa là thay máy bên trong không làm hỏng hợp đồng bên ngoài.

- [ ] **Step 1: Chạy 1 file test đại diện TRƯỚC khi sửa, ghi lại kết quả làm baseline**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_traces_api.py tests/test_agent_tools_offboard.py -v`
Expected: PASS hết (baseline — đây là hành vi phải giữ nguyên sau khi sửa fixture).

- [ ] **Step 2: Sửa fixture `client` — đính kèm session maker để `_invite_and_join` dùng được**

Trong `backend/tests/conftest.py`, sửa fixture `client` (dòng 32-44):

```python
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
        # Đính session maker lên client — _invite_and_join cần tạo User trực tiếp
        # qua DB (không còn route /invites+/activate để tạo user có mật khẩu).
        c.db_maker = maker
        yield c
```

- [ ] **Step 3: Viết lại `_invite_and_join` — tạo User trực tiếp qua DB rồi login thật**

Trong `backend/tests/conftest.py`, thêm import ở đầu file (sau các import hiện có) và thay thế hàm `_invite_and_join` (dòng 58-71):

```python
from app import security
from app.models import Role, User, UserStatus
```

```python
async def _invite_and_join(client, headers, role, email, manager_id=None):
    """Tạo 1 user CÓ THỂ ĐĂNG NHẬP cho test (manager/employee cũ vẫn cần login được
    qua HTTP để test hành vi theo vai trò/quyền — KHÔNG liên quan gì tới add_employee
    sản phẩm, đây thuần là hạ tầng test).

    Trước 2026-07-26: tạo qua POST /invites + POST /auth/activate. Route /activate đã
    tắt (product quyết định chỉ CEO đăng nhập — xem spec employee-as-list) nên tạo
    thẳng qua DB (đã hash mật khẩu, status=active) rồi login thật qua /auth/login.
    GIỮ NGUYÊN chữ ký/kiểu trả về để không sửa lan sang các file test khác đang dùng
    helper này (test_traces_api.py, test_agent_tools_account.py, ...)."""
    payload = security.decode_access_token(headers["Authorization"].removeprefix("Bearer "))
    workspace_id = payload["ws"]
    password = "pw123456"
    async with client.db_maker() as db:
        user = User(workspace_id=workspace_id, email=email, full_name=email,
                   password_hash=security.hash_password(password),
                   role=Role(role), manager_id=manager_id, status=UserStatus.active)
        db.add(user)
        await db.commit()
    login = await client.post("/api/v1/auth/login", json={
        "email": email, "password": password, "device_uuid": "d-" + email, "device_name": ""})
    assert login.status_code == 200, login.text
    return login.json()
```

- [ ] **Step 4: Chạy lại đúng 2 file baseline, xác nhận vẫn xanh y hệt**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_traces_api.py tests/test_agent_tools_offboard.py -v`
Expected: PASS hết — số lượng test pass phải khớp Step 1.

- [ ] **Step 5: Chạy toàn bộ test suite để xác nhận không có file nào khác vỡ vì đổi fixture**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -q`
Expected: Kết quả pass/fail phải giống hệt trước khi bắt đầu plan này NGOẠI TRỪ các file liên quan trực tiếp tới `create_employee`/`activate`/`invites` (test_create_employee.py, test_agent_tools_account.py, test_openapi_export.py, test_subscription.py) — các file đó xử lý ở Task 3/5/6, có thể đang đỏ ở bước này, đó là dự kiến. Nếu có file KHÁC vỡ ngoài 4 file trên, dừng lại điều tra trước khi tiếp tục.

- [ ] **Step 6: Commit**

```bash
cd "d:\8. AI\ai-assistant"
git add backend/tests/conftest.py
git commit -m "test(infra): _invite_and_join tạo user qua DB + login thật, không qua route activate

Route /auth/activate sắp bị tắt (chỉ CEO đăng nhập). Fixture dùng ở 36 file/150
lần gọi để test hành vi theo vai trò manager/employee — giữ nguyên chữ ký/shape
trả về, chỉ đổi cách tạo user bên trong (DB trực tiếp + /auth/login thật) để
không phụ thuộc route sắp bị comment-out.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Service — `add_employee` (thay `create_employee`)

**Files:**
- Modify: `backend/app/services/auth_service.py:185-236` (hàm `create_employee` → `add_employee`)
- Delete + Create: `backend/tests/test_create_employee.py` → nội dung mới hoàn toàn (giữ tên file, chỉ vì lịch sử ít quan trọng; đổi tên file cũng được nếu công cụ hỗ trợ — dùng `Write` ghi đè)

**Interfaces:**
- Consumes: `Role`, `UserStatus`, `security.hash_password` (đã có sẵn trong `auth_service.py`).
- Produces: `auth_service.add_employee(db, *, actor: User, full_name: str, email: str | None = None) -> User` — Task 4 (tool AI) và Task 5 (REST route) gọi hàm này.

- [ ] **Step 1: Viết test thất bại cho `add_employee`**

Ghi đè toàn bộ nội dung `backend/tests/test_create_employee.py`:

```python
import pytest
from fastapi import HTTPException

from app.models import Invite, Role, User, UserStatus, Workspace
from app.services import auth_service
from sqlalchemy import select
from tests.conftest import SIGNUP, _ceo_headers, _invite_and_join


async def _ceo(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    await db.commit()
    return ws, ceo


@pytest.mark.asyncio
async def test_add_employee_with_name_only(db_session):
    ws, ceo = await _ceo(db_session)
    user = await auth_service.add_employee(db_session, actor=ceo, full_name="Duy Linh")
    assert user.full_name == "Duy Linh"
    assert user.email is None
    assert user.password_hash is None
    assert user.status == UserStatus.active
    assert user.role == Role.employee
    assert user.workspace_id == ws.id


@pytest.mark.asyncio
async def test_add_employee_with_name_and_email(db_session):
    ws, ceo = await _ceo(db_session)
    user = await auth_service.add_employee(db_session, actor=ceo, full_name="Nam",
                                           email="nam@a.vn")
    assert user.email == "nam@a.vn"
    assert user.password_hash is None


@pytest.mark.asyncio
async def test_add_employee_no_activation_code_or_invite_row(db_session):
    """Khác hẳn create_employee cũ: KHÔNG sinh Invite/mã kích hoạt gì."""
    ws, ceo = await _ceo(db_session)
    await auth_service.add_employee(db_session, actor=ceo, full_name="Duy Linh")
    invites = (await db_session.execute(select(Invite))).scalars().all()
    assert invites == []


@pytest.mark.asyncio
async def test_add_employee_duplicate_email_409(db_session):
    ws, ceo = await _ceo(db_session)
    await auth_service.add_employee(db_session, actor=ceo, full_name="A", email="dup@a.vn")
    with pytest.raises(HTTPException) as exc:
        await auth_service.add_employee(db_session, actor=ceo, full_name="B", email="dup@a.vn")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_non_ceo_cannot_add_employee(db_session):
    ws, ceo = await _ceo(db_session)
    mgr = User(workspace_id=ws.id, email="m@a.vn", password_hash="x", full_name="M",
              role=Role.manager)
    db_session.add(mgr)
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await auth_service.add_employee(db_session, actor=mgr, full_name="X")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_added_employee_cannot_login(db_session):
    """End-to-end với guard Task 1: nhân viên vừa thêm không đăng nhập được."""
    ws, ceo = await _ceo(db_session)
    await auth_service.add_employee(db_session, actor=ceo, full_name="Duy Linh",
                                    email="duy@a.vn")
    with pytest.raises(HTTPException) as exc:
        await auth_service.login(db_session, email="duy@a.vn", password="anything",
                                 device_uuid="d", device_name="")
    assert exc.value.status_code == 401
```

- [ ] **Step 2: Chạy test, xác nhận fail (hàm `add_employee` chưa tồn tại)**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_create_employee.py -v`
Expected: FAIL — `AttributeError: module 'app.services.auth_service' has no attribute 'add_employee'`

- [ ] **Step 3: Viết `add_employee`, thay hoàn toàn `create_employee`**

Trong `backend/app/services/auth_service.py`, thay thế toàn bộ hàm `create_employee` (dòng 185-236) bằng:

```python
async def add_employee(db: AsyncSession, *, actor: User, full_name: str,
                       email: str | None = None) -> User:
    """Thêm 1 người vào DANH SÁCH NHÂN VIÊN công ty (chỉ CEO) — record chỉ để gán
    việc, KHÔNG phải tạo tài khoản. Không mật khẩu (password_hash=None) nên
    login() (Task 1) luôn từ chối — người này không bao giờ đăng nhập app được.
    Sản phẩm quyết định 2026-07-26: chỉ CEO dùng app; xem
    docs/superpowers/specs/2026-07-26-employee-as-list-design.md."""
    if actor.role != Role.ceo:
        raise HTTPException(403, "forbidden")
    await plans.enforce_limit(db, actor.workspace_id, "members")
    email = email.strip().lower() if email else None
    if email and (await db.execute(
            select(User).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(409, "email_taken")
    user = User(workspace_id=actor.workspace_id, email=email, password_hash=None,
               full_name=full_name, role=Role.employee, status=UserStatus.active)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "email_taken")
    return user
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_create_employee.py -v`
Expected: PASS hết (6 test)

- [ ] **Step 5: Commit**

```bash
cd "d:\8. AI\ai-assistant"
git add backend/app/services/auth_service.py backend/tests/test_create_employee.py
git commit -m "feat(auth): add_employee thay create_employee — chỉ tên+email, không tài khoản

create_employee cũ tạo tài khoản + sinh activation_code (CEO đưa mã cho nhân
viên tự kích hoạt). add_employee chỉ tạo record để gán việc: password_hash=None
(không bao giờ đăng nhập được, guard ở Task 1), không Invite, không mã, không
role/manager_id (luôn role=employee). Product quyết định 2026-07-26: chỉ CEO
dùng app.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Công cụ AI — `add_employee` (thay `create_employee`)

**Files:**
- Modify: `backend/app/agent/tools.py:343-380` (`CreateEmployeeToolIn`, `_create_employee`)
- Modify: `backend/app/agent/tools.py:417-422` (`_register("create_employee", ...)`)
- Modify: `backend/app/agent/tools.py:1045-1048` (`TOOL_GROUPS["admin"]`)
- Modify: `backend/app/agent/tools.py:1078-1083` (`SNAPSHOT_WRITE_TOOLS`)
- Modify: `backend/tests/test_agent_tools_account.py` (test tool)

**Interfaces:**
- Consumes: `auth_service.add_employee` (Task 3).
- Produces: tool `"add_employee"` đăng ký trong `TOOLS` — không còn `"create_employee"`.

- [ ] **Step 1: Viết test thất bại cho tool `add_employee`**

Trong `backend/tests/test_agent_tools_account.py`, thay hàm `test_create_employee_tool` (dòng 18-26):

```python
@pytest.mark.asyncio
async def test_add_employee_tool(db_session):
    ws, ceo = await _ceo(db_session)
    result = await call_tool(db_session, ceo, "add_employee", {"full_name": "Duy Linh"})
    assert result["full_name"] == "Duy Linh"
    assert "role" not in result
    assert "activation_code" not in result
    assert "danh sách nhân viên" in result["note"]
```

Và sửa `test_lock_and_unlock_are_marked_sensitive` (dòng 54-58), dòng cuối:

```python
    assert TOOLS["add_employee"].sensitive is False
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_agent_tools_account.py -v`
Expected: FAIL — `KeyError: 'add_employee'` hoặc tool không tồn tại (not_found).

- [ ] **Step 3: Đổi `CreateEmployeeToolIn`/`_create_employee` thành `AddEmployeeToolIn`/`_add_employee`**

Trong `backend/app/agent/tools.py`, thay khối dòng 343-348:

```python
class AddEmployeeToolIn(BaseModel):
    full_name: str
    email: EmailStr | None = None
```

Thay khối dòng 370-379 (`_create_employee`):

```python
async def _add_employee(db, actor, body: AddEmployeeToolIn) -> dict:
    user = await auth_service.add_employee(
        db, actor=actor, full_name=body.full_name, email=body.email)
    return {"user_id": str(user.id), "full_name": user.full_name, "email": user.email,
           "note": f"Đã thêm {user.full_name} vào danh sách nhân viên công ty."}
```

- [ ] **Step 4: Đổi `_register` call — mô tả KHÔNG chứa mời/hệ thống/tài khoản/kích hoạt**

Trong `backend/app/agent/tools.py`, thay khối dòng 417-422:

```python
_register("add_employee", "Thêm 1 người vào DANH SÁCH NHÂN VIÊN của công ty để giao "
          "việc (chỉ CEO). Chỉ cần tên; email là tùy chọn. Đây KHÔNG PHẢI tạo tài "
          "khoản/đăng nhập — nhân viên không dùng app này, chỉ CEO dùng. Dùng khi CEO "
          "nhắc tên người chưa có trong danh sách (kiểm tra trước bằng resolve_person "
          "hoặc danh bạ trong system prompt) mà muốn giao việc cho họ — nếu vậy, thêm "
          "vào danh sách rồi giao việc luôn trong 1 lượt, đừng hỏi lại xác nhận thêm.",
          AddEmployeeToolIn, _add_employee)
```

- [ ] **Step 5: Đổi tên trong `TOOL_GROUPS["admin"]` và `SNAPSHOT_WRITE_TOOLS`**

Trong `backend/app/agent/tools.py` dòng 1045-1048, đổi `"create_employee"` → `"add_employee"`:

```python
    "admin": frozenset({
        "list_users", "add_employee", "lock_user", "unlock_user",
        "offboard_user", "change_user_role", "list_audit_events", "forget_memory",
    }),
```

Dòng 1078-1083, đổi `"create_employee"` → `"add_employee"`:

```python
SNAPSHOT_WRITE_TOOLS: frozenset[str] = frozenset({
    "create_project", "update_project", "delete_project",
    "create_task", "update_task", "delete_task",
    "assign_task", "unassign_task", "add_task_update",
    "offboard_user", "change_user_role", "create_directive", "add_employee",
})
```

- [ ] **Step 6: Chạy test, xác nhận pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_agent_tools_account.py -v`
Expected: PASS hết (5 test)

- [ ] **Step 7: Chạy toàn bộ test tools để chắc không vỡ chỗ khác (vd đếm số tool)**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_agent_tools_report_schedule.py -k "registered" -v`
Expected: PASS — `assert len(TOOLS) == 62` vẫn đúng (đổi tên không đổi số lượng).

- [ ] **Step 8: Commit**

```bash
cd "d:\8. AI\ai-assistant"
git add backend/app/agent/tools.py backend/tests/test_agent_tools_account.py
git commit -m "feat(tools): add_employee thay create_employee — mô tả không còn 'mời/tài khoản'

Đây là nguồn gốc thật của lỗi AI nói 'mời X vào hệ thống': mô tả tool cũ đầy
chữ tạo tài khoản/mã kích hoạt nên model tự diễn đạt lại thành mời. Mô tả mới
nói rõ đây là danh sách để gán việc, không phải tài khoản/đăng nhập, và dạy
model tự thêm+giao việc luôn trong 1 lượt khi gặp tên lạ.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: REST route — `POST /api/v1/employees`

**Files:**
- Modify: `backend/app/schemas.py:72-86` (`CreateEmployeeIn/Out` → comment-out + `AddEmployeeIn/Out` mới)
- Modify: `backend/app/api/invites.py` (comment-out route cũ, thêm router mới)
- Modify: `backend/app/main.py` (đăng ký router mới)
- Modify: `backend/tests/test_subscription.py` (1 chỗ gọi `/invites` trực tiếp)
- Test: `backend/tests/test_add_employee_api.py` (file mới)

**Interfaces:**
- Consumes: `auth_service.add_employee` (Task 3).
- Produces: route `POST /api/v1/employees` — Task 7 (FE) sẽ không cần gọi route này (xác nhận ở Task 7 rằng FE hiện KHÔNG có form thêm nhân viên qua REST, chỉ qua chat), route này tồn tại để có REST parity + phục vụ test_subscription.py.

- [ ] **Step 1: Viết test thất bại cho route mới**

Tạo file `backend/tests/test_add_employee_api.py`:

```python
import pytest

from tests.conftest import _ceo_headers, _invite_and_join


@pytest.mark.asyncio
async def test_add_employee_route_name_only(client):
    headers = await _ceo_headers(client)
    resp = await client.post("/api/v1/employees", headers=headers,
                             json={"full_name": "Duy Linh"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["full_name"] == "Duy Linh"
    assert body["email"] is None
    assert "role" not in body
    assert "activation_code" not in body


@pytest.mark.asyncio
async def test_add_employee_route_with_email(client):
    headers = await _ceo_headers(client)
    resp = await client.post("/api/v1/employees", headers=headers,
                             json={"full_name": "Nam", "email": "nam@a.vn"})
    assert resp.status_code == 201
    assert resp.json()["email"] == "nam@a.vn"


@pytest.mark.asyncio
async def test_add_employee_route_non_ceo_403(client):
    headers = await _ceo_headers(client)
    mgr = await _invite_and_join(client, headers, "manager", "m1@a.vn")
    mgr_headers = {"Authorization": f"Bearer {mgr['access_token']}"}
    resp = await client.post("/api/v1/employees", headers=mgr_headers,
                             json={"full_name": "X"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_old_invites_route_gone(client):
    headers = await _ceo_headers(client)
    resp = await client.post("/api/v1/invites", headers=headers,
                             json={"full_name": "X", "email": "x@a.vn",
                                   "role": "manager", "manager_id": None})
    assert resp.status_code == 404
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_add_employee_api.py -v`
Expected: FAIL — `test_add_employee_route_name_only`/`test_add_employee_route_with_email`/`test_add_employee_route_non_ceo_403` trả 404 (route chưa tồn tại); `test_old_invites_route_gone` trả 201 (route cũ vẫn còn).

- [ ] **Step 3: Thêm schema `AddEmployeeIn/Out`, comment-out schema cũ**

Trong `backend/app/schemas.py`, thay khối dòng 72-86:

```python
# CreateEmployeeIn/Out (route /invites cũ) tắt cùng route — xem api/invites.py.
# Giữ code theo quy ước dự án (comment-out, không xóa).
# class CreateEmployeeIn(BaseModel):
#     email: EmailStr
#     full_name: str
#     role: Role
#     manager_id: uuid.UUID | None = None
#
#
# class CreateEmployeeOut(BaseModel):
#     user_id: uuid.UUID
#     email: str
#     full_name: str
#     role: Role
#     activation_code: str
#     expires_at: dt.datetime


class AddEmployeeIn(BaseModel):
    full_name: str
    email: EmailStr | None = None


class AddEmployeeOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str | None = None
```

- [ ] **Step 4: Comment-out route cũ, thêm router+route mới trong `invites.py`**

Thay toàn bộ nội dung `backend/app/api/invites.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import AddEmployeeIn, AddEmployeeOut
from app.services import auth_service

# Route cũ (tạo tài khoản + mã kích hoạt) tắt — sản phẩm quyết định 2026-07-26 chỉ
# CEO đăng nhập, nhân viên chỉ là record trong danh sách (add_employee bên dưới).
# Giữ router này (rỗng) để không phải sửa main.py; xem
# docs/superpowers/specs/2026-07-26-employee-as-list-design.md.
router = APIRouter(prefix="/api/v1/invites", tags=["invites"])

# @router.post("", response_model=CreateEmployeeOut, status_code=201)
# async def create_employee(
#     body: CreateEmployeeIn,
#     actor: User = Depends(get_current_user),
#     db: AsyncSession = Depends(get_db),
# ):
#     user, code, expires_at = await auth_service.create_employee(
#         db, actor=actor, email=body.email, full_name=body.full_name,
#         role=body.role.value, manager_id=body.manager_id,
#     )
#     return CreateEmployeeOut(user_id=user.id, email=user.email, full_name=user.full_name,
#                              role=user.role, activation_code=code, expires_at=expires_at)


employees_router = APIRouter(prefix="/api/v1/employees", tags=["employees"])


@employees_router.post("", response_model=AddEmployeeOut, status_code=201)
async def add_employee(
    body: AddEmployeeIn,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await auth_service.add_employee(
        db, actor=actor, full_name=body.full_name, email=body.email)
    return AddEmployeeOut(user_id=user.id, full_name=user.full_name, email=user.email)
```

- [ ] **Step 5: Đăng ký router mới trong `main.py`**

Trong `backend/app/main.py`, tìm dòng `app.include_router(invites.router)` và thêm ngay sau:

```python
    app.include_router(invites.router)
    app.include_router(invites.employees_router)
```

- [ ] **Step 6: Sửa `test_subscription.py` — chỗ gọi `/invites` trực tiếp đổi sang `/employees`**

Trong `backend/tests/test_subscription.py`, sửa dòng 64-66 (biến `over`):

```python
    over = await client.post("/api/v1/employees", headers=ceo_h,
                             json={"full_name": "M2", "email": "m2@a.vn"})
    assert over.status_code == 403
    assert over.json()["detail"] == "plan_limit_reached"
```

- [ ] **Step 7: Chạy test, xác nhận pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_add_employee_api.py tests/test_subscription.py -v`
Expected: PASS hết.

- [ ] **Step 8: Commit**

```bash
cd "d:\8. AI\ai-assistant"
git add backend/app/schemas.py backend/app/api/invites.py backend/app/main.py backend/tests/test_add_employee_api.py backend/tests/test_subscription.py
git commit -m "feat(api): POST /employees thay POST /invites — comment-out route tài khoản cũ

Route /invites (tạo tài khoản + mã kích hoạt) comment-out, giữ code. Route mới
/employees chỉ nhận tên+email tùy chọn, gọi auth_service.add_employee.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Tắt route `/auth/activate`

**Files:**
- Modify: `backend/app/api/auth.py:29-32`
- Modify: `backend/tests/test_openapi_export.py`

**Interfaces:**
- Consumes: không có (chỉ comment-out).
- Produces: `/api/v1/auth/activate` không còn reachable qua HTTP (404).

- [ ] **Step 1: Viết test thất bại — route activate phải biến mất khỏi OpenAPI + trả 404**

Thay nội dung `backend/tests/test_openapi_export.py`:

```python
import json

from scripts.export_openapi import build_openapi


def test_openapi_contains_auth_routes():
    spec = build_openapi()
    paths = spec["paths"]
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/activate" not in paths
    assert "/api/v1/employees" in paths
    assert "/api/v1/users/{user_id}/lock" in paths
    json.dumps(spec)  # serializable
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_openapi_export.py -v`
Expected: FAIL — `/api/v1/auth/activate` vẫn có trong `paths`.

- [ ] **Step 3: Comment-out route `/activate`, theo đúng phong cách đã dùng cho `/signup-code` trong CÙNG FILE (dòng 35-41)**

Trong `backend/app/api/auth.py`, thay khối dòng 29-32:

```python
# Kích hoạt tài khoản đã CEO tạo trước (create_employee cũ) tắt — sản phẩm quyết
# định 2026-07-26 chỉ CEO đăng nhập, nhân viên là record chỉ-tên (add_employee),
# không còn ai kích hoạt. Giữ nguyên auth_service.activate_account, chỉ bỏ route
# (cùng quy ước đã dùng cho /signup-code bên dưới, 2026-07-23).
# @router.post("/activate", response_model=AuthOut, status_code=201)
# async def activate(body: ActivateAccountIn, db: AsyncSession = Depends(get_db)):
#     user, access, refresh = await auth_service.activate_account(db, **body.model_dump())
#     return AuthOut(access_token=access, refresh_token=refresh, user=user)
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_openapi_export.py -v`
Expected: PASS

- [ ] **Step 5: Export lại `openapi.json` (contract cho FE)**

Run: `cd backend && .venv/Scripts/python.exe scripts/export_openapi.py`
Expected: ghi `openapi.json` ở repo root, không lỗi.

- [ ] **Step 6: Commit**

```bash
cd "d:\8. AI\ai-assistant"
git add backend/app/api/auth.py openapi.json
git commit -m "fix(auth): tắt route /auth/activate — không còn ai kích hoạt tài khoản

Comment-out theo đúng quy ước đã dùng cho /signup-code (2026-07-23) — giữ
nguyên auth_service.activate_account, chỉ bỏ route reachable. Chỉ CEO đăng
nhập app từ giờ; xem docs/superpowers/specs/2026-07-26-employee-as-list-design.md.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Frontend — đổi nhãn tool, tắt màn kích hoạt

**Files:**
- Modify: `frontend/app/main/chat.tsx` (`TOOL_LABELS`)
- Modify: `frontend/src/navigation/AuthNavigator.tsx`
- Modify: `frontend/app/auth/login.tsx`

**Interfaces:** Không có — thay đổi thuần UI/routing, không đổi kiểu dữ liệu dùng chỗ khác.

**Ghi chú quan trọng:** đã kiểm tra `frontend/app/main/settings.tsx` và `frontend/app/main/team.tsx`/`team/detail.tsx` — **không có form thêm nhân viên qua REST nào ở FE hiện tại** (việc thêm nhân viên trước giờ chỉ qua chat với AI). Vì vậy Task này KHÔNG cần thêm/sửa form nào, chỉ cần đổi nhãn tool trong chat và tắt màn kích hoạt.

- [ ] **Step 1: Đổi nhãn tool trong `chat.tsx`**

Trong `frontend/app/main/chat.tsx`, tìm dòng:
```
  create_employee: "Tạo nhân viên mới",
```
Đổi thành:
```
  add_employee: "Thêm vào danh sách nhân viên",
```

- [ ] **Step 2: Comment-out màn `Activate` trong `AuthNavigator.tsx`, theo đúng phong cách đã dùng cho `SignupCode` (cùng file)**

Thay toàn bộ nội dung `frontend/src/navigation/AuthNavigator.tsx`:

```tsx
import React from "react";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { colors, fonts } from "../ui/theme";
import type { AuthStackParamList } from "./types";
import Login from "../../app/auth/login";
import ForgotPassword from "../../app/auth/forgot-password";
// SignupCode (tự đăng ký bằng mã mời chung workspace) tắt tạm - product quyết
// định nhân viên không còn đăng nhập vào app (2026-07-23). Giữ nguyên file,
// chỉ bỏ đăng ký route để không truy cập được nữa.
// import SignupCode from "../../app/auth/signup-code";
import SignupWorkspace from "../../app/auth/signup-workspace";
// Activate (kích hoạt tài khoản CEO tạo trước) tắt - product quyết định
// 2026-07-26 chỉ CEO đăng nhập, nhân viên là record chỉ-tên (add_employee),
// không còn ai kích hoạt. Giữ nguyên file, chỉ bỏ route.
// import Activate from "../../app/auth/activate";

const Stack = createNativeStackNavigator<AuthStackParamList>();

export function AuthNavigator() {
  return (
    <Stack.Navigator
      screenOptions={{
        animation: "slide_from_right", // iOS slide trái→phải
        headerStyle: { backgroundColor: colors.surface },
        headerShadowVisible: false,
        headerTintColor: colors.primary,
        headerTitleAlign: "center",
        headerTitleStyle: { fontFamily: fonts.bold, fontSize: 17, color: colors.text },
      }}
    >
      <Stack.Screen name="Login" component={Login} options={{ title: "Đăng nhập" }} />
      <Stack.Screen name="ForgotPassword" component={ForgotPassword} options={{ title: "Quên mật khẩu" }} />
      {/* <Stack.Screen name="SignupCode" component={SignupCode} options={{ title: "Đăng ký bằng mã mời" }} /> */}
      <Stack.Screen name="SignupWorkspace" component={SignupWorkspace} options={{ title: "Tạo công ty mới" }} />
      {/* <Stack.Screen name="Activate" component={Activate} options={{ title: "Kích hoạt tài khoản" }} /> */}
    </Stack.Navigator>
  );
}
```

- [ ] **Step 3: Comment-out link "Kích hoạt tài khoản" trong `login.tsx`, theo đúng phong cách đã dùng cho link SignupCode (cùng file)**

Trong `frontend/app/auth/login.tsx`, thay khối (khoảng dòng 50-64):

```tsx
      <View style={{ marginTop: spacing.xl, gap: spacing.md }}>
        {/* Tự đăng ký bằng mã mời chung (nhân viên) tắt tạm - nhân viên không
            còn đăng nhập vào app (2026-07-23). */}
        {/* <Text
          style={{ color: colors.primary, fontFamily: fonts.semibold }}
          onPress={() => navigation.navigate("SignupCode")}
        >
          Nhân viên mới? Đăng ký bằng mã mời công ty
        </Text> */}
        {/* Kích hoạt tài khoản (create_employee cũ) tắt - chỉ CEO đăng nhập app,
            nhân viên là record chỉ-tên (2026-07-26). */}
        {/* <Text
          style={{ color: colors.primary, fontFamily: fonts.semibold }}
          onPress={() => navigation.navigate("Activate")}
        >
          Đã được thêm vào công ty? Kích hoạt tài khoản
        </Text> */}
        <Text
          style={{ color: colors.primary, fontFamily: fonts.semibold }}
          onPress={() => navigation.navigate("SignupWorkspace")}
        >
          Tạo công ty mới (CEO)
```

(Giữ nguyên phần code còn lại phía sau dòng "Tạo công ty mới (CEO)" — chỉ đoạn trên bị thay.)

- [ ] **Step 4: Kiểm tra TypeScript biên dịch sạch**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit code 0, không lỗi.

- [ ] **Step 5: Commit**

```bash
cd "d:\8. AI\ai-assistant"
git add frontend/app/main/chat.tsx frontend/src/navigation/AuthNavigator.tsx frontend/app/auth/login.tsx
git commit -m "fix(fe): đổi nhãn add_employee + tắt màn kích hoạt tài khoản

TOOL_LABELS: create_employee -> add_employee ('Thêm vào danh sách nhân viên').
Màn Activate + link 'Kích hoạt tài khoản' comment-out theo đúng phong cách đã
dùng cho SignupCode (2026-07-23) — chỉ CEO đăng nhập app từ giờ. Không có form
thêm nhân viên qua REST ở FE (chỉ qua chat), nên không cần sửa gì thêm.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Xác nhận toàn cục + kiểm tra hành vi AI qua chat

**Files:**
- Test: `backend/tests/test_agent_add_employee_flow.py` (file mới — kiểm tra end-to-end qua agent loop giả lập)

**Interfaces:** Không tạo interface mới — task xác nhận toàn bộ chuỗi Task 1-7 khớp nhau.

- [ ] **Step 1: Viết test end-to-end — CEO giao việc cho người chưa có trong danh bạ, AI tự đề xuất thêm + giao việc**

Tạo file `backend/tests/test_agent_add_employee_flow.py`:

```python
import pytest

from app.agent.llm_client import FakeLLMClient, StreamDone, ToolUseBlock
from app.agent.loop import run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Project, Role, User,
    Workspace,
)


@pytest.mark.asyncio
async def test_ceo_giao_viec_cho_nguoi_moi_qua_propose_actions(db_session):
    """Mô phỏng đúng luồng CEO báo lỗi: giao việc cho người chưa có trong danh sách.
    AI (giả lập) phải đề xuất gộp add_employee + assign_task qua propose_actions —
    không hỏi lại, không tự chạy tool luôn (add_employee không sensitive nhưng đối
    tượng phải SUY LUẬN nên qua propose_actions theo luật 3 mức trong system prompt)."""
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add(conv)
    await db_session.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="giao viec thiet ke landing page cho Duy Linh",
                      queue_position=1.0)
    db_session.add(req)
    await db_session.flush()
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    actions = [
        {"tool_name": "add_employee", "tool_input": {"full_name": "Duy Linh"},
         "display_text": "Thêm Duy Linh vào danh sách nhân viên"},
    ]
    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[ToolUseBlock(
            id="t1", name="propose_actions",
            input={"actions": actions, "reasoning": "Duy Linh chưa có trong danh sách"})],
            stop_reason="tool_use", input_tokens=1, output_tokens=1)],
    ])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    await db_session.refresh(req)
    assert req.status == ChatRequestStatus.awaiting_confirmation
    assert req.pending_action["kind"] == "proposal"
    assert req.pending_action["actions"][0]["tool_name"] == "add_employee"
```

- [ ] **Step 2: Chạy test, xác nhận pass (nếu fail, kiểm tra lại `validate_proposal_actions` không chặn nhầm `add_employee`)**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_agent_add_employee_flow.py -v`
Expected: PASS

- [ ] **Step 3: Chạy TOÀN BỘ backend test suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -q`
Expected: Tất cả PASS (trừ skip đã có từ trước). Nếu có fail, đọc traceback — khả năng cao là 1 file test khác còn sót gọi `create_employee`/`/invites`/`/auth/activate` mà Task 1-7 chưa quét hết; sửa file đó theo đúng pattern của Task 3/4/5/6 rồi chạy lại.

- [ ] **Step 4: Chạy grep xác nhận không còn sót chữ "mời...hệ thống" trong description tool hoặc system prompt**

Run: `cd backend && grep -rn "mời.*hệ thống\|vào hệ thống" app/agent/tools.py app/agent/loop.py app/services/resolver_service.py`
Expected: không có output (không match).

- [ ] **Step 5: Chạy FE typecheck lần cuối**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit code 0.

- [ ] **Step 6: Commit (nếu Step 3 có sửa thêm gì) hoặc chỉ commit test end-to-end**

```bash
cd "d:\8. AI\ai-assistant"
git add backend/tests/test_agent_add_employee_flow.py
git commit -m "test(agent): end-to-end CEO giao việc cho người mới -> propose add_employee+assign_task

Xác nhận toàn chuỗi Task 1-7 khớp nhau: model không nói 'mời vào hệ thống',
propose_actions chấp nhận add_employee, luồng gộp thêm+giao việc hoạt động
đúng theo mô tả tool mới.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Sau khi hoàn thành plan

- Redeploy backend (CI tự chạy khi push `backend/**` lên `main` — xem quy trình đã dùng trước đó).
- FE: chỉ cần reload Expo dev server để thấy nhãn mới.
- Nhắc CEO: nhân viên tạo TRƯỚC ngày làm plan này (có email + status pending + Invite cũ) vẫn còn trong DB nguyên vẹn, không cần dọn — họ chỉ đơn giản không kích hoạt được nữa (đã dự tính trong spec §6).
