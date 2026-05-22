"""Async SQLAlchemy session factory scoped to the Clinical Evidence island.

The island opens its own engine against CE_DATABASE_URL. The host may use a
separate connection pool for its own concerns; this keeps the island
self-contained.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from clinical_evidence.config import get_settings

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _init() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_factory
    if _session_factory is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, future=True, pool_pre_ping=True)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    factory = _init()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency."""
    factory = _init()
    async with factory() as session:
        yield session
