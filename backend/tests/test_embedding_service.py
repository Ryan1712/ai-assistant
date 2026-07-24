"""Phase 6 §10.3 — semantic_search / embeddings.

embedding_service.MockEmbeddingClient dùng hashing bag-of-words (KHÔNG phải
ngữ nghĩa thật) — đủ để cosine similarity phản ánh đúng số từ trùng nhau,
dùng cho test không cần API key thật.
"""
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.loop import run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.api.chat import get_arq_pool
from app.db import get_db
from app.main import create_app
from app.models import ChatRequest, Conversation, Embedding, Message, MessageRole, Role, User, Workspace
from app.services import embedding_service, note_service, work_service
from tests.conftest import _ceo_headers, _invite_and_join


class _FakeArqPool:
    async def enqueue_job(self, name, *args, **kwargs):
        return "job"


@pytest.fixture
async def chat_client(engine):
    """client fixture chuẩn không set app.state.arq_pool (không chạy lifespan
    startup) — POST .../messages cần Depends(get_arq_pool), mirror
    test_chat_api.py::chat_client để test qua REST thật."""
    app = create_app()
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_arq_pool] = lambda: _FakeArqPool()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# MockEmbeddingClient / cosine — thuần Python, không cần DB
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_embedding_client_is_deterministic():
    client = embedding_service.MockEmbeddingClient()
    v1 = await client.embed("hop voi doi tac ABC")
    v2 = await client.embed("hop voi doi tac ABC")
    assert v1 == v2
    assert len(v1) == embedding_service.EMBED_DIM


@pytest.mark.asyncio
async def test_mock_embedding_similarity_reflects_shared_words():
    client = embedding_service.MockEmbeddingClient()
    a = await client.embed("Goi lai cho khach hang ABC vao thu 3")
    b = await client.embed("Nho goi khach hang ABC thu 3 tuan sau")
    c = await client.embed("Deadline du an Website Redesign thang 8")

    sim_related = embedding_service.cosine_similarity(a, b)
    sim_unrelated = embedding_service.cosine_similarity(a, c)
    assert sim_related > sim_unrelated


def test_cosine_similarity_handles_zero_vectors():
    assert embedding_service.cosine_similarity([], [1.0]) == 0.0
    assert embedding_service.cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0


# ---------------------------------------------------------------------------
# index_content — best-effort, idempotent
# ---------------------------------------------------------------------------

