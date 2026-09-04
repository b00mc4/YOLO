from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from app.core.security import validate_password_policy
from app.schemas.user import UserRead
from app.core.error_messages import ValidationErrors

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class LoginResponse(TokenResponse):
    user: UserRead

class SetPasswordRequest(BaseModel):
    token: str = Field(max_length=512)
    new_password: str = Field(max_length=36)
    confirm_new_password: str = Field(max_length=36)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return validate_password_policy(v)

    @model_validator(mode="after")
    def check_passwords_match(self) -> SetPasswordRequest:
        if self.new_password != self.confirm_new_password:
            raise ValueError(ValidationErrors.PASSWORD_MISMATCH)
        return self

class SetPasswordResponse(BaseModel):
    detail: str
    username: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(max_length=255)

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=36)
    confirm_new_password: str = Field(max_length=36)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return validate_password_policy(v)

    @model_validator(mode="after")
    def check_passwords_match(self) -> ChangePasswordRequest:
        if self.new_password != self.confirm_new_password:
            raise ValueError(ValidationErrors.PASSWORD_MISMATCH)
        return self

class EmailChangeConfirm(BaseModel):
    token: str = Field(max_length=512)


class EmailChangeConfirmResponse(BaseModel):
    detail: str
    username: str
    email: EmailStr

class VerifyTokenRequest(BaseModel):
    token: str = Field(max_length=512)

class SessionInfo(BaseModel):
    id: uuid.UUID
    created_at: datetime
    expired_at: datetime
    is_current: bool = False

class ActiveSessionsResponse(BaseModel):
    active_sessions_count: int
    max_sessions: int
    sessions: list[SessionInfo]