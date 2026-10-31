import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from sqa.auth.clerk import AuthError, ClerkVerifier, map_role
from sqa.core.config import Settings
from sqa.models import Role
from tests.conftest import MintToken

ROLE_MAP = Settings().clerk_role_map


async def test_valid_v2_token_yields_org_claims(
    verifier: ClerkVerifier, mint_token: MintToken
) -> None:
    principal = await verifier.verify(mint_token(user_id="u1", org_id="org_1", role="org:editor"))
    assert principal.user_id == "u1"
    assert principal.clerk_org_id == "org_1"
    assert map_role(principal.clerk_org_role, ROLE_MAP) is Role.EDITOR


async def test_valid_v1_token_yields_org_claims(
    verifier: ClerkVerifier, mint_token: MintToken
) -> None:
    principal = await verifier.verify(mint_token(org_id="org_9", role="org:viewer", v2=False))
    assert principal.clerk_org_id == "org_9"
    assert principal.clerk_org_role == "org:viewer"


async def test_token_without_org(verifier: ClerkVerifier, mint_token: MintToken) -> None:
    principal = await verifier.verify(mint_token(org_id=None))
    assert principal.clerk_org_id is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"expires_in": -60},
        {"issuer": "https://evil.example"},
        {"azp": "https://evil.example"},
    ],
    ids=["expired", "wrong-issuer", "wrong-azp"],
)
async def test_rejects_bad_tokens(
    verifier: ClerkVerifier, mint_token: MintToken, kwargs: dict[str, object]
) -> None:
    with pytest.raises(AuthError):
        await verifier.verify(mint_token(**kwargs))


async def test_rejects_token_signed_by_other_key(
    verifier: ClerkVerifier, mint_token: MintToken
) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(AuthError):
        await verifier.verify(mint_token(key=other))


async def test_rejects_garbage(verifier: ClerkVerifier) -> None:
    with pytest.raises(AuthError):
        await verifier.verify("not-a-jwt")


@pytest.mark.parametrize(
    ("clerk_role", "expected"),
    [
        ("org:admin", Role.OWNER),
        ("admin", Role.OWNER),  # v2 tokens drop the "org:" prefix
        ("org:editor", Role.EDITOR),
        ("org:member", Role.VIEWER),
        ("org:something_new", Role.VIEWER),  # unknown -> least privilege
        (None, Role.VIEWER),
    ],
)
def test_role_mapping(clerk_role: str | None, expected: Role) -> None:
    assert map_role(clerk_role, ROLE_MAP) is expected


def test_role_ordering() -> None:
    assert Role.OWNER.at_least(Role.EDITOR)
    assert Role.EDITOR.at_least(Role.VIEWER)
    assert not Role.VIEWER.at_least(Role.EDITOR)
