from __future__ import annotations
import re
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.models.user import UserRole
from app.schemas.camera import CameraBasicRead

_ADDRESS_PATTERN = re.compile(r"^[A-Za-z0-9ก-ฮะ-์เ-ไ\s\/\.\,\-]+$")


class VillageCreate(BaseModel):
    name: str = Field(max_length=255)
    address: str = Field(max_length=255)

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 1 or len(v) > 255:
            raise ValueError("ที่อยู่ต้องมีความยาวระหว่าง 1 ถึง 255 ตัวอักษร")
        if not _ADDRESS_PATTERN.match(v):
            raise ValueError("ที่อยู่ต้องประกอบด้วยตัวอักษรภาษาไทย ภาษาอังกฤษ ตัวเลข หรือเครื่องหมายพื้นฐาน (/ . , -) เท่านั้น")
        return v


class VillageUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if len(v) < 1 or len(v) > 255:
                raise ValueError("ที่อยู่ต้องมีความยาวระหว่าง 1 ถึง 255 ตัวอักษร")
            if not _ADDRESS_PATTERN.match(v):
                raise ValueError("ที่อยู่ต้องประกอบด้วยตัวอักษรภาษาไทย ภาษาอังกฤษ ตัวเลข หรือเครื่องหมายพื้นฐาน (/ . , -) เท่านั้น")
        return v


class VillageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    address: str
    is_active: bool
    created_at: datetime

class VillageMemberSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    fullname: str
    role: UserRole
    is_active: bool

class VillageDetailRead(VillageRead):
    cameras: list[CameraBasicRead]
    members: list[VillageMemberSummary]