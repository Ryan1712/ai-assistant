from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_client import LLMClient, StreamDone, TextDelta
from app.agent.publisher import EventPublisher
from app.agent.tools import SENSITIVE_TOOLS, TOOLS, call_tool
from app.config import get_settings
from app.models import ChatRequest, ChatRequestStatus, Message, MessageRole, UsageLog, User

SYSTEM_PROMPT = (
    "Ban la tro ly AI quan ly cong viec. Thuc hien yeu cau cua nguoi dung bang cach "
    "goi tool phu hop. Neu tool tra ve error, hay bao lai ro rang cho nguoi dung, "
    "khong tu suy dien hoac chon doi tuong thay the."
)

# Chặn vòng lặp agent chạy vô hạn nếu model cứ gọi tool không nhạy cảm mà không bao
# giờ tới end_turn (buggy/adversarial). Nếu không có chặn này, arq job_timeout (mặc
# định 300s) sẽ giết job bằng CancelledError — BaseException, lọt qua except Exception
# bên dưới — kẹt request ở status=running vĩnh viễn (worker chỉ pickup request queued).
MAX_ITERATIONS = 25


def _tool_specs_for_api() -> list[dict]:
    return [{"name": name, "description": spec.description, "input_schema": spec.input_schema}
           for name, spec in TOOLS.items()]


async def _load_history(db: AsyncSession, conversation_id: uuid.UUID) -> list[dict]:
    rows = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    return [{"role": m.role.value, "content": m.content} for m in rows.scalars()]


async def _never_cancelled(_request_id: uuid.UUID) -> bool:
    return False


async def _mark_failed(db: AsyncSession, req: ChatRequest, publisher: EventPublisher,
                       error_message: str) -> None:
    """Đưa request về status=failed và publish request_failed. Dùng chung cho lỗi hạ
    tầng (except Exception) lẫn trường hợp vượt MAX_ITERATIONS."""
    await db.rollback()
    req.status = ChatRequestStatus.failed
    req.error = error_message
    req.finished_at = datetime.now(timezone.utc)
    await db.commit()
    await publisher.publish(req.conversation_id,
                            {"type": "request_failed", "chat_request_id": str(req.id),
                             "error": error_message})


async def run_agent_loop(
    db: AsyncSession, req: ChatRequest, llm: LLMClient, publisher: EventPublisher,
    is_cancelled: Callable[[uuid.UUID], Awaitable[bool]] | None = None,
) -> None:
    """Chạy agent loop cho 1 chat_request tới khi end_turn / awaiting_confirmation /
    cancelled / failed. Không bao giờ raise — mọi lỗi hạ tầng chuyển thành status=failed."""
    check_cancelled = is_cancelled or _never_cancelled
    req.status = ChatRequestStatus.running
    req.started_at = datetime.now(timezone.utc)
    await db.commit()

    actor = await db.get(User, req.user_id)

    async def _cancel_and_exit() -> None:
        req.status = ChatRequestStatus.cancelled
        req.finished_at = datetime.now(timezone.utc)
        await db.commit()
        await publisher.publish(req.conversation_id,
                                {"type": "status_update", "chat_request_id": str(req.id),
                                 "status": "cancelled"})

    try:
        iteration = 0
        while True:
            if await check_cancelled(req.id):
                await _cancel_and_exit()
                return

            iteration += 1
            if iteration > MAX_ITERATIONS:
                await _mark_failed(db, req, publisher, "max_iterations_exceeded")
                return

            history = await _load_history(db, req.conversation_id)
            text_parts: list[str] = []
            done: StreamDone | None = None
            async for event in llm.stream(system=SYSTEM_PROMPT, messages=history,
                                          tools=_tool_specs_for_api()):
                if await check_cancelled(req.id):
                    await _cancel_and_exit()
                    return
                if isinstance(event, TextDelta):
                    text_parts.append(event.text)
                    await publisher.publish(req.conversation_id,
                                            {"type": "token", "chat_request_id": str(req.id),
                                             "text": event.text})
                else:
                    done = event

            assistant_content: list[dict] = []
            if text_parts:
                assistant_content.append({"type": "text", "text": "".join(text_parts)})
            for tu in done.tool_uses:
                assistant_content.append({"type": "tool_use", "id": tu.id, "name": tu.name,
                                          "input": tu.input})
            db.add(Message(workspace_id=req.workspace_id, conversation_id=req.conversation_id,
                           chat_request_id=req.id, role=MessageRole.assistant,
                           content=assistant_content))
            db.add(UsageLog(workspace_id=req.workspace_id, chat_request_id=req.id,
                            model=get_settings().model_chat, input_tokens=done.input_tokens,
                            output_tokens=done.output_tokens,
                            cache_read_tokens=done.cache_read_tokens,
                            cache_write_tokens=done.cache_write_tokens))

            if done.stop_reason != "tool_use" or not done.tool_uses:
                req.status = ChatRequestStatus.done
                req.finished_at = datetime.now(timezone.utc)
                req.result_summary = "".join(text_parts)[:500]
                await db.commit()
                await publisher.publish(req.conversation_id,
                                        {"type": "request_done", "chat_request_id": str(req.id),
                                         "result_summary": req.result_summary})
                return

            first_sensitive = next((tu for tu in done.tool_uses if tu.name in SENSITIVE_TOOLS),
                                   None)
            if first_sensitive is not None:
                req.status = ChatRequestStatus.awaiting_confirmation
                req.pending_action = {"tool_name": first_sensitive.name,
                                      "tool_input": first_sensitive.input,
                                      "tool_use_id": first_sensitive.id}
                await db.commit()
                await publisher.publish(req.conversation_id,
                                        {"type": "confirmation_required",
                                         "chat_request_id": str(req.id),
                                         "tool_name": first_sensitive.name,
                                         "tool_input": first_sensitive.input})
                return

            tool_results = []
            for tu in done.tool_uses:
                result = await call_tool(db, actor, tu.name, tu.input)
                tool_results.append({"type": "tool_result", "tool_use_id": tu.id,
                                     "content": json.dumps(result, default=str)})
            db.add(Message(workspace_id=req.workspace_id, conversation_id=req.conversation_id,
                           chat_request_id=req.id, role=MessageRole.user, content=tool_results))
            await db.commit()
    except Exception as exc:
        await _mark_failed(db, req, publisher, str(exc))


async def resolve_confirmation(db: AsyncSession, req: ChatRequest, approved: bool) -> None:
    """Xử lý xác nhận (hoặc từ chối) hành động nhạy cảm đang chờ; đưa request về
    queued để lần chạy run_agent_loop tiếp theo tự thấy tool_result trong history."""
    if req.pending_action is None:
        raise ValueError("no_pending_action")
    actor = await db.get(User, req.user_id)
    action = req.pending_action
    if approved:
        result = await call_tool(db, actor, action["tool_name"], action["tool_input"])
    else:
        result = {"error": "user_denied", "message": "Người dùng từ chối xác nhận hành động này."}
    db.add(Message(workspace_id=req.workspace_id, conversation_id=req.conversation_id,
                   chat_request_id=req.id, role=MessageRole.user,
                   content=[{"type": "tool_result", "tool_use_id": action["tool_use_id"],
                            "content": json.dumps(result, default=str)}]))
    req.pending_action = None
    req.status = ChatRequestStatus.queued
    await db.commit()
