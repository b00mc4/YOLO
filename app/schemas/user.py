from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, model_validator

from app.models.user import UserRole


class UserCreate(BaseModel):
    username: str
    fullname: str
    email: EmailStr
    role: UserRole
    village_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def check_village_matches_role(self) -> UserCreate:
        if self.role == UserRole.SUPERADMIN and self.village_id is not None:
            raise ValueError("superadmin must not have a village_id")
        if self.role != UserRole.SUPERADMIN and self.village_id is None:
            raise ValueError("village_id is required for this role")
        return self


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    fullname: str
    email: EmailStr
    role: UserRole
    village_id: uuid.UUID | None
    is_active: bool
    is_verify: bool
    created_at: datetime


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    role: UserRole
    is_active: bool
    is_verify: bool
    created_at: datetime


class UserDetail(BaseModel):
    id: uuid.UUID
    username: str
    fullname: str
    email: EmailStr
    role: UserRole
    village_id: uuid.UUID | None
    is_active: bool
    is_verify: bool
    created_at: datetime
    contact_count: int