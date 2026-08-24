from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


class WhitelistCreate(BaseModel):
    village_id: uuid.UUID | None = None
    name: str = Field(max_length=255)
    house_no: str = Field(default=None, max_length=255)
    phone: str = Field(default=None, max_length=20)
    license_plate: str = Field(max_length=255)
    province: str = Field(max_length=255)
    color: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("license_plate", "province")
    @classmethod
    def normalize(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("house_no", "phone", "color", "note")
    @classmethod
    def normalize_optional(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v


class WhitelistUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    house_no: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    license_plate: str | None = Field(default=None, max_length=255)
    province: str | None = Field(default=None, max_length=255)
    color: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v

    @field_validator("license_plate", "province")
    @classmethod
    def normalize(cls, v: str | None) -> str | None:
        return v.strip().upper() if v is not None else v

    @field_validator("house_no", "phone", "color", "note")
    @classmethod
    def normalize_optional(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v


class WhitelistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    village_id: uuid.UUID
    name: str
    house_no: str | None
    phone: str | None
    license_plate: str
    province: str
    color: str | None
    note: str | None
    added_by: uuid.UUID | None
    created_at: datetime