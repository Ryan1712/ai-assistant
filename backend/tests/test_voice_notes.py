import pytest

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
