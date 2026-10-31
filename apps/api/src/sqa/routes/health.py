from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis

from sqa.auth.deps import get_database
from sqa.core.logging import get_logger
from sqa.db.session import Database
from sqa.schemas.tenancy import HealthOut

router = APIRouter(tags=["health"])
log = get_logger(__name__)


@router.get("/health")
async def liveness() -> HealthOut:
    return HealthOut(status="ok")


@router.get("/health/ready")
async def readiness(request: Request, db: Annotated[Database, Depends(get_database)]) -> HealthOut:
    redis: Redis = request.app.state.redis
    try:
        await db.ping()
        await redis.ping()
    except Exception as exc:
        log.warning("readiness_failed", error_type=type(exc).__name__)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Not ready") from None
    return HealthOut(status="ready")
