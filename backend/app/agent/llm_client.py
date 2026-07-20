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
    model: str = "unknown"

    @abc.abstractmethod
    def stream(self, *, system: str | list[dict], messages: list[dict],
              tools: list[dict]) -> AsyncIterator[StreamEvent]:
        ...


class FakeLLMClient(LLMClient):
    """Test double: phát lại kịch bản dựng sẵn, 1 lượt/lần gọi .stream()."""

    def __init__(self, turns: list[list[StreamEvent]], model: str = "fake"):
        self._turns = list(turns)
        self.calls: list[dict] = []
        self.model = model

    async def stream(self, *, system: str | list[dict], messages: list[dict],
                     tools: list[dict]) -> AsyncIterator[StreamEvent]:
        self.calls.append({"system": system, "messages": messages, "tools": tools})
        events = self._turns.pop(0)
        for event in events:
            yield event


class AnthropicLLMClient(LLMClient):
    """Prod impl — bọc anthropic.AsyncAnthropic (inject qua constructor để test không cần network).

    Đọc RAW event stream (messages.create(stream=True)) và tự accumulate thay vì
    dùng helper messages.stream(): một số gateway (vd beeknoee) phát message_start
    synthetic + content_block_start text rỗng TRƯỚC message_start thật, làm
    accumulator của helper lạc chỉ mục block ⇒ tool input về {} và usage về 0
    (bug tìm ra khi smoke test LLM thật 2026-07-13). Accumulator ở đây reset theo
    message_start MỚI NHẤT nên chạy đúng với cả API chính thức lẫn gateway.
    """

    def __init__(self, client, model: str, max_tokens: int = 8192):
        self._client = client
        self.model = model
        self._max_tokens = max_tokens

    async def stream(self, *, system: str | list[dict], messages: list[dict],
                     tools: list[dict]) -> AsyncIterator[StreamEvent]:
        import json

        # Prompt caching: system prompt + ~44 tool schema giống hệt nhau giữa các
        # lượt — không cache thì mỗi vòng tool trả tiền input đầy đủ cho toàn bộ.
        # cache_control đặt ở block cuối của mỗi vùng (system, tools) theo API Anthropic.
        if isinstance(system, str):
            system_payload = [{"type": "text", "text": system,
                               "cache_control": {"type": "ephemeral"}}]
        else:
            # [tĩnh, *động] (Phase 1): breakpoint ở block ĐẦU — block động
            # (instruction/snapshot đổi thường xuyên) đứng sau, không phá cache
            # của tools + phần tĩnh. Copy dict, không mutate input.
            system_payload = [{**system[0], "cache_control": {"type": "ephemeral"}},
                              *(dict(b) for b in system[1:])]
        tools_payload = list(tools)
        if tools_payload:
            tools_payload = tools_payload[:-1] + [
                {**tools_payload[-1], "cache_control": {"type": "ephemeral"}}]

        # Incremental caching (Phase 0, spec 4.3): breakpoint thứ 3 ở block cuối
        # của message cuối — các vòng tool sau đọc lại toàn bộ history từ cache.
        # Copy shallow từng lớp thay vì mutate: content là JSON column của ORM
        # Message, mutate tại đây sẽ làm dirty session của agent loop.
        messages_payload = list(messages)
        if messages_payload:
            last = messages_payload[-1]
            content = last.get("content")
            if isinstance(content, list) and content:
                messages_payload[-1] = {**last, "content": content[:-1] + [
                    {**content[-1], "cache_control": {"type": "ephemeral"}}]}

        resp = await self._client.messages.create(
            model=self.model, max_tokens=self._max_tokens,
            system=system_payload, messages=messages_payload, tools=tools_payload,
            tool_choice={"type": "auto", "disable_parallel_tool_use": True},
            stream=True,
        )
        blocks: dict[int, dict] = {}
        stop_reason: str = "end_turn"
        input_tokens = output_tokens = cache_read = cache_write = 0
        async for ev in resp:
            etype = getattr(ev, "type", None)
            if etype == "message_start":
                blocks = {}  # bỏ prelude synthetic của gateway (nếu có)
                u = ev.message.usage
                input_tokens = getattr(u, "input_tokens", 0) or 0
                cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
                cache_write = getattr(u, "cache_creation_input_tokens", 0) or 0
            elif etype == "content_block_start":
                cb = ev.content_block
                if cb.type == "tool_use":
                    blocks[ev.index] = {"type": "tool_use", "id": cb.id, "name": cb.name,
                                        "json": "", "start_input": getattr(cb, "input", None)}
                else:
                    blocks[ev.index] = {"type": cb.type}
            elif etype == "content_block_delta":
                d = ev.delta
                dtype = getattr(d, "type", None)
                if dtype == "text_delta":
                    yield TextDelta(text=d.text)
                elif dtype == "input_json_delta":
                    b = blocks.get(ev.index)
                    if b is not None and b["type"] == "tool_use":
                        b["json"] += d.partial_json
            elif etype == "message_delta":
                if getattr(ev.delta, "stop_reason", None):
                    stop_reason = ev.delta.stop_reason
                u = getattr(ev, "usage", None)
                if u is not None and getattr(u, "output_tokens", None):
                    output_tokens = u.output_tokens

        tool_uses = []
        for _idx, b in sorted(blocks.items()):
            if b["type"] != "tool_use":
                continue
            raw = b["json"].strip()
            tool_input = json.loads(raw) if raw else (b["start_input"] or {})
            tool_uses.append(ToolUseBlock(id=b["id"], name=b["name"], input=tool_input))
        yield StreamDone(
            tool_uses=tool_uses, stop_reason=stop_reason,
            input_tokens=input_tokens, output_tokens=output_tokens,
            cache_read_tokens=cache_read, cache_write_tokens=cache_write,
        )


@lru_cache
def get_llm_client(model: str | None = None) -> LLMClient:
    import anthropic

    from app.config import get_settings

    settings = get_settings()
    client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        base_url=settings.anthropic_base_url or None,  # None = api.anthropic.com
    )
    return AnthropicLLMClient(client, model=model or settings.model_fast)
