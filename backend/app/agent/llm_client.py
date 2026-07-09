from __future__ import annotations

import abc
from dataclasses import dataclass
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
