from __future__ import annotations
import re
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator

_THAI_PLATE_PATTERN = re.compile(r"^[ก-ฮะ-์เ-ไ0-9\s]+$")


class BlacklistCreate(BaseModel):
    village_id: uuid.UUID | None = None
    license_plate: str = Field(max_length=255)
    province: str = Field(max_length=255)
    reason: str = Field(max_length=255)


    @field_validator("license_plate", "province")
    @classmethod
    def normalize(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("license_plate")
    @classmethod
    def validate_thai_plate(cls, v: str) -> str:
        if not _THAI_PLATE_PATTERN.match(v):
            raise ValueError("ป้ายทะเบียนต้องเป็นภาษาไทยและตัวเลข 0-9 เท่านั้น")
        return v


class BlacklistUpdate(BaseModel):
    license_plate: str | None = Field(default=None, max_length=255)
    province: str | None = Field(default=None, max_length=255)
    reason: str | None = Field(default=None, max_length=255)

    @field_validator("license_plate", "province")
    @classmethod
    def normalize(cls, v: str | None) -> str | None:
        return v.strip().upper() if v is not None else v

    @field_validator("license_plate")
    @classmethod
    def validate_thai_plate(cls, v: str | None) -> str | None:
        if v is not None and not _THAI_PLATE_PATTERN.match(v):
            raise ValueError("ป้ายทะเบียนต้องเป็นภาษาไทยและตัวเลข 0-9 เท่านั้น")
        return v


class BlacklistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    village_id: uuid.UUID
    license_plate: str
    province: str
    reason: str
    added_by: uuid.UUID | None
    created_at: datetime