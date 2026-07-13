"""Đếm số WebSocket đang mở per-conversation (funtional-plan 5.7).

In-process (module-level dict) — đúng khi API chạy 1 instance như hiện tại.
Nếu sau này API scale nhiều instance, chuyển counter sang redis (INCR/DECR
kèm TTL) và giữ nguyên interface connect/disconnect.
"""
import uuid

_counts: dict[uuid.UUID, int] = {}


def connect(conversation_id: uuid.UUID) -> int:
    """Socket mở thêm — trả về số socket đang mở sau khi tăng."""
    _counts[conversation_id] = _counts.get(conversation_id, 0) + 1
    return _counts[conversation_id]


def disconnect(conversation_id: uuid.UUID) -> int:
    """Socket đóng — trả về số socket còn lại (floor 0; 0 = user rời hẳn)."""
    remaining = max(0, _counts.get(conversation_id, 0) - 1)
    if remaining == 0:
        _counts.pop(conversation_id, None)
    else:
        _counts[conversation_id] = remaining
    return remaining


def reset() -> None:
    """Xóa toàn bộ counter — chỉ dùng trong test."""
    _counts.clear()
