"""Router (Phase 4, spec AI upgrade §8.1): phân loại ý định câu nói -> tool cần
nạp + fast/deep path. Tier 1 heuristic (regex tiếng Việt, 0ms) trước; tier 2 (1
lượt model_fast, ép ra đúng 1 từ) chỉ khi tier 1 không chắc. Không chắc cả 2
tầng -> trả None (tầng gọi PHẢI fallback nạp full toolset — an toàn hơn thiếu
tool, đúng quyết định đã chốt ở Phase 2 §6.4).

Lưu ý thiết kế: heuristic CHỈ dùng cụm từ nhiều tiếng, tránh từ đơn phổ biến —
vd "mời" (admin, mời nhân viên) và "mới" (tính từ "mới", cực kỳ phổ biến, "task
mới") RÚT GỌN VỀ CÙNG "moi" sau khi bỏ dấu (dấu thanh + móc của "ơ" đều là
combining mark bị NFD tách ra), nên không dùng "moi" làm từ khóa đơn — sẽ khớp
nhầm hầu hết câu có "mới". Tương tự "hôm nay" quá phổ biến (xuất hiện trong câu
bất kỳ) nên không dùng làm từ khóa đơn cho nhóm insight. Coi mọi trường hợp mơ
hồ là việc của tier 2 / fallback, không cố phủ hết bằng regex.
"""
from __future__ import annotations

import re
import unicodedata

from app.agent.llm_client import LLMClient
from app.agent.tools import TOOL_GROUPS

_VALID_TIER2_WORDS = {"work", "insight", "admin", "reporting", "skill", "personal", "deep"}
# Tier 2 trả từ ngắn gọn "skill" — map sang tên nhóm thật trong TOOL_GROUPS.
_ROUTE_TO_GROUP = {"skill": "skill_instruction"}


def _strip_diacritics(text: str) -> str:
    # "đ"/"Đ" là ký tự gốc riêng (Latin d with stroke), KHÔNG phân rã qua NFD như
    # các dấu thanh/móc khác (vd "ơ" -> "o" + combining horn) — phải tự thay tay,
    # nếu không "đánh giá" sẽ còn "đanh gia" chứ không thành "danh gia".
    text = text.replace("đ", "d").replace("Đ", "D")
    norm = unicodedata.normalize("NFD", text)
    return "".join(c for c in norm if unicodedata.category(c) != "Mn").lower()


# Thứ tự có ý nghĩa: kiểm tra deep trước để câu vừa có ý phân tích vừa nhắc tới
# task/dự án (rất thường gặp, vd "phân tích rủi ro dự án X") vẫn được xếp deep.
_HEURISTIC_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("deep", re.compile(
        r"\b(phan tich|danh gia|vi sao|tai sao|so sanh|nhan xet|rui ro|"
        r"bao cao chi tiet|tong ket tinh hinh)\b")),
    ("admin", re.compile(
        r"\b(khoa tai khoan|mo khoa|phan quyen|nghi viec|doi vai tro|"
        r"them nhan vien|them quan ly|nhat ky he thong)\b")),
    ("reporting", re.compile(
        r"\b(xuat bao cao|xuat file|xuat excel|lich bao cao|tai file bao cao)\b")),
    ("skill", re.compile(
        r"\b(skill|ky nang lam viec|huong dan su dung)\b")),
    ("personal", re.compile(
        r"\b(ghi chu|ghi am|thong bao cua toi)\b")),
    ("insight", re.compile(
        r"\b(tinh trang cong ty|tien do du an|dashboard|tuan nay lam duoc|"
        r"thang nay tien do|so voi ky truoc)\b")),
    ("work", re.compile(
        r"\b(giao viec|cap nhat tien do|tao task|tao du an|deadline|"
        r"gan task|hoan thanh task)\b")),
]


def classify_heuristic(text: str) -> str | None:
    """Tier 1 — 0ms, không gọi model. Trả None nếu không khớp cụm nào (không
    chắc), tầng gọi (classify_route) sẽ thử tier 2."""
    norm = _strip_diacritics(text)
    for route, pattern in _HEURISTIC_PATTERNS:
        if pattern.search(norm):
            return route
    return None


_TIER2_SYSTEM = (
    "Phân loại câu sau vào ĐÚNG MỘT từ trong danh sách: work, insight, admin, "
    "reporting, skill, personal, deep. Chỉ trả về đúng 1 từ đó, không giải "
    "thích, không thêm chữ nào khác."
)


async def classify_route(text: str, llm_fast: LLMClient) -> str | None:
    """Trả route ('work'|'insight'|'admin'|'reporting'|'skill'|'personal'|'deep')
    hoặc None nếu không chắc ở cả 2 tầng — tầng gọi PHẢI fallback nạp full
    toolset khi None, không được tự đoán."""
    heuristic = classify_heuristic(text)
    if heuristic is not None:
        return heuristic

    reply = ""
    async for event in llm_fast.stream(
        system=_TIER2_SYSTEM,
        messages=[{"role": "user", "content": [{"type": "text", "text": text}]}],
        tools=[],
    ):
        if hasattr(event, "text"):
            reply += event.text
    word = reply.strip().lower()
    return word if word in _VALID_TIER2_WORDS else None


def tool_names_for_route(route: str | None) -> set[str] | None:
    """Tên tool cần nạp cho route (core + nhóm tương ứng). None nếu route
    không rõ HOẶC route="deep" (đường sâu dùng riêng nhóm insight + luồng khác
    hẳn ở worker.py, không đi qua toolset của fast path này)."""
    if route is None or route == "deep":
        return None
    group = _ROUTE_TO_GROUP.get(route, route)
    if group not in TOOL_GROUPS:
        return None
    return set(TOOL_GROUPS["core"]) | set(TOOL_GROUPS[group])
