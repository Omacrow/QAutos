"""Clerk webhooks keep org names and memberships in sync.

Signatures are verified with Svix before the payload is parsed. Every write
still goes through a tenant session, so RLS applies to webhook writes too.
"""

import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from svix.webhooks import Webhook, WebhookVerificationError

from sqa.auth.clerk import map_role
from sqa.auth.deps import get_database, get_settings_dep
from sqa.core.config import Settings
from sqa.core.logging import get_logger
from sqa.db.session import Database
from sqa.models import Membership, Organization
from sqa.services import audit

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])
log = get_logger(__name__)


@router.post("/clerk", status_code=status.HTTP_204_NO_CONTENT)
async def clerk_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    db: Annotated[Database, Depends(get_database)],
) -> None:
    if settings.clerk_webhook_secret is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    body = await request.body()
    try:
        Webhook(settings.clerk_webhook_secret.get_secret_value()).verify(
            body, dict(request.headers)
        )
    except WebhookVerificationError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature") from None
    event: dict[str, Any] = json.loads(body)

    event_type = str(event.get("type", ""))
    data: dict[str, Any] = event.get("data") or {}
    log.info("clerk_webhook", webhook_type=event_type)

    if event_type in ("organization.created", "organization.updated"):
        await _upsert_org(db, data)
    elif event_type == "organization.deleted":
        await _delete_org(db, data)
    elif event_type in ("organizationMembership.created", "organizationMembership.updated"):
        await _upsert_membership(db, data, settings)
    elif event_type == "organizationMembership.deleted":
        await _delete_membership(db, data)


async def _upsert_org(db: Database, data: dict[str, Any]) -> None:
    org_id = await db.ensure_org(data["id"], data.get("name") or data["id"])
    async with db.tenant(org_id) as session:
        await session.execute(
            update(Organization)
            .where(Organization.id == org_id)
            .values(name=data.get("name") or data["id"], slug=data.get("slug"))
        )


async def _delete_org(db: Database, data: dict[str, Any]) -> None:
    # Soft delete; a scheduled job (later phase) purges data and files.
    org_id = await db.ensure_org(data["id"], data["id"])
    async with db.tenant(org_id) as session:
        await session.execute(
            update(Organization)
            .where(Organization.id == org_id)
            .values(deleted_at=datetime.now(UTC))
        )
        await audit.record(session, org_id=org_id, action="org.deleted", actor_clerk_user_id=None)


async def _upsert_membership(db: Database, data: dict[str, Any], settings: Settings) -> None:
    org = data["organization"]
    user = data.get("public_user_data") or {}
    org_id = await db.ensure_org(org["id"], org.get("name") or org["id"])
    role = map_role(data.get("role"), settings.clerk_role_map).value
    display_name = (
        " ".join(part for part in (user.get("first_name"), user.get("last_name")) if part) or None
    )
    async with db.tenant(org_id) as session:
        await session.execute(
            insert(Membership)
            .values(
                org_id=org_id,
                clerk_user_id=user["user_id"],
                email=user.get("identifier"),
                display_name=display_name,
                role=role,
            )
            .on_conflict_do_update(
                index_elements=["org_id", "clerk_user_id"],
                set_={
                    "email": user.get("identifier"),
                    "display_name": display_name,
                    "role": role,
                },
            )
        )
        await audit.record(
            session,
            org_id=org_id,
            action="membership.upserted",
            actor_clerk_user_id=None,
            target_type="user",
            target_id=user["user_id"],
            details={"role": role},
        )


async def _delete_membership(db: Database, data: dict[str, Any]) -> None:
    org = data["organization"]
    user = data.get("public_user_data") or {}
    org_id = await db.ensure_org(org["id"], org.get("name") or org["id"])
    async with db.tenant(org_id) as session:
        await session.execute(
            delete(Membership).where(
                Membership.org_id == org_id, Membership.clerk_user_id == user["user_id"]
            )
        )
        await audit.record(
            session,
            org_id=org_id,
            action="membership.deleted",
            actor_clerk_user_id=None,
            target_type="user",
            target_id=user["user_id"],
        )
