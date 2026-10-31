"""Seed data for the shared demo organization. Idempotent."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from sqa.core.config import Settings
from sqa.db.session import Database
from sqa.models import AuditEvent, Membership, Organization

DEMO_MEMBERS = [
    ("demo:visitor", "you@demo.example", "Demo Visitor", "owner"),
    ("demo:priya", "priya@northwind.example", "Priya Raman", "owner"),
    ("demo:marcus", "marcus@northwind.example", "Marcus Bell", "editor"),
    ("demo:elena", "elena@northwind.example", "Elena Sokolova", "editor"),
    ("demo:tom", "tom@northwind.example", "Tom Whitaker", "viewer"),
]

DEMO_EVENTS = [
    ("demo:priya", "membership.upserted", "user", "demo:marcus", 26),
    ("demo:priya", "membership.upserted", "user", "demo:elena", 25),
    ("demo:marcus", "settings.updated", "org", None, 20),
    ("demo:priya", "membership.upserted", "user", "demo:tom", 8),
]

DEMO_SETTINGS = {"confidence": {"manual_threshold": 50, "review_threshold": 80}}


async def seed_demo_org(db: Database, settings: Settings) -> None:
    org_id = await db.ensure_org(settings.demo_clerk_org_id, settings.demo_org_name)
    async with db.tenant(org_id) as session:
        await session.execute(
            update(Organization)
            .where(Organization.id == org_id)
            .values(name=settings.demo_org_name, slug="demo", settings=DEMO_SETTINGS)
        )
        for user_id, email, name, role in DEMO_MEMBERS:
            await session.execute(
                insert(Membership)
                .values(
                    org_id=org_id,
                    clerk_user_id=user_id,
                    email=email,
                    display_name=name,
                    role=role,
                )
                .on_conflict_do_nothing(index_elements=["org_id", "clerk_user_id"])
            )
        existing = await session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.org_id == org_id)
        )
        if not existing:
            now = datetime.now(UTC)
            for actor, action, target_type, target_id, days_ago in DEMO_EVENTS:
                session.add(
                    AuditEvent(
                        org_id=org_id,
                        actor_clerk_user_id=actor,
                        action=action,
                        target_type=target_type,
                        target_id=target_id,
                        created_at=now - timedelta(days=days_ago),
                    )
                )
