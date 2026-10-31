"""Tenant isolation and authorization at the HTTP layer."""

import base64
import json
import time
import uuid
from collections.abc import Iterator

import pytest
from fakeredis import FakeAsyncRedis
from fastapi.testclient import TestClient
from pydantic import SecretStr
from svix.webhooks import Webhook

from sqa.auth.clerk import ClerkVerifier
from sqa.core.config import Settings
from sqa.main import create_app
from tests.conftest import MintToken

pytestmark = pytest.mark.db


@pytest.fixture
def client(app_settings: Settings, verifier: ClerkVerifier) -> Iterator[TestClient]:
    app = create_app(app_settings, verifier=verifier, redis=FakeAsyncRedis())
    with TestClient(app) as c:
        yield c


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_requires_token(client: TestClient) -> None:
    assert client.get("/v1/me").status_code == 401
    assert client.get("/v1/me", headers=_auth("garbage")).status_code == 401


def test_requires_active_org(client: TestClient, mint_token: MintToken) -> None:
    assert client.get("/v1/me", headers=_auth(mint_token(org_id=None))).status_code == 403


def test_orgs_are_isolated(client: TestClient, mint_token: MintToken) -> None:
    suffix = uuid.uuid4().hex[:8]
    a = _auth(mint_token(user_id="alice", org_id=f"org_a_{suffix}", role="org:admin"))
    b = _auth(mint_token(user_id="bob", org_id=f"org_b_{suffix}", role="org:admin"))

    me_a = client.get("/v1/me", headers=a).json()
    me_b = client.get("/v1/me", headers=b).json()
    assert me_a["org"]["id"] != me_b["org"]["id"]
    assert me_a["role"] == "owner"

    members_a = client.get("/v1/org/members", headers=a).json()
    assert [m["clerk_user_id"] for m in members_a] == ["alice"]
    members_b = client.get("/v1/org/members", headers=b).json()
    assert [m["clerk_user_id"] for m in members_b] == ["bob"]


def test_audit_log_requires_owner(client: TestClient, mint_token: MintToken) -> None:
    org = f"org_{uuid.uuid4().hex[:8]}"
    viewer = _auth(mint_token(user_id="v", org_id=org, role="org:member"))
    owner = _auth(mint_token(user_id="o", org_id=org, role="org:admin"))
    assert client.get("/v1/audit-events", headers=viewer).status_code == 403
    assert client.get("/v1/audit-events", headers=owner).status_code == 200


def _signed(settings: Settings, payload: dict[str, object]) -> tuple[bytes, dict[str, str]]:
    assert settings.clerk_webhook_secret is not None
    body = json.dumps(payload).encode()
    msg_id = "msg_" + uuid.uuid4().hex
    ts = int(time.time())
    from datetime import UTC, datetime

    signature = Webhook(settings.clerk_webhook_secret.get_secret_value()).sign(
        msg_id, datetime.fromtimestamp(ts, UTC), body.decode()
    )
    return body, {"svix-id": msg_id, "svix-timestamp": str(ts), "svix-signature": signature}


def _demo_token(secret: str) -> str:
    import jwt

    from sqa.auth.clerk import DEMO_ISSUER

    now = int(time.time())
    return jwt.encode(
        {"iss": DEMO_ISSUER, "sub": "visitor", "iat": now, "exp": now + 60, "org_id": "org_x"},
        secret,
        algorithm="HS256",
    )


def test_demo_token_rejected_when_demo_disabled(client: TestClient) -> None:
    assert client.get("/v1/me", headers=_auth(_demo_token("s" * 40))).status_code == 401


def test_demo_session_only_sees_demo_org(
    app_settings: Settings, verifier: ClerkVerifier, mint_token: MintToken
) -> None:
    secret = "s" * 40
    demo_settings = app_settings.model_copy(update={"demo_jwt_secret": SecretStr(secret)})
    app = create_app(demo_settings, verifier=verifier, redis=FakeAsyncRedis())
    with TestClient(app) as c:
        # A real org with a member the demo must never see.
        real = _auth(mint_token(user_id="real_user", org_id=f"org_{uuid.uuid4().hex[:8]}"))
        assert c.get("/v1/me", headers=real).status_code == 200

        demo = _auth(_demo_token(secret))
        me = c.get("/v1/me", headers=demo).json()
        assert me["org"]["name"] == demo_settings.demo_org_name
        assert me["role"] == "owner"
        members = [m["clerk_user_id"] for m in c.get("/v1/org/members", headers=demo).json()]
        assert "demo:priya" in members  # seeded
        assert "real_user" not in members


def test_webhook_rejects_bad_signature(client: TestClient) -> None:
    fake_sig = "v1," + base64.b64encode(b"x" * 32).decode()
    resp = client.post(
        "/v1/webhooks/clerk",
        content=b"{}",
        headers={
            "svix-id": "m",
            "svix-timestamp": str(int(time.time())),
            "svix-signature": fake_sig,
        },
    )
    assert resp.status_code == 400


def test_webhook_membership_lands_in_correct_org(
    client: TestClient, app_settings: Settings, mint_token: MintToken
) -> None:
    org = f"org_{uuid.uuid4().hex[:8]}"
    other = f"org_{uuid.uuid4().hex[:8]}"
    body, headers = _signed(
        app_settings,
        {
            "type": "organizationMembership.created",
            "data": {
                "organization": {"id": org, "name": "Acme", "slug": "acme"},
                "public_user_data": {
                    "user_id": "carol",
                    "identifier": "carol@acme.test",
                    "first_name": "Carol",
                },
                "role": "org:editor",
            },
        },
    )
    assert client.post("/v1/webhooks/clerk", content=body, headers=headers).status_code == 204

    owner = _auth(mint_token(user_id="o", org_id=org, role="org:admin"))
    members = client.get("/v1/org/members", headers=owner).json()
    assert {m["clerk_user_id"]: m["role"] for m in members}.get("carol") == "editor"

    outsider = _auth(mint_token(user_id="x", org_id=other, role="org:admin"))
    assert "carol" not in [
        m["clerk_user_id"] for m in client.get("/v1/org/members", headers=outsider).json()
    ]
