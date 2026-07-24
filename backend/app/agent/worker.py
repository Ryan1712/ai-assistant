from __future__ import annotations

import logging
import uuid

from arq.connections import RedisSettings
from arq.cron import cron
from arq.worker import func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.llm_client import get_llm_client
from app.agent.loop import run_agent_loop, run_deep_ack_turn
from app.agent.publisher import get_event_publisher
from app.agent.router import classify_route, tool_names_for_route
from app.agent.summarizer import maybe_compress_history
from app.agent.tools import TOOL_GROUPS
from app.config import get_settings
from app.models import ChatRequest, ChatRequestStatus, Conversation
from app.services import directive_service, report_schedule_service, voice_service, work_service
from app.services.notify import notify

logger = logging.getLogger(__name__)

# Phase 4 §8.2 (đường sâu): model_smart + extended thinking chạy nhiều vòng/tốn
# token hơn hẳn Haiku fast path -> trần cao hơn hẳn MAX_ITERATIONS=25/
# MAX_DURATION_SECONDS=240 (loop.py). 800s < timeout=900 job (đăng ký bên dưới),
# giữ đúng tỉ lệ an toàn "loop tự dừng trước khi arq giết job" như fast path.
DEEP_MAX_ITERATIONS = 40
DEEP_MAX_DURATION_SECONDS = 800
DEEP_THINKING_BUDGET = 8000


async def process_conversation(ctx: dict, conversation_id: uuid.UUID) -> None:
    """arq job: xử lý lần lượt mọi chat_request `queued` của 1 conversation tới khi hết."""
    session_factory = ctx["session_factory"]
    llm = ctx["llm_client"]
    publisher = ctx["event_publisher"]
    is_cancelled = ctx["is_cancelled"]

    while True:
        async with session_factory() as db:
            paused = (await db.execute(
                select(ChatRequest.id).where(
                    ChatRequest.conversation_id == conversation_id,
                    ChatRequest.status == ChatRequestStatus.awaiting_confirmation,
                ).limit(1)
            )).scalar_one_or_none()
            if paused is not None:
                # Mot request khac trong cung conversation dang cho nguoi dung xac
                # nhan tool nhay cam (vd lock_user): tool_use cua no chua co
                # tool_result di kem. Neu chay tiep 1 queued request khac ngay bay
                # gio, message cua request do se chen vao GIUA tool_use va
                # tool_result trong lich su hoi thoai (run_agent_loop luon load toan
                # bo Message cua conversation) — vi pham yeu cau cua Anthropic API la
                # tool_result phai theo ngay sau tool_use. Vi vay dung han xu ly toan
                # bo queue cua conversation nay cho toi khi resolve_confirmation duoc
                # goi (chuyen request dang paused ve lai `queued` va enqueue lai job).
                return
            conv = await db.get(Conversation, conversation_id)
            if conv is not None and conv.queue_held:
                # 5.7: mat mang/dong app -> khong tu chay tiep; cho nguoi dung go
                # "tiep tuc cong viec" (send_message clear co + enqueue lai job).
                return
            req = (await db.execute(
                select(ChatRequest).where(
                    ChatRequest.conversation_id == conversation_id,
                    ChatRequest.status == ChatRequestStatus.queued,
                ).order_by(ChatRequest.queue_position.asc()).limit(1)
            )).scalar_one_or_none()
            if req is None:
                return
            if req.voice_note_id is not None:
                # Đính kèm ghi âm: transcribe trước (STT thật) để agent thấy nội dung.
                # Lỗi STT không được giết job — request vẫn chạy, model thấy dòng
                # "[Đính kèm ghi âm...]" và tự báo transcript chưa có.
                try:
                    await voice_service.inject_transcript_for_request(db, req)
                except Exception:
                    logger.exception("inject transcript failed for request %s", req.id)
                    await db.rollback()
            # Phase 5: nén hội thoại cũ trước khi chạy loop (dùng model_fast = llm).
            # Lỗi nén không được giết job — request vẫn chạy với summary cũ.
            try:
                await maybe_compress_history(db, conv, llm)
            except Exception:
                logger.exception("nen rolling summary fail cho conversation %s",
                                 conversation_id)
                await db.rollback()
            # Router (Phase 4 §8.1) - chi phan loai 1 lan luc pickup dau tien cua
            # request nay (status queued -> chuyen ngay khoi queued ben trong
            # run_deep_ack_turn/run_agent_loop, khong bao gio duoc chon lai o day).
            group = await classify_route(req.content, llm)
            if group == "deep":
                await run_deep_ack_turn(db, req, llm, publisher, is_cancelled=is_cancelled)
                await ctx["arq_pool"].enqueue_job(
                    "run_deep_analysis", req.id, _job_id=f"deep:{req.id}")
            else:
                await run_agent_loop(db, req, llm, publisher, is_cancelled=is_cancelled,
                                     tool_names=tool_names_for_route(group))


