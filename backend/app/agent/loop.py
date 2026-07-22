from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_client import LLMClient, StreamDone, TextDelta
from app.agent.publisher import EventPublisher
from app.agent.tools import SENSITIVE_TOOLS, SNAPSHOT_WRITE_TOOLS, TOOLS, call_tool
from app.models import (
    AgentTrace, ChatRequest, ChatRequestStatus, Message, MessageRole, UsageLog, User,
)
from app.services import instruction_service, snapshot_service
from app.tz import VN_TZ

_VN_WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]

logger = logging.getLogger(__name__)

_TRACE_TRUNC = 500


def _tool_trace_entry(name: str, tool_input: dict, result: dict, latency_ms: int) -> dict:
    """1 phần tử tools_called của AgentTrace — input/output nén 500 ký tự (spec 4.1)."""
    return {
        "name": name, "latency_ms": latency_ms,
        "input": json.dumps(tool_input, ensure_ascii=False, default=str)[:_TRACE_TRUNC],
        "output": json.dumps(result, ensure_ascii=False, default=str)[:_TRACE_TRUNC],
    }


def _build_system_prompt(actor: User, now: datetime | None = None) -> str:
    """System prompt theo từng request: danh tính actor lấy từ JWT (không bao giờ
    hỏi user ID), ngày GIỜ theo VN (user ở VN — 'hôm nay/ngày mai/3h chiều' đều
    là giờ VN), và thiên hướng hành động thay vì hỏi vặt."""
    now_vn = (now or datetime.now(timezone.utc)).astimezone(VN_TZ)
    weekday = _VN_WEEKDAYS[now_vn.weekday()]
    return (
        "Bạn là trợ lý AI quản lý công việc của công ty. "
        "Luôn trả lời bằng tiếng Việt (trừ khi người dùng chủ động dùng ngôn ngữ khác).\n"
        f"Người đang nói chuyện với bạn: {actor.full_name} "
        f"(id: {actor.id}, vai trò: {actor.role.value}). "
        "Khi người dùng nói 'tôi'/'của tôi'/'cho tôi' thì chính là người này — dùng id ở trên, "
        "TUYỆT ĐỐI không hỏi lại user ID.\n"
        f"Bây giờ là {weekday}, {now_vn:%Y-%m-%d} {now_vn:%H:%M} giờ Việt Nam (UTC+7). "
        "Mọi mốc thời gian người dùng nói ('hôm nay', 'ngày mai', '3h chiều') hiểu theo giờ VN.\n"
        "Ranh giới quyền chính: tạo/sửa/giao task & project, quản lý skill/instruction/"
        "lịch báo cáo/tài khoản là việc của CEO. Nếu người dùng không phải CEO mà nhờ các việc "
        "đó, đừng gọi tool — báo họ nhờ CEO thực hiện.\n"
        "Người dùng có thể được cấp 'skill' (quy trình/tri thức riêng của công ty): khi yêu cầu "
        "liên quan tới quy trình nội bộ, hãy tra list_skills rồi use_skill để lấy hướng dẫn.\n"
        "Thực hiện yêu cầu bằng cách gọi tool phù hợp. Khi đủ thông tin bắt buộc thì hành động "
        "ngay và chọn mặc định hợp lý cho tham số tùy chọn, đừng hỏi vặt. Thiếu thông tin thì "
        "ưu tiên tự tra bằng tool list (project/task/người) trước khi hỏi người dùng. "
        "Nếu tool trả về error, báo lại rõ ràng cho người dùng, không tự suy diễn hoặc chọn "
        "đối tượng thay thế. Với hành động nhạy cảm (khóa/mở tài khoản, "
        "gửi email, xóa instruction): GỌI TOOL NGAY — hệ thống tự dừng lại và hiện nút "
        "xác nhận cho người dùng; đừng tự hỏi xác nhận bằng lời trong chat.\n"
        "Nếu system prompt có kèm 1 mục số liệu công ty tổng hợp sẵn (đầu dòng bắt "
        "đầu bằng dấu #, nằm ở cuối): đó là số liệu SQL mới nhất theo đúng phạm vi "
        "quyền của người dùng — ưu tiên trả lời trực tiếp từ đó (0 lần gọi tool); "
        "chỉ gọi tool khi cần chi tiết không có sẵn ở đó."
    )

# Chặn vòng lặp agent chạy vô hạn nếu model cứ gọi tool không nhạy cảm mà không bao
# giờ tới end_turn (buggy/adversarial). Nếu không có chặn này, arq job_timeout (mặc
# định 300s) sẽ giết job bằng CancelledError — BaseException, lọt qua except Exception
# bên dưới — kẹt request ở status=running vĩnh viễn (worker chỉ pickup request queued).
MAX_ITERATIONS = 25

# Trần số message nạp vào ngữ cảnh — hội thoại dài không giới hạn sẽ (1) phình token
# gần bậc hai theo vòng tool, (2) tới lúc vượt context window thì MỌI tin nhắn sau đó
# của conversation đều fail vĩnh viễn.
MAX_HISTORY_MESSAGES = 80


