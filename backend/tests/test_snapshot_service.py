"""Phase 1: orchestrator — cache hit/miss, cắt quyền end-to-end, không bao giờ raise."""
import json

from app.services import snapshot_service
from app.services.snapshot_service import get_snapshot_text, invalidate

from tests.test_snapshot_builder import NOW, _world


async def test_miss_build_set_cache_roi_hit(db_session, fake_snapshot_store):
    ws, ceo, ha, duy, p, tasks = await _world(db_session)
    text = await get_snapshot_text(db_session, ceo, now=NOW)
    assert "Marketing Q3" in text and "Duy Phạm" in text
    key = f"snapshot:{ws.id}"
    assert key in fake_snapshot_store.data          # đã SET sau miss
    # sửa cache bằng tay → lần 2 đọc từ cache (không build lại)
    cached = json.loads(fake_snapshot_store.data[key])
    cached["projects"][0]["name"] = "TÊN TỪ CACHE"
    fake_snapshot_store.data[key] = json.dumps(cached, ensure_ascii=False)
    text2 = await get_snapshot_text(db_session, ceo, now=NOW)
    assert "TÊN TỪ CACHE" in text2


async def test_employee_bi_cat_theo_quyen_end_to_end(db_session, fake_snapshot_store):
    ws, ceo, ha, duy, p, (t1, t2, t3, t4) = await _world(db_session)
    text = await get_snapshot_text(db_session, duy, now=NOW)
    assert "Landing page" in text                    # task mình
    assert "Duy Phạm" in text
    assert "Sếp" not in text.split("## Nhân sự")[1].split("## Hôm nay")[0] \
        if "## Nhân sự" in text else True             # dòng workload người khác không có
    assert "Họp khách" not in text                   # task của Hà, Duy không thấy


async def test_invalidate_xoa_key(db_session, fake_snapshot_store):
    ws, ceo, *_ = await _world(db_session)
    await get_snapshot_text(db_session, ceo, now=NOW)
    key = f"snapshot:{ws.id}"
    assert key in fake_snapshot_store.data
    await invalidate(ws.id)
    assert key not in fake_snapshot_store.data
    assert fake_snapshot_store.deleted == [key]


async def test_store_no_khong_pha_chat(db_session, monkeypatch):
    ws, ceo, *_ = await _world(db_session)

    class _Boom:
        async def get(self, key):
            raise RuntimeError("redis chết")

        async def set(self, key, value, ttl):
            raise RuntimeError("redis chết")

        async def delete(self, key):
            raise RuntimeError("redis chết")

    monkeypatch.setattr(snapshot_service, "get_snapshot_store", lambda: _Boom())
    assert await get_snapshot_text(db_session, ceo, now=NOW) == ""   # không raise
    await invalidate(ws.id)                                          # không raise


async def test_store_set_loi_van_khong_pha_chat(db_session, monkeypatch):
    """store.get() thành công (miss = None) nhưng store.set() raise — vẫn phải
    trả '' (build xong rồi, chỉ lỗi lưu cache), KHÔNG raise."""
    ws, ceo, *_ = await _world(db_session)

    class _SetBoom:
        async def get(self, key):
            return None  # cache miss — build_workspace_data sẽ chạy

        async def set(self, key, value, ttl):
            raise RuntimeError("redis set chết")

        async def delete(self, key):
            raise RuntimeError("redis chết")

    monkeypatch.setattr(snapshot_service, "get_snapshot_store", lambda: _SetBoom())
    text = await get_snapshot_text(db_session, ceo, now=NOW)
    assert text == ""  # set fail → toàn hàm trả "" (vì set nằm trong try)
