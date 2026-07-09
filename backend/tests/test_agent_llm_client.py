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
