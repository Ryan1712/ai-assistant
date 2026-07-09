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
