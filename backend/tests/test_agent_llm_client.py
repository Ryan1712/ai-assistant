import pytest

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta, ToolUseBlock


@pytest.mark.asyncio
async def test_fake_llm_client_replays_scripted_turns_in_order():
    fake = FakeLLMClient(turns=[
        [TextDelta(text="Xin "), TextDelta(text="chao"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=10, output_tokens=5)],
        [StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=3, output_tokens=1)],
    ])

    events = [e async for e in fake.stream(system="sys", messages=[], tools=[])]
    assert [type(e).__name__ for e in events] == ["TextDelta", "TextDelta", "StreamDone"]
    assert events[-1].stop_reason == "end_turn"
    assert events[-1].input_tokens == 10

    second = [e async for e in fake.stream(system="sys", messages=[{"role": "user"}], tools=[])]
    assert len(second) == 1
    assert len(fake.calls) == 2
    assert fake.calls[1]["messages"] == [{"role": "user"}]


@pytest.mark.asyncio
async def test_fake_llm_client_yields_tool_use():
    fake = FakeLLMClient(turns=[[
        StreamDone(tool_uses=[ToolUseBlock(id="t1", name="create_task", input={"title": "X"})],
                  stop_reason="tool_use", input_tokens=20, output_tokens=8),
    ]])
    events = [e async for e in fake.stream(system="sys", messages=[], tools=[])]
    assert events[0].tool_uses[0].name == "create_task"


class _FakeUsage:
    def __init__(self, input_tokens, output_tokens, cache_read=0, cache_write=0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_input_tokens = cache_read
        self.cache_creation_input_tokens = cache_write


class _FakeContentBlock:
    def __init__(self, type_, **kw):
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeFinalMessage:
    def __init__(self, content, stop_reason, usage):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = usage


class _FakeStreamContext:
    def __init__(self, texts, final_message):
        self._texts = texts
        self._final_message = final_message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def text_stream(self):
        async def _gen():
            for t in self._texts:
                yield t
        return _gen()

    async def get_final_message(self):
        return self._final_message


class _FakeMessagesAPI:
    def __init__(self, stream_ctx):
        self._stream_ctx = stream_ctx
        self.last_kwargs = None

    def stream(self, **kwargs):
        self.last_kwargs = kwargs
        return self._stream_ctx


class _FakeAnthropicSDKClient:
    def __init__(self, stream_ctx):
        self.messages = _FakeMessagesAPI(stream_ctx)


@pytest.mark.asyncio
async def test_anthropic_llm_client_translates_sdk_stream_to_events():
    from app.agent.llm_client import AnthropicLLMClient

    final = _FakeFinalMessage(
        content=[_FakeContentBlock("text", text="Da lam xong"),
                 _FakeContentBlock("tool_use", id="t1", name="create_task", input={"title": "X"})],
        stop_reason="tool_use",
        usage=_FakeUsage(input_tokens=100, output_tokens=20, cache_read=80),
    )
    stream_ctx = _FakeStreamContext(texts=["Da ", "lam ", "xong"], final_message=final)
    sdk_client = _FakeAnthropicSDKClient(stream_ctx)

    client = AnthropicLLMClient(sdk_client, model="claude-haiku-4-5")
    events = [e async for e in client.stream(
        system="sys", messages=[{"role": "user", "content": "hi"}], tools=[])]

    assert [e.text for e in events[:-1]] == ["Da ", "lam ", "xong"]
    done = events[-1]
    assert done.stop_reason == "tool_use"
    assert done.tool_uses == [ToolUseBlock(id="t1", name="create_task", input={"title": "X"})]
    assert done.input_tokens == 100
    assert done.cache_read_tokens == 80
    assert sdk_client.messages.last_kwargs["model"] == "claude-haiku-4-5"


@pytest.mark.asyncio
async def test_anthropic_llm_client_disables_parallel_tool_use():
    """Finding 1 (final review): a sensitive tool_use (lock_user/unlock_user) emitted
    alongside other tool_use blocks in the same turn would leave those other blocks
    without a matching tool_result, breaking the next API call. Constrain the model
    to at most one tool_use per turn via tool_choice.disable_parallel_tool_use."""
    from app.agent.llm_client import AnthropicLLMClient

    final = _FakeFinalMessage(
        content=[_FakeContentBlock("text", text="ok")],
        stop_reason="end_turn",
        usage=_FakeUsage(input_tokens=5, output_tokens=1),
    )
    stream_ctx = _FakeStreamContext(texts=["ok"], final_message=final)
    sdk_client = _FakeAnthropicSDKClient(stream_ctx)

    client = AnthropicLLMClient(sdk_client, model="claude-haiku-4-5")
    _ = [e async for e in client.stream(
        system="sys", messages=[{"role": "user", "content": "hi"}], tools=[])]

    assert sdk_client.messages.last_kwargs["tool_choice"] == {
        "type": "auto",
        "disable_parallel_tool_use": True,
    }
