from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BlacklistCreate(BaseModel):
    license_plate: str
    province: str
    reason: str


class BlacklistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    village_id: uuid.UUID
    license_plate: str
    province: str
    reason: str
    added_by: uuid.UUID
    created_at: datetime
