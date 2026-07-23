import pytest

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.router import classify_heuristic, classify_route, tool_names_for_route
from app.agent.tools import TOOL_GROUPS


@pytest.mark.parametrize("text,expected", [
    ("Phân tích rủi ro dự án Marketing tháng này", "deep"),
    ("Đánh giá xem đội đang làm tốt không", "deep"),
    ("Vì sao task này lại trễ hạn vậy", "deep"),
    ("Khóa tài khoản của Duy ngay", "admin"),
    ("Thêm nhân viên mới tên Lan", "admin"),
    ("Cho tôi xuất báo cáo doanh thu tháng 6", "reporting"),
    ("Hướng dẫn sử dụng skill soạn hợp đồng", "skill"),
    ("Tạo ghi chú nhắc việc mai", "personal"),
    ("Tình trạng công ty hôm nay ra sao", "insight"),
    ("So với kỳ trước thì đội làm tốt hơn không", "insight"),
    ("Tạo task mới cho dự án X", "work"),
    ("Giao việc này cho Nam nhé", "work"),
])
def test_classify_heuristic_matches_expected_group(text, expected):
    assert classify_heuristic(text) == expected


def test_classify_heuristic_diacritic_insensitive():
    assert classify_heuristic("danh gia rui ro du an") == "deep"


def test_classify_heuristic_no_match_returns_none():
    assert classify_heuristic("xin chao ban khoe khong") is None


def test_classify_heuristic_moi_alone_does_not_false_positive_admin():
    """'mới' (tính từ, rất phổ biến) và 'mời' (admin) rút gọn về cùng 'moi' sau
    khi bỏ dấu — heuristic KHÔNG được dùng 'moi' đơn làm từ khóa admin, nếu
    không câu này sẽ bị xếp nhầm admin thay vì work."""
    assert classify_heuristic("Tạo task mới cho dự án X") != "admin"


@pytest.mark.asyncio
async def test_classify_route_uses_heuristic_first_without_calling_llm():
    llm = FakeLLMClient(turns=[])
    route = await classify_route("Khóa tài khoản của Duy ngay", llm)
    assert route == "admin"
    assert llm.calls == []


@pytest.mark.asyncio
async def test_classify_route_falls_back_to_tier2_when_heuristic_unsure():
    llm = FakeLLMClient(turns=[[TextDelta(text="work"),
                               StreamDone(tool_uses=[], stop_reason="end_turn",
                                         input_tokens=5, output_tokens=1)]])
    route = await classify_route("Ê Duy ơi làm cái kia đi", llm)
    assert route == "work"
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_classify_route_tier2_garbage_output_falls_back_to_none():
    llm = FakeLLMClient(turns=[[TextDelta(text="khong biet"),
                               StreamDone(tool_uses=[], stop_reason="end_turn",
                                         input_tokens=5, output_tokens=2)]])
    route = await classify_route("blah blah unclear message", llm)
    assert route is None


def test_tool_names_for_route_core_plus_group():
    names = tool_names_for_route("admin")
    assert names == set(TOOL_GROUPS["core"]) | set(TOOL_GROUPS["admin"])


def test_tool_names_for_route_skill_maps_to_skill_instruction_group():
    names = tool_names_for_route("skill")
    assert names == set(TOOL_GROUPS["core"]) | set(TOOL_GROUPS["skill_instruction"])


def test_tool_names_for_route_deep_or_none_returns_none():
    assert tool_names_for_route("deep") is None
    assert tool_names_for_route(None) is None
