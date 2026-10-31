import time
from pathlib import Path
from typing import Any

import jwt
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from sqa.core.middleware import BodySizeLimitMiddleware
from sqa.storage import LocalStore, S3Store, content_disposition

SECRET = "x" * 40


@pytest.fixture
def store(tmp_path: Path) -> LocalStore:
    return LocalStore(tmp_path, secret=SECRET, public_api_url="http://api.test/")


async def test_local_put_get_delete(store: LocalStore) -> None:
    await store.put("orgs/a/documents/b/original.pdf", b"data", "application/pdf")
    assert await store.get("orgs/a/documents/b/original.pdf") == b"data"
    await store.delete("orgs/a/documents/b/original.pdf")
    with pytest.raises(FileNotFoundError):
        await store.get("orgs/a/documents/b/original.pdf")


@pytest.mark.parametrize("key", ["../outside.pdf", "orgs/../../x", ""])
async def test_local_rejects_keys_outside_root(store: LocalStore, key: str) -> None:
    with pytest.raises(ValueError, match="invalid storage key"):
        await store.put(key, b"x", "text/plain")


async def test_signed_url_round_trip(store: LocalStore) -> None:
    await store.put("orgs/a/f.pdf", b"x", "application/pdf")
    url = await store.signed_url(
        "orgs/a/f.pdf", filename="Policy.pdf", content_type="application/pdf", expires_in=60
    )
    assert url.startswith("http://api.test/v1/files/")
    path, filename, content_type = store.resolve_token(url.rsplit("/", 1)[1])
    assert path.read_bytes() == b"x"
    assert (filename, content_type) == ("Policy.pdf", "application/pdf")


def test_signed_url_rejects_tampering_and_expiry(store: LocalStore) -> None:
    now = int(time.time())
    forged = jwt.encode(
        {"iss": "sqa-files", "k": "orgs/b/f.pdf", "exp": now + 60}, "wrong" * 8, algorithm="HS256"
    )
    with pytest.raises(jwt.InvalidSignatureError):
        store.resolve_token(forged)
    expired = jwt.encode(
        {"iss": "sqa-files", "k": "orgs/a/f.pdf", "exp": now - 1}, SECRET, algorithm="HS256"
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        store.resolve_token(expired)


def test_content_disposition_is_safe_for_any_name() -> None:
    header = content_disposition('Pol"icy ü.pdf')
    assert header.startswith('attachment; filename="Policy ?.pdf"')
    assert "filename*=UTF-8''Pol%22icy%20%C3%BC.pdf" in header


class _FakeS3:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def put_object(self, **kwargs: Any) -> None:
        self.calls.append(("put", kwargs))

    def generate_presigned_url(self, op: str, Params: dict[str, Any], ExpiresIn: int) -> str:
        self.calls.append((op, {**Params, "ExpiresIn": ExpiresIn}))
        return "https://bucket.test/signed"


async def test_s3_encrypts_and_signs_short_lived_links() -> None:
    from sqa.core.config import Settings

    settings = Settings(
        database_url="postgresql://u:p@h/d",  # type: ignore[arg-type]
        clerk_issuer="https://x",
        s3_bucket="b",
    )
    fake = _FakeS3()
    s3 = S3Store(settings, client=fake)
    await s3.put("k", b"x", "application/pdf")
    assert fake.calls[0][1]["ServerSideEncryption"] == "AES256"
    url = await s3.signed_url("k", filename="a.pdf", content_type="application/pdf", expires_in=300)
    assert url == "https://bucket.test/signed"
    params = fake.calls[1][1]
    assert params["ExpiresIn"] == 300
    assert params["ResponseContentDisposition"].startswith("attachment;")


def _echo_app(limit: int) -> TestClient:
    async def echo(request: Request) -> JSONResponse:
        return JSONResponse({"size": len(await request.body())})

    app = Starlette(routes=[Route("/", echo, methods=["POST"])])
    return TestClient(BodySizeLimitMiddleware(app, max_bytes=limit))  # type: ignore[arg-type]


def test_body_limit_by_content_length() -> None:
    client = _echo_app(10)
    assert client.post("/", content=b"x" * 10).json() == {"size": 10}
    assert client.post("/", content=b"x" * 11).status_code == 413


def test_body_limit_for_chunked_bodies() -> None:
    client = _echo_app(10)

    def chunks() -> Any:
        yield b"x" * 6
        yield b"x" * 6

    assert client.post("/", content=chunks()).status_code == 413
