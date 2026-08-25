from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from .settings import settings


def normalize_async_db_url(url: str) -> str:
    """Normalizes standard postgres connection strings to use the asyncpg driver."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return url.replace(prefix, "postgresql+asyncpg://", 1)
    return url


db_url = normalize_async_db_url(settings.DATABASE_URL)

engine = create_async_engine(db_url, echo=settings.DB_ECHO)
async_session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an active database session with rollback on failure."""
    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
