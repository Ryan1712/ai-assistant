"""Phase 5 (session model): nén rolling summary cho 1 conversation.

Khi số message sống (sau summary_through_at, đã lọc is_ack/rỗng) vượt
SUMMARY_TRIGGER → gộp phần cũ (trừ ~KEEP_RECENT đuôi) vào Conversation.rolling_summary
bằng 1 lượt model_fast KHÔNG tool. Summary tiêm vào SYSTEM prompt ở run_agent_loop,
KHÔNG bao giờ chèn làm message (bài học is_ack: phá luật user/assistant xen kẽ).
"""
from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_client import LLMClient, TextDelta
from app.models import ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole

SUMMARY_TRIGGER = 60
SUMMARY_KEEP_RECENT = 40

_SUMMARY_SYSTEM = (
    "Bạn là bộ nén hội thoại của một trợ lý điều hành công ty. Gộp phần tóm tắt cũ "
    "(nếu có) và đoạn hội thoại mới thành MỘT đoạn tóm tắt tiếng Việt ngắn gọn. "
    "BẮT BUỘC giữ lại: quyết định đã chốt, con số, tên người/task/project/deadline "
    "cụ thể, và việc còn dang dở. Bỏ lời chào và câu xã giao. Chỉ trả về đoạn tóm "
    "tắt, không thêm lời dẫn."
)


def _render_for_summary(msgs: list[Message]) -> str:
    lines: list[str] = []
    for m in msgs:
        who = "Người dùng" if m.role == MessageRole.user else "Trợ lý"
        texts = [b.get("text", "") for b in m.content if b.get("type") == "text"]
        tools = [b.get("name", "") for b in m.content if b.get("type") == "tool_use"]
        if texts:
            lines.append(f"{who}: {' '.join(t for t in texts if t)}")
        for name in tools:
            lines.append(f"Trợ lý gọi công cụ: {name}")
    return "\n".join(lines)


async def _summarize(llm: LLMClient, old_summary: str, chunk: str) -> str:
    prompt_parts = []
    if old_summary:
        prompt_parts.append("Tóm tắt hiện có:\n" + old_summary)
    prompt_parts.append("Đoạn hội thoại cần gộp vào tóm tắt:\n" + chunk)
    parts: list[str] = []
    async for event in llm.stream(
        system=_SUMMARY_SYSTEM,
        messages=[{"role": "user",
                   "content": [{"type": "text", "text": "\n\n".join(prompt_parts)}]}],
        tools=[]):
        if isinstance(event, TextDelta):
            parts.append(event.text)
    return "".join(parts).strip()


async def maybe_compress_history(db: AsyncSession, conv: Conversation, llm: LLMClient,
                                 *, force: bool = False,
                                 keep_recent: int = SUMMARY_KEEP_RECENT) -> bool:
    """Nén message cũ vào conv.rolling_summary nếu vượt ngưỡng (hoặc force). Trả True
    nếu đã nén + commit. force=True (dùng khi xoay conversation) bỏ qua SUMMARY_TRIGGER."""
    # Request CHƯA chạy (queued, hoặc cancelled chưa từng start): message của chúng
    # KHÔNG được fold vào summary. Nếu fold, watermark summary_through_at vượt qua
    # câu hỏi của chính request đó → _load_history (created_at > watermark) sẽ bỏ
    # luôn câu hỏi khi request tới lượt → model trả lời nhầm. Dùng cùng điều kiện
    # skip như _load_history (loop.py).
    skip_ids = select(ChatRequest.id).where(
        ChatRequest.conversation_id == conv.id,
        or_(ChatRequest.status == ChatRequestStatus.queued,
            and_(ChatRequest.status == ChatRequestStatus.cancelled,
                 ChatRequest.started_at.is_(None))),
    ).scalar_subquery()
    # Mốc thời gian sớm nhất của các message "chưa chạy" đó — watermark phải nằm
    # TRƯỚC mốc này (message xen kẽ theo created_at: R1 đang chạy có thể sinh
    # message SAU câu hỏi R2 queued).
    oldest_pending = (await db.execute(
        select(func.min(Message.created_at)).where(
            Message.conversation_id == conv.id,
            Message.chat_request_id.in_(skip_ids)))).scalar()

    stmt = select(Message).where(
        Message.conversation_id == conv.id, Message.is_ack.is_(False),
        Message.is_seed.is_(False),
        or_(Message.chat_request_id.is_(None), Message.chat_request_id.not_in(skip_ids)))
    if conv.summary_through_at is not None:
        stmt = stmt.where(Message.created_at > conv.summary_through_at)
    stmt = stmt.order_by(Message.created_at.asc(), Message.seq.asc())
    msgs = [m for m in (await db.execute(stmt)).scalars().all() if m.content]

    if not msgs:
        return False
    if not force and len(msgs) <= SUMMARY_TRIGGER:
        return False

    cut = max(0, len(msgs) - keep_recent)
    # Đuôi giữ lại phải bắt đầu bằng user-text (không mở đầu bằng tool_result mồ côi).
    while cut < len(msgs):
        m = msgs[cut]
        if (m.role == MessageRole.user and m.content
                and m.content[0].get("type") == "text"):
            break
        cut += 1
    to_fold = msgs[:cut]
    if oldest_pending is not None:
        # Không đẩy watermark tới/vượt message của request chưa chạy (dù message
        # đó đã bị loại khỏi msgs, message của R1 sinh SAU nó vẫn có thể lọt vào
        # to_fold và đẩy watermark qua mốc) — cắt to_fold về trước oldest_pending.
        to_fold = [m for m in to_fold if m.created_at < oldest_pending]
    if not to_fold:
        return False

    new_summary = await _summarize(llm, conv.rolling_summary, _render_for_summary(to_fold))
    if not new_summary:
        return False  # LLM trả rỗng -> đừng ghi đè summary cũ / đừng đẩy mốc
    conv.rolling_summary = new_summary
    conv.summary_through_at = to_fold[-1].created_at
    await db.commit()
    return True
