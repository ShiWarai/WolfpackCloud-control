"""
Настройка подключения к базе данных.

Использует SQLAlchemy 2.0 async API с asyncpg.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

# Создание async engine
engine = create_async_engine(
    settings.async_database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

# Фабрика сессий
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Алиас для фоновых задач (контекстный менеджер)
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
    """Инициализация таблиц в БД.

    Миграции управляются через Alembic (запускаются в entrypoint.sh).
    Эта функция оставлена для совместимости, но не создаёт таблицы.
    """
    pass
