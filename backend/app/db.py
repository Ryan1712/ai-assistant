from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_maker = None


def get_engine():
    global _engine, _maker
    if _engine is None:
        # Default SQLAlchemy (pool_size=5, max_overflow=10) từng cạn kiệt
        # dưới tải thật trên production (2026-08-10): sqlalchemy.exc.TimeoutError
        # QueuePool limit of size 5 overflow 10 reached — nâng lên đủ rộng cho
        # API + nhiều request đồng thời (worker dùng engine riêng, xem
        # app/agent/worker.py, không cộng dồn vào đây). pool_pre_ping tránh
        # trả về connection đã bị Postgres/network đóng âm thầm.
        _engine = create_async_engine(
            get_settings().database_url,
            pool_size=15,
            max_overflow=20,
            pool_timeout=30,
            pool_pre_ping=True,
        )
        _maker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def get_db():
    get_engine()
    async with _maker() as session:
        yield session
