"""Example bank — "fine-tune bằng context" (spec AI upgrade §10.4).

FewShotExample.workspace_id NULL = ví dụ toàn cục dùng chung mọi workspace —
NGOẠI LỆ có chủ đích với quy ước "mọi bảng có workspace_id, mọi query lọc
theo workspace_id" (CLAUDE.md) vì đây là nội dung do dev/ops chọn lọc (cách
AI nên hành xử), không phải dữ liệu khách hàng. add_example() (tool CEO-dùng
qua chat) CHỈ tạo được ví dụ SCOPE THEO WORKSPACE CỦA CHÍNH ACTOR — KHÔNG có
đường nào từ tool tạo ra ví dụ global (đó là hành động XUYÊN TENANT, ngoài
phạm vi 1 CEO của 1 workspace); ví dụ global chỉ tạo được bằng cách seed
thẳng vào DB/script của dev.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import FewShotExample, Role, User, Workspace
from app.services import example_bank_service


async def _ceo(db, name="A"):
    ws = Workspace(name=name)
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email=f"c-{name}@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    await db.commit()
    return ws, ceo


@pytest.mark.asyncio
async def test_add_example_creates_workspace_scoped_row(db_session):
    ws, ceo = await _ceo(db_session)

    example = await example_bank_service.add_example(
        db_session, ceo, user_text="khoa acc thang Nam",
        ideal_behavior="gọi lock_user ngay, hệ thống tự hiện xác nhận, không hỏi lại bằng lời")

    assert example["workspace_id"] == str(ws.id)
    row = await db_session.get(FewShotExample, example["id"])
    assert row.workspace_id == ws.id  # KHÔNG BAO GIỜ None (global) qua đường tool


@pytest.mark.asyncio
async def test_add_example_requires_ceo(db_session):
    ws, ceo = await _ceo(db_session)
    employee = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
                    role=Role.employee)
    db_session.add(employee)
    await db_session.commit()

    with pytest.raises(HTTPException):
        await example_bank_service.add_example(db_session, employee, user_text="x",
                                                ideal_behavior="y")


@pytest.mark.asyncio
async def test_build_example_block_finds_relevant_workspace_example(db_session):
    ws, ceo = await _ceo(db_session)
    await example_bank_service.add_example(
        db_session, ceo, user_text="khoa tai khoan nhan vien Nam",
        ideal_behavior="gọi lock_user ngay, không hỏi xác nhận bằng lời")

    block = await example_bank_service.build_example_block(
        db_session, ws.id, "khoa acc cua Nam giup toi")

    assert block.startswith("# Ví dụ xử lý đúng")
    assert "lock_user" in block


@pytest.mark.asyncio
async def test_build_example_block_includes_global_example(db_session):
    ws, ceo = await _ceo(db_session)
    # Global chỉ seed thẳng DB (mô phỏng dev/ops), KHÔNG qua add_example.
    global_ex = FewShotExample(workspace_id=None,
                               user_text="tao task moi cho du an X",
                               ideal_behavior="gọi create_task ngay nếu đủ thông tin")
    db_session.add(global_ex)
    await db_session.commit()
    await example_bank_service.index_example(db_session, global_ex)

    block = await example_bank_service.build_example_block(
        db_session, ws.id, "tao task moi cho du an Marketing")

    assert "create_task" in block


@pytest.mark.asyncio
async def test_build_example_block_excludes_other_workspace_example(db_session):
    ws_a, ceo_a = await _ceo(db_session, "A")
    ws_b, ceo_b = await _ceo(db_session, "B")
    await example_bank_service.add_example(
        db_session, ceo_b, user_text="khoa tai khoan nhan vien Nam",
        ideal_behavior="gọi lock_user ngay")

    block = await example_bank_service.build_example_block(
        db_session, ws_a.id, "khoa acc cua Nam giup toi")

    assert block == ""


@pytest.mark.asyncio
async def test_build_example_block_empty_when_no_match(db_session):
    ws, ceo = await _ceo(db_session)
    await example_bank_service.add_example(
        db_session, ceo, user_text="khoa tai khoan nhan vien Nam",
        ideal_behavior="gọi lock_user ngay")

    block = await example_bank_service.build_example_block(
        db_session, ws.id, "xyzabc khong lien quan gi ca 123999")

    assert block == ""
