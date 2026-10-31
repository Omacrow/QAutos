import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from sqa.models import Role


class OrgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str | None
    settings: dict[str, Any]


class MeOut(BaseModel):
    user_id: str
    role: Role
    org: OrgOut


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clerk_user_id: str
    email: str | None
    display_name: str | None
    role: Role
    last_seen_at: datetime


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_clerk_user_id: str | None
    action: str
    target_type: str | None
    target_id: str | None
    details: dict[str, Any]
    created_at: datetime


class HealthOut(BaseModel):
    status: str
