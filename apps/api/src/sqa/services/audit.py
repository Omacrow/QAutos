import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from sqa.models import AuditEvent


async def record(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    action: str,
    actor_clerk_user_id: str | None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Append an audit event in the caller's transaction.

    Keep `details` to ids and enums. Never put customer content in it.
    """
    session.add(
        AuditEvent(
            org_id=org_id,
            actor_clerk_user_id=actor_clerk_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details or {},
        )
    )
