from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.camera import CameraRead
from app.schemas.user import UserRead


class VillageCreate(BaseModel):
    name: str
    is_active: bool = True


class VillageUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None


class VillageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    is_active: bool
    created_at: datetime


class VillageDetailRead(VillageRead):
    cameras: list[CameraRead]
    members: list[UserRead]