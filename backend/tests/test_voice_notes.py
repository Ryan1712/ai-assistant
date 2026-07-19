import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import get_db
from app.main import create_app
from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


def _upload_files(name="ghi-am.m4a", content=b"fake-audio-bytes"):
    return {"file": (name, content, "audio/m4a")}


class _FakeArqPool:
    """Thay cho arq_pool that trong test HTTP — ghi lai job da enqueue de assert,
    khong can Redis. Xem test_chat_api.py cho pattern goc (chat_client fixture)."""

    def __init__(self):
        self.enqueued = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.enqueued.append((name, args, kwargs))
        return "job"


@pytest.fixture
async def client(engine):
    """Ghi de fixture `client` cua conftest.py: route voice-notes tu Task 16 can
    Depends(get_arq_pool) doc request.app.state.arq_pool — fixture goc khong chay
    lifespan startup nen state.arq_pool khong ton tai (AttributeError). Gan
    _FakeArqPool truc tiep vao app.state (khong can dependency_overrides) va dinh
    kem app len client de test kiem duoc job da enqueue."""
    app = create_app()
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.state.arq_pool = _FakeArqPool()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.app = app
        yield c


@pytest.mark.asyncio
async def test_upload_and_list_own_voice_note(client, storage_dir):
    ceo_h = await _ceo_headers(client)
    r = await client.post("/api/v1/voice-notes", headers=ceo_h,
                          files=_upload_files(), data={"tags": "hop,y-tuong"})
    assert r.status_code == 201, r.text
    note = r.json()
    assert note["language"] == "und"  # mock STT
    assert sorted(note["tags"]) == ["hop", "y-tuong"]

    listed = await client.get("/api/v1/voice-notes", headers=ceo_h)
    assert len(listed.json()) == 1

    # file được lưu trong thư mục voice của workspace, tên file là uuid (không traversal)
    voice_dir = storage_dir / "voice"
    files = list(voice_dir.rglob("*.m4a"))
    assert len(files) == 1
    assert "ghi-am" not in files[0].name


@pytest.mark.asyncio
async def test_voice_note_private_and_file_download(client, storage_dir):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    r = await client.post("/api/v1/voice-notes", headers=_h(m1), files=_upload_files())
    vid = r.json()["id"]

    # CEO không thấy voice note của m1
    assert (await client.get("/api/v1/voice-notes", headers=ceo_h)).json() == []
    assert (await client.get(f"/api/v1/voice-notes/{vid}/file",
                             headers=ceo_h)).status_code == 404

    # chủ nhân tải được file
    f = await client.get(f"/api/v1/voice-notes/{vid}/file", headers=_h(m1))
    assert f.status_code == 200
    assert f.content == b"fake-audio-bytes"


@pytest.mark.asyncio
async def test_list_by_date_uses_vn_timezone_not_utc(client, db_session, storage_dir):
    """23:30 UTC 18/7 = 06:30 sang 19/7 gio VN (UTC+7) — nguoi dung ghi am luc do
    o VN coi day la ghi am 'hom nay' (19/7), du created_at (UTC) van la 18/7."""
    ceo_h = await _ceo_headers(client)
    from app.models import User, VoiceNote
    ceo = (await db_session.execute(select(User).where(User.email == "ceo@a.vn"))).scalar_one()
    note = VoiceNote(workspace_id=ceo.workspace_id, author_id=ceo.id, file_path="x",
                     created_at=datetime(2026, 7, 18, 23, 30, tzinfo=timezone.utc))
    db_session.add(note)
    await db_session.commit()

    same_day = await client.get("/api/v1/voice-notes?on_date=2026-07-19", headers=ceo_h)
    assert len(same_day.json()) == 1

    prev_day_utc = await client.get("/api/v1/voice-notes?on_date=2026-07-18", headers=ceo_h)
    assert len(prev_day_utc.json()) == 0


@pytest.mark.asyncio
async def test_upload_khong_transcribe_dong_bo_va_co_field_moi(client, db_session, storage_dir):
    """create_voice_note KHONG goi STT dong bo nua: transcript luon rong,
    transcript_status="pending" khi stt_mock=True (cho STT that qua async job -
    Task 16). title/duration_seconds la field moi nhan tu client."""
    from fastapi import HTTPException
    from app.models import User
    from app.services import voice_service

    ceo_h = await _ceo_headers(client)
    ceo = (await db_session.execute(select(User).where(User.email == "ceo@a.vn"))).scalar_one()

    out = await voice_service.create_voice_note(
        db_session, ceo, filename="a.m4a", data=b"xxx",
        title="Hop giao ban", duration_seconds=12.5)
    assert out["transcript"] == ""
    assert out["transcript_status"] == "pending"   # stt_mock=True → chờ STT thật
    assert out["title"] == "Hop giao ban"
    assert out["duration_seconds"] == 12.5


