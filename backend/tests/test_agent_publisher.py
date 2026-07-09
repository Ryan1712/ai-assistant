import asyncio
import uuid

import pytest

from app.agent.publisher import FakeEventPublisher


@pytest.mark.asyncio
async def test_publish_records_history():
    pub = FakeEventPublisher()
    conv_id = uuid.uuid4()
    await pub.publish(conv_id, {"type": "token", "text": "hi"})
    assert pub.events == [(conv_id, {"type": "token", "text": "hi"})]


@pytest.mark.asyncio
async def test_subscribe_receives_events_published_after_subscribing():
    pub = FakeEventPublisher()
    conv_id = uuid.uuid4()
    received = []

    async def reader():
        async for event in pub.subscribe(conv_id):
            received.append(event)

    task = asyncio.create_task(reader())
    await asyncio.sleep(0)  # để subscriber đăng ký queue trước khi publish
    await pub.publish(conv_id, {"type": "token", "text": "a"})
    await pub.publish(conv_id, {"type": "request_done"})
    await pub.close(conv_id)
    await asyncio.wait_for(task, timeout=1)

    assert received == [{"type": "token", "text": "a"}, {"type": "request_done"}]


@pytest.mark.asyncio
async def test_subscribers_are_scoped_per_conversation():
    pub = FakeEventPublisher()
    conv_a, conv_b = uuid.uuid4(), uuid.uuid4()
    received = []

    async def reader():
        async for event in pub.subscribe(conv_a):
            received.append(event)

    task = asyncio.create_task(reader())
    await asyncio.sleep(0)
    await pub.publish(conv_b, {"type": "token", "text": "khac conversation"})
    await pub.close(conv_a)
    await asyncio.wait_for(task, timeout=1)
    assert received == []


import json


class _FakeRedisPubSub:
    def __init__(self, messages):
        self._messages = messages
        self.subscribed_channels = []
        self.unsubscribed_channels = []

    async def subscribe(self, channel):
        self.subscribed_channels.append(channel)

    async def unsubscribe(self, channel):
        self.unsubscribed_channels.append(channel)

    async def listen(self):
        for m in self._messages:
            yield m


class _FakeRedis:
    def __init__(self, pubsub_messages=None):
        self.published = []
        self._pubsub = _FakeRedisPubSub(pubsub_messages or [])

    async def publish(self, channel, data):
        self.published.append((channel, data))

    def pubsub(self):
        return self._pubsub


@pytest.mark.asyncio
async def test_redis_event_publisher_publishes_json_to_conversation_channel():
    from app.agent.publisher import RedisEventPublisher

    redis = _FakeRedis()
    pub = RedisEventPublisher(redis)
    conv_id = uuid.uuid4()
    await pub.publish(conv_id, {"type": "token", "text": "hi"})

    channel, data = redis.published[0]
    assert channel == f"conv:{conv_id}"
    assert json.loads(data) == {"type": "token", "text": "hi"}


@pytest.mark.asyncio
async def test_redis_event_publisher_subscribe_yields_decoded_events():
    from app.agent.publisher import RedisEventPublisher

    conv_id = uuid.uuid4()
    messages = [
        {"type": "subscribe", "data": 1},
        {"type": "message", "data": json.dumps({"type": "token", "text": "a"})},
        {"type": "message", "data": json.dumps({"type": "request_done"})},
    ]
    redis = _FakeRedis(pubsub_messages=messages)
    pub = RedisEventPublisher(redis)

    received = [e async for e in pub.subscribe(conv_id)]
    assert received == [{"type": "token", "text": "a"}, {"type": "request_done"}]
    assert redis._pubsub.subscribed_channels == [f"conv:{conv_id}"]
    assert redis._pubsub.unsubscribed_channels == [f"conv:{conv_id}"]
