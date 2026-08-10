from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.user import UserRole


class PresenceTicketResponse(BaseModel):
    ticket: str


class PresenceUserEntry(BaseModel):
    user_id: uuid.UUID
    username: str
    fullname: str
    role: UserRole


class VillagePresenceSnapshot(BaseModel):
    village_id: uuid.UUID
    total_online: int
    online_users: list[PresenceUserEntry]
    online_superadmins: list[PresenceUserEntry]


class VillageBreakdownEntry(BaseModel):
    village_id: uuid.UUID
    village_name: str
    total_online: int
    online_users: list[PresenceUserEntry]


class AllVillagesPresenceSnapshot(BaseModel):
    total_online: int
    villages: list[VillageBreakdownEntry]
    online_superadmins: list[PresenceUserEntry]