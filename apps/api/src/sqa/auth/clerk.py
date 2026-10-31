"""Verification of Clerk session tokens.

FastAPI never trusts an org id from the URL or body. The active org and the
member's role come only from a token signed by Clerk.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

import jwt

from sqa.models import Role


class AuthError(Exception):
    """Token missing, invalid or expired. Maps to 401."""


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    session_id: str | None
    clerk_org_id: str | None
    clerk_org_role: str | None
    org_slug: str | None


def map_role(clerk_role: str | None, role_map: dict[str, str]) -> Role:
    """Map a Clerk org role to an app role. Unknown roles get least privilege."""
    if not clerk_role:
        return Role.VIEWER
    key = clerk_role if clerk_role.startswith("org:") else f"org:{clerk_role}"
    mapped = role_map.get(key)
    try:
        return Role(mapped) if mapped else Role.VIEWER
    except ValueError:
        return Role.VIEWER


def principal_from_claims(claims: dict[str, Any]) -> Principal:
    # Session token v2 nests org claims under "o"; v1 uses flat org_* claims.
    org = claims.get("o")
    if isinstance(org, dict):
        org_id, org_role, org_slug = org.get("id"), org.get("rol"), org.get("slg")
    else:
        org_id, org_role, org_slug = (
            claims.get("org_id"),
            claims.get("org_role"),
            claims.get("org_slug"),
        )
    return Principal(
        user_id=str(claims["sub"]),
        session_id=claims.get("sid"),
        clerk_org_id=org_id,
        clerk_org_role=org_role,
        org_slug=org_slug,
    )


class ClerkVerifier:
    def __init__(
        self,
        *,
        issuer: str,
        jwks_url: str,
        authorized_parties: list[str],
        jwks_client: jwt.PyJWKClient | None = None,
        leeway_seconds: int = 5,
    ) -> None:
        self._issuer = issuer.rstrip("/")
        self._authorized_parties = set(authorized_parties)
        self._jwks = jwks_client or jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300)
        self._leeway = leeway_seconds

    def verify_sync(self, token: str) -> Principal:
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp", "iat", "iss", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthError("invalid token") from exc

        # azp guards against tokens minted for another site using our Clerk instance.
        azp = claims.get("azp")
        if azp is not None and azp not in self._authorized_parties:
            raise AuthError("unauthorized party")
        return principal_from_claims(claims)

    async def verify(self, token: str) -> Principal:
        # PyJWKClient fetches keys with blocking I/O on cache misses.
        return await asyncio.to_thread(self.verify_sync, token)


DEMO_ISSUER = "sqa-demo"


class DemoVerifier:
    """Verifies demo tokens minted by the web app's /demo/token route.

    Demo tokens are HS256 with their own issuer and secret. Whatever they
    claim, the resulting principal is pinned to the single demo org, so a
    leaked demo secret can never reach a real customer's data.
    """

    def __init__(self, *, secret: str, demo_clerk_org_id: str) -> None:
        if len(secret) < 32:
            raise ValueError("DEMO_JWT_SECRET must be at least 32 characters")
        self._secret = secret
        self._org = demo_clerk_org_id

    def verify(self, token: str) -> Principal:
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                issuer=DEMO_ISSUER,
                options={"require": ["exp", "iat", "iss", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthError("invalid demo token") from exc
        return Principal(
            user_id=f"demo:{claims['sub']}"[:64],
            session_id=None,
            clerk_org_id=self._org,
            clerk_org_role="org:admin",
            org_slug="demo",
        )


def is_demo_token(token: str) -> bool:
    """Route a token to the right verifier. Reads claims WITHOUT trusting them;
    each verifier then checks signature, algorithm and issuer strictly."""
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return False
    return bool(claims.get("iss") == DEMO_ISSUER)
