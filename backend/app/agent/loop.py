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
from app.agent.tools import (
    SENSITIVE_TOOLS, SNAPSHOT_WRITE_TOOLS, TOOLS, call_tool, validate_proposal_actions,
)
from app.models import (
    AgentTrace, ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole,
    UsageLog, User,
)
from app.services import distiller_service, embedding_service, instruction_service, snapshot_service
from app.tz import VN_TZ

_VN_WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]

logger = logging.getLogger(__name__)

_TRACE_TRUNC = 500

# Uoc luong noi bo (USD/1M token) — KHONG dung tinh hoa don that, chi de tra loi tho
# "feature/model nao ton tien". Khop theo substring trong model id (gateway co the
# tiem prefix "anthropic/" + date suffix). Model khong nam trong bang (vd gateway dev
# glm-4.7-flash) -> estimated_cost = 0.
_MODEL_PRICING_USD_PER_1M: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
}


def _estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    for key, (in_price, out_price) in _MODEL_PRICING_USD_PER_1M.items():
        if key in model:
            return round(input_tokens * in_price / 1_000_000
                        + output_tokens * out_price / 1_000_000, 6)
    return 0.0


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
        "chỉ gọi tool khi cần chi tiết không có sẵn ở đó.\n"
        "Luật hành xử 3 mức khi thực hiện 1 yêu cầu thay đổi dữ liệu:\n"
        "1) Tường minh + đảo ngược được (vd 'cập nhật task X lên 80%', đối tượng đã rõ "
        "ràng, sửa lại được dễ dàng) → làm ngay bằng tool tương ứng, rồi echo đầy đủ "
        "đối tượng đã tác động (tên task/người thật, không chỉ nói 'đã xong').\n"
        "2) Phải SUY LUẬN đối tượng (đoán task/người/deadline từ ngữ cảnh thay vì "
        "người dùng nói tường minh), hành động khó đảo ngược, hoặc gộp nhiều hành "
        "động trong 1 câu → gọi propose_actions NGAY (không tự hỏi trước bằng lời), "
        "điền hết tham số bằng suy luận hợp lý, mỗi action kèm display_text là 1 câu "
        "tiếng Việt người đọc hiểu ngay, và 1 câu reasoning ngắn giải thích vì sao "
        "suy luận vậy. Hệ thống tự hiện thẻ cho người dùng duyệt.\n"
        "3) Nhạy cảm (khóa/mở tài khoản, xóa, gửi email) → gọi tool nhạy cảm trực "
        "tiếp như đã nói ở trên (không qua propose_actions).\n"
        "Khi cần xác định MỘT người/task cụ thể: ưu tiên khớp từ số liệu công ty đã "
        "có sẵn trong system prompt trước. Chỉ dùng resolve_person/resolve_task khi "
        "ca khó (trùng tên, tên viết tắt/không dấu, hoặc đối tượng không có trong số "
        "liệu tóm tắt — vd task trạng thái chưa làm không hiện ở mục 'đang làm'). Nếu "
        "kết quả resolve_person/resolve_task trả 'ambiguous' kèm nhiều candidates: "
        "TUYỆT ĐỐI không tự chọn đại 1 người/task — hỏi lại người dùng ĐÚNG MỘT câu, "
        "liệt kê rõ các lựa chọn cụ thể (tên/tiêu đề) để họ chọn.\n"
        "Khi người dùng hỏi nhớ lại điều đã nói/ghi trước đây mà không có trong số liệu "
        "công ty hay lịch sử hội thoại hiện tại (vd 'tuần trước tôi dặn gì về X', 'trước đây "
        "có note gì về Y'): dùng semantic_search (tìm theo nghĩa, không cần trùng chữ) thay "
        "vì nói 'tôi không nhớ'.\n"
        "Khi tool_result của propose_actions có 'outcome' khác 'completed' (tức "
        "'partially_completed' hoặc 'failed' — một số action trong bản nháp đã lỗi): "
        "TUYỆT ĐỐI không nói chung chung 'đã xong' — PHẢI liệt kê rõ việc nào thành "
        "công ('succeeded'), việc nào thất bại kèm lý do ('failed'), để người dùng "
        "biết chính xác cái gì cần làm lại."
    )

