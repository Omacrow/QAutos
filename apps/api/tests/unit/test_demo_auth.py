import time

import jwt
import pytest

from sqa.auth.clerk import DEMO_ISSUER, AuthError, DemoVerifier, is_demo_token
from tests.conftest import TEST_ISSUER, MintToken

SECRET = "d" * 40


def _demo_token(secret: str = SECRET, **extra: object) -> str:
    now = int(time.time())
    claims = {"iss": DEMO_ISSUER, "sub": "visitor", "iat": now, "exp": now + 300, **extra}
    return jwt.encode(claims, secret, algorithm="HS256")


def test_demo_principal_is_pinned_to_demo_org() -> None:
    verifier = DemoVerifier(secret=SECRET, demo_clerk_org_id="demo_org")
    # Even a token claiming another org lands in the demo org.
    principal = verifier.verify(_demo_token(org_id="org_victim", o={"id": "org_victim"}))
    assert principal.clerk_org_id == "demo_org"
    assert principal.user_id == "demo:visitor"


def test_rejects_wrong_secret() -> None:
    verifier = DemoVerifier(secret=SECRET, demo_clerk_org_id="demo_org")
    with pytest.raises(AuthError):
        verifier.verify(_demo_token(secret="x" * 40))


def test_rejects_expired() -> None:
    verifier = DemoVerifier(secret=SECRET, demo_clerk_org_id="demo_org")
    with pytest.raises(AuthError):
        verifier.verify(_demo_token(exp=int(time.time()) - 10))


def test_rejects_short_secret() -> None:
    with pytest.raises(ValueError, match="32"):
        DemoVerifier(secret="short", demo_clerk_org_id="demo_org")


def test_token_routing(mint_token: MintToken) -> None:
    assert is_demo_token(_demo_token())
    assert not is_demo_token(mint_token())
    assert not is_demo_token("garbage")


def test_hs256_token_with_clerk_issuer_is_not_demo() -> None:
    """An attacker can't sign an HS256 token 'as Clerk': it goes to the Clerk
    verifier, which only accepts RS256 with Clerk's keys."""
    forged = jwt.encode({"iss": TEST_ISSUER, "sub": "x"}, SECRET, algorithm="HS256")
    assert not is_demo_token(forged)
