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


class _Obj:
    """Namespace giả lập raw event của SDK anthropic (chỉ cần attribute access)."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _usage(input_tokens=0, output_tokens=0, cache_read=0, cache_write=0):
    return _Obj(input_tokens=input_tokens, output_tokens=output_tokens,
                cache_read_input_tokens=cache_read, cache_creation_input_tokens=cache_write)


class _FakeMessagesAPI:
    def __init__(self, events):
        self._events = events
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs

        async def _gen():
            for e in self._events:
                yield e
        return _gen()


class _FakeAnthropicSDKClient:
    def __init__(self, events):
        self.messages = _FakeMessagesAPI(events)


def _official_stream_events():
    """Chuỗi event chuẩn từ api.anthropic.com: text + tool_use với input stream dần."""
    return [
        _Obj(type="message_start", message=_Obj(usage=_usage(input_tokens=100, cache_read=80))),
        _Obj(type="content_block_start", index=0, content_block=_Obj(type="text", text="")),
        _Obj(type="content_block_delta", index=0, delta=_Obj(type="text_delta", text="Da ")),
        _Obj(type="content_block_delta", index=0, delta=_Obj(type="text_delta", text="lam ")),
        _Obj(type="content_block_delta", index=0, delta=_Obj(type="text_delta", text="xong")),
        _Obj(type="content_block_stop", index=0),
        _Obj(type="content_block_start", index=1,
             content_block=_Obj(type="tool_use", id="t1", name="create_task", input={})),
        _Obj(type="content_block_delta", index=1,
             delta=_Obj(type="input_json_delta", partial_json='{"tit')),
        _Obj(type="content_block_delta", index=1,
             delta=_Obj(type="input_json_delta", partial_json='le": "X"}')),
        _Obj(type="content_block_stop", index=1),
        _Obj(type="message_delta", delta=_Obj(type=None, stop_reason="tool_use"),
             usage=_Obj(output_tokens=20)),
        _Obj(type="message_stop"),
    ]


@pytest.mark.asyncio
async def test_anthropic_llm_client_translates_raw_stream_to_events():
    from app.agent.llm_client import AnthropicLLMClient

    sdk_client = _FakeAnthropicSDKClient(_official_stream_events())
    client = AnthropicLLMClient(sdk_client, model="claude-haiku-4-5")
    events = [e async for e in client.stream(
        system="sys", messages=[{"role": "user", "content": "hi"}], tools=[])]

    assert [e.text for e in events[:-1]] == ["Da ", "lam ", "xong"]
    done = events[-1]
    assert done.stop_reason == "tool_use"
    assert done.tool_uses == [ToolUseBlock(id="t1", name="create_task", input={"title": "X"})]
    assert done.input_tokens == 100
    assert done.cache_read_tokens == 80
    assert done.output_tokens == 20
    assert sdk_client.messages.last_kwargs["model"] == "claude-haiku-4-5"
    assert sdk_client.messages.last_kwargs["stream"] is True


@pytest.mark.asyncio
async def test_anthropic_llm_client_survives_gateway_synthetic_prelude():
    """Bug tìm ra khi smoke test LLM thật (2026-07-13): gateway (beeknoee) phát
    message_start synthetic + content_block_start text rỗng TRƯỚC message_start
    thật — accumulator của SDK helper lạc chỉ mục block ⇒ tool input về {}.
    Accumulator tự quản phải reset theo message_start MỚI NHẤT và vẫn ráp đủ
    input_json_delta."""
    from app.agent.llm_client import AnthropicLLMClient

    prelude = [
        _Obj(type="ping"),
        _Obj(type="message_start", message=_Obj(usage=_usage())),  # synthetic, usage=0
        _Obj(type="content_block_start", index=0, content_block=_Obj(type="text", text="")),
    ]
    sdk_client = _FakeAnthropicSDKClient(prelude + _official_stream_events())
    client = AnthropicLLMClient(sdk_client, model="claude-haiku-4-5")
    events = [e async for e in client.stream(
        system="sys", messages=[{"role": "user", "content": "hi"}], tools=[])]

    done = events[-1]
    assert done.tool_uses == [ToolUseBlock(id="t1", name="create_task", input={"title": "X"})]
    assert done.input_tokens == 100  # usage lấy từ message_start thật, không phải synthetic
    assert [e.text for e in events[:-1]] == ["Da ", "lam ", "xong"]


@pytest.mark.asyncio
async def test_anthropic_llm_client_disables_parallel_tool_use():
    """Finding 1 (final review): a sensitive tool_use (lock_user/unlock_user) emitted
    alongside other tool_use blocks in the same turn would leave those other blocks
    without a matching tool_result, breaking the next API call. Constrain the model
    to at most one tool_use per turn via tool_choice.disable_parallel_tool_use."""
    from app.agent.llm_client import AnthropicLLMClient

    events = [
        _Obj(type="message_start", message=_Obj(usage=_usage(input_tokens=5))),
        _Obj(type="content_block_start", index=0, content_block=_Obj(type="text", text="")),
        _Obj(type="content_block_delta", index=0, delta=_Obj(type="text_delta", text="ok")),
        _Obj(type="message_delta", delta=_Obj(type=None, stop_reason="end_turn"),
             usage=_Obj(output_tokens=1)),
        _Obj(type="message_stop"),
    ]
    sdk_client = _FakeAnthropicSDKClient(events)
    client = AnthropicLLMClient(sdk_client, model="claude-haiku-4-5")
    _ = [e async for e in client.stream(
        system="sys", messages=[{"role": "user", "content": "hi"}], tools=[])]

    assert sdk_client.messages.last_kwargs["tool_choice"] == {
        "type": "auto",
        "disable_parallel_tool_use": True,
    }
