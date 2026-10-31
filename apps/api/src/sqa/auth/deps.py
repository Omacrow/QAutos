import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from sqa.auth.clerk import (
    AuthError,
    ClerkVerifier,
    DemoVerifier,
    Principal,
    is_demo_token,
    map_role,
)
from sqa.core.config import Settings
from sqa.core.rate_limit import RateLimiter
from sqa.db.session import Database
from sqa.models import Role

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class OrgContext:
    org_id: uuid.UUID
    clerk_org_id: str
    user_id: str
    role: Role


class OrgResolver:
    """Caches Clerk org id -> internal org id. Mappings never change once created."""

    def __init__(self, db: Database, ttl_seconds: int = 300) -> None:
        self._db = db
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[uuid.UUID, float]] = {}

    async def resolve(self, clerk_org_id: str, fallback_name: str) -> uuid.UUID:
        hit = self._cache.get(clerk_org_id)
        now = time.monotonic()
        if hit and hit[1] > now:
            return hit[0]
        org_id = await self._db.ensure_org(clerk_org_id, fallback_name)
        self._cache[clerk_org_id] = (org_id, now + self._ttl)
        return org_id


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_database(request: Request) -> Database:
    db: Database = request.app.state.db
    return db


async def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    token = credentials.credentials
    demo: DemoVerifier | None = request.app.state.demo_verifier
    try:
        if is_demo_token(token):
            if demo is None:
                raise AuthError("demo mode disabled")
            return demo.verify(token)
        verifier: ClerkVerifier = request.app.state.verifier
        return await verifier.verify(token)
    except AuthError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from None


async def rate_limit(
    request: Request, principal: Annotated[Principal, Depends(get_principal)]
) -> None:
    limiter: RateLimiter = request.app.state.rate_limiter
    result = await limiter.hit(f"user:{principal.user_id}")
    if not result.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Rate limit exceeded",
            headers={"Retry-After": str(result.retry_after)},
        )


async def get_org_context(
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    _: Annotated[None, Depends(rate_limit)],
) -> OrgContext:
    if not principal.clerk_org_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No active organization")
    resolver: OrgResolver = request.app.state.org_resolver
    org_id = await resolver.resolve(
        principal.clerk_org_id, principal.org_slug or principal.clerk_org_id
    )
    return OrgContext(
        org_id=org_id,
        clerk_org_id=principal.clerk_org_id,
        user_id=principal.user_id,
        role=map_role(principal.clerk_org_role, settings.clerk_role_map),
    )


def require_role(minimum: Role) -> Callable[..., Awaitable[OrgContext]]:
    async def checker(ctx: Annotated[OrgContext, Depends(get_org_context)]) -> OrgContext:
        if not ctx.role.at_least(minimum):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return ctx

    return checker


async def get_tenant_session(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[Database, Depends(get_database)],
) -> AsyncIterator[AsyncSession]:
    async with db.tenant(ctx.org_id) as session:
        yield session


CurrentOrg = Annotated[OrgContext, Depends(get_org_context)]
TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]
Viewer = Annotated[OrgContext, Depends(require_role(Role.VIEWER))]
Editor = Annotated[OrgContext, Depends(require_role(Role.EDITOR))]
Owner = Annotated[OrgContext, Depends(require_role(Role.OWNER))]
