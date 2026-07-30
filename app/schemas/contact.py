from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ContactCreate(BaseModel):
    content_type: str
    custom_label: str | None = None
    value: str


class ContactUpdate(BaseModel):
    content_type: str | None = None
    custom_label: str | None = None
    value: str | None = None


class ContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    content_type: str
    custom_label: str | None
    value: str
    created_at: datetime
