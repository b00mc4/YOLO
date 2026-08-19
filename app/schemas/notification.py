from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    village_id: uuid.UUID | None
    action: str
    detail: str
    payload: dict[str, Any] | None
    is_read: bool
    created_at: datetime


class UnreadCountResponse(BaseModel):
    count: int