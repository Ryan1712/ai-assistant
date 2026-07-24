import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.publisher import FakeEventPublisher
from app.agent.worker import WorkerSettings, enqueue_conversation, process_conversation
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Role, User, Workspace,
)
from app.services import note_service


@pytest.mark.asyncio
async def test_process_conversation_runs_queued_requests_in_order_then_stops(engine, db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    other_conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add_all([conv, other_conv])
    await db_session.flush()

    # Noi dung khop heuristic tier 1 (router.py) ro rang - tranh ton them 1 luot
    # goi FakeLLMClient cho tier 2 (khong lien quan muc dich test nay).
    req1 = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                       content="xem dashboard hom nay", queue_position=1.0)
    req2 = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                       content="tao task moi cho du an X", queue_position=2.0)
    other_req = ChatRequest(workspace_id=ws.id, conversation_id=other_conv.id, user_id=ceo.id,
                            content="khac conversation", queue_position=1.0)
    db_session.add_all([req1, req2, other_req])
    await db_session.flush()
    for req in (req1, req2, other_req):
        db_session.add(Message(workspace_id=ws.id, conversation_id=req.conversation_id,
                               chat_request_id=req.id, role=MessageRole.user,
                               content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[
        [TextDelta(text="tra loi 1"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
        [TextDelta(text="tra loi 2"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
    ])
    pub = FakeEventPublisher()

    async def never_cancelled(_id):
        return False

    ctx = {
        "session_factory": async_sessionmaker(engine, expire_on_commit=False),
        "llm_client": llm,
        "event_publisher": pub,
        "is_cancelled": never_cancelled,
    }

    await process_conversation(ctx, conv.id)

    await db_session.refresh(req1)
    await db_session.refresh(req2)
    await db_session.refresh(other_req)
    assert req1.status == ChatRequestStatus.done
    assert req2.status == ChatRequestStatus.done
    assert other_req.status == ChatRequestStatus.queued  # conversation khác không bị đụng tới
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_process_conversation_blocks_queue_while_awaiting_confirmation(engine, db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add(conv)
    await db_session.flush()

    paused_req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                             content="khoa mot nguoi", queue_position=1.0,
                             status=ChatRequestStatus.awaiting_confirmation,
                             pending_action={"tool_name": "lock_user",
                                            "tool_input": {"target_id": str(ceo.id)},
                                            "tool_use_id": "t1"})
    queued_req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                             content="tin nhan tiep theo", queue_position=2.0)
    db_session.add_all([paused_req, queued_req])
    await db_session.flush()
    for req in (paused_req, queued_req):
        db_session.add(Message(workspace_id=ws.id, conversation_id=req.conversation_id,
                               chat_request_id=req.id, role=MessageRole.user,
                               content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[])
    pub = FakeEventPublisher()

    async def never_cancelled(_id):
        return False

    ctx = {
        "session_factory": async_sessionmaker(engine, expire_on_commit=False),
        "llm_client": llm,
        "event_publisher": pub,
        "is_cancelled": never_cancelled,
    }

    await process_conversation(ctx, conv.id)

    await db_session.refresh(paused_req)
    await db_session.refresh(queued_req)
    assert queued_req.status == ChatRequestStatus.queued  # khong bi dong xu ly
    assert paused_req.status == ChatRequestStatus.awaiting_confirmation  # khong bi dung
    assert len(llm.calls) == 0  # khong goi LLM nao het, vi queue bi chan ngay tu dau


@pytest.mark.asyncio
async def test_process_conversation_stops_when_queue_held(engine, db_session):
    """5.7: mất mạng/đóng app → queue_held; worker không tự chạy tiếp."""
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id, queue_held=True)
    db_session.add(conv)
    await db_session.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="viec dang do", queue_position=1.0)
    db_session.add(req)
    await db_session.flush()
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id,
                           chat_request_id=req.id, role=MessageRole.user,
                           content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[])
    pub = FakeEventPublisher()

    async def never_cancelled(_id):
        return False

    ctx = {
        "session_factory": async_sessionmaker(engine, expire_on_commit=False),
        "llm_client": llm,
        "event_publisher": pub,
        "is_cancelled": never_cancelled,
    }

    await process_conversation(ctx, conv.id)

    await db_session.refresh(req)
    assert req.status == ChatRequestStatus.queued  # được ghi nhớ, không chạy
    assert len(llm.calls) == 0


@pytest.mark.asyncio
async def test_process_conversation_routes_deep_request_to_ack_then_enqueues_job(engine, db_session):
    """Task 8: request khop route "deep" (router.py tier 1) phai di qua
    run_deep_ack_turn - KHONG phai run_agent_loop thuong - roi tu enqueue job
    run_deep_analysis rieng qua ctx["arq_pool"]. Queue KHONG bi chan cho job nen
    nay (process_conversation tra ve ngay sau khi enqueue, khong cho job chay)."""
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add(conv)
    await db_session.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="phan tich rui ro du an thang nay", queue_position=1.0)
    db_session.add(req)
    await db_session.flush()
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[
        [TextDelta(text="Da nhan, dang phan tich sau..."),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
    ])
    pub = FakeEventPublisher()

    class _FakePool:
        def __init__(self):
            self.calls = []

        async def enqueue_job(self, name, *args, **kwargs):
            self.calls.append((name, args, kwargs))
            return "job-handle"

    pool = _FakePool()

    async def never_cancelled(_id):
        return False

    ctx = {
        "session_factory": async_sessionmaker(engine, expire_on_commit=False),
        "llm_client": llm,
        "event_publisher": pub,
        "is_cancelled": never_cancelled,
        "arq_pool": pool,
    }

    await process_conversation(ctx, conv.id)

    await db_session.refresh(req)
    assert req.status == ChatRequestStatus.deep_running
    assert len(llm.calls) == 1  # chi 1 luot ack, khong chay tool loop thuong
    assert pool.calls == [("run_deep_analysis", (req.id,), {"_job_id": f"deep:{req.id}"})]
    event_types = [event["type"] for _conv_id, event in pub.events]
    assert "deep_analysis_started" in event_types
    assert "request_done" not in event_types  # job nen chua xong that


@pytest.mark.asyncio
async def test_process_conversation_filters_toolset_by_classified_route(engine, db_session):
    """Task 8: request KHONG khop "deep" van chay run_agent_loop nhu cu, nhung
    toolset da bi loc theo group phan loai duoc (an toan: fallback full toolset
    neu khong chac - da co san o tool_names_for_route/router.py)."""
    from app.agent.tools import TOOL_GROUPS

    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add(conv)
    await db_session.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="tao task moi cho du an X", queue_position=1.0)
    db_session.add(req)
    await db_session.flush()
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
    ])

    async def never_cancelled(_id):
        return False

    ctx = {
        "session_factory": async_sessionmaker(engine, expire_on_commit=False),
        "llm_client": llm,
        "event_publisher": FakeEventPublisher(),
        "is_cancelled": never_cancelled,
    }

    await process_conversation(ctx, conv.id)

    await db_session.refresh(req)
    assert req.status == ChatRequestStatus.done
    called_tool_names = {t["name"] for t in llm.calls[0]["tools"]}
    assert called_tool_names == set(TOOL_GROUPS["core"]) | set(TOOL_GROUPS["work"])


