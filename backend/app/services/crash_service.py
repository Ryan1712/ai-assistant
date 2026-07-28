"""crash_service.py — Service layer cho Crash Reporting (Sprint 1, Task 1.1)

Trách nhiệm:
- Tính fingerprint ổn định từ (source, message chuẩn hoá, dòng đầu stack).
- Cắt payload quá dài phía server (message ≤ 2000, stack ≤ 20000, context ≤ 8KB).
- Kiểm tra rate limit 60 bản ghi / user / 5 phút (in-memory trên app.state).
- Dedupe theo UniqueConstraint(workspace_id, client_event_id) — bắt IntegrityError.
- Trả về danh sách và summary cho CEO.

Quy ước:
- workspace_id/user_id lấy từ actor (JWT), KHÔNG từ body client.
- Quyền CEO kiểm ở service layer (require_ceo), không ở router.
"""

import hashlib
import json
import re
import time
import traceback
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, distinct, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CrashLog, CrashSource, CrashSeverity, User
from app.permissions import require_ceo
from app.schemas import CrashLogIn

# ─── Giới hạn cắt payload ────────────────────────────────────────────────────

_MAX_MESSAGE = 2_000
_MAX_STACK = 20_000
_MAX_CONTEXT_BYTES = 8_192
_RATE_LIMIT_RECORDS = 60
_RATE_LIMIT_WINDOW = 300  # 5 phút tính bằng giây


# ─── Fingerprint ─────────────────────────────────────────────────────────────

def _normalize_message(msg: str) -> str:
    """Chuẩn hoá message: xoá số/địa chỉ/UUID biến thiên để crash cùng loại
    có fingerprint giống nhau qua nhiều lần chạy.

    Hàm thuần — không có side-effect, có thể test riêng.
    """
    # Xoá UUID
    msg = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "<uuid>",
        msg,
        flags=re.IGNORECASE,
    )
    # Xoá địa chỉ bộ nhớ (0x...)
    msg = re.sub(r"0x[0-9a-fA-F]+", "<addr>", msg)
    # Xoá số nguyên đứng độc lập (tránh làm mất ý nghĩa tên lỗi)
    msg = re.sub(r"\b\d+\b", "<n>", msg)
    return msg.strip()


def compute_fingerprint(source: str, message: str, stack: str | None) -> str:
    """Tính fingerprint SHA-256 ổn định 64 ký tự hex.

    Hàm thuần — không có side-effect, có thể test riêng.
    Đầu vào:   source (string), message thô, stack thô (nullable).
    Đầu ra:    64 ký tự hex (SHA-256 full).
    """
    normalized = _normalize_message(message)
    # Chỉ lấy dòng đầu của stack để bỏ qua số dòng biến thiên
    first_stack_line = ""
    if stack:
        lines = stack.strip().splitlines()
        if lines:
            first_stack_line = lines[0]
    raw = f"{source}|{normalized}|{first_stack_line}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ─── Cắt payload ─────────────────────────────────────────────────────────────

def _truncate_context(ctx: dict | None) -> dict | None:
    """Đảm bảo context JSON ≤ 8 KB sau khi serialize.

    Chiến lược: nếu vượt giới hạn, cắt bớt list breadcrumbs (các phần tử đầu)
    cho đến khi vừa. Nếu vẫn quá → giữ breadcrumbs rỗng + extra còn lại.
    Không bao giờ raise exception — crash reporter không được gây crash.
    """
    if ctx is None:
        return None
    try:
        encoded = json.dumps(ctx, ensure_ascii=False).encode("utf-8")
        if len(encoded) <= _MAX_CONTEXT_BYTES:
            return ctx

        # Thử cắt breadcrumbs nếu có
        result = dict(ctx)
        crumbs = result.get("breadcrumbs")
        if isinstance(crumbs, list) and crumbs:
            # Cắt dần từ đầu (giữ lại breadcrumb mới nhất)
            while crumbs and len(json.dumps(result, ensure_ascii=False).encode()) > _MAX_CONTEXT_BYTES:
                crumbs = crumbs[1:]
            result["breadcrumbs"] = crumbs
            encoded = json.dumps(result, ensure_ascii=False).encode("utf-8")
            if len(encoded) <= _MAX_CONTEXT_BYTES:
                return result

        # Fallback: giữ breadcrumbs rỗng, chỉ giữ extra nếu còn đủ chỗ
        result["breadcrumbs"] = []
        if len(json.dumps(result, ensure_ascii=False).encode()) <= _MAX_CONTEXT_BYTES:
            return result

        # Trường hợp hiếm: context rỗng hoàn toàn
        return {}
    except Exception:
        # Không được để exception trong crash reporter
        return None