# Chặn vòng lặp agent chạy vô hạn nếu model cứ gọi tool không nhạy cảm mà không bao
# giờ tới end_turn (buggy/adversarial). Nếu không có chặn này, arq job_timeout (mặc
# định 300s) sẽ giết job bằng CancelledError — BaseException, lọt qua except Exception
# bên dưới — kẹt request ở status=running vĩnh viễn (worker chỉ pickup request queued).
MAX_ITERATIONS = 25
# Guardrail hardening (trước Phase 3): MAX_ITERATIONS không đủ vì 1 lượt có thể gọi
# nhiều tool cùng lúc, hoặc gateway dev độ trễ rất cao (đã quan sát 260s+/lượt) khiến
# tổng thời gian request phình to dù số vòng lặp ít. MAX_DURATION_SECONDS < arq
# job_timeout mặc định 300s để dừng SẠCH (ghi trace/status) trước khi bị arq kill.
MAX_TOOL_CALLS = 60
MAX_DURATION_SECONDS = 240
MAX_TOTAL_TOKENS = 200_000

# Trần số message nạp vào ngữ cảnh — hội thoại dài không giới hạn sẽ (1) phình token
# gần bậc hai theo vòng tool, (2) tới lúc vượt context window thì MỌI tin nhắn sau đó
# của conversation đều fail vĩnh viễn.
MAX_HISTORY_MESSAGES = 80


def _tool_specs_for_api(tool_names: set[str] | None = None) -> list[dict]:
    """tool_names=None -> full toolset (mặc định/fallback an toàn khi Router
    Phase 4 không chắc route). Có tool_names -> chỉ nạp đúng tập đó (core +
    nhóm theo router.tool_names_for_route)."""
    items = TOOLS.items() if tool_names is None else (
        (name, spec) for name, spec in TOOLS.items() if name in tool_names)
    return [{"name": name, "description": spec.description, "input_schema": spec.input_schema}
           for name, spec in items]


