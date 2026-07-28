"""
test_crash_middleware.py — Tests cho CrashCaptureMiddleware (ADR-005)

Coverage:
  1. JWT hợp lệ → endpoint ném exception → có bản ghi crash_logs với
     source=be_unhandled, severity=fatal, đúng workspace_id/user_id từ JWT,
     có traceback trong stack, có request_path/request_method, response_status=500
  2. Thiếu JWT / JWT hỏng → KHÔNG ghi crash_logs, client nhận 500, ghi ra logger
  3. HTTPException 404/401/422 → KHÔNG ghi log, status giữ nguyên mã gốc
  4. Ghi log thất bại (monkeypatch) → client vẫn nhận 500 của lỗi gốc
  5. Request thành công bình thường → không phát sinh ghi crash_logs thêm

Kiến trúc quan trọng:
  Route test ném lỗi được thêm vào app trong fixture của file này,
  KHÔNG phải trong production code. Production code không chứa bất kỳ
  nhánh nào theo sys.modules/pytest.
"""

import uuid

import httpx
import pytest
from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import create_app


# ─── Thông tin đăng ký CEO cho test cần JWT ──────────────────────────────────

_SIGNUP = {
    "workspace_name": "Crash Test Corp",
    "email": "ceo@crashtest.vn",
    "password": "secret123",
    "full_name": "Crash CEO",
    "device_uuid": "dev-crash-test",
    "device_name": "",
}


# ─── Fixture: engine + session + app riêng có route test ─────────────────────

@pytest.fixture
async def crash_engine():
    """Engine SQLite in-memory riêng cho test crash middleware.

    Dùng StaticPool để mọi session cùng thấy dữ liệu lẫn nhau
    (bắt buộc với SQLite in-memory).
    """
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def crash_session(crash_engine):
    """Session DB dùng để kiểm tra kết quả ghi log sau mỗi test."""
    maker = async_sessionmaker(crash_engine, expire_on_commit=False)
    async with maker() as session:
        yield session


def _add_test_routes(app) -> None:
    """Thêm route test vào app — chỗ đúng, KHÔNG phải production code.

    Route ném lỗi chỉ tồn tại trong test. Production code không chứa nhánh
    nào dành riêng cho pytest (sys.modules / môi trường).
    """
    router = APIRouter()

    @router.get("/api/v1/test-crash")
    async def crash_route():
        raise RuntimeError("Unhandled exception cố ý — dùng trong test")

    @router.get("/api/v1/test-404")
    async def not_found_route():
        raise HTTPException(status_code=404, detail="Not Found")

    @router.get("/api/v1/test-422")
    async def validation_error_route():
        raise HTTPException(status_code=422, detail="Unprocessable Entity")

    @router.get("/api/v1/test-401")
    async def unauthorized_route():
        raise HTTPException(status_code=401, detail="Unauthorized")

    @router.get("/api/v1/test-ok")
    async def ok_route():
        return {"status": "ok"}

    app.include_router(router)


