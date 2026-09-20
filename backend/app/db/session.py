from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

_settings = get_settings()

# NullPool: open a fresh connection per session, close on release.
# Neon terminates idle pooled connections aggressively; pool_pre_ping can miss
# them because Neon may close the socket between checkout and use. NullPool
# sidesteps that at the cost of an extra TCP+TLS handshake per request.
engine = create_async_engine(
    _settings.database_url,
    echo=_settings.db_echo,
    future=True,
    poolclass=NullPool,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
