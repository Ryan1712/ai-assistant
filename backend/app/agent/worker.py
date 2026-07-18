from __future__ import annotations

import uuid

from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.llm_client import get_llm_client
from app.agent.loop import run_agent_loop
from app.agent.publisher import get_event_publisher
from app.config import get_settings
from app.models import ChatRequest, ChatRequestStatus, Conversation
from app.services import report_schedule_service, work_service


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
            await run_agent_loop(db, req, llm, publisher, is_cancelled=is_cancelled)


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


async def _is_cancelled_redis(ctx: dict, request_id: uuid.UUID) -> bool:
    return bool(await ctx["redis"].exists(f"cancel:{request_id}"))


async def _startup(ctx: dict) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    ctx["engine"] = engine
    ctx["session_factory"] = async_sessionmaker(engine, expire_on_commit=False)
    ctx["llm_client"] = get_llm_client()
    ctx["event_publisher"] = get_event_publisher()
    import redis.asyncio as redis_asyncio
    ctx["redis"] = redis_asyncio.from_url(settings.redis_url)
    ctx["is_cancelled"] = lambda request_id: _is_cancelled_redis(ctx, request_id)


async def _shutdown(ctx: dict) -> None:
    await ctx["engine"].dispose()
    await ctx["redis"].close()


class WorkerSettings:
    functions = [process_conversation]
    cron_jobs = [cron(check_report_schedules, second=0), cron(check_task_deadlines, second=0)]
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
