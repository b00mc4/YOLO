from __future__ import annotations
import re
from pydantic import BaseModel, EmailStr, field_validator, model_validator
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
    confirm_new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return _validate_password_policy(v)

    @model_validator(mode="after")
    def check_passwords_match(self) -> SetPasswordRequest:
        if self.new_password != self.confirm_new_password:
            raise ValueError("New password and confirm password do not match")
        return self

class SetPasswordResponse(BaseModel):
    detail: str
    username: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_new_password: str
    logout_all_sessions: bool

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return _validate_password_policy(v)

    @model_validator(mode="after")
    def check_passwords_match(self) -> ChangePasswordRequest:
        if self.new_password != self.confirm_new_password:
            raise ValueError("New password and confirm password do not match")
        return self