@pytest.mark.asyncio
async def test_process_conversation_injects_rag_context_once_before_loop(engine, db_session):
    """Phase 6 §10.3 fast-follow: worker tính rag_context ĐÚNG MỘT LẦN lúc pickup
    (giống Router) rồi truyền vào run_agent_loop — không phải loop tự gọi lại
    semantic_search mỗi vòng."""
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    await note_service.create_note(db_session, ceo, content="Nho ky hop dong doi tac XYZ")
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add(conv)
    await db_session.flush()
    # "tinh trang cong ty" khớp heuristic tier 1 (nhóm insight) -> khỏi tốn 1
    # lượt LLM cho classify_route tier 2, llm.calls[0] chắc chắn là lượt
    # run_agent_loop thật (không lẫn lượt phân loại route).
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="tinh trang cong ty ve hop dong doi tac XYZ the nao roi",
                      queue_position=1.0)
    db_session.add(req)
    await db_session.flush()
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
    ])

    async def never_cancelled(_id):
        return False

    ctx = {
        "session_factory": async_sessionmaker(engine, expire_on_commit=False),
        "llm_client": llm,
        "event_publisher": FakeEventPublisher(),
        "is_cancelled": never_cancelled,
    }

    await process_conversation(ctx, conv.id)

    system = llm.calls[0]["system"]
    text = system if isinstance(system, str) else "\n".join(b["text"] for b in system)
    assert "Dữ liệu liên quan" in text
    assert "XYZ" in text


@pytest.mark.asyncio
async def test_enqueue_conversation_uses_conversation_scoped_job_id():
    class _FakePool:
        def __init__(self):
            self.calls = []

        async def enqueue_job(self, name, *args, **kwargs):
            self.calls.append((name, args, kwargs))
            return "job-handle"

    pool = _FakePool()
    conv_id = uuid.uuid4()
    result = await enqueue_conversation(pool, conv_id)

    assert result == "job-handle"
    name, args, kwargs = pool.calls[0]
    assert name == "process_conversation"
    assert args == (conv_id,)
    assert kwargs["_job_id"] == f"conv:{conv_id}"


