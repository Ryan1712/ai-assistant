"""crash_capture.py — CrashCaptureMiddleware (Task 1.2)

Bắt mọi unhandled exception từ FastAPI endpoint:
- Giải mã được JWT → ghi vào crash_logs (source=be_unhandled, severity=fatal)
  bằng session DB riêng (session của request đã hỏng sau exception).
- Không giải mã được JWT → ghi một dòng log có cấu trúc ra stderr,
  KHÔNG ghi DB (workspace_id/user_id là NOT NULL + FK, không có dữ liệu).
  Xem ADR-005 trong .project/documentation/architecture.md.

Lưu ý kỹ thuật:
- HTTPException / RequestValidationError là luồng nghiệp vụ bình thường → không ghi.
- Lỗi ghi log không được nuốt / biến đổi response gốc — bọc try/except riêng.
- Không có route hay nhánh nào theo môi trường (pytest/sys.modules).
  Route test ném lỗi thuộc về file test, không thuộc về production code.
"""

import logging
import traceback
import uuid

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app import security
from app.db import get_db

_logger = logging.getLogger(__name__)


class CrashCaptureMiddleware(BaseHTTPMiddleware):
    """Middleware bắt unhandled exception, ghi vào crash_logs (source=be_unhandled).

    Được đăng ký trong main.py qua app.add_middleware(CrashCaptureMiddleware).
    Stack (ngoài → trong): ServerError → CORS → [đây] → ExceptionMiddleware → Router.
    """

    # ─── Dispatch chính ───────────────────────────────────────────────────────

    async def dispatch(self, request: Request, call_next) -> Response:
        """Forward request. Nếu có unhandled exception → log + trả JSON 500."""
        try:
            return await call_next(request)
        except (HTTPException, RequestValidationError):
            # Luồng nghiệp vụ bình thường — re-raise để Starlette xử lý.
            raise
        except Exception as exc:
            # Exception thật sự chưa được xử lý → ghi log, trả 500 JSON
            await self._log_exception(request, exc)
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal Server Error"},
                headers={"content-type": "application/json"},
            )

    # ─── Ghi log ─────────────────────────────────────────────────────────────

    async def _log_exception(self, request: Request, exc: Exception) -> None:
        """Ghi crash log. Lỗi ghi log → im lặng (không raise).

        Nhánh JWT hợp lệ: ghi vào crash_logs bằng session DB mới, độc lập.
        Nhánh không có JWT: ghi một dòng cấu trúc ra stderr (ADR-005).
        """
        try:
            ids = self._extract_ids_from_jwt(request)
            if ids is None:
                # Không giải mã được JWT → ghi ra stderr, không ghi DB
                self._log_unauthenticated_to_stderr(request, exc)
                return

            workspace_id, user_id = ids

            # Ghi vào DB bằng session mới, hoàn toàn độc lập với session request
            from app.services import crash_service  # import muộn → monkeypatch hoạt động

            get_db_fn = request.app.dependency_overrides.get(get_db, get_db)
            gen = get_db_fn()
            try:
                session = await gen.__anext__()
                try:
                    await crash_service.log_be_exception(
                        db=session,
                        exc=exc,
                        request_method=request.method,
                        request_path=str(request.url.path),
                        workspace_id=workspace_id,
                        user_id=user_id,
                    )
                except Exception:
                    # Ghi log thất bại (DB down, …) → im lặng
                    pass
            finally:
                try:
                    await gen.aclose()
                except Exception:
                    pass
        except Exception:
            # Lớp bảo vệ cuối — không bao giờ raise từ đây
            pass

    def _log_unauthenticated_to_stderr(self, request: Request, exc: Exception) -> None:
        """Ghi crash không xác định được danh tính ra stderr có cấu trúc.

        Dùng logging chuẩn Python (docker logs bắt được). Không ghi DB vì
        workspace_id/user_id là NOT NULL + FK — không có dữ liệu để gắn.
        Theo ADR-005: path, method, fingerprint, traceback.
        """
        from app.services.crash_service import compute_fingerprint
        from app.models import CrashSource

        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        fingerprint = compute_fingerprint(
            source=CrashSource.be_unhandled.value,
            message=str(exc),
            stack=tb,
        )
        _logger.error(
            "be_unhandled_no_identity | path=%s method=%s fingerprint=%s | %s",
            request.url.path,
            request.method,
            fingerprint,
            tb,
        )

    # ─── Giải mã JWT ─────────────────────────────────────────────────────────

    def _extract_ids_from_jwt(
        self, request: Request
    ) -> tuple[uuid.UUID, uuid.UUID] | None:
        """Lấy workspace_id và user_id từ JWT Authorization header.

        Chỉ dùng để GẮN NHÃN log — không xác thực (không query DB, không kiểm
        trạng thái user). Trả None nếu không giải mã được (thiếu header, token
        hỏng, hết hạn, thiếu claim, …).
        """
        try:
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                return None
            token = auth[7:]
            payload = security.decode_access_token(token)
            workspace_id = uuid.UUID(payload["ws"])
            user_id = uuid.UUID(payload["sub"])
            return workspace_id, user_id
        except Exception:
            return None
