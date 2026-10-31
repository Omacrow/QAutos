"""Shared fixtures.

Unit tests run anywhere. Tests marked `db` need TEST_DATABASE_URL pointing at
a PostgreSQL server (with pgvector) as a superuser; they create a throwaway
database, migrate it as the owner, and then connect as the non-superuser app
role exactly like production does.
"""

import asyncio
import os
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

TEST_ISSUER = "https://test.clerk.example"
TEST_PARTY = "http://localhost:3000"
APP_ROLE = "sqa_app"
APP_ROLE_PASSWORD = "sqa_app_test_pw"

os.environ.setdefault("CLERK_ISSUER", TEST_ISSUER)
os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@localhost:5432/unused")
os.environ.setdefault("ENVIRONMENT", "test")

from sqa.auth.clerk import ClerkVerifier  # noqa: E402
from sqa.core.config import Settings  # noqa: E402

# --- Tokens -------------------------------------------------------------------


@dataclass
class _SigningKey:
    key: Any


class StaticJWKClient:
    """Stands in for PyJWKClient: always returns the test public key."""

    def __init__(self, public_key: Any) -> None:
        self._key = _SigningKey(public_key)

    def get_signing_key_from_jwt(self, _token: str) -> _SigningKey:
        return self._key


@pytest.fixture(scope="session")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def verifier(rsa_key: rsa.RSAPrivateKey) -> ClerkVerifier:
    return ClerkVerifier(
        issuer=TEST_ISSUER,
        jwks_url="unused",
        authorized_parties=[TEST_PARTY],
        jwks_client=StaticJWKClient(rsa_key.public_key()),  # type: ignore[arg-type]
    )


MintToken = Callable[..., str]


@pytest.fixture(scope="session")
def mint_token(rsa_key: rsa.RSAPrivateKey) -> MintToken:
    def _mint(
        user_id: str = "user_a",
        org_id: str | None = "org_a",
        role: str | None = "org:admin",
        *,
        issuer: str = TEST_ISSUER,
        azp: str = TEST_PARTY,
        expires_in: int = 60,
        key: rsa.RSAPrivateKey | None = None,
        v2: bool = True,
    ) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "sub": user_id,
            "iss": issuer,
            "azp": azp,
            "iat": now,
            "nbf": now,
            "exp": now + expires_in,
            "sid": "sess_1",
        }
        if org_id is not None:
            if v2:
                claims["v"] = 2
                claims["o"] = {
                    "id": org_id,
                    "rol": role.removeprefix("org:") if role else None,
                    "slg": f"{org_id}-slug",
                }
            else:
                claims.update(org_id=org_id, org_role=role, org_slug=f"{org_id}-slug")
        return jwt.encode(claims, key or rsa_key, algorithm="RS256")

    return _mint


# --- Database -----------------------------------------------------------------


def _with_db(url: str, dbname: str, user: str | None = None, password: str | None = None) -> str:
    parts = urlsplit(url)
    netloc = parts.netloc.rsplit("@", 1)[-1]
    if user is not None:
        netloc = f"{user}:{password}@{netloc}"
    elif "@" in parts.netloc:
        netloc = parts.netloc
    return urlunsplit((parts.scheme, netloc, f"/{dbname}", parts.query, ""))


def _admin_execute(url: str, *statements: str) -> None:
    """Run statements outside a transaction (CREATE DATABASE requires that)."""
    import asyncpg

    async def run() -> None:
        conn = await asyncpg.connect(url)
        try:
            for statement in statements:
                await conn.execute(statement)
        finally:
            await conn.close()

    asyncio.run(run())


@dataclass(frozen=True)
class TestDatabase:
    owner_url: str
    app_url: str


@pytest.fixture(scope="session")
def test_database() -> Iterator[TestDatabase]:
    admin_url = os.environ.get("TEST_DATABASE_URL")
    if not admin_url:
        if os.environ.get("REQUIRE_DB_TESTS") == "1":
            pytest.fail("TEST_DATABASE_URL must be set when REQUIRE_DB_TESTS=1")
        pytest.skip("TEST_DATABASE_URL not set")

    dbname = f"sqa_test_{uuid.uuid4().hex[:8]}"
    _admin_execute(
        admin_url,
        f"""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_ROLE_PASSWORD}'
              NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
          END IF;
        END $$;
        """,
        f"CREATE DATABASE {dbname}",
    )
    owner_url = _with_db(admin_url, dbname)
    app_url = _with_db(admin_url, dbname, APP_ROLE, APP_ROLE_PASSWORD)

    from alembic import command
    from alembic.config import Config

    from sqa.core.config import _asyncpg_url

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.attributes["url"] = _asyncpg_url(owner_url)
    command.upgrade(cfg, "head")

    yield TestDatabase(owner_url=owner_url, app_url=app_url)

    _admin_execute(admin_url, f"DROP DATABASE IF EXISTS {dbname} WITH (FORCE)")


@pytest.fixture(scope="session")
def app_settings(test_database: TestDatabase, tmp_path_factory: pytest.TempPathFactory) -> Settings:
    return Settings(
        environment="test",
        database_url=test_database.app_url,  # type: ignore[arg-type]
        clerk_issuer=TEST_ISSUER,
        clerk_authorized_parties=[TEST_PARTY],
        clerk_webhook_secret="whsec_" + "dGVzdHNlY3JldHRlc3RzZWNyZXQ=",  # type: ignore[arg-type]
        rate_limit_requests=1000,
        # Jobs run inside the request, files go to a temp dir, embeddings are local.
        queue_backend="inline",
        storage_backend="local",
        local_storage_dir=str(tmp_path_factory.mktemp("storage")),
        embeddings_provider="hash",
        public_api_url="http://testserver",
        docx_converter="none",
    )


@pytest.fixture
async def db(app_settings: Settings) -> AsyncIterator[Any]:
    from sqa.db.session import Database

    database = Database(app_settings.async_database_url, pool_size=2)
    yield database
    await database.dispose()
