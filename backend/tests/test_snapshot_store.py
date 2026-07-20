"""Phase 1 (spec AI upgrade §5.2): store cache snapshot + config TTL."""
from app.config import Settings
from app.services import snapshot_service
from app.services.snapshot_service import FakeSnapshotStore


def test_config_snapshot_ttl_mac_dinh():
    s = Settings(_env_file=None)
    assert s.snapshot_ttl_seconds == 300


async def test_fake_store_get_set_delete():
    store = FakeSnapshotStore()
    assert await store.get("snapshot:ws1") is None
    await store.set("snapshot:ws1", "{\"a\": 1}", ttl=300)
    assert await store.get("snapshot:ws1") == "{\"a\": 1}"
    await store.delete("snapshot:ws1")
    assert await store.get("snapshot:ws1") is None
    assert store.deleted == ["snapshot:ws1"]


async def test_conftest_patch_store_thanh_fake(fake_snapshot_store):
    # fixture autouse: mọi test lấy store qua get_snapshot_store đều nhận Fake
    assert snapshot_service.get_snapshot_store() is fake_snapshot_store
    assert isinstance(fake_snapshot_store, FakeSnapshotStore)
