from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    village_id: uuid.UUID | None
    village_name: str | None
    user_id: uuid.UUID | None
    username: str | None
    action: str
    detail: str
    ip_address: str
    user_agent: str
    created_at: datetime