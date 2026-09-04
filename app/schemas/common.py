from typing import Generic, TypeVar

from pydantic import BaseModel, Field, field_validator, model_validator
from app.core.security import validate_password_policy
from app.core.error_messages import ValidationErrors

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class ErrorResponse(BaseModel):
    detail: str


class MessageResponse(BaseModel):
    detail: str


class PasswordConfirmMixin(BaseModel):
    new_password: str = Field(max_length=36)
    confirm_new_password: str = Field(max_length=36)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return validate_password_policy(v)

    @model_validator(mode="after")
    def check_passwords_match(self) -> "PasswordConfirmMixin":
        if self.new_password != self.confirm_new_password:
            raise ValueError(ValidationErrors.PASSWORD_MISMATCH)
        return self