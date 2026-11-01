from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Every value comes from the environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    # The app connects as a non-superuser role so Postgres RLS is enforced.
    # Migrations run as the owner role (DATABASE_URL_MIGRATIONS).
    database_url: PostgresDsn
    database_url_migrations: PostgresDsn | None = None
    db_app_role: str = "sqa_app"
    db_pool_size: int = 10

    # "memory://" uses an in-process fake (development/test only).
    redis_url: str = "redis://localhost:6379/0"

    # Clerk
    clerk_issuer: str = Field(description="e.g. https://your-app.clerk.accounts.dev")
    clerk_jwks_url: str | None = None
    clerk_authorized_parties: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    clerk_webhook_secret: SecretStr | None = None
    # Clerk role key -> app role. Unknown roles fall back to least privilege.
    clerk_role_map: dict[str, str] = Field(
        default_factory=lambda: {
            "org:owner": "owner",
            "org:admin": "owner",
            "org:editor": "editor",
            "org:viewer": "viewer",
            "org:member": "viewer",
        }
    )

    # Demo mode: when the secret is set, the web app can mint short-lived demo
    # tokens. Every demo session is pinned to this one org, whatever it claims.
    demo_jwt_secret: SecretStr | None = None
    demo_clerk_org_id: str = "demo_org"
    demo_org_name: str = "Northwind (Demo)"

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Per user, per window.
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60

    # Background jobs. "inline" runs jobs inside the request (tests and Redis-less
    # dev only); production uses the arq worker.
    queue_backend: Literal["arq", "inline"] = "arq"

    # Document storage. "local" is a development stand-in for S3/R2.
    storage_backend: Literal["s3", "local"] = "s3"
    local_storage_dir: str = ".data/storage"
    s3_endpoint_url: str | None = None
    s3_region: str = "auto"
    s3_bucket: str = "sqa-documents"
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None
    # AWS S3/MinIO: "AES256". Cloudflare R2 encrypts every object already: set "".
    s3_sse: str = "AES256"
    signed_url_ttl_seconds: int = Field(default=300, ge=30, le=3600)
    # Where browsers reach this API; used for local-storage download links.
    public_api_url: str = "http://localhost:8000"

    # Uploads
    max_upload_bytes: int = 50 * 1024 * 1024
    max_document_pages: int = 2000
    max_spreadsheet_rows: int = 50_000
    # DOCX -> PDF for real page numbers. "auto" uses LibreOffice when installed.
    docx_converter: Literal["auto", "libreoffice", "none"] = "auto"

    # Embeddings: provider and model are swappable; vectors are always 1024-d.
    embeddings_provider: Literal["voyage", "openai", "hash"] = "voyage"
    embeddings_model: str = "voyage-3.5"
    voyage_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"

    # Reranking re-scores the top search candidates with a cross-encoder. Its
    # score is what Phase 2's evidence gate thresholds on.
    rerank_provider: Literal["voyage", "none"] = "none"
    rerank_model: str = "rerank-2.5"

    # Scanned questionnaires and images. "local": PaddleOCR models via RapidOCR
    # (ONNX, CPU, offline). "claude": optional Claude vision engine (needs a key).
    questionnaire_ocr: Literal["local", "claude", "none"] = "local"
    max_ocr_pages: int = 50
    max_questionnaire_questions: int = 3000

    # Optional Claude API engine. The default path uses local models only.
    anthropic_api_key: SecretStr | None = None
    anthropic_model_extract: str = "claude-opus-5-5"

    # Shared demo org: off by default so anonymous visitors can't store files.
    demo_allow_uploads: bool = False
    # Fill an empty demo org with the Northwind sample documents and questionnaire.
    demo_seed: bool = True

    @model_validator(mode="after")
    def _check_dev_only_backends(self) -> "Settings":
        if self.environment == "production":
            for name, value, dev_only in (
                ("REDIS_URL", self.redis_url, "memory://"),
                ("QUEUE_BACKEND", self.queue_backend, "inline"),
                ("STORAGE_BACKEND", self.storage_backend, "local"),
                ("EMBEDDINGS_PROVIDER", self.embeddings_provider, "hash"),
            ):
                if value == dev_only:
                    raise ValueError(f"{name}={dev_only} is for development only")
        if self.redis_url == "memory://" and self.queue_backend == "arq":
            raise ValueError("REDIS_URL=memory:// needs QUEUE_BACKEND=inline")
        return self

    @property
    def jwks_url(self) -> str:
        return self.clerk_jwks_url or f"{self.clerk_issuer.rstrip('/')}/.well-known/jwks.json"

    @property
    def async_database_url(self) -> str:
        return _asyncpg_url(str(self.database_url))

    @property
    def async_migrations_url(self) -> str:
        return _asyncpg_url(str(self.database_url_migrations or self.database_url))


def _asyncpg_url(url: str) -> str:
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix) :]
    return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
