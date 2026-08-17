from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


class WhitelistCreate(BaseModel):
    village_id: uuid.UUID | None = None
    license_plate: str = Field(max_length=255)
    province: str = Field(max_length=255)
    note: str | None = Field(default=None, max_length=255)

    @field_validator("license_plate", "province")
    @classmethod
    def normalize(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("note")
    @classmethod
    def normalize_note(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v


class WhitelistUpdate(BaseModel):
    license_plate: str | None = Field(default=None, max_length=255)
    province: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=255)

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
    license_plate: str
    province: str
    note: str | None
    added_by: uuid.UUID | None
    created_at: datetime
