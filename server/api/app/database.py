"""
Настройка подключения к базе данных.

Использует SQLAlchemy 2.0 async API с asyncpg.
"""

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, StaticPool

from app.config import get_settings

settings = get_settings()

_sqlite = "sqlite" in settings.async_database_url

if _sqlite:
    engine = create_async_engine(
        settings.async_database_url,
        echo=settings.debug,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    _pool_kwargs: dict = {
        "echo": settings.debug,
        "pool_pre_ping": True,
    }
    if os.environ.get("TESTING_POSTGRES"):
        _pool_kwargs["poolclass"] = NullPool
    else:
        _pool_kwargs["pool_size"] = 5
        _pool_kwargs["max_overflow"] = 10
    engine = create_async_engine(settings.async_database_url, **_pool_kwargs)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async_session_factory = async_session_maker


class Base(DeclarativeBase):
    """Базовый класс для ORM моделей."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency для получения сессии БД."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Миграции выполняет Alembic в entrypoint; здесь заглушка для lifespan."""
    pass
