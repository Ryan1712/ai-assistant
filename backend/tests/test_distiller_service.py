"""Distiller — bộ nhớ dài hạn công ty (spec AI upgrade §10.2).

Cron chạy mỗi phút (giống watcher/report-schedule) nhưng hàm tự guard chỉ
thực sự chưng cất đúng phút 02:00 giờ VN. Dedup theo cosine similarity qua
hạ tầng embedding_service có sẵn (Phase 6 §10.3) — KHÔNG phải bảng riêng.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.models import Project, Role, Task, TaskUpdate, User, Workspace, WorkspaceMemory
from app.services import distiller_service

# 19:00 UTC (ngày trước) = 02:00 VN hôm sau (UTC+7)
TWO_AM_VN = datetime(2026, 7, 24, 19, 0, tzinfo=timezone.utc)


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    p = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db.add(p)
    await db.flush()
    t = Task(workspace_id=ws.id, project_id=p.id, title="T", created_by=ceo.id)
    db.add(t)
    await db.flush()
    await db.commit()
    return ws, ceo, t


def _llm(reply: str):
    return FakeLLMClient(turns=[[
        TextDelta(text=reply),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])


@pytest.mark.asyncio
async def test_distill_only_runs_at_two_am_vn(db_session):
    ws, ceo, t = await _world(db_session)
    db_session.add(TaskUpdate(workspace_id=ws.id, task_id=t.id, author_id=ceo.id,
                              content="Doi tac X doi lich giao hang sang thang sau",
                              created_at=TWO_AM_VN))
    await db_session.commit()

    not_two_am = TWO_AM_VN.replace(hour=10)
    count = await distiller_service.distill_workspace_memories(
        db_session, _llm("Đối tác X dời lịch giao hàng sang tháng sau."), now=not_two_am)

    assert count == 0
    assert (await db_session.execute(select(WorkspaceMemory))).scalars().all() == []


@pytest.mark.asyncio
async def test_distill_extracts_fact_from_todays_task_updates(db_session):
    ws, ceo, t = await _world(db_session)
    db_session.add(TaskUpdate(workspace_id=ws.id, task_id=t.id, author_id=ceo.id,
                              content="Doi tac X doi lich giao hang sang thang sau",
                              created_at=TWO_AM_VN))
    await db_session.commit()

    llm = _llm("Đối tác X dời lịch giao hàng sang tháng sau.")
    count = await distiller_service.distill_workspace_memories(db_session, llm, now=TWO_AM_VN)

    assert count == 1
    mem = (await db_session.execute(select(WorkspaceMemory))).scalar_one()
    assert mem.workspace_id == ws.id
    assert mem.scope == "workspace"
    assert mem.source == "distiller"
    assert "Đối tác X" in mem.content


@pytest.mark.asyncio
async def test_distill_skips_when_model_says_khong(db_session):
    ws, ceo, t = await _world(db_session)
    db_session.add(TaskUpdate(workspace_id=ws.id, task_id=t.id, author_id=ceo.id,
                              content="cap nhat vun vat hang ngay", created_at=TWO_AM_VN))
    await db_session.commit()

    count = await distiller_service.distill_workspace_memories(
        db_session, _llm("KHÔNG"), now=TWO_AM_VN)

    assert count == 0
    assert (await db_session.execute(select(WorkspaceMemory))).scalars().all() == []


@pytest.mark.asyncio
async def test_distill_no_task_updates_today_skips_workspace_no_llm_call(db_session):
    ws, ceo, t = await _world(db_session)
    llm = _llm("khong quan trong")

    count = await distiller_service.distill_workspace_memories(db_session, llm, now=TWO_AM_VN)

    assert count == 0
    assert llm.calls == []


@pytest.mark.asyncio
async def test_distill_dedup_skips_near_duplicate_fact(db_session):
    ws, ceo, t = await _world(db_session)
    db_session.add(TaskUpdate(workspace_id=ws.id, task_id=t.id, author_id=ceo.id,
                              content="Doi tac X doi lich giao hang sang thang sau",
                              created_at=TWO_AM_VN))
    await db_session.commit()

    same_fact = "Đối tác X dời lịch giao hàng sang tháng sau."
    first = await distiller_service.distill_workspace_memories(
        db_session, _llm(same_fact), now=TWO_AM_VN)
    assert first == 1

    next_day = TWO_AM_VN + timedelta(days=1)
    second = await distiller_service.distill_workspace_memories(
        db_session, _llm(same_fact), now=next_day)

    assert second == 0  # trùng ý với fact hôm qua -> dedup, không thêm bản 2
    assert len((await db_session.execute(select(WorkspaceMemory))).scalars().all()) == 1


# ---------------------------------------------------------------------------
# active_memories_text — tiêm vào system prompt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_active_memories_text_includes_workspace_scope(db_session):
    ws, ceo, t = await _world(db_session)
    db_session.add(WorkspaceMemory(workspace_id=ws.id, scope="workspace",
                                   content="Công ty ưu tiên dự án Marketing Q3",
                                   source="distiller"))
    await db_session.commit()

    text = await distiller_service.active_memories_text(db_session, ceo)
    assert "# Ghi nhớ dài hạn" in text
    assert "Marketing Q3" in text


@pytest.mark.asyncio
async def test_active_memories_text_excludes_archived(db_session):
    ws, ceo, t = await _world(db_session)
    db_session.add(WorkspaceMemory(workspace_id=ws.id, scope="workspace",
                                   content="Fact da bi quen", source="distiller",
                                   archived_at=datetime.now(timezone.utc)))
    await db_session.commit()

    text = await distiller_service.active_memories_text(db_session, ceo)
    assert text == ""


@pytest.mark.asyncio
async def test_active_memories_text_excludes_other_workspace(db_session):
    ws, ceo, t = await _world(db_session)
    other_ws = Workspace(name="B")
    db_session.add(other_ws)
    await db_session.flush()
    db_session.add(WorkspaceMemory(workspace_id=other_ws.id, scope="workspace",
                                   content="Fact cua cong ty khac", source="distiller"))
    await db_session.commit()

    text = await distiller_service.active_memories_text(db_session, ceo)
    assert text == ""


# ---------------------------------------------------------------------------
# list_memories / forget_memory — CEO-only
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_memories_requires_ceo(db_session):
    from fastapi import HTTPException

    ws, ceo, t = await _world(db_session)
    employee = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
                    role=Role.employee)
    db_session.add(employee)
    await db_session.commit()

    with pytest.raises(HTTPException):
        await distiller_service.list_memories(db_session, employee)


@pytest.mark.asyncio
async def test_list_memories_excludes_archived(db_session):
    ws, ceo, t = await _world(db_session)
    db_session.add_all([
        WorkspaceMemory(workspace_id=ws.id, scope="workspace", content="Con hieu luc",
                        source="distiller"),
        WorkspaceMemory(workspace_id=ws.id, scope="workspace", content="Da quen",
                        source="distiller", archived_at=datetime.now(timezone.utc)),
    ])
    await db_session.commit()

    memories = await distiller_service.list_memories(db_session, ceo)
    assert [m["content"] for m in memories] == ["Con hieu luc"]


@pytest.mark.asyncio
async def test_forget_memory_archives_and_requires_ceo(db_session):
    from fastapi import HTTPException

    ws, ceo, t = await _world(db_session)
    employee = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
                    role=Role.employee)
    db_session.add(employee)
    mem = WorkspaceMemory(workspace_id=ws.id, scope="workspace", content="X", source="distiller")
    db_session.add(mem)
    await db_session.commit()

    with pytest.raises(HTTPException):
        await distiller_service.forget_memory(db_session, employee, mem.id)

    await distiller_service.forget_memory(db_session, ceo, mem.id)
    await db_session.refresh(mem)
    assert mem.archived_at is not None
