import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from sqa.auth.clerk import ClerkVerifier, DemoVerifier
from sqa.auth.deps import OrgResolver
from sqa.core.config import Settings, get_settings
from sqa.core.logging import configure_logging, get_logger
from sqa.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from sqa.core.rate_limit import RateLimiter
from sqa.db.session import Database
from sqa.embeddings import make_embedder
from sqa.ingestion.pipeline import IngestDeps, make_deps
from sqa.queue import ArqQueue, InlineQueue, JobQueue
from sqa.routes import documents, files, health, org, webhooks
from sqa.services.demo import seed_demo_org
from sqa.services.demo_documents import seed_demo_documents
from sqa.storage import make_store

log = get_logger(__name__)


def _make_redis(settings: Settings) -> Redis:
    if settings.redis_url == "memory://":  # Settings refuses this in production
        from fakeredis import FakeAsyncRedis  # dev dependency

        fake: Redis = FakeAsyncRedis()
        return fake
    client: Redis = Redis.from_url(settings.redis_url)
    return client


async def _make_queue(settings: Settings, deps: IngestDeps) -> JobQueue:
    if settings.queue_backend == "inline":  # Settings refuses this in production
        return InlineQueue(deps)
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return ArqQueue(pool)


def create_app(
    settings: Settings | None = None,
    *,
    verifier: ClerkVerifier | None = None,
    redis: Redis | None = None,
) -> FastAPI:
    """App factory. Tests inject `verifier` and `redis`; production builds both from settings."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, json=settings.environment != "development")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(settings.async_database_url, pool_size=settings.db_pool_size)
        redis_client = redis or _make_redis(settings)
        app.state.settings = settings
        app.state.db = db
        app.state.redis = redis_client
        app.state.org_resolver = OrgResolver(db)
        app.state.rate_limiter = RateLimiter(
            redis_client,
            limit=settings.rate_limit_requests,
            window_seconds=settings.rate_limit_window_seconds,
        )
        app.state.verifier = verifier or ClerkVerifier(
            issuer=settings.clerk_issuer,
            jwks_url=settings.jwks_url,
            authorized_parties=settings.clerk_authorized_parties,
        )
        # Signs local-storage download links; per process, links live minutes.
        store = make_store(settings, local_secret=secrets.token_urlsafe(32))
        embedder = make_embedder(settings)
        queue = await _make_queue(settings, make_deps(db, store, embedder, settings))
        app.state.store = store
        app.state.embedder = embedder
        app.state.queue = queue
        app.state.demo_verifier = None
        if settings.demo_jwt_secret is not None:
            app.state.demo_verifier = DemoVerifier(
                secret=settings.demo_jwt_secret.get_secret_value(),
                demo_clerk_org_id=settings.demo_clerk_org_id,
            )
            await seed_demo_org(db, settings)
            await seed_demo_documents(db, store, queue, settings)
            log.info("demo_mode_enabled")
        try:
            yield
        finally:
            await queue.aclose()
            await embedder.aclose()
            await redis_client.aclose()
            await db.dispose()

    app = FastAPI(
        title="QAutos API",
        version="0.1.0",
        lifespan=lifespan,
        # No interactive docs in production; the schema is exported at build time.
        docs_url=None if settings.environment == "production" else "/docs",
        redoc_url=None,
        openapi_url=None if settings.environment == "production" else "/openapi.json",
    )

    @app.exception_handler(Exception)
    async def unhandled(_request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled_exception", exc_info=exc)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    # Multipart overhead on top of the largest allowed file.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_upload_bytes + 1024 * 1024)
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)
    app.include_router(org.router)
    app.include_router(documents.router)
    app.include_router(files.router)
    app.include_router(webhooks.router)
    return app