@pytest.mark.asyncio
async def test_upload_qua_25mb_bi_chan(client, db_session, storage_dir):
    from fastapi import HTTPException
    from app.models import User
    from app.services import voice_service

    ceo_h = await _ceo_headers(client)
    ceo = (await db_session.execute(select(User).where(User.email == "ceo@a.vn"))).scalar_one()

    with pytest.raises(HTTPException) as ei:
        await voice_service.create_voice_note(db_session, ceo, filename="a.m4a",
                                               data=b"0" * (25 * 1024 * 1024 + 1))
    assert ei.value.status_code == 413
    assert ei.value.detail == "file_too_large"


@pytest.mark.asyncio
async def test_agent_tools_voice(client, db_session, storage_dir):
    ceo_h = await _ceo_headers(client)
    await client.post("/api/v1/voice-notes", headers=ceo_h,
                      files=_upload_files(), data={"tags": "hop"})
    from sqlalchemy import select
    from app.agent.tools import call_tool
    from app.models import User
    ceo = (await db_session.execute(
        select(User).where(User.email == "ceo@a.vn"))).scalar_one()

    listed = await call_tool(db_session, ceo, "list_voice_notes", {"tag": "hop"})
    assert len(listed["voice_notes"]) == 1
    vid = listed["voice_notes"][0]["id"]
    got = await call_tool(db_session, ceo, "get_voice_note", {"voice_note_id": vid})
    assert "transcript" in got


async def _make_actor(db_session):
    from app.models import Role, User, Workspace
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    actor = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
                role=Role.ceo, is_root=True)
    db_session.add(actor)
    await db_session.flush()
    await db_session.commit()
    return actor


# --- Task 16: transcribe bat dong bo qua arq + endpoint re-transcribe ---


@pytest.mark.asyncio
async def test_transcribe_note_cap_nhat_transcript(db_session, storage_dir, monkeypatch):
    from app.models import VoiceNote
    from app.services import voice_service

    actor = await _make_actor(db_session)
    out = await voice_service.create_voice_note(db_session, actor, filename="a.m4a", data=b"x")

    class _Stub:
        async def transcribe(self, data, filename):
            return "xin chao ca nha", "vi"
    monkeypatch.setattr(voice_service, "get_transcription_client", lambda: _Stub())

    await voice_service.transcribe_note(db_session, uuid.UUID(out["id"]))
    note = await db_session.get(VoiceNote, uuid.UUID(out["id"]))
    assert note.transcript == "xin chao ca nha"
    assert note.language == "vi"
    assert note.transcript_status == "done"


@pytest.mark.asyncio
async def test_transcribe_note_loi_thanh_failed(db_session, storage_dir, monkeypatch):
    from app.models import VoiceNote
    from app.services import voice_service

    actor = await _make_actor(db_session)
    out = await voice_service.create_voice_note(db_session, actor, filename="a.m4a", data=b"x")

    class _Boom:
        async def transcribe(self, data, filename):
            raise RuntimeError("stt down")
    monkeypatch.setattr(voice_service, "get_transcription_client", lambda: _Boom())

    await voice_service.transcribe_note(db_session, uuid.UUID(out["id"]))
    note = await db_session.get(VoiceNote, uuid.UUID(out["id"]))
    assert note.transcript_status == "failed"


@pytest.mark.asyncio
async def test_transcribe_note_bo_qua_neu_note_khong_ton_tai(db_session):
    """job co the chay sau khi note bi xoa — khong duoc raise (arq se retry vo ich)."""
    from app.services import voice_service

    await voice_service.transcribe_note(db_session, uuid.uuid4())  # khong raise la dat


@pytest.mark.asyncio
async def test_request_transcription_409_khi_stt_mock(db_session, storage_dir):
    from fastapi import HTTPException
    from app.services import voice_service

    actor = await _make_actor(db_session)
    out = await voice_service.create_voice_note(db_session, actor, filename="a.m4a", data=b"x")

    with pytest.raises(HTTPException) as ei:
        await voice_service.request_transcription(db_session, actor, uuid.UUID(out["id"]))
    assert ei.value.status_code == 409
    assert ei.value.detail == "stt_not_configured"


