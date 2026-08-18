from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel


class LoginBruteforceAlertPayload(BaseModel):
    username: str
    user_id: uuid.UUID | None
    ip_address: str
    locked_for_seconds: float
    occurred_at: datetime


class LoginBruteforceAlertPayloadGlobal(LoginBruteforceAlertPayload):
    village_id: uuid.UUID | None