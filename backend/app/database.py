"""
Database session management and initialization.

Uses SQLAlchemy 2.0 async engine with connection pooling.
pgvector extension is created automatically on first startup.
"""

import contextlib
import logging
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.models.database import Base

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """
    Create all tables and install pgvector extension.

    Called on application startup. Safe to call multiple times.
    """
    async with engine.begin() as conn:
        # Install pgvector extension
        await conn.execute(
            __import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS vector")
        )
        # Create all tables defined in ORM models
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized")


async def close_db() -> None:
    """Close the database connection pool."""
    await engine.dispose()
    logger.info("Database connections closed")


@contextlib.asynccontextmanager
async def get_async_session() -> AsyncIterator[AsyncSession]:
    """
    Context manager providing an async DB session.

    Use this in Prefect tasks and background workers where FastAPI's
    dependency injection is not available.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """
    FastAPI dependency for injecting a database session into route handlers.

    Usage:
        @app.get("/")
        async def route(db: AsyncSession = Depends(get_db_session)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
