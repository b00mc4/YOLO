from __future__ import annotations
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from app.core.security import validate_password_policy
from app.schemas.user import UserRead
from app.core.error_messages import ValidationErrors

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class LoginResponse(TokenResponse):
    user: UserRead

class SetPasswordRequest(BaseModel):
    token: str = Field(max_length=512)
    new_password: str = Field(max_length=128)
    confirm_new_password: str = Field(max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return validate_password_policy(v)

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