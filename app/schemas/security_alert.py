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


class RapidLoginAlertPayload(BaseModel):
    username: str
    user_id: uuid.UUID
    ip_address: str
    count: int
    window_seconds: int
    occurred_at: datetime


class RapidLoginAlertPayloadGlobal(RapidLoginAlertPayload):
    village_id: uuid.UUID | None