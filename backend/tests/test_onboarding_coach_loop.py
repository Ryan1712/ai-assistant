import uuid

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.loop import _build_system_prompt, run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    ChatRequest, Conversation, Message, MessageRole, Project, Report, Role, Task,
    TaskStatus, User, Workspace,
)


async def _seed(db, role=Role.ceo):
    ws = Workspace(name="Cong ty D")
    db.add(ws)
    await db.flush()
    actor = User(workspace_id=ws.id, email="d@a.vn", password_hash="x", full_name="D",
                role=role, is_root=(role == Role.ceo))
    db.add(actor)
    await db.flush()
    return ws, actor


async def _run(db, ws, actor, content="xin chao"):
    conv = Conversation(workspace_id=ws.id, user_id=actor.id)
    db.add(conv)
    await db.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=actor.id,
                      content=content, queue_position=1.0)
    db.add(req)
    await db.flush()
    db.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                   role=MessageRole.user, content=[{"type": "text", "text": content}]))
    await db.commit()
    llm = FakeLLMClient(turns=[[TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)]])
    await run_agent_loop(db, req, llm, FakeEventPublisher())
    return llm.calls[0]["system"]


def _system_text(system):
    return system if isinstance(system, str) else "\n".join(
        b["text"] for b in system if b.get("type") == "text")


async def test_coach_block_hien_voi_ceo_workspace_rong(db_session):
    ws, ceo = await _seed(db_session, role=Role.ceo)
    system = await _run(db_session, ws, ceo)
    assert "Gợi ý dẫn dắt" in _system_text(system)


async def test_coach_block_khong_hien_voi_manager(db_session):
    ws, manager = await _seed(db_session, role=Role.manager)
    system = await _run(db_session, ws, manager)
    assert "Gợi ý dẫn dắt" not in _system_text(system)


async def test_coach_block_khong_hien_khi_du_setup(db_session):
    ws, ceo = await _seed(db_session, role=Role.ceo)
    proj = Project(workspace_id=ws.id, name="Du an", created_by=ceo.id)
    db_session.add(proj)
    await db_session.flush()
    db_session.add(Task(workspace_id=ws.id, project_id=proj.id, title="T1",
                        status=TaskStatus.todo, created_by=ceo.id))
    other = User(workspace_id=ws.id, email="mgr@a.vn", password_hash="x", full_name="M",
                role=Role.manager)
    db_session.add(other)
    db_session.add(Report(workspace_id=ws.id, requested_by=ceo.id, file_path="x.xlsx"))
    await db_session.commit()
    system = await _run(db_session, ws, ceo)
    assert "Gợi ý dẫn dắt" not in _system_text(system)


def test_system_prompt_tinh_co_huong_dan_import_text():
    actor = User(id=uuid.uuid4(), workspace_id=uuid.uuid4(), email="x@a.vn",
                password_hash="x", full_name="X", role=Role.ceo)
    prompt = _build_system_prompt(actor)
    assert "propose_actions" in prompt
    assert "dán" in prompt.lower() or "liệt kê nhiều công việc" in prompt
