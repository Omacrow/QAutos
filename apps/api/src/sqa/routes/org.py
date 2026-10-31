from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from sqa.auth.deps import Owner, TenantSession, Viewer
from sqa.models import AuditEvent, Membership, Organization
from sqa.schemas.tenancy import AuditEventOut, MemberOut, MeOut, OrgOut

router = APIRouter(prefix="/v1", tags=["org"])


@router.get("/me")
async def me(ctx: Viewer, session: TenantSession) -> MeOut:
    org = await session.get(Organization, ctx.org_id)
    if org is None:  # RLS hides it: should be impossible with a resolved context
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")

    # Keep the local membership mirror fresh; webhooks fill in email/name.
    await session.execute(
        insert(Membership)
        .values(
            org_id=ctx.org_id,
            clerk_user_id=ctx.user_id,
            role=ctx.role.value,
            last_seen_at=datetime.now(UTC),
        )
        .on_conflict_do_update(
            index_elements=["org_id", "clerk_user_id"],
            set_={"role": ctx.role.value, "last_seen_at": datetime.now(UTC)},
        )
    )
    return MeOut(user_id=ctx.user_id, role=ctx.role, org=OrgOut.model_validate(org))


@router.get("/org/members")
async def list_members(ctx: Viewer, session: TenantSession) -> list[MemberOut]:
    # Explicit org filter on top of RLS: defense in depth.
    rows = await session.scalars(
        select(Membership).where(Membership.org_id == ctx.org_id).order_by(Membership.created_at)
    )
    return [MemberOut.model_validate(m) for m in rows]


@router.get("/audit-events")
async def list_audit_events(
    ctx: Owner,
    session: TenantSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AuditEventOut]:
    rows = await session.scalars(
        select(AuditEvent)
        .where(AuditEvent.org_id == ctx.org_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    )
    return [AuditEventOut.model_validate(e) for e in rows]
