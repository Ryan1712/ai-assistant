from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


def _upload_files(name="ghi-am.m4a", content=b"fake-audio-bytes"):
    return {"file": (name, content, "audio/m4a")}


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