async def _ceo(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    await db.commit()
    return ws, ceo


@pytest.mark.asyncio
async def test_index_content_creates_row(db_session):
    ws, ceo = await _ceo(db_session)
    import uuid as uuid_mod
    source_id = uuid_mod.uuid4()

    await embedding_service.index_content(db_session, ws.id, "note", source_id, "Noi dung ghi chu")

    rows = (await db_session.execute(select(Embedding))).scalars().all()
    assert len(rows) == 1
    assert rows[0].source_type == "note"
    assert rows[0].source_id == source_id
    assert len(rows[0].embedding) == embedding_service.EMBED_DIM


@pytest.mark.asyncio
async def test_index_content_idempotent_skips_existing(db_session):
    ws, ceo = await _ceo(db_session)
    import uuid as uuid_mod
    source_id = uuid_mod.uuid4()

    await embedding_service.index_content(db_session, ws.id, "note", source_id, "Noi dung A")
    await embedding_service.index_content(db_session, ws.id, "note", source_id, "Noi dung A")

    rows = (await db_session.execute(select(Embedding))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_index_content_updates_in_place_when_content_changes(db_session):
    """voice_transcript có thể retranscribe (KHÁC note/task_update/comment/
    chat_message bất biến) — content đổi thì update embedding tại chỗ,
    content GIỐNG hệt thì bỏ qua (khỏi tốn tiền embed lại)."""
    ws, ceo = await _ceo(db_session)
    import uuid as uuid_mod
    source_id = uuid_mod.uuid4()

    await embedding_service.index_content(db_session, ws.id, "voice_transcript",
                                          source_id, "ban nhap dau tien")
    rows = (await db_session.execute(select(Embedding))).scalars().all()
    assert len(rows) == 1
    first_vector = rows[0].embedding

    # Cùng nội dung -> không tạo thêm row, không re-embed
    await embedding_service.index_content(db_session, ws.id, "voice_transcript",
                                          source_id, "ban nhap dau tien")
    rows = (await db_session.execute(select(Embedding))).scalars().all()
    assert len(rows) == 1

    # Retranscribe ra nội dung khác -> update TẠI CHỖ (vẫn 1 row, vector đổi)
    await embedding_service.index_content(db_session, ws.id, "voice_transcript",
                                          source_id, "ban chinh thuc sau khi STT lai")
    rows = (await db_session.execute(select(Embedding))).scalars().all()
    assert len(rows) == 1
    assert rows[0].content == "ban chinh thuc sau khi STT lai"
    assert rows[0].embedding != first_vector


@pytest.mark.asyncio
async def test_index_content_ignores_blank_text(db_session):
    ws, ceo = await _ceo(db_session)
    import uuid as uuid_mod

    await embedding_service.index_content(db_session, ws.id, "note", uuid_mod.uuid4(), "   ")

    rows = (await db_session.execute(select(Embedding))).scalars().all()
    assert rows == []


# ---------------------------------------------------------------------------
# semantic_search — tích hợp qua service thật + quyền
# ---------------------------------------------------------------------------

def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


@pytest.mark.asyncio
async def test_semantic_search_finds_own_note_by_meaning(client, db_session):
    ceo_h = await _ceo_headers(client)
    ceo = (await db_session.execute(select(User).where(User.email == "ceo@a.vn"))).scalar_one()

    await note_service.create_note(
        db_session, ceo, content="Goi lai cho khach hang ABC vao thu 3 tuan sau")
    await note_service.create_note(
        db_session, ceo, content="Deadline du an Website Redesign thang 8")

    results = await embedding_service.semantic_search(
        db_session, ceo, "nho goi khach hang ABC", source_types=["note"])

    assert results
    assert "khach hang ABC" in results[0]["content"] or "ABC" in results[0]["content"]


@pytest.mark.asyncio
async def test_semantic_search_notes_are_private(client, db_session):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    manager = (await db_session.execute(select(User).where(User.email == "m1@a.vn"))).scalar_one()

    await note_service.create_note(db_session, manager, content="Ghi chu rieng cua quan ly")

    ceo = (await db_session.execute(select(User).where(User.email == "ceo@a.vn"))).scalar_one()
    results = await embedding_service.semantic_search(
        db_session, ceo, "ghi chu rieng cua quan ly", source_types=["note"])

    assert results == []


@pytest.mark.asyncio
async def test_semantic_search_task_update_respects_visible_task_ids(client, db_session):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", manager_id=m1["user"]["id"])

    p = await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P"})
    t = await client.post("/api/v1/tasks", headers=ceo_h,
                          json={"project_id": p.json()["id"], "title": "Thiet ke landing page"})
    task_id = t.json()["id"]
    await client.post(f"/api/v1/tasks/{task_id}/assignees", headers=ceo_h,
                      json={"user_id": e1["user"]["id"]})

    employee = (await db_session.execute(select(User).where(User.email == "e1@a.vn"))).scalar_one()
    from uuid import UUID
    await work_service.add_task_update(db_session, employee, UUID(task_id),
                                       content="Da xong 50% phan landing page")

    other_employee_h = await _invite_and_join(client, ceo_h, "employee", "e2@a.vn",
                                              manager_id=m1["user"]["id"])
    outsider = (await db_session.execute(select(User).where(User.email == "e2@a.vn"))).scalar_one()

    visible_results = await embedding_service.semantic_search(
        db_session, employee, "landing page 50%", source_types=["task_update"])
    assert visible_results

    hidden_results = await embedding_service.semantic_search(
        db_session, outsider, "landing page 50%", source_types=["task_update"])
    assert hidden_results == []


@pytest.mark.asyncio
async def test_semantic_search_chat_message_scoped_to_own_conversations(chat_client, db_session):
    client = chat_client
    ceo_h = await _ceo_headers(client)
    conv = await client.post("/api/v1/conversations", headers=ceo_h, json={})
    conv_id = conv.json()["id"]
    await client.post(f"/api/v1/conversations/{conv_id}/messages", headers=ceo_h,
                      json={"content": "Nho tuan sau ky hop dong voi doi tac XYZ"})

    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    manager = (await db_session.execute(select(User).where(User.email == "m1@a.vn"))).scalar_one()
    ceo = (await db_session.execute(select(User).where(User.email == "ceo@a.vn"))).scalar_one()

    ceo_results = await embedding_service.semantic_search(
        db_session, ceo, "hop dong doi tac XYZ", source_types=["chat_message"])
    assert ceo_results

    manager_results = await embedding_service.semantic_search(
        db_session, manager, "hop dong doi tac XYZ", source_types=["chat_message"])
    assert manager_results == []


@pytest.mark.asyncio
async def test_semantic_search_indexes_assistant_message_text(db_session):
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
                      content="tinh hinh du an the nao", queue_position=1.0)
    db_session.add(req)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[[
        TextDelta(text="Du an Marketing Q3 dang chay dung tien do."),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=10, output_tokens=8),
    ]])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    results = await embedding_service.semantic_search(
        db_session, ceo, "Marketing Q3 tien do", source_types=["chat_message"])
    assert results
    assert "Marketing Q3" in results[0]["content"]


