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
