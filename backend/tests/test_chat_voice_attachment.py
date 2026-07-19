import io
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.chat import get_arq_pool
from app.api.voice_notes import get_arq_pool as voice_get_arq_pool
from app.db import get_db
from app.main import create_app
from tests.conftest import _ceo_headers, _invite_and_join


class _FakeArqPool:
    async def enqueue_job(self, name, *args, **kwargs):
        return "job"


@pytest.fixture
async def client(engine, storage_dir):
    app = create_app()
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_arq_pool] = lambda: _FakeArqPool()
    app.dependency_overrides[voice_get_arq_pool] = lambda: _FakeArqPool()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _audio_files():
    return {"file": ("a.m4a", io.BytesIO(b"fake"), "audio/m4a")}


@pytest.mark.asyncio
async def test_gui_tin_kem_ghi_am(client):
    h = await _ceo_headers(client)
    vid = (await client.post("/api/v1/voice-notes", headers=h, files=_audio_files())).json()["id"]
    conv = (await client.post("/api/v1/conversations", headers=h, json={})).json()

    r = await client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=h,
                          json={"content": "bóc task từ cuộc họp này", "voice_note_id": vid})
    assert r.status_code == 201, r.text
    assert r.json()["voice_note_id"] == vid

    msgs = (await client.get(f"/api/v1/conversations/{conv['id']}/messages", headers=h)).json()
    assert msgs[0]["voice_note_id"] == vid
    text = msgs[0]["content"][0]["text"]
    assert "bóc task từ cuộc họp này" in text
    assert "[Đính kèm ghi âm" in text  # model phải biết có file


@pytest.mark.asyncio
async def test_ghi_am_cua_nguoi_khac_404(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    m1_h = {"Authorization": f"Bearer {m1['access_token']}"}
    vid = (await client.post("/api/v1/voice-notes", headers=m1_h, files=_audio_files())).json()["id"]
    conv = (await client.post("/api/v1/conversations", headers=ceo_h, json={})).json()

    r = await client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=ceo_h,
                          json={"content": "x", "voice_note_id": vid})
    assert r.status_code == 404  # voice note author-only, CEO cũng không mượn được


@pytest.mark.asyncio
async def test_khong_kem_ghi_am_van_nhu_cu(client):
    h = await _ceo_headers(client)
    conv = (await client.post("/api/v1/conversations", headers=h, json={})).json()
    r = await client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=h,
                          json={"content": "tin thuong"})
    assert r.status_code == 201
    assert r.json()["voice_note_id"] is None