# ---------------------------------------------------------------------------
# build_rag_context_block — prefetch 1 lần lúc worker pickup (worker.py)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_rag_context_block_formats_matches(db_session):
    ws, ceo = await _ceo(db_session)
    await note_service.create_note(
        db_session, ceo, content="Nho ky hop dong voi doi tac XYZ truoc thu 6")

    block = await embedding_service.build_rag_context_block(
        db_session, ceo, "hop dong doi tac XYZ")

    assert block.startswith("# Dữ liệu liên quan")
    assert "doi tac XYZ" in block or "XYZ" in block


@pytest.mark.asyncio
async def test_build_rag_context_block_empty_when_no_match(db_session):
    ws, ceo = await _ceo(db_session)
    await note_service.create_note(db_session, ceo, content="Mot ghi chu hoan toan khac")

    block = await embedding_service.build_rag_context_block(
        db_session, ceo, "xyzabc khong lien quan gi ca 123999")
    assert block == ""


@pytest.mark.asyncio
async def test_semantic_search_voice_transcript_private_and_updates_on_retranscribe(
        db_session, tmp_path, monkeypatch):
    from app.config import get_settings
    from app.services import voice_service

    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path))
    ws, ceo = await _ceo(db_session)
    manager = User(workspace_id=ws.id, email="m@a.vn", password_hash="x", full_name="M",
                  role=Role.manager)
    db_session.add(manager)
    await db_session.commit()

    out = await voice_service.create_voice_note(db_session, ceo, filename="a.m4a", data=b"x")

    class _Stub:
        async def transcribe(self, data, filename):
            return "nho hop voi doi tac ABC thu 3", "vi"
    monkeypatch.setattr(voice_service, "get_transcription_client", lambda: _Stub())
    import uuid as uuid_mod
    await voice_service.transcribe_note(db_session, uuid_mod.UUID(out["id"]))

    ceo_results = await embedding_service.semantic_search(
        db_session, ceo, "hop voi doi tac ABC", source_types=["voice_transcript"])
    assert ceo_results

    manager_results = await embedding_service.semantic_search(
        db_session, manager, "hop voi doi tac ABC", source_types=["voice_transcript"])
    assert manager_results == []  # ghi âm riêng tư như note, không phải người tạo thì không thấy


@pytest.mark.asyncio
async def test_semantic_search_skill_respects_grant(client, db_session):
    from app.models import SkillKind
    from app.services import skill_service

    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    ceo = (await db_session.execute(select(User).where(User.email == "ceo@a.vn"))).scalar_one()
    manager = (await db_session.execute(select(User).where(User.email == "m1@a.vn"))).scalar_one()

    skill = await skill_service.create_skill(
        db_session, ceo, name="Quy trinh cham cong", kind=SkillKind.knowledge,
        content="Huong dan cham cong hang thang cho nhan vien")

    ceo_results = await embedding_service.semantic_search(
        db_session, ceo, "quy trinh cham cong", source_types=["skill"])
    assert ceo_results

    manager_results = await embedding_service.semantic_search(
        db_session, manager, "quy trinh cham cong", source_types=["skill"])
    assert manager_results == []  # chưa được cấp quyền

    await skill_service.grant_skill(db_session, ceo, skill["id"], manager.id)
    manager_results_after_grant = await embedding_service.semantic_search(
        db_session, manager, "quy trinh cham cong", source_types=["skill"])
    assert manager_results_after_grant


@pytest.mark.asyncio
async def test_semantic_search_no_match_returns_empty_list(client, db_session):
    ceo_h = await _ceo_headers(client)
    ceo = (await db_session.execute(select(User).where(User.email == "ceo@a.vn"))).scalar_one()
    await note_service.create_note(db_session, ceo, content="Mot ghi chu hoan toan khac")

    results = await embedding_service.semantic_search(
        db_session, ceo, "xyzabc khong lien quan gi ca 123999", source_types=["note"])
    assert results == []