# ─── Rate limit (in-memory, lưu trên app.state) ─────────────────────────────

def check_rate_limit(rate_store: dict, user_id: uuid.UUID, n_items: int) -> None:
    """Kiểm tra rate limit 60 bản ghi / user / 5 phút.

    rate_store: dict lưu trên app.state (fresh mỗi lần create_app() — đảm bảo
        không lộ dữ liệu giữa các test).
    Nếu rate_store là None → fail-open (không chặn), không làm hỏng việc ghi log.
    Hàm KHÔNG async — đơn giản, không cần await.
    """
    if rate_store is None:
        return  # fail-open khi không có store (không bao giờ xảy ra bình thường)

    key = str(user_id)
    now = time.monotonic()

    entry = rate_store.get(key)
    if entry is None:
        rate_store[key] = {"count": n_items, "start": now}
        return

    # Kiểm tra xem cửa sổ 5 phút đã hết chưa
    if now - entry["start"] > _RATE_LIMIT_WINDOW:
        rate_store[key] = {"count": n_items, "start": now}
        return

    new_count = entry["count"] + n_items
    if new_count > _RATE_LIMIT_RECORDS:
        raise HTTPException(status_code=429, detail="rate_limit_exceeded")

    entry["count"] = new_count


# ─── ingest_batch ─────────────────────────────────────────────────────────────

async def ingest_batch(
    db: AsyncSession,
    actor: User,
    items: list[CrashLogIn],
    rate_store: dict,
) -> dict:
    """Nhận batch crash log, lưu vào DB.

    Quy trình:
    1. Kiểm tra rate limit (60 bản ghi / user / 5 phút).
    2. Với mỗi item: cắt payload, tính fingerprint nếu thiếu.
    3. Insert từng bản ghi; bắt IntegrityError → đếm vào duplicates.
    4. Trả về {"accepted": n, "duplicates": m}.

    workspace_id/user_id lấy từ actor (JWT) — KHÔNG tin body client.
    """
    # Kiểm tra rate limit trước khi xử lý
    check_rate_limit(rate_store, actor.id, len(items))

    accepted = 0
    duplicates = 0

    for item in items:
        # Cắt các trường text quá dài phía server (không 500, không lưu nguyên)
        message = item.message[:_MAX_MESSAGE]
        stack = item.stack[:_MAX_STACK] if item.stack else None
        component_stack = (
            item.component_stack[:_MAX_STACK] if item.component_stack else None
        )
        ctx = _truncate_context(item.context)

        # Dùng fingerprint client gửi nếu có, ngược lại tự tính
        fingerprint = item.fingerprint
        if not fingerprint:
            fingerprint = compute_fingerprint(
                source=item.source.value,
                message=message,
                stack=stack,
            )
        # Đảm bảo fingerprint không vượt String(64) — cắt nếu client gửi quá dài
        fingerprint = fingerprint[:64]

        log = CrashLog(
            workspace_id=actor.workspace_id,   # từ JWT
            user_id=actor.id,                   # từ JWT
            source=item.source,
            severity=item.severity,
            fingerprint=fingerprint,
            message=message,
            stack=stack,
            component_stack=component_stack,
            screen=item.screen,
            app_version=item.app_version,
            build_number=item.build_number,
            platform=item.platform,
            os_version=item.os_version,
            device_model=item.device_model,
            is_device=item.is_device,
            request_method=item.request_method,
            request_path=item.request_path,
            response_status=item.response_status,
            request_id=item.request_id,
            context=ctx,
            client_event_id=item.client_event_id,
            occurred_at=item.occurred_at,
        )
        db.add(log)
        try:
            # flush từng bản ghi để bắt IntegrityError ngay lập tức
            await db.flush()
            accepted += 1
        except IntegrityError:
            # UniqueConstraint(workspace_id, client_event_id) bị vi phạm → trùng
            await db.rollback()
            duplicates += 1

    # Commit toàn bộ batch sau khi xử lý hết
    await db.commit()
    return {"accepted": accepted, "duplicates": duplicates}


# ─── list_crashes (CEO only) ──────────────────────────────────────────────────

