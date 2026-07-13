from __future__ import annotations

import abc
from dataclasses import dataclass
from functools import lru_cache
from typing import AsyncIterator, Union


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict


@dataclass
class StreamDone:
    tool_uses: list[ToolUseBlock]
    stop_reason: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


StreamEvent = Union[TextDelta, StreamDone]


class LLMClient(abc.ABC):
    @abc.abstractmethod
    def stream(self, *, system: str, messages: list[dict],
              tools: list[dict]) -> AsyncIterator[StreamEvent]:
        ...


class FakeLLMClient(LLMClient):
    """Test double: phát lại kịch bản dựng sẵn, 1 lượt/lần gọi .stream()."""

    def __init__(self, turns: list[list[StreamEvent]]):
        self._turns = list(turns)
        self.calls: list[dict] = []

    async def stream(self, *, system: str, messages: list[dict],
                     tools: list[dict]) -> AsyncIterator[StreamEvent]:
        self.calls.append({"system": system, "messages": messages, "tools": tools})
        events = self._turns.pop(0)
        for event in events:
            yield event


class AnthropicLLMClient(LLMClient):
    """Prod impl — bọc anthropic.AsyncAnthropic (inject qua constructor để test không cần network)."""

    def __init__(self, client, model: str, max_tokens: int = 4096):
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    async def stream(self, *, system: str, messages: list[dict],
                     tools: list[dict]) -> AsyncIterator[StreamEvent]:
        async with self._client.messages.stream(
            model=self._model, max_tokens=self._max_tokens,
            system=system, messages=messages, tools=tools,
            tool_choice={"type": "auto", "disable_parallel_tool_use": True},
        ) as stream:
            async for text in stream.text_stream:
                yield TextDelta(text=text)
            final = await stream.get_final_message()
        tool_uses = [
            ToolUseBlock(id=block.id, name=block.name, input=block.input)
            for block in final.content if block.type == "tool_use"
        ]
        usage = final.usage
        yield StreamDone(
            tool_uses=tool_uses, stop_reason=final.stop_reason,
            input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        )


@lru_cache
def get_llm_client() -> LLMClient:
    import anthropic

    from app.config import get_settings

    settings = get_settings()
    client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        base_url=settings.anthropic_base_url or None,  # None = api.anthropic.com
    )
    return AnthropicLLMClient(client, model=settings.model_chat)