@pytest.fixture
async def crash_client(crash_engine):
    """App riêng có CrashCaptureMiddleware + route test ném lỗi.

    Route test được thêm vào app ở đây (trong fixture), không phải
    trong production code. Cách này đúng kiến trúc theo ADR-005.
    """
    app = create_app()
    maker = async_sessionmaker(crash_engine, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    _add_test_routes(app)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _get_ceo_headers(
    client,
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    """Đăng ký workspace, trả về (headers, workspace_id, user_id) từ JWT."""
    from app import security

    resp = await client.post("/api/v1/auth/signup-workspace", json=_SIGNUP)
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    payload = security.decode_access_token(token)
    workspace_id = uuid.UUID(payload["ws"])
    user_id = uuid.UUID(payload["sub"])
    return {"Authorization": f"Bearer {token}"}, workspace_id, user_id


# ─── Test 1: JWT hợp lệ → ghi crash_logs ─────────────────────────────────────

@pytest.mark.asyncio
async def test_jwt_valid_creates_be_unhandled_log(crash_client, crash_session):
    """Request có JWT hợp lệ → endpoint ném exception → có bản ghi be_unhandled.

    Kiểm tra: source, severity, workspace_id, user_id, stack, path, method,
    response_status — tất cả phải khớp ADR-005.
    """
    headers, expected_ws, expected_uid = await _get_ceo_headers(crash_client)

    resp = await crash_client.get("/api/v1/test-crash", headers=headers)

    # Client phải nhận 500 JSON
    assert resp.status_code == 500
    assert "application/json" in resp.headers.get("content-type", "")

    from app.models import CrashLog, CrashSeverity, CrashSource

    rows = (
        await crash_session.execute(
            select(CrashLog).where(CrashLog.source == CrashSource.be_unhandled)
        )
    ).scalars().all()

    assert len(rows) == 1, "Phải có đúng 1 bản ghi be_unhandled"
    crash = rows[0]

    assert crash.severity == CrashSeverity.fatal, "severity phải là fatal"
    assert crash.workspace_id == expected_ws, "workspace_id phải lấy từ JWT"
    assert crash.user_id == expected_uid, "user_id phải lấy từ JWT"
    assert crash.stack, "Phải có stack trace"
    assert "RuntimeError" in crash.stack or "Unhandled exception" in crash.stack
    assert crash.request_path and "/test-crash" in crash.request_path
    assert crash.request_method and crash.request_method.upper() == "GET"
    assert crash.response_status == 500


# ─── Test 2a: Không có JWT → không ghi DB, ghi stderr ───────────────────────

@pytest.mark.asyncio
async def test_no_jwt_no_db_record_but_logged(crash_client, crash_session, caplog):
    """Request không có JWT → KHÔNG ghi crash_logs, client nhận 500, ghi ra logger."""
    import logging

    from app.models import CrashLog

    with caplog.at_level(logging.ERROR, logger="app.middleware.crash_capture"):
        resp = await crash_client.get("/api/v1/test-crash")

    # Client phải vẫn nhận 500 JSON
    assert resp.status_code == 500
    assert "application/json" in resp.headers.get("content-type", "")

    # Không có bản ghi trong crash_logs
    rows = (await crash_session.execute(select(CrashLog))).scalars().all()
    assert len(rows) == 0, "Thiếu JWT → KHÔNG được ghi vào crash_logs"

    # Phải có ghi ra logger với tag be_unhandled_no_identity
    assert any(
        "be_unhandled_no_identity" in msg for msg in caplog.messages
    ), "Phải ghi be_unhandled_no_identity ra logger khi thiếu JWT"


# ─── Test 2b: JWT hỏng → không ghi DB, ghi stderr ───────────────────────────

@pytest.mark.asyncio
async def test_bad_jwt_no_db_record_but_logged(crash_client, crash_session, caplog):
    """Request JWT không hợp lệ → KHÔNG ghi crash_logs, client nhận 500, ghi ra logger."""
    import logging

    from app.models import CrashLog

    bad_headers = {"Authorization": "Bearer token.khong.hop.le"}
    with caplog.at_level(logging.ERROR, logger="app.middleware.crash_capture"):
        resp = await crash_client.get("/api/v1/test-crash", headers=bad_headers)

    assert resp.status_code == 500
    assert "application/json" in resp.headers.get("content-type", "")

    rows = (await crash_session.execute(select(CrashLog))).scalars().all()
    assert len(rows) == 0, "JWT hỏng → KHÔNG được ghi vào crash_logs"

    assert any(
        "be_unhandled_no_identity" in msg for msg in caplog.messages
    ), "Phải ghi ra logger khi JWT hỏng"


# ─── Test 3: HTTPException không bị ghi log, status giữ nguyên ──────────────

@pytest.mark.asyncio
async def test_http_exception_404_not_logged_and_status_preserved(crash_client, crash_session):
    """HTTPException 404 KHÔNG được ghi vào crash_logs; status code giữ nguyên 404."""
    from app.models import CrashLog

    count_before = len((await crash_session.execute(select(CrashLog))).scalars().all())
    resp = await crash_client.get("/api/v1/test-404")

    assert resp.status_code == 404, "Status phải giữ nguyên 404"
    count_after = len((await crash_session.execute(select(CrashLog))).scalars().all())
    assert count_after == count_before, "HTTPException 404 không được ghi crash log"


@pytest.mark.asyncio
async def test_http_exception_401_not_logged_and_status_preserved(crash_client, crash_session):
    """HTTPException 401 KHÔNG được ghi vào crash_logs; status code giữ nguyên 401."""
    from app.models import CrashLog

    count_before = len((await crash_session.execute(select(CrashLog))).scalars().all())
    resp = await crash_client.get("/api/v1/test-401")

    assert resp.status_code == 401, "Status phải giữ nguyên 401"
    count_after = len((await crash_session.execute(select(CrashLog))).scalars().all())
    assert count_after == count_before, "HTTPException 401 không được ghi crash log"


@pytest.mark.asyncio
async def test_http_exception_422_not_logged_and_status_preserved(crash_client, crash_session):
    """HTTPException 422 KHÔNG được ghi vào crash_logs; status code giữ nguyên 422."""
    from app.models import CrashLog

    count_before = len((await crash_session.execute(select(CrashLog))).scalars().all())
    resp = await crash_client.get("/api/v1/test-422")

    assert resp.status_code == 422, "Status phải giữ nguyên 422"
    count_after = len((await crash_session.execute(select(CrashLog))).scalars().all())
    assert count_after == count_before, "HTTPException 422 không được ghi crash log"


# ─── Test 4: Ghi log thất bại → vẫn trả 500 lỗi gốc ────────────────────────

@pytest.mark.asyncio
async def test_log_failure_does_not_swallow_500(crash_client, monkeypatch):
    """Ghi log thất bại (monkeypatch) → client vẫn nhận 500, không bị biến thành lỗi khác.

    Dùng JWT hợp lệ để đi vào nhánh ghi DB, rồi patch log_be_exception để ném lỗi.
    Middleware phải im lặng bắt lỗi đó và vẫn trả 500 của lỗi gốc.
    """
    headers, _, _ = await _get_ceo_headers(crash_client)

    from app.services import crash_service

    async def _fake_log(*args, **kwargs):
        raise RuntimeError("DB lỗi tạm thời — giả lập ghi log thất bại")

    monkeypatch.setattr(crash_service, "log_be_exception", _fake_log)

    resp = await crash_client.get("/api/v1/test-crash", headers=headers)
    assert resp.status_code == 500, "Ghi log thất bại không được thay đổi status code"
    assert "application/json" in resp.headers.get("content-type", "")


# ─── Test 5: Request thành công → không phát sinh ghi DB thêm ───────────────

@pytest.mark.asyncio
async def test_successful_request_no_extra_db_write(crash_client, crash_session):
    """Request thành công bình thường → không phát sinh ghi thêm vào crash_logs."""
    from app.models import CrashLog

    count_before = len((await crash_session.execute(select(CrashLog))).scalars().all())

    resp = await crash_client.get("/api/v1/test-ok")
    assert resp.status_code == 200

    count_after = len((await crash_session.execute(select(CrashLog))).scalars().all())
    assert count_after == count_before, (
        "Request thành công không được ghi thêm vào crash_logs"
    )