@pytest.mark.asyncio
async def test_request_transcription_dua_ve_queued_khi_co_stt_that(db_session, storage_dir,
                                                                    monkeypatch):
    from app.config import get_settings
    from app.models import VoiceNote
    from app.services import voice_service

    actor = await _make_actor(db_session)
    out = await voice_service.create_voice_note(db_session, actor, filename="a.m4a", data=b"x")
    monkeypatch.setattr(get_settings(), "stt_mock", False)

    result = await voice_service.request_transcription(db_session, actor, uuid.UUID(out["id"]))
    assert result == {"id": out["id"], "status": "queued"}
    note = await db_session.get(VoiceNote, uuid.UUID(out["id"]))
    assert note.transcript_status == "queued"


@pytest.mark.asyncio
async def test_upload_khong_enqueue_khi_stt_mock(client, storage_dir):
    """Mac dinh stt_mock=True -> status "pending", khong co job nao duoc enqueue."""
    ceo_h = await _ceo_headers(client)
    r = await client.post("/api/v1/voice-notes", headers=ceo_h, files=_upload_files())
    assert r.status_code == 201
    assert r.json()["transcript_status"] == "pending"
    assert client.app.state.arq_pool.enqueued == []


@pytest.mark.asyncio
async def test_upload_enqueue_job_khi_co_stt_that(client, storage_dir, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "stt_mock", False)

    ceo_h = await _ceo_headers(client)
    r = await client.post("/api/v1/voice-notes", headers=ceo_h, files=_upload_files())
    assert r.status_code == 201
    note = r.json()
    assert note["transcript_status"] == "queued"

    name, args, kwargs = client.app.state.arq_pool.enqueued[-1]
    assert name == "transcribe_voice_note"
    assert args == (uuid.UUID(note["id"]),)


@pytest.mark.asyncio
async def test_retranscribe_endpoint_409_khi_stt_mock(client, storage_dir):
    ceo_h = await _ceo_headers(client)
    up = await client.post("/api/v1/voice-notes", headers=ceo_h, files=_upload_files())
    vid = up.json()["id"]

    r = await client.post(f"/api/v1/voice-notes/{vid}/transcribe", headers=ceo_h)
    assert r.status_code == 409
    assert r.json()["detail"] == "stt_not_configured"
    assert client.app.state.arq_pool.enqueued == []


@pytest.mark.asyncio
async def test_retranscribe_endpoint_202_enqueue_job_khi_co_stt_that(client, storage_dir,
                                                                      monkeypatch):
    from app.config import get_settings

    ceo_h = await _ceo_headers(client)
    up = await client.post("/api/v1/voice-notes", headers=ceo_h, files=_upload_files())
    vid = up.json()["id"]
    monkeypatch.setattr(get_settings(), "stt_mock", False)

    r = await client.post(f"/api/v1/voice-notes/{vid}/transcribe", headers=ceo_h)
    assert r.status_code == 202
    assert r.json() == {"id": vid, "status": "queued"}

    name, args, kwargs = client.app.state.arq_pool.enqueued[-1]
    assert name == "transcribe_voice_note"
    assert args == (uuid.UUID(vid),)


@pytest.mark.asyncio
async def test_retranscribe_endpoint_404_neu_khong_phai_chu_nhan(client, storage_dir):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    up = await client.post("/api/v1/voice-notes", headers=_h(m1), files=_upload_files())
    vid = up.json()["id"]

    r = await client.post(f"/api/v1/voice-notes/{vid}/transcribe", headers=ceo_h)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_transcribe_voice_note_job_goi_service(engine, monkeypatch):
    """arq job transcribe_voice_note chi la wrapper mo session roi goi
    voice_service.transcribe_note — test worker lien quan (khong dung DB that)."""
    from app.agent import worker as worker_module

    called = {}

    async def fake_transcribe_note(db, voice_note_id):
        called["db"] = db
        called["voice_note_id"] = voice_note_id
    monkeypatch.setattr(worker_module.voice_service, "transcribe_note", fake_transcribe_note)

    ctx = {"session_factory": async_sessionmaker(engine, expire_on_commit=False)}
    vid = uuid.uuid4()
    await worker_module.transcribe_voice_note(ctx, vid)

    assert called["voice_note_id"] == vid
    assert called["db"] is not None


def test_worker_settings_registers_transcribe_voice_note():
    from app.agent.worker import WorkerSettings, transcribe_voice_note

    assert transcribe_voice_note in WorkerSettings.functions


