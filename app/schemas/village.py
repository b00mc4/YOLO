from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.models.user import UserRole
from app.schemas.camera import CameraBasicRead


class VillageCreate(BaseModel):
    name: str = Field(max_length=255)


class VillageUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
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