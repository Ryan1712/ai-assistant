from app.agent.tools import TOOL_GROUPS, TOOLS


def test_every_tool_is_in_exactly_one_group():
    seen: dict[str, str] = {}
    for group_name, names in TOOL_GROUPS.items():
        for name in names:
            assert name in TOOLS, f"'{name}' trong nhóm '{group_name}' không phải tool có thật"
            assert name not in seen, (
                f"'{name}' trùng ở cả '{seen.get(name)}' và '{group_name}' — mỗi tool chỉ 1 nhóm"
            )
            seen[name] = group_name
    missing = set(TOOLS) - set(seen)
    assert not missing, f"Các tool chưa được phân nhóm: {sorted(missing)}"


def test_core_group_always_loaded_tools_present():
    core = TOOL_GROUPS["core"]
    for name in ("get_task", "search", "resolve_person", "resolve_task", "propose_actions"):
        assert name in core


def test_tool_groups_not_wired_into_api_tool_specs():
    # Phase 2 CHỦ Ý chưa lọc theo nhóm — Router (Phase 4) mới quyết định lọc.
    # Guard này canary nếu ai đó wiring sớm mà quên cập nhật design decision.
    from app.agent.loop import _tool_specs_for_api
    specs = _tool_specs_for_api()
    assert len(specs) == len(TOOLS)
