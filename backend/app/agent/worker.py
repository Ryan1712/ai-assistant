from __future__ import annotations

import uuid

from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.llm_client import get_llm_client
from app.agent.loop import run_agent_loop
from app.agent.publisher import get_event_publisher
from app.config import get_settings
from app.models import ChatRequest, ChatRequestStatus


async def process_conversation(ctx: dict, conversation_id: uuid.UUID) -> None:
    """arq job: xử lý lần lượt mọi chat_request `queued` của 1 conversation tới khi hết."""
    session_factory = ctx["session_factory"]
    llm = ctx["llm_client"]
    publisher = ctx["event_publisher"]
    is_cancelled = ctx["is_cancelled"]

    while True:
        async with session_factory() as db:
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
    on_startup = _startup
    on_shutdown = _shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
