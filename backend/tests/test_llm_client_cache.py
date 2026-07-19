from app.agent.llm_client import AnthropicLLMClient


class _FakeMessages:
    def __init__(self):
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs

        async def _empty():
            if False:
                yield  # pragma: no cover
        return _empty()


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


async def test_cache_control_duoc_set():
    fake = _FakeClient()
    llm = AnthropicLLMClient(fake, model="claude-haiku-4-5")
    async for _ in llm.stream(system="sys", messages=[], tools=[
            {"name": "a", "description": "", "input_schema": {}},
            {"name": "b", "description": "", "input_schema": {}}]):
        pass
    kw = fake.messages.kwargs
    assert kw["system"] == [{"type": "text", "text": "sys",
                             "cache_control": {"type": "ephemeral"}}]
    assert "cache_control" not in kw["tools"][0]
    assert kw["tools"][-1]["cache_control"] == {"type": "ephemeral"}


async def test_incremental_cache_tren_message_cuoi():
    """Phase 0 (spec 4.3): breakpoint cache thứ 3 đặt ở block cuối của message cuối."""
    fake = _FakeClient()
    llm = AnthropicLLMClient(fake, model="m")
    msgs = [
        {"role": "user", "content": [{"type": "text", "text": "cau 1"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "tra loi"},
                                          {"type": "tool_use", "id": "t1",
                                           "name": "list_tasks", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1",
                                      "content": "{}"}]},
    ]
    async for _ in llm.stream(system="sys", messages=msgs, tools=[]):
        pass
    sent = fake.messages.kwargs["messages"]
    assert sent[-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    # message trước đó không bị gắn
    assert "cache_control" not in sent[0]["content"][0]
    assert "cache_control" not in sent[1]["content"][-1]
    # KHÔNG mutate input gốc (content là JSON của ORM Message)
    assert "cache_control" not in msgs[-1]["content"][-1]


async def test_khong_co_message_van_chay():
    fake = _FakeClient()
    llm = AnthropicLLMClient(fake, model="m")
    async for _ in llm.stream(system="sys", messages=[], tools=[]):
        pass
    assert fake.messages.kwargs["messages"] == []
