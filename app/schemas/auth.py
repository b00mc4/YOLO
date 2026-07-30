from __future__ import annotations
import re
from pydantic import BaseModel, EmailStr, field_validator
from app.schemas.user import UserRead

class MessageResponse(BaseModel):
    detail: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class LoginResponse(TokenResponse):
    user: UserRead

def _validate_password_policy(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not re.search(r"[A-Za-z]", value):
        raise ValueError("Password must contain at least one letter")
    if not re.search(r"\d", value):
        raise ValueError("Password must contain at least one digit")
    return value

class SetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return _validate_password_policy(v)

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    logout_all_sessions: bool

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return _validate_password_policy(v)