async def _load_history(db: AsyncSession, conversation_id: uuid.UUID,
                        current_request_id: uuid.UUID,
                        since: datetime | None = None) -> list[dict]:
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
    stmt = select(Message).where(
        Message.conversation_id == conversation_id,
        or_(Message.chat_request_id.is_(None),
            Message.chat_request_id.not_in(skip_ids)),
        Message.is_ack.is_(False),
    )
    if since is not None:
        # Phase 5: message <= mốc summary_through_at đã gộp vào rolling_summary
        # (tiêm ở system prompt), chỉ nạp đuôi verbatim.
        stmt = stmt.where(Message.created_at > since)
    rows = await db.execute(stmt.order_by(Message.created_at.asc(), Message.id.asc()))
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
    *, route: str = "fast", tool_names: set[str] | None = None,
    rag_context: str | None = None,
    max_iterations: int | None = None, max_tool_calls: int | None = None,
    max_duration_seconds: int | None = None, max_total_tokens: int | None = None,
) -> None:
    """Chạy agent loop cho 1 chat_request tới khi end_turn / awaiting_confirmation /
    cancelled / failed. Không bao giờ raise — mọi lỗi hạ tầng chuyển thành status=failed.

    route: ghi vào AgentTrace ("fast" mặc định — Router Phase 4 truyền "deep" khi
    gọi cho job phân tích nền). tool_names: None = full toolset (mặc định/fallback
    an toàn); có giá trị = chỉ nạp đúng tập tool đó (xem router.tool_names_for_route).

    rag_context: block "# Dữ liệu liên quan" đã build SẴN (Phase 6 §10.3, xem
    embedding_service.build_rag_context_block) — worker.py tính ĐÚNG MỘT LẦN
    lúc pickup request (giống Router) rồi truyền vào đây, KHÔNG được tự gọi
    semantic_search lại mỗi vòng lặp trong hàm này (tốn embedding API vô ích).

    max_*: None (mặc định) = dùng đúng hằng số module MAX_ITERATIONS/MAX_TOOL_CALLS/
    MAX_DURATION_SECONDS/MAX_TOTAL_TOKENS như cũ — cố ý ĐỌC hằng số bên trong hàm
    (không bind vào default parameter lúc định nghĩa) để monkeypatch trong test vẫn
    có tác dụng. Job phân tích nền (worker.py::run_deep_analysis) truyền trần cao
    hơn hẳn: model_smart + extended thinking chạy nhiều vòng/tốn token hơn hẳn
    Haiku fast path."""
    check_cancelled = is_cancelled or _never_cancelled
    iterations_limit = max_iterations if max_iterations is not None else MAX_ITERATIONS
    tool_calls_limit = max_tool_calls if max_tool_calls is not None else MAX_TOOL_CALLS
    duration_limit = (max_duration_seconds if max_duration_seconds is not None
                     else MAX_DURATION_SECONDS)
    total_tokens_limit = (max_total_tokens if max_total_tokens is not None
                          else MAX_TOTAL_TOKENS)
    req.status = ChatRequestStatus.running
    req.started_at = datetime.now(timezone.utc)
    await db.commit()

    actor = await db.get(User, req.user_id)
    conv = await db.get(Conversation, req.conversation_id)

    iteration = 0
    tool_call_count = 0
    total_tokens = 0
    trace_tools: list[dict] = []
    loop_started = time.monotonic()

    async def _write_trace(stop_reason: str) -> None:
        """Ghi 1 dòng AgentTrace — lỗi ghi trace không bao giờ được phá request."""
        try:
            db.add(AgentTrace(
                workspace_id=req.workspace_id, chat_request_id=req.id,
                route=route,
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
            if iteration > iterations_limit:
                await _mark_failed(db, req, publisher, "max_iterations_exceeded")
                await _write_trace("max_iterations")
                return
            if tool_call_count > tool_calls_limit:
                await _mark_failed(db, req, publisher, "max_tool_calls_exceeded")
                await _write_trace("max_tool_calls")
                return
            if time.monotonic() - loop_started > duration_limit:
                await _mark_failed(db, req, publisher, "max_duration_exceeded")
                await _write_trace("max_duration")
                return
            if total_tokens > total_tokens_limit:
                await _mark_failed(db, req, publisher, "max_total_tokens_exceeded")
                await _write_trace("max_total_tokens")
                return

            history = await _load_history(db, req.conversation_id, req.id,
                                          since=conv.summary_through_at if conv else None)
            system_static = _build_system_prompt(actor)
            dynamic_parts: list[str] = []
            # Instruction + snapshot đọc DB/cache mỗi lượt → cập nhật là nạp lại ngay
            instructions_text = await instruction_service.active_instructions_text(
                db, req.workspace_id)
            if instructions_text:
                dynamic_parts.append("# Chỉ dẫn từ CEO công ty\n" + instructions_text)
            memories_text = await distiller_service.active_memories_text(db, actor)
            if memories_text:
                dynamic_parts.append(memories_text)
            snapshot_text = await snapshot_service.get_snapshot_text(db, actor)
            if snapshot_text:
                dynamic_parts.append(snapshot_text)
            if rag_context:
                # Phase 6 §10.3: đã build sẵn 1 lần ở worker.py — chỉ nối chuỗi,
                # không gọi lại semantic_search ở đây.
                dynamic_parts.append(rag_context)
            if conv is not None and conv.rolling_summary:
                # Phase 5: tóm tắt hội thoại cũ — block ĐỘNG cuối, gần message nhất.
                dynamic_parts.append(
                    "# Tóm tắt hội thoại trước đó\n" + conv.rolling_summary)
            system_payload: str | list[dict] = system_static
            if dynamic_parts:
                # 2 block: [tĩnh (cache_control ở llm_client), động] — snapshot đổi
                # không phá cache tools + phần tĩnh.
                system_payload = [{"type": "text", "text": system_static},
                                  {"type": "text", "text": "\n\n".join(dynamic_parts)}]
            text_parts: list[str] = []
            done: StreamDone | None = None
            call_started = time.monotonic()
            async for event in llm.stream(system=system_payload, messages=history,
                                          tools=_tool_specs_for_api(tool_names)):
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
            # Block "thinking" (Phase 4, model_smart + extended thinking) PHẢI đứng
            # ĐẦU content, nguyên văn kèm signature không sửa — hợp đồng thinking+
            # tool-use của Anthropic, thiếu/sai thứ tự sẽ bị từ chối ở lượt tool tiếp theo.
            assistant_content.extend(done.thinking_blocks)
            if text_parts:
                assistant_content.append({"type": "text", "text": "".join(text_parts)})
            for tu in done.tool_uses:
                assistant_content.append({"type": "tool_use", "id": tu.id, "name": tu.name,
                                          "input": tu.input})
            assistant_msg: Message | None = None
            if assistant_content:
                # Lượt rỗng (model/gateway trả về không text không tool) mà vẫn lưu
                # content=[] thì mọi lần gọi API sau của conversation fail 400.
                assistant_msg = Message(workspace_id=req.workspace_id,
                                        conversation_id=req.conversation_id,
                                        chat_request_id=req.id, role=MessageRole.assistant,
                                        content=assistant_content)
                db.add(assistant_msg)
            db.add(UsageLog(workspace_id=req.workspace_id, chat_request_id=req.id,
                            user_id=actor.id, feature="chat", status=done.stop_reason,
                            latency_ms=int((time.monotonic() - call_started) * 1000),
                            tool_call_count=len(done.tool_uses), iteration=iteration,
                            estimated_cost=_estimate_cost_usd(
                                llm.model, done.input_tokens, done.output_tokens),
                            model=llm.model, input_tokens=done.input_tokens,
                            output_tokens=done.output_tokens,
                            cache_read_tokens=done.cache_read_tokens,
                            cache_write_tokens=done.cache_write_tokens))
            total_tokens += done.input_tokens + done.output_tokens
            tool_call_count += len(done.tool_uses)

            if done.stop_reason != "tool_use" or not done.tool_uses:
                req.status = ChatRequestStatus.done
                req.finished_at = datetime.now(timezone.utc)
                req.result_summary = "".join(text_parts)[:500]
                await db.commit()
                if text_parts and assistant_msg is not None:
                    # Phase 6 §10.3: "ký ức xuyên session" — best-effort, không
                    # chặn hoàn tất request nếu embedding provider lỗi.
                    await embedding_service.index_content(
                        db, req.workspace_id, "chat_message", assistant_msg.id,
                        "".join(text_parts))
                await publisher.publish(req.conversation_id,
                                        {"type": "request_done", "chat_request_id": str(req.id),
                                         "result_summary": req.result_summary})
                await _write_trace(done.stop_reason)
                return

            # propose_actions cùng hàng "chặn tuần tự" với sensitive tool — tool_use
            # nào tới trước trong batch thắng, y hệt cơ chế sensitive hiện có (tool_use
            # khác trong cùng lượt bị bỏ qua, không phải gap mới của Phase 2).
            first_gate = next((tu for tu in done.tool_uses
                               if tu.name == "propose_actions" or tu.name in SENSITIVE_TOOLS),
                              None)
            if first_gate is not None and first_gate.name == "propose_actions":
                err = validate_proposal_actions(first_gate.input.get("actions", []))
                if err is not None:
                    # Sai định dạng — trả lỗi ngay trong lượt này (không pause chờ
                    # người dùng) để model tự sửa hoặc gọi tool nhạy cảm trực tiếp.
                    error_result = {"error": "invalid_input", "hint": err}
                    db.add(Message(workspace_id=req.workspace_id,
                                   conversation_id=req.conversation_id, chat_request_id=req.id,
                                   role=MessageRole.user,
                                   content=[{"type": "tool_result", "tool_use_id": first_gate.id,
                                            "content": json.dumps(error_result, default=str)}]))
                    await db.commit()
                    continue
                actions = first_gate.input.get("actions", [])
                reasoning = first_gate.input.get("reasoning", "")
                req.status = ChatRequestStatus.awaiting_confirmation
                req.pending_action = {"kind": "proposal", "actions": actions,
                                      "reasoning": reasoning, "tool_use_id": first_gate.id}
                await db.commit()
                await publisher.publish(req.conversation_id,
                                        {"type": "confirmation_required",
                                         "kind": "proposal",
                                         "chat_request_id": str(req.id),
                                         "actions": actions, "reasoning": reasoning})
                await _write_trace("awaiting_confirmation")
                return

            if first_gate is not None:
                req.status = ChatRequestStatus.awaiting_confirmation
                req.pending_action = {"kind": "tool", "tool_name": first_gate.name,
                                      "tool_input": first_gate.input,
                                      "tool_use_id": first_gate.id}
                await db.commit()
                await publisher.publish(req.conversation_id,
                                        {"type": "confirmation_required",
                                         "kind": "tool",
                                         "chat_request_id": str(req.id),
                                         "tool_name": first_gate.name,
                                         "tool_input": first_gate.input})
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
            if text_parts and assistant_msg is not None:
                # Lượt vừa nói vừa gọi tool (vd "Để tôi kiểm tra..." + tool_use) —
                # vẫn index phần text, cùng lý do ở nhánh done phía trên.
                await embedding_service.index_content(
                    db, req.workspace_id, "chat_message", assistant_msg.id,
                    "".join(text_parts))

            if any(tu.name in SNAPSHOT_WRITE_TOOLS for tu in done.tool_uses):
                # AI vừa đổi dữ liệu → lượt sau phải thấy ngay (không chờ TTL)
                await snapshot_service.invalidate(req.workspace_id)
    except Exception as exc:
        await _mark_failed(db, req, publisher, str(exc))
        await _write_trace("error")


_ACK_SYSTEM_PROMPT = (
    "Bạn vừa nhận 1 yêu cầu cần phân tích sâu, sẽ được xử lý ở lượt sau bằng "
    "model mạnh hơn. Nhiệm vụ DUY NHẤT của bạn ngay bây giờ: viết đúng 1-2 câu "
    "ngắn bằng tiếng Việt xác nhận đã nhận yêu cầu, nhắc sẽ mất khoảng 30 giây, "
    "và sẽ báo khi xong. TUYỆT ĐỐI KHÔNG trả lời nội dung câu hỏi, không bàn "
    "luận thêm."
)
_ACK_FALLBACK_TEXT = "Đang phân tích, khoảng 30 giây — tôi sẽ báo khi xong."


async def run_deep_ack_turn(
    db: AsyncSession, req: ChatRequest, llm_fast: LLMClient, publisher: EventPublisher,
    is_cancelled: Callable[[uuid.UUID], Awaitable[bool]] | None = None,
) -> None:
    """Đường sâu (Phase 4 §8.2), lượt đầu: model_fast KHÔNG tool, chỉ tạo 1 ack
    message ngắn rồi chuyển request sang `deep_running` (CHƯA done thật) — job
    phân tích nền (`run_deep_analysis`, worker.py) do tầng gọi tự enqueue sau khi
    hàm này trả về thành công. Lỗi lúc gọi ack LLM dùng lại `_mark_failed`, giống
    `run_agent_loop`."""
    check_cancelled = is_cancelled or _never_cancelled
    if await check_cancelled(req.id):
        req.status = ChatRequestStatus.cancelled
        req.finished_at = datetime.now(timezone.utc)
        await db.commit()
        await publisher.publish(req.conversation_id,
                                {"type": "status_update", "chat_request_id": str(req.id),
                                 "status": "cancelled"})
        return

    req.status = ChatRequestStatus.running
    req.started_at = datetime.now(timezone.utc)
    await db.commit()

    loop_started = time.monotonic()
    text_parts: list[str] = []
    try:
        async for event in llm_fast.stream(
            system=_ACK_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": [{"type": "text", "text": req.content}]}],
            tools=[],
        ):
            if isinstance(event, TextDelta):
                text_parts.append(event.text)
                await publisher.publish(req.conversation_id,
                                        {"type": "token", "chat_request_id": str(req.id),
                                         "text": event.text})
    except Exception as exc:
        await _mark_failed(db, req, publisher, str(exc))
        return

    ack_text = "".join(text_parts).strip() or _ACK_FALLBACK_TEXT
    db.add(Message(workspace_id=req.workspace_id, conversation_id=req.conversation_id,
                   chat_request_id=req.id, role=MessageRole.assistant,
                   content=[{"type": "text", "text": ack_text}], is_ack=True))
    req.status = ChatRequestStatus.deep_running
    await db.commit()
    await publisher.publish(req.conversation_id,
                            {"type": "deep_analysis_started", "chat_request_id": str(req.id)})
    try:
        db.add(AgentTrace(
            workspace_id=req.workspace_id, chat_request_id=req.id,
            route="deep", model=getattr(llm_fast, "model", ""),
            iterations=1, stop_reason="ack_sent", tools_called=[],
            total_latency_ms=int((time.monotonic() - loop_started) * 1000)))
        await db.commit()
    except Exception:
        logger.exception("ghi agent trace fail cho request %s (ack)", req.id)
        await db.rollback()


async def _resolve_proposal(db: AsyncSession, actor: User, action: dict, approved: bool,
                            workspace_id: uuid.UUID, trace_tools: list[dict]) -> dict:
    """Duyệt bản nháp propose_actions: chạy tuần tự từng action qua call_tool() (đã
    không bao giờ raise) — action lỗi thì ghi lỗi vào kết quả và làm tiếp action sau,
    giống hàng đợi (bỏ qua, báo rõ), không dừng cả bản nháp vì 1 action hỏng.
    Mỗi action chạy được nối vào trace_tools (dùng chung AgentTrace của lượt confirm)."""
    if not approved:
        return {"error": "user_denied", "message": "Người dùng từ chối bản nháp này."}
    results: list[dict] = []
    succeeded: list[str] = []
    failed: list[str] = []
    any_write = False
    for a in action["actions"]:
        tool_started = time.monotonic()
        r = await call_tool(db, actor, a["tool_name"], a["tool_input"])
        trace_tools.append(_tool_trace_entry(a["tool_name"], a["tool_input"], r,
                                             int((time.monotonic() - tool_started) * 1000)))
        results.append({"tool_name": a["tool_name"], "display_text": a.get("display_text"),
                        "result": r})
        label = a.get("display_text") or a["tool_name"]
        if "error" in r:
            failed.append(label)
        else:
            succeeded.append(label)
            if a["tool_name"] in SNAPSHOT_WRITE_TOOLS:
                any_write = True
    if any_write:
        await snapshot_service.invalidate(workspace_id)
    if not failed:
        outcome = "completed"
    elif not succeeded:
        outcome = "failed"
    else:
        outcome = "partially_completed"
    return {"proposal_results": results, "outcome": outcome,
            "succeeded": succeeded, "failed": failed}


async def resolve_confirmation(db: AsyncSession, req: ChatRequest, approved: bool) -> None:
    """Xử lý xác nhận (hoặc từ chối) hành động nhạy cảm/bản nháp đang chờ; đưa request
    về queued để lần chạy run_agent_loop tiếp theo tự thấy tool_result trong history.
    Tool thật sự chạy (approved=True) được ghi 1 dòng AgentTrace route="confirm" —
    trước đây bị bỏ sót (backlog Phase 0), khiến tool nhạy cảm/proposal đã duyệt
    vô hình với observability."""
    if req.pending_action is None:
        raise ValueError("no_pending_action")
    actor = await db.get(User, req.user_id)
    action = req.pending_action
    # .get("kind", "tool"): dong pending_action tao TRUOC Phase 2 khong co "kind" —
    # mac dinh ve nhanh cu de tuong thich nguoc, khong can migrate du lieu.
    kind = action.get("kind", "tool")
    trace_tools: list[dict] = []
    if kind == "proposal":
        result = await _resolve_proposal(db, actor, action, approved, req.workspace_id,
                                         trace_tools)
    elif approved:
        tool_started = time.monotonic()
        result = await call_tool(db, actor, action["tool_name"], action["tool_input"])
        trace_tools.append(_tool_trace_entry(action["tool_name"], action["tool_input"], result,
                                             int((time.monotonic() - tool_started) * 1000)))
        if action["tool_name"] in SNAPSHOT_WRITE_TOOLS:
            await snapshot_service.invalidate(req.workspace_id)
    else:
        result = {"error": "user_denied", "message": "Người dùng từ chối xác nhận hành động này."}
    db.add(Message(workspace_id=req.workspace_id, conversation_id=req.conversation_id,
                   chat_request_id=req.id, role=MessageRole.user,
                   content=[{"type": "tool_result", "tool_use_id": action["tool_use_id"],
                            "content": json.dumps(result, default=str)}]))
    if trace_tools:
        db.add(AgentTrace(workspace_id=req.workspace_id, chat_request_id=req.id,
                          route="confirm", model="", iterations=0, stop_reason="confirmed",
                          tools_called=trace_tools,
                          total_latency_ms=sum(t["latency_ms"] for t in trace_tools)))
    req.pending_action = None
    req.status = ChatRequestStatus.queued
    await db.commit()
