from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CameraCreate(BaseModel):
    village_id: uuid.UUID
    name: str
    lat: float = Field(ge=-90, le=90)
    long: float = Field(ge=-180, le=180)
    stream_url: str


class CameraUpdate(BaseModel):
    name: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    long: float | None = Field(default=None, ge=-180, le=180)
    stream_url: str | None = None


class CameraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    village_id: uuid.UUID
    name: str
    lat: float
    long: float
    stream_url: str
    created_at: datetime
    is_active: bool