def test_worker_settings_registers_process_conversation():
    assert process_conversation in WorkerSettings.functions
    assert WorkerSettings.redis_settings is not None


def test_worker_settings_has_explicit_max_jobs_and_job_timeout():
    """Finding 3 (final review): max_jobs bounds how many conversations can run
    Claude calls concurrently (per design spec); job_timeout must comfortably exceed
    MAX_ITERATIONS' realistic wall-clock time so the loop's own cap (Finding 2) is
    what normally ends a runaway job, not arq killing it via CancelledError."""
    assert WorkerSettings.max_jobs == 10
    assert WorkerSettings.job_timeout == 600


def test_worker_settings_registers_report_schedule_cron():
    """Plan 9: báo cáo định kỳ tự động — arq cron quét ReportSchedule mỗi phút."""
    from app.agent.worker import check_report_schedules

    assert WorkerSettings.cron_jobs is not None
    names = [j.name for j in WorkerSettings.cron_jobs]
    assert "cron:check_report_schedules" in names
    job = next(j for j in WorkerSettings.cron_jobs if j.name == "cron:check_report_schedules")
    assert job.coroutine is check_report_schedules


def test_worker_settings_registers_directive_escalation_cron():
    """Phase 3 §7.3: arq cron nhắc/escalate Directive chưa xác nhận sau 24h/48h."""
    from app.agent.worker import check_directive_escalations

    names = [j.name for j in WorkerSettings.cron_jobs]
    assert "cron:check_directive_escalations" in names
    job = next(j for j in WorkerSettings.cron_jobs
              if j.name == "cron:check_directive_escalations")
    assert job.coroutine is check_directive_escalations


def test_worker_settings_registers_morning_brief_cron():
    """Phase 6 §10.2 watcher: arq cron 07:00 VN, guard giờ nằm trong watcher_service."""
    from app.agent.worker import send_morning_briefs

    names = [j.name for j in WorkerSettings.cron_jobs]
    assert "cron:send_morning_briefs" in names
    job = next(j for j in WorkerSettings.cron_jobs if j.name == "cron:send_morning_briefs")
    assert job.coroutine is send_morning_briefs


def test_worker_settings_registers_distiller_cron():
    """Phase 6 §10.2 distiller: arq cron 02:00 VN, guard giờ nằm trong distiller_service."""
    from app.agent.worker import distill_workspace_memories

    names = [j.name for j in WorkerSettings.cron_jobs]
    assert "cron:distill_workspace_memories" in names
    job = next(j for j in WorkerSettings.cron_jobs
              if j.name == "cron:distill_workspace_memories")
    assert job.coroutine is distill_workspace_memories


@pytest.mark.asyncio
async def test_check_directive_escalations_calls_escalate_overdue(engine, monkeypatch):
    from app.agent import worker as worker_module

    called = {}

    async def fake_escalate_overdue(db):
        called["db"] = db
        return 0

    monkeypatch.setattr(worker_module.directive_service, "escalate_overdue",
                        fake_escalate_overdue)
    ctx = {"session_factory": async_sessionmaker(engine, expire_on_commit=False)}

    await worker_module.check_directive_escalations(ctx)

    assert "db" in called


@pytest.mark.asyncio
async def test_check_report_schedules_calls_run_due_schedules(engine, monkeypatch):
    from app.agent import worker as worker_module

    called = {}

    async def fake_run_due_schedules(db):
        called["db"] = db
        return []

    monkeypatch.setattr(worker_module.report_schedule_service, "run_due_schedules",
                        fake_run_due_schedules)
    ctx = {"session_factory": async_sessionmaker(engine, expire_on_commit=False)}

    await worker_module.check_report_schedules(ctx)

    assert "db" in called


def test_worker_settings_does_not_keep_result():
    """Bug tìm ra khi chạy LLM thật (2026-07-13): job_id cố định conv:{id} + arq
    keep_result mặc định 3600s ⇒ sau khi job xong, mọi enqueue cùng conversation
    trong 1 giờ bị arq từ chối lặng lẽ — tin nhắn thứ 2 không bao giờ được xử lý.
    keep_result=0 giải phóng job_id ngay khi xong (vẫn dedup lúc đang chạy)."""
    assert WorkerSettings.keep_result == 0


