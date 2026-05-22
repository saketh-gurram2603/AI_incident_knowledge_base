"""
Postgres integration via SQLAlchemy with connection pooling.
Used for:
  - L3 escalation ticket storage
  - Evaluation run results
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from src.handlers.logger import get_logger, log_error, log_info, log_warning

logger = get_logger("integrations.database")

_engine = None
_session_factory = None


class Base(DeclarativeBase):
    pass


def init_database(
    host: str,
    port: int,
    db: str,
    user: str,
    password: str,
    pool_size: int = 20,
    max_overflow: int = 10,
    pool_recycle: int = 3600,
) -> None:
    """
    Initialise the async SQLAlchemy engine with connection pooling.
    Called once at startup inside FastAPI lifespan.
    """
    global _engine, _session_factory

    url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"

    _engine = create_async_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_recycle=pool_recycle,
        pool_pre_ping=True,      # validate connection before use
        echo=False,
    )
    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    log_info(
        "Postgres engine initialised | host=%s port=%d db=%s pool_size=%d",
        host, port, db, pool_size,
    )


def get_engine():
    if _engine is None:
        raise RuntimeError("Database not initialised. Call init_database() at startup.")
    return _engine


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager that yields a DB session and handles commit/rollback."""
    if _session_factory is None:
        raise RuntimeError("Database not initialised. Call init_database() at startup.")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            await session.rollback()
            log_error("DB session rolled back | error=%s", exc)
            raise


async def create_tables() -> None:
    """Create all tables defined via SQLAlchemy ORM models."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log_info("Database tables created / verified")


async def health_check() -> bool:
    """Return True if Postgres is reachable."""
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        log_warning("Postgres health check failed | error=%s", exc)
        return False
