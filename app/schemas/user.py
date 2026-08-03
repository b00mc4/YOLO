from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator
from app.models.user import UserRole
from app.schemas.contact import ContactRead
import re

def _validate_password_policy(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not re.search(r"[A-Za-z]", value):
        raise ValueError("Password must contain at least one letter")
    if not re.search(r"\d", value):
        raise ValueError("Password must contain at least one digit")
    return value

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


class AdminResetPasswordRequest(BaseModel):
    new_password: str
    confirm_new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return _validate_password_policy(v)

    @model_validator(mode="after")
    def check_passwords_match(self) -> AdminResetPasswordRequest:
        if self.new_password != self.confirm_new_password:
            raise ValueError("New password and confirm password do not match")
        return self


class AdminResetPasswordResponse(BaseModel):
    detail: str
    username: str


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


class UserMeDetail(BaseModel):
    id: uuid.UUID
    username: str
    fullname: str
    email: EmailStr
    role: UserRole
    village_id: uuid.UUID | None
    is_active: bool
    is_verify: bool
    created_at: datetime
    contacts: list[ContactRead]