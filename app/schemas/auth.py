from __future__ import annotations
import re
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from app.schemas.user import UserRead

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
    token: str = Field(max_length=512)
    new_password: str = Field(max_length=128)
    confirm_new_password: str = Field(max_length=128)

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
    email: EmailStr = Field(max_length=255)

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)
    confirm_new_password: str = Field(max_length=128)
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