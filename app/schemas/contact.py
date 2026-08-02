from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from app.models.contact import ContactType


def _normalize_content_type(value):
    if isinstance(value, str):
        return value.strip().lower()
    return value


class ContactCreate(BaseModel):
    user_id: uuid.UUID | None = None
    content_type: ContactType
    custom_label: str | None = None
    value: str

    @field_validator("content_type", mode="before")
    @classmethod
    def normalize_content_type(cls, v):
        return _normalize_content_type(v)

    @field_validator("value")
    @classmethod
    def normalize_value(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("custom_label")
    @classmethod
    def normalize_custom_label(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v

    @model_validator(mode="after")
    def check_custom_label_matches_content_type(self) -> ContactCreate:
        if self.content_type == ContactType.OTHER:
            if not self.custom_label:
                raise ValueError("custom_label is required when content_type is 'other'")
        elif self.custom_label is not None:
            raise ValueError("custom_label must not be set unless content_type is 'other'")
        return self


class ContactUpdate(BaseModel):
    content_type: ContactType | None = None
    custom_label: str | None = None
    value: str | None = None

    @field_validator("content_type", mode="before")
    @classmethod
    def normalize_content_type(cls, v):
        return _normalize_content_type(v)

    @field_validator("value")
    @classmethod
    def normalize_value(cls, v: str | None) -> str | None:
        return v.strip().lower() if v is not None else v

    @field_validator("custom_label")
    @classmethod
    def normalize_custom_label(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v


class ContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    content_type: ContactType
    custom_label: str | None
    value: str
    created_at: datetime


class UserContactSummary(BaseModel):
    user_id: uuid.UUID
    username: str
    fullname: str
    village_id: uuid.UUID | None
    village_name: str | None
    contact_count: int


class UserContactsDetail(BaseModel):
    user_id: uuid.UUID
    username: str
    fullname: str
    village_id: uuid.UUID | None
    village_name: str | None
    contacts: list[ContactRead]