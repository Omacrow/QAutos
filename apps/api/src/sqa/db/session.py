"""Database access. All tenant data goes through `Database.tenant()`.

`tenant()` opens a transaction and sets `app.org_id` with SET LOCAL semantics
(`set_config(..., true)`), which RLS policies read. The setting dies with the
transaction, so a pooled connection can never carry one org's context into
another request. If no org is set, every RLS-protected query returns zero rows.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class Database:
    def __init__(self, url: str, *, pool_size: int = 10) -> None:
        self.engine: AsyncEngine = create_async_engine(url, pool_size=pool_size, pool_pre_ping=True)
        self._sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def tenant(self, org_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
        async with self._sessions() as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.org_id', :org_id, true)"),
                {"org_id": str(org_id)},
            )
            yield session

    async def ensure_org(self, clerk_org_id: str, name: str) -> uuid.UUID:
        """Map a Clerk org id to our internal id, creating the org on first sight.

        Runs through a narrow SECURITY DEFINER function because the lookup
        happens before any org context exists (RLS would hide the row).
        """
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                text("SELECT sqa_ensure_org(:clerk_org_id, :name)"),
                {"clerk_org_id": clerk_org_id, "name": name},
            )
            org_id: uuid.UUID = result.scalar_one()
            return org_id

    async def ping(self) -> None:
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        await self.engine.dispose()