# --- Task 17: xoa + sua title/tags voice note ---


@pytest.mark.asyncio
async def test_delete_voice_note(db_session, storage_dir):
    from app.models import VoiceNote
    from app.services import voice_service

    actor = await _make_actor(db_session)
    out = await voice_service.create_voice_note(db_session, actor, filename="a.m4a", data=b"x")
    file_path = Path((await db_session.get(VoiceNote, uuid.UUID(out["id"]))).file_path)
    assert file_path.is_file()

    await voice_service.delete_voice_note(db_session, actor, uuid.UUID(out["id"]))

    assert await db_session.get(VoiceNote, uuid.UUID(out["id"])) is None
    assert not file_path.exists()


@pytest.mark.asyncio
async def test_delete_voice_note_file_da_mat_van_xoa_duoc_row(db_session, storage_dir):
    """File tren dia co the da bi mat (hong/xoa tay) — Path.unlink(missing_ok=True)
    khong duoc chan viec xoa row."""
    from app.models import VoiceNote
    from app.services import voice_service

    actor = await _make_actor(db_session)
    out = await voice_service.create_voice_note(db_session, actor, filename="a.m4a", data=b"x")
    note = await db_session.get(VoiceNote, uuid.UUID(out["id"]))
    Path(note.file_path).unlink()

    await voice_service.delete_voice_note(db_session, actor, uuid.UUID(out["id"]))

    assert await db_session.get(VoiceNote, uuid.UUID(out["id"])) is None


@pytest.mark.asyncio
async def test_patch_title_tags(db_session, storage_dir):
    from app.services import voice_service

    actor = await _make_actor(db_session)
    out = await voice_service.create_voice_note(db_session, actor, filename="a.m4a", data=b"x",
                                                 title="Cu", tags=["a"])

    updated = await voice_service.update_voice_note(
        db_session, actor, uuid.UUID(out["id"]), title="Hop sang", tags=["hop", "sang"])

    assert updated["title"] == "Hop sang"
    assert updated["tags"] == ["hop", "sang"]


@pytest.mark.asyncio
async def test_patch_chi_field_duoc_truyen_moi_doi(db_session, storage_dir):
    """title=None (khong truyen) khong duoc ghi de title cu."""
    from app.services import voice_service

    actor = await _make_actor(db_session)
    out = await voice_service.create_voice_note(db_session, actor, filename="a.m4a", data=b"x",
                                                 title="Giu nguyen", tags=["a"])

    updated = await voice_service.update_voice_note(
        db_session, actor, uuid.UUID(out["id"]), tags=["b"])

    assert updated["title"] == "Giu nguyen"
    assert updated["tags"] == ["b"]


@pytest.mark.asyncio
async def test_nguoi_khac_khong_xoa_hay_sua_duoc(client, db_session, storage_dir):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    up = await client.post("/api/v1/voice-notes", headers=_h(m1), files=_upload_files())
    vid = up.json()["id"]

    del_r = await client.delete(f"/api/v1/voice-notes/{vid}", headers=ceo_h)
    assert del_r.status_code == 404

    patch_r = await client.patch(f"/api/v1/voice-notes/{vid}", headers=ceo_h,
                                 json={"title": "hack"})
    assert patch_r.status_code == 404

    # note van con nguyen ven voi chu nhan
    still_there = await client.get(f"/api/v1/voice-notes/{vid}", headers=_h(m1))
    assert still_there.status_code == 200


@pytest.mark.asyncio
async def test_delete_endpoint_204(client, storage_dir):
    ceo_h = await _ceo_headers(client)
    up = await client.post("/api/v1/voice-notes", headers=ceo_h, files=_upload_files())
    vid = up.json()["id"]

    r = await client.delete(f"/api/v1/voice-notes/{vid}", headers=ceo_h)
    assert r.status_code == 204

    assert (await client.get(f"/api/v1/voice-notes/{vid}", headers=ceo_h)).status_code == 404


@pytest.mark.asyncio
async def test_patch_endpoint_tra_ve_note_da_cap_nhat(client, storage_dir):
    ceo_h = await _ceo_headers(client)
    up = await client.post("/api/v1/voice-notes", headers=ceo_h, files=_upload_files(),
                           data={"tags": "a"})
    vid = up.json()["id"]

    r = await client.patch(f"/api/v1/voice-notes/{vid}", headers=ceo_h,
                           json={"title": "Hop sang", "tags": ["hop", "sang"]})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Hop sang"
    assert sorted(body["tags"]) == ["hop", "sang"]
