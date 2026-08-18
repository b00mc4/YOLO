from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.models.whitelist import WhitelistCategory


def _normalize_category(value):
    if isinstance(value, str):
        return value.strip().lower()
    return value


class WhitelistCreate(BaseModel):
    village_id: uuid.UUID | None = None
    category: WhitelistCategory
    name: str = Field(max_length=255)
    license_plate: str = Field(max_length=255)
    province: str = Field(max_length=255)
    note: str | None = Field(default=None, max_length=255)

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v):
        return _normalize_category(v)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("license_plate", "province")
    @classmethod
    def normalize(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("note")
    @classmethod
    def normalize_note(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v


class WhitelistUpdate(BaseModel):
    category: WhitelistCategory | None = None
    name: str | None = Field(default=None, max_length=255)
    license_plate: str | None = Field(default=None, max_length=255)
    province: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=255)

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v):
        return _normalize_category(v)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v

    @field_validator("license_plate", "province")
    @classmethod
    def normalize(cls, v: str | None) -> str | None:
        return v.strip().upper() if v is not None else v

    @field_validator("note")
    @classmethod
    def normalize_note(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v


class WhitelistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    village_id: uuid.UUID
    category: WhitelistCategory
    name: str
    license_plate: str
    province: str
    note: str | None
    added_by: uuid.UUID | None
    created_at: datetime