def _tool_specs_for_api() -> list[dict]:
    return [{"name": name, "description": spec.description, "input_schema": spec.input_schema}
           for name, spec in TOOLS.items()]


async def _load_history(db: AsyncSession, conversation_id: uuid.UUID,
                        current_request_id: uuid.UUID) -> list[dict]:
    """Lịch sử hội thoại CHO 1 request đang chạy: loại message của các request còn
    đang xếp hàng (và cancelled chưa từng chạy) — nếu không, model đang trả lời tin 1
    đã 'nhìn thấy' tin 2, 3... chưa xử lý và trả lời gộp/nhầm; reorder cũng vô nghĩa."""
    skip_ids = select(ChatRequest.id).where(
        ChatRequest.conversation_id == conversation_id,
        ChatRequest.id != current_request_id,
        or_(ChatRequest.status == ChatRequestStatus.queued,
            and_(ChatRequest.status == ChatRequestStatus.cancelled,
                 ChatRequest.started_at.is_(None))),
    ).scalar_subquery()
    rows = await db.execute(
        select(Message).where(
            Message.conversation_id == conversation_id,
            or_(Message.chat_request_id.is_(None),
                Message.chat_request_id.not_in(skip_ids)),
        ).order_by(Message.created_at.asc(), Message.id.asc())
    )
    # Bỏ message content rỗng (dữ liệu cũ trước guard bên dưới) — Anthropic API
    # từ chối request có message rỗng.
    msgs = [{"role": m.role.value, "content": m.content} for m in rows.scalars() if m.content]
    if len(msgs) > MAX_HISTORY_MESSAGES:
        msgs = msgs[-MAX_HISTORY_MESSAGES:]
        # Không được mở đầu bằng tool_result mồ côi (thiếu tool_use đi trước) —
        # trượt tới user message thuần text đầu tiên.
        start = next((i for i, m in enumerate(msgs)
                      if m["role"] == "user" and m["content"]
                      and m["content"][0].get("type") == "text"), None)
        # Không có message nào trong cửa sổ thỏa an toàn (chỉ có thể xảy ra nếu
        # MAX_ITERATIONS tăng vượt MAX_HISTORY_MESSAGES/2 sau này) — KHÔNG đoán bừa
        # bằng msgs[-1:] (message đó chưa chắc an toàn), trả rỗng còn hơn gửi lên
        # Anthropic 1 message mở đầu bằng tool_result mồ côi.
        msgs = msgs[start:] if start is not None else []
    return msgs


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

    iteration = 0
    trace_tools: list[dict] = []
    loop_started = time.monotonic()

    async def _write_trace(stop_reason: str) -> None:
        """Ghi 1 dòng AgentTrace — lỗi ghi trace không bao giờ được phá request."""
        try:
            db.add(AgentTrace(
                workspace_id=req.workspace_id, chat_request_id=req.id,
                route="fast",  # "fast" cứng ở Phase 0 — router Phase 4 sẽ truyền route thật
                model=getattr(llm, "model", ""),
                iterations=iteration, stop_reason=stop_reason,
                tools_called=trace_tools,
                total_latency_ms=int((time.monotonic() - loop_started) * 1000)))
            await db.commit()
        except Exception:
            logger.exception("ghi agent trace fail cho request %s", req.id)
            await db.rollback()

    async def _cancel_and_exit() -> None:
        req.status = ChatRequestStatus.cancelled
        req.finished_at = datetime.now(timezone.utc)
        await db.commit()
        await publisher.publish(req.conversation_id,
                                {"type": "status_update", "chat_request_id": str(req.id),
                                 "status": "cancelled"})
        await _write_trace("cancelled")

    try:
        while True:
            if await check_cancelled(req.id):
                await _cancel_and_exit()
                return

            iteration += 1
            if iteration > MAX_ITERATIONS:
                await _mark_failed(db, req, publisher, "max_iterations_exceeded")
                await _write_trace("max_iterations")
                return

            history = await _load_history(db, req.conversation_id, req.id)
            system_static = _build_system_prompt(actor)
            dynamic_parts: list[str] = []
            # Instruction + snapshot đọc DB/cache mỗi lượt → cập nhật là nạp lại ngay
            instructions_text = await instruction_service.active_instructions_text(
                db, req.workspace_id)
            if instructions_text:
                dynamic_parts.append("# Chỉ dẫn từ CEO công ty\n" + instructions_text)
            snapshot_text = await snapshot_service.get_snapshot_text(db, actor)
            if snapshot_text:
                dynamic_parts.append(snapshot_text)
            system_payload: str | list[dict] = system_static
            if dynamic_parts:
                # 2 block: [tĩnh (cache_control ở llm_client), động] — snapshot đổi
                # không phá cache tools + phần tĩnh.
                system_payload = [{"type": "text", "text": system_static},
                                  {"type": "text", "text": "\n\n".join(dynamic_parts)}]
            text_parts: list[str] = []
            done: StreamDone | None = None
            async for event in llm.stream(system=system_payload, messages=history,
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

            if done.stop_reason == "max_tokens":
                # Trả lời bị cắt vì chạm trần output — nói thẳng cho người dùng
                # thay vì im lặng như thể đã trả lời xong.
                cut_note = ("\n\n⚠️ Câu trả lời đã chạm giới hạn độ dài và bị cắt — "
                            "nhắn 'viết tiếp' để xem phần còn lại.")
                text_parts.append(cut_note)
                await publisher.publish(req.conversation_id,
                                        {"type": "token", "chat_request_id": str(req.id),
                                         "text": cut_note})

            assistant_content: list[dict] = []
            if text_parts:
                assistant_content.append({"type": "text", "text": "".join(text_parts)})
            for tu in done.tool_uses:
                assistant_content.append({"type": "tool_use", "id": tu.id, "name": tu.name,
                                          "input": tu.input})
            if assistant_content:
                # Lượt rỗng (model/gateway trả về không text không tool) mà vẫn lưu
                # content=[] thì mọi lần gọi API sau của conversation fail 400.
                db.add(Message(workspace_id=req.workspace_id,
                               conversation_id=req.conversation_id,
                               chat_request_id=req.id, role=MessageRole.assistant,
                               content=assistant_content))
            db.add(UsageLog(workspace_id=req.workspace_id, chat_request_id=req.id,
                            model=llm.model, input_tokens=done.input_tokens,
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
                await _write_trace(done.stop_reason)
                return

            first_sensitive = next((tu for tu in done.tool_uses if tu.name in SENSITIVE_TOOLS),
                                   None)
            if first_sensitive is not None:
                req.status = ChatRequestStatus.awaiting_confirmation
                req.pending_action = {"kind": "tool", "tool_name": first_sensitive.name,
                                      "tool_input": first_sensitive.input,
                                      "tool_use_id": first_sensitive.id}
                await db.commit()
                await publisher.publish(req.conversation_id,
                                        {"type": "confirmation_required",
                                         "kind": "tool",
                                         "chat_request_id": str(req.id),
                                         "tool_name": first_sensitive.name,
                                         "tool_input": first_sensitive.input})
                await _write_trace("awaiting_confirmation")
                return

            tool_results = []
            for tu in done.tool_uses:
                await publisher.publish(req.conversation_id,
                                        {"type": "tool_running", "chat_request_id": str(req.id),
                                         "tool_name": tu.name})
                tool_started = time.monotonic()
                result = await call_tool(db, actor, tu.name, tu.input)
                trace_tools.append(_tool_trace_entry(
                    tu.name, tu.input, result,
                    int((time.monotonic() - tool_started) * 1000)))
                tool_results.append({"type": "tool_result", "tool_use_id": tu.id,
                                     "content": json.dumps(result, default=str)})
            db.add(Message(workspace_id=req.workspace_id, conversation_id=req.conversation_id,
                           chat_request_id=req.id, role=MessageRole.user, content=tool_results))
            await db.commit()

            if any(tu.name in SNAPSHOT_WRITE_TOOLS for tu in done.tool_uses):
                # AI vừa đổi dữ liệu → lượt sau phải thấy ngay (không chờ TTL)
                await snapshot_service.invalidate(req.workspace_id)
    except Exception as exc:
        await _mark_failed(db, req, publisher, str(exc))
        await _write_trace("error")


async def resolve_confirmation(db: AsyncSession, req: ChatRequest, approved: bool) -> None:
    """Xử lý xác nhận (hoặc từ chối) hành động nhạy cảm đang chờ; đưa request về
    queued để lần chạy run_agent_loop tiếp theo tự thấy tool_result trong history."""
    if req.pending_action is None:
        raise ValueError("no_pending_action")
    actor = await db.get(User, req.user_id)
    action = req.pending_action
    # .get("kind", "tool"): dong pending_action tao TRUOC Phase 2 khong co "kind" —
    # mac dinh ve nhanh cu de tuong thich nguoc, khong can migrate du lieu.
    kind = action.get("kind", "tool")
    if approved:
        result = await call_tool(db, actor, action["tool_name"], action["tool_input"])
        if action["tool_name"] in SNAPSHOT_WRITE_TOOLS:
            await snapshot_service.invalidate(req.workspace_id)
    else:
        result = {"error": "user_denied", "message": "Người dùng từ chối xác nhận hành động này."}
    db.add(Message(workspace_id=req.workspace_id, conversation_id=req.conversation_id,
                   chat_request_id=req.id, role=MessageRole.user,
                   content=[{"type": "tool_result", "tool_use_id": action["tool_use_id"],
                            "content": json.dumps(result, default=str)}]))
    req.pending_action = None
    req.status = ChatRequestStatus.queued
    await db.commit()
