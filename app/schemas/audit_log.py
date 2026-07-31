from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    village_id: uuid.UUID | None
    user_id: uuid.UUID | None
    action: str
    detail: str
    ip_address: str
    user_agent: str
    created_at: datetime