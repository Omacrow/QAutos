"""Object storage for uploaded files.

Production uses S3-compatible storage (Cloudflare R2, AWS S3, MinIO). Objects
are encrypted at rest (R2 always; S3/MinIO via SSE-S3) and downloads go
through short-lived pre-signed URLs, so the bucket stays private.

`LocalStore` is a development stand-in that writes to disk and signs its own
expiring download tokens served by `/v1/files/{token}`.

Keys are always `orgs/{org_id}/documents/{document_id}/...`, built by the API
from ids, never from user input.
"""

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

import jwt

from sqa.core.config import Settings

_FILE_TOKEN_ISSUER = "sqa-files"  # noqa: S105 - an issuer name, not a secret


class ObjectStore(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...

    async def signed_url(
        self, key: str, *, filename: str, content_type: str, expires_in: int, inline: bool = False
    ) -> str: ...


def document_key(org_id: uuid.UUID, document_id: uuid.UUID, name: str) -> str:
    return f"orgs/{org_id}/documents/{document_id}/{name}"


def content_disposition(filename: str, *, inline: bool = False) -> str:
    """RFC 6266 header with an ASCII fallback and a UTF-8 name."""
    ascii_name = filename.encode("ascii", "replace").decode().replace('"', "")
    kind = "inline" if inline else "attachment"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


class S3Store:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self._bucket = settings.s3_bucket
        self._sse = settings.s3_sse
        if client is None:
            import boto3
            from botocore.config import Config

            client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url,
                region_name=settings.s3_region,
                aws_access_key_id=(
                    settings.s3_access_key_id.get_secret_value()
                    if settings.s3_access_key_id
                    else None
                ),
                aws_secret_access_key=(
                    settings.s3_secret_access_key.get_secret_value()
                    if settings.s3_secret_access_key
                    else None
                ),
                config=Config(signature_version="s3v4", retries={"mode": "standard"}),
            )
        self._client = client

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        extra: dict[str, str] = {"ServerSideEncryption": self._sse} if self._sse else {}
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            **extra,
        )

    async def get(self, key: str) -> bytes:
        response = await asyncio.to_thread(self._client.get_object, Bucket=self._bucket, Key=key)
        body: bytes = await asyncio.to_thread(response["Body"].read)
        return body

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)

    async def signed_url(
        self, key: str, *, filename: str, content_type: str, expires_in: int, inline: bool = False
    ) -> str:
        url: str = await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ResponseContentDisposition": content_disposition(filename, inline=inline),
                "ResponseContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
        return url


class LocalStore:
    def __init__(self, root: str | Path, *, secret: str, public_api_url: str) -> None:
        self._root = Path(root).resolve()
        self._secret = secret
        self._base = public_api_url.rstrip("/")

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root) or path == self._root:
            raise ValueError("invalid storage key")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    async def signed_url(
        self, key: str, *, filename: str, content_type: str, expires_in: int, inline: bool = False
    ) -> str:
        now = int(time.time())
        token = jwt.encode(
            {
                "iss": _FILE_TOKEN_ISSUER,
                "k": key,
                "fn": filename,
                "ct": content_type,
                "in": inline,
                "iat": now,
                "exp": now + expires_in,
            },
            self._secret,
            algorithm="HS256",
        )
        return f"{self._base}/v1/files/{token}"

    def resolve_token(self, token: str) -> tuple[Path, str, str, bool]:
        """Verify a download token. Returns (path, filename, content type, inline)."""
        claims = jwt.decode(
            token,
            self._secret,
            algorithms=["HS256"],
            issuer=_FILE_TOKEN_ISSUER,
            options={"require": ["exp", "iss", "k"]},
        )
        return (
            self._path(claims["k"]),
            str(claims.get("fn", "")),
            str(claims.get("ct", "")),
            bool(claims.get("in", False)),
        )


def make_store(settings: Settings, *, local_secret: str) -> ObjectStore:
    if settings.storage_backend == "local":
        return LocalStore(
            settings.local_storage_dir, secret=local_secret, public_api_url=settings.public_api_url
        )
    return S3Store(settings)