@pytest.mark.asyncio
async def test_run_deep_analysis_uses_smart_client_and_insight_toolset(engine, db_session):
    """Phase 4 §8.2 Task 7: job nền đường sâu - dùng client smart+thinking (ctx
    riêng, khác ctx["llm_client"] của fast path), chỉ nạp toolset insight (+core),
    route="deep" ghi vào AgentTrace, request chuyển deep_running -> done."""
    from app.agent.worker import run_deep_analysis

    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add(conv)
    await db_session.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="phan tich rui ro du an", queue_position=1.0,
                      status=ChatRequestStatus.deep_running)
    db_session.add(req)
    await db_session.flush()
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm_smart = FakeLLMClient(turns=[
        [TextDelta(text="ket qua phan tich sau"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
    ], model="sonnet-smart")
    pub = FakeEventPublisher()

    async def never_cancelled(_id):
        return False

    ctx = {
        "session_factory": async_sessionmaker(engine, expire_on_commit=False),
        "llm_client_smart": llm_smart,
        "event_publisher": pub,
        "is_cancelled": never_cancelled,
    }

    await run_deep_analysis(ctx, req.id)

    await db_session.refresh(req)
    assert req.status == ChatRequestStatus.done
    assert len(llm_smart.calls) == 1
    called_tool_names = {t["name"] for t in llm_smart.calls[0]["tools"]}
    assert called_tool_names == {"get_task", "search", "semantic_search", "resolve_person",
                                 "resolve_task", "propose_actions", "get_today_dashboard",
                                 "get_directive_status", "get_project_health",
                                 "get_progress_stats", "list_memories"}

    from sqlalchemy import select

    from app.models import AgentTrace
    (trace,) = (await db_session.execute(select(AgentTrace).where(
        AgentTrace.chat_request_id == req.id))).scalars().all()
    assert trace.route == "deep"


@pytest.mark.asyncio
async def test_run_deep_analysis_injects_rag_context(engine, db_session):
    from app.agent.worker import run_deep_analysis

    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    await note_service.create_note(db_session, ceo, content="Nho ky hop dong doi tac XYZ")
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add(conv)
    await db_session.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="hop dong doi tac XYZ the nao roi", queue_position=1.0,
                      status=ChatRequestStatus.deep_running)
    db_session.add(req)
    await db_session.flush()
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm_smart = FakeLLMClient(turns=[
        [TextDelta(text="ket qua"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
    ], model="sonnet-smart")

    async def never_cancelled(_id):
        return False

    ctx = {
        "session_factory": async_sessionmaker(engine, expire_on_commit=False),
        "llm_client_smart": llm_smart,
        "event_publisher": FakeEventPublisher(),
        "is_cancelled": never_cancelled,
    }

    await run_deep_analysis(ctx, req.id)

    system = llm_smart.calls[0]["system"]
    text = system if isinstance(system, str) else "\n".join(b["text"] for b in system)
    assert "Dữ liệu liên quan" in text
    assert "XYZ" in text


@pytest.mark.asyncio
async def test_run_deep_analysis_noop_if_request_not_deep_running(engine, db_session):
    """Guard chống reset nhầm: nếu request đã bị hủy (CEO bấm dừng) hoặc xử lý
    xong bởi luồng khác trước khi job này tới lượt chạy, không được đụng vào
    nữa - không gọi LLM, không ghi trace, giữ nguyên status hiện tại."""
    from app.agent.worker import run_deep_analysis

    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add(conv)
    await db_session.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="phan tich rui ro du an", queue_position=1.0,
                      status=ChatRequestStatus.cancelled)
    db_session.add(req)
    await db_session.commit()

    llm_smart = FakeLLMClient(turns=[])
    ctx = {
        "session_factory": async_sessionmaker(engine, expire_on_commit=False),
        "llm_client_smart": llm_smart,
        "event_publisher": FakeEventPublisher(),
        "is_cancelled": lambda _id: False,
    }

    await run_deep_analysis(ctx, req.id)

    await db_session.refresh(req)
    assert req.status == ChatRequestStatus.cancelled
    assert len(llm_smart.calls) == 0


def test_worker_settings_registers_run_deep_analysis_with_extended_timeout():
    """Task 7/Quyết định #4: job đường sâu cần timeout riêng cao hơn hẳn
    job_timeout=600 global (model_smart + extended thinking chạy lâu hơn Haiku
    nhiều) - đăng ký qua arq.worker.func(timeout=900), không phải hàm trần."""
    from arq.worker import Function

    from app.agent.worker import run_deep_analysis

    entry = next((f for f in WorkerSettings.functions
                 if isinstance(f, Function) and f.name == "run_deep_analysis"), None)
    assert entry is not None, "run_deep_analysis chưa đăng ký trong WorkerSettings.functions"
    assert entry.coroutine is run_deep_analysis
    assert entry.timeout_s == 900
