from __future__ import annotations

import abc
import asyncio
import json
import uuid
from functools import lru_cache
from typing import AsyncIterator


class EventPublisher(abc.ABC):
    @abc.abstractmethod
    async def publish(self, conversation_id: uuid.UUID, event: dict) -> None:
        ...

    @abc.abstractmethod
    def subscribe(self, conversation_id: uuid.UUID) -> AsyncIterator[dict]:
        ...


class FakeEventPublisher(EventPublisher):
    """Test double: giữ lịch sử publish + fan-out cho subscriber qua asyncio.Queue."""

    def __init__(self):
        self.events: list[tuple[uuid.UUID, dict]] = []
        self._queues: dict[uuid.UUID, list[asyncio.Queue]] = {}

    async def publish(self, conversation_id: uuid.UUID, event: dict) -> None:
        self.events.append((conversation_id, event))
        for q in self._queues.get(conversation_id, []):
            await q.put(event)

    def subscribe(self, conversation_id: uuid.UUID) -> AsyncIterator[dict]:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues.setdefault(conversation_id, []).append(queue)

        async def _gen():
            while True:
                event = await queue.get()
                if event is None:
                    return
                yield event

        return _gen()

    async def close(self, conversation_id: uuid.UUID) -> None:
        for q in self._queues.get(conversation_id, []):
            await q.put(None)


class RedisEventPublisher(EventPublisher):
    def __init__(self, redis):
        self._redis = redis

    async def publish(self, conversation_id: uuid.UUID, event: dict) -> None:
        await self._redis.publish(f"conv:{conversation_id}", json.dumps(event, default=str))

    async def subscribe(self, conversation_id: uuid.UUID) -> AsyncIterator[dict]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(f"conv:{conversation_id}")
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                yield json.loads(message["data"])
        finally:
            await pubsub.unsubscribe(f"conv:{conversation_id}")


@lru_cache
def get_event_publisher() -> EventPublisher:
    import redis.asyncio as redis_asyncio

    from app.config import get_settings

    redis_client = redis_asyncio.from_url(get_settings().redis_url)
    return RedisEventPublisher(redis_client)
