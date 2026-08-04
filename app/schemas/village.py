from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models.user import UserRole
from app.schemas.camera import CameraBasicRead


class VillageCreate(BaseModel):
    name: str


class VillageUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None


class VillageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    is_active: bool
    created_at: datetime

class VillageMemberSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    fullname: str
    role: UserRole
    is_active: bool

class VillageDetailRead(VillageRead):
    cameras: list[CameraBasicRead]
    members: list[VillageMemberSummary]