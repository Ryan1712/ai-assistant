"""Workspace snapshot (spec AI upgrade §5) — bức tranh công ty dạng text nén.

Kiến trúc: build DATA per-workspace (SQL aggregates, KHÔNG LLM) cache Redis TTL;
render TEXT per-actor tại request bằng visible_* của app/permissions.py (quyền
luôn tươi — data cache chung, không lộ vượt quyền). Lỗi bất kỳ → trả "" (snapshot
là tăng cường, không bao giờ được phá chat).

Refresh (deviation §5.2 đã chốt): lazy build-on-miss + TTL + invalidate() gọi từ
agent loop sau write-tool — thay cho worker nền/debounce arq (spec cho phép chọn
cách rẻ hơn).
"""
from __future__ import annotations

import abc
import logging
import uuid
from functools import lru_cache

logger = logging.getLogger(__name__)


class SnapshotStore(abc.ABC):
    @abc.abstractmethod
    async def get(self, key: str) -> str | None: ...

    @abc.abstractmethod
    async def set(self, key: str, value: str, ttl: int) -> None: ...

    @abc.abstractmethod
    async def delete(self, key: str) -> None: ...


class FakeSnapshotStore(SnapshotStore):
    """Test double: dict trong RAM, không TTL thật; .deleted ghi lại invalidation."""

    def __init__(self):
        self.data: dict[str, str] = {}
        self.deleted: list[str] = []

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ttl: int) -> None:
        self.data[key] = value

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)
        self.deleted.append(key)


class RedisSnapshotStore(SnapshotStore):
    def __init__(self, redis):
        self._redis = redis

    async def get(self, key: str) -> str | None:
        raw = await self._redis.get(key)
        if raw is None:
            return None
        return raw.decode() if isinstance(raw, bytes) else raw

    async def set(self, key: str, value: str, ttl: int) -> None:
        await self._redis.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)


@lru_cache
def get_snapshot_store() -> SnapshotStore:
    import redis.asyncio as redis_asyncio

    from app.config import get_settings

    # Timeout ngắn: redis chết thì get_snapshot_text bắt exception trả "" —
    # không được treo request chat vài chục giây chờ TCP.
    client = redis_asyncio.from_url(get_settings().redis_url,
                                    socket_connect_timeout=2, socket_timeout=2)
    return RedisSnapshotStore(client)


def _key(workspace_id: uuid.UUID | str) -> str:
    return f"snapshot:{workspace_id}"