async def list_crashes(
    db: AsyncSession,
    actor: User,
    page: int = 1,
    size: int = 50,
    source: str | None = None,
    platform: str | None = None,
    fingerprint: str | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> dict:
    """Danh sách crash log — chỉ CEO.

    Luôn lọc theo workspace_id của actor (không bao giờ lộ log workspace khác).
    Sắp xếp mới nhất trước.
    """
    require_ceo(actor)

    stmt = select(CrashLog).where(CrashLog.workspace_id == actor.workspace_id)

    if source:
        stmt = stmt.where(CrashLog.source == source)
    if platform:
        stmt = stmt.where(CrashLog.platform == platform)
    if fingerprint:
        stmt = stmt.where(CrashLog.fingerprint == fingerprint)
    if from_dt:
        stmt = stmt.where(CrashLog.created_at >= from_dt)
    if to_dt:
        stmt = stmt.where(CrashLog.created_at <= to_dt)

    # Đếm tổng
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Lấy trang
    offset = (page - 1) * size
    stmt = stmt.order_by(CrashLog.created_at.desc()).offset(offset).limit(size)
    rows = (await db.execute(stmt)).scalars().all()

    return {
        "items": rows,
        "total": total,
        "page": page,
        "size": size,
    }


# ─── summarize (CEO only) ─────────────────────────────────────────────────────

async def summarize(
    db: AsyncSession,
    actor: User,
    source: str | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> dict:
    """Gom nhóm crash theo fingerprint — endpoint quan trọng nhất của sprint.

    Trả về: số lần xảy ra, số user bị ảnh hưởng, lần đầu, lần cuối,
    message mẫu, source. Sắp xếp theo số lần giảm dần.

    Chỉ CEO được gọi.
    """
    require_ceo(actor)

    stmt = (
        select(
            CrashLog.fingerprint,
            func.count(CrashLog.id).label("count"),
            func.count(distinct(CrashLog.user_id)).label("affected_users"),
            func.min(CrashLog.occurred_at).label("first_seen"),
            func.max(CrashLog.occurred_at).label("last_seen"),
            # Dùng min(message) làm "sample" — ổn định, không tuỳ ý
            func.min(CrashLog.message).label("sample_message"),
            # source của nhóm (lấy min — thực ra mọi bản ghi cùng fingerprint
            # thường cùng source; min cho kết quả ổn định)
            func.min(CrashLog.source).label("source"),
        )
        .where(CrashLog.workspace_id == actor.workspace_id)
    )

    if source:
        stmt = stmt.where(CrashLog.source == source)
    if from_dt:
        stmt = stmt.where(CrashLog.occurred_at >= from_dt)
    if to_dt:
        stmt = stmt.where(CrashLog.occurred_at <= to_dt)

    stmt = (
        stmt
        .group_by(CrashLog.fingerprint)
        .order_by(func.count(CrashLog.id).desc())
    )

    result = await db.execute(stmt)
    rows_raw = result.all()

    rows = [
        {
            "fingerprint": r.fingerprint,
            "count": r.count,
            "affected_users": r.affected_users,
            "first_seen": r.first_seen,
            "last_seen": r.last_seen,
            "sample_message": r.sample_message,
            "source": r.source,
        }
        for r in rows_raw
    ]
    return {"rows": rows}


# ─── log_be_exception (dùng bởi CrashCaptureMiddleware) ─────────────────────

async def log_be_exception(
    db: AsyncSession,
    exc: Exception,
    request_method: str,
    request_path: str,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Ghi một unhandled exception từ BE vào crash_logs với source=be_unhandled.

    Chỉ dùng nội bộ bởi CrashCaptureMiddleware — không gọi từ router.
    workspace_id/user_id phải được xác định bởi middleware (từ JWT hoặc sentinel).

    Hàm KHÔNG raise — mọi lỗi ghi log phải bị bắt phía caller.
    """
    # Lấy full traceback từ exception object (an toàn ngay cả khi exc không còn "current")
    tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    stack = "".join(tb_lines)[:_MAX_STACK]

    message = str(exc)[:_MAX_MESSAGE]
    fingerprint = compute_fingerprint(
        source=CrashSource.be_unhandled.value,
        message=message,
        stack=stack,
    )

    log = CrashLog(
        workspace_id=workspace_id,
        user_id=user_id,
        source=CrashSource.be_unhandled,
        severity=CrashSeverity.fatal,
        fingerprint=fingerprint,
        message=message,
        stack=stack,
        request_method=request_method.upper()[:16],
        request_path=request_path[:512],
        response_status=500,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(log)
    await db.commit()