async def run_deep_analysis(ctx: dict, chat_request_id: uuid.UUID) -> None:
    """arq job (Phase 4 §8.2 Task 7): phân tích nền cho 1 chat_request đã qua lượt
    ack (`run_deep_ack_turn`, status=deep_running) — model_smart + extended
    thinking, toolset insight (+core). Guard: chỉ chạy nếu request VẪN đang
    deep_running (tránh reset nhầm request đã bị hủy/xử lý xong bởi luồng khác
    trước khi job này tới lượt)."""
    async with ctx["session_factory"]() as db:
        req = await db.get(ChatRequest, chat_request_id)
        if req is None or req.status != ChatRequestStatus.deep_running:
            return
        tool_names = set(TOOL_GROUPS["core"]) | set(TOOL_GROUPS["insight"])
        await run_agent_loop(
            db, req, ctx["llm_client_smart"], ctx["event_publisher"],
            is_cancelled=ctx["is_cancelled"],
            route="deep", tool_names=tool_names,
            max_iterations=DEEP_MAX_ITERATIONS,
            max_duration_seconds=DEEP_MAX_DURATION_SECONDS,
        )
        if req.status == ChatRequestStatus.done:
            # Chi bao "da xong" khi THAT SU xong (khong bao cancelled/failed) -
            # nguoi gui khong ngoi cho 30s-800s, can duoc nhac qua push khi ket
            # qua san sang.
            await notify(db, workspace_id=req.workspace_id, recipient_id=req.user_id,
                        type="deep_analysis_done",
                        payload={"chat_request_id": str(req.id),
                                 "conversation_id": str(req.conversation_id)})
            await db.commit()


async def enqueue_conversation(arq_pool, conversation_id: uuid.UUID):
    return await arq_pool.enqueue_job("process_conversation", conversation_id,
                                      _job_id=f"conv:{conversation_id}")


async def check_report_schedules(ctx: dict) -> None:
    """arq cron (mỗi phút): quét ReportSchedule tới hạn, sinh báo cáo + notify
    (funtional-plan 6.5 nâng cao — báo cáo định kỳ tự động, gói Advanced)."""
    async with ctx["session_factory"]() as db:
        await report_schedule_service.run_due_schedules(db)


async def check_task_deadlines(ctx: dict) -> None:
    """arq cron (mỗi phút): quét task sắp tới hạn trong 24h, notify assignees
    (funtional-plan 6.6 "sắp tới hạn")."""
    async with ctx["session_factory"]() as db:
        await work_service.notify_upcoming_deadlines(db)


async def check_directive_escalations(ctx: dict) -> None:
    """arq cron (mỗi phút): nhắc/escalate Directive chưa xác nhận sau 24h/48h
    (Phase 3 §7.3)."""
    async with ctx["session_factory"]() as db:
        await directive_service.escalate_overdue(db)


async def transcribe_voice_note(ctx: dict, voice_note_id: uuid.UUID) -> None:
    """arq job: chạy STT cho 1 voice note (enqueue sau upload hoặc từ POST
    /voice-notes/{id}/transcribe — Task 16)."""
    async with ctx["session_factory"]() as db:
        await voice_service.transcribe_note(db, voice_note_id)


async def _is_cancelled_redis(ctx: dict, request_id: uuid.UUID) -> bool:
    return bool(await ctx["redis"].exists(f"cancel:{request_id}"))


async def _startup(ctx: dict) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    ctx["engine"] = engine
    ctx["session_factory"] = async_sessionmaker(engine, expire_on_commit=False)
    ctx["llm_client"] = get_llm_client()
    ctx["llm_client_smart"] = get_llm_client(settings.model_smart, DEEP_THINKING_BUDGET)
    ctx["event_publisher"] = get_event_publisher()
    import redis.asyncio as redis_asyncio
    ctx["redis"] = redis_asyncio.from_url(settings.redis_url)
    ctx["is_cancelled"] = lambda request_id: _is_cancelled_redis(ctx, request_id)
    from arq import create_pool
    # process_conversation can bo pool arq rieng de tu enqueue job run_deep_analysis
    # (job noi tiep) - khac ctx["redis"] (client thuan, chi dung cho is_cancelled).
    ctx["arq_pool"] = await create_pool(RedisSettings.from_dsn(settings.redis_url))


async def _shutdown(ctx: dict) -> None:
    await ctx["engine"].dispose()
    await ctx["redis"].close()
    await ctx["arq_pool"].close()


class WorkerSettings:
    functions = [process_conversation, transcribe_voice_note,
                func(run_deep_analysis, timeout=900)]
    cron_jobs = [cron(check_report_schedules, second=0), cron(check_task_deadlines, second=0),
                cron(check_directive_escalations, second=0)]
    on_startup = _startup
    on_shutdown = _shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    # max_jobs = semaphore giới hạn số conversation chạy Claude call đồng thời (theo
    # design spec) — trước đây không set nên nhận default ngầm định của arq (10); giờ
    # khai báo tường minh để dễ tune. job_timeout đủ lớn so với thời gian thực tế của
    # MAX_ITERATIONS (app/agent/loop.py) để chính cap đó là thứ chặn vòng lặp chạy vô
    # hạn, không phải arq giết job bằng CancelledError (BaseException, lọt qua
    # except Exception trong run_agent_loop, kẹt request ở status=running vĩnh viễn).
    max_jobs = 10
    job_timeout = 600
    # keep_result=0: job_id cố định conv:{id} chỉ để dedup khi job ĐANG chạy.
    # Nếu giữ result (default 3600s), enqueue cùng job_id sau khi job xong bị arq
    # từ chối lặng lẽ → tin nhắn thứ 2 trong 1 giờ không bao giờ được xử lý
    # (bug tìm ra khi smoke test LLM thật 2026-07-13).
    keep_result = 0
