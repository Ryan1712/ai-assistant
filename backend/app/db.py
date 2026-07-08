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
        _engine = create_async_engine(get_settings().database_url)
        _maker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def get_db():
    get_engine()
    async with _maker() as session:
        yield session
