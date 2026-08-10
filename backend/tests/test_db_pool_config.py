"""app/db.py — cấu hình connection pool cho engine chính (API).

Phát hiện qua log production thật (2026-08-10): create_async_engine() trước
đó không truyền pool_size/max_overflow -> SQLAlchemy dùng default rất nhỏ
(pool_size=5, max_overflow=10, pool_timeout=30) -> dưới tải đồng thời cao,
pool cạn kiệt -> sqlalchemy.exc.TimeoutError: QueuePool limit of size 5
overflow 10 reached, connection timed out, timeout 30.00 -> request treo 30s
rồi lỗi. Test này khóa lại cấu hình pool lớn hơn, không để ai vô tình bỏ đi.

Không test bằng cách connect Postgres thật (không có trong CI) -- chỉ verify
kwargs truyền cho create_async_engine() đúng như mong đợi, qua patch."""
import app.db as db_module


def test_get_engine_configures_larger_pool(monkeypatch):
    captured = {}

    def fake_create_async_engine(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return "fake-engine"

    def fake_sessionmaker(engine, **kwargs):
        return "fake-maker"

    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr(db_module, "_maker", None)
    monkeypatch.setattr(db_module, "create_async_engine", fake_create_async_engine)
    monkeypatch.setattr(db_module, "async_sessionmaker", fake_sessionmaker)

    db_module.get_engine()

    # Default cũ (5+10=15) từng cạn kiệt dưới tải thật trên production -
    # nâng lên đủ rộng cho API + nhiều request đồng thời.
    assert captured["pool_size"] >= 10
    assert captured["max_overflow"] >= 15
    # pool_pre_ping: tránh trả về connection Postgres đã bị server/network
    # đóng âm thầm (idle timeout) -> lỗi "server closed the connection
    # unexpectedly" thay vì tự động dò và mở lại.
    assert captured["pool_pre_ping"] is True


def test_get_engine_is_cached_singleton(monkeypatch):
    calls = {"n": 0}

    def fake_create_async_engine(url, **kwargs):
        calls["n"] += 1
        return f"engine-{calls['n']}"

    def fake_sessionmaker(engine, **kwargs):
        return "fake-maker"

    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr(db_module, "_maker", None)
    monkeypatch.setattr(db_module, "create_async_engine", fake_create_async_engine)
    monkeypatch.setattr(db_module, "async_sessionmaker", fake_sessionmaker)

    e1 = db_module.get_engine()
    e2 = db_module.get_engine()

    assert e1 == e2 == "engine-1"
    assert calls["n"] == 1
