from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.models.camera import CameraDirection, CameraVerificationStatus


class CameraCreate(BaseModel):
    village_id: uuid.UUID
    name: str = Field(max_length=255)
    lat: float = Field(ge=-90, le=90)
    long: float = Field(ge=-180, le=180)
    stream_ai: str = Field(max_length=255)
    direction: CameraDirection


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    lat: float | None = Field(default=None, ge=-90, le=90)
    long: float | None = Field(default=None, ge=-180, le=180)
    stream_ai: str | None = Field(default=None, max_length=255)
    direction: CameraDirection | None = None
    is_active: bool | None = None


class CameraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    village_id: uuid.UUID
    name: str
    lat: float
    long: float
    stream_ai: str
    direction: CameraDirection | None
    stream_url: str
    webhook_url: str
    verification_status: CameraVerificationStatus
    ai_vision_synced_at: datetime | None
    created_at: datetime
    is_active: bool


class CameraBasicRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    lat: float
    long: float
    direction: CameraDirection | None
    is_active: bool


class CameraStatusRead(BaseModel):
    id: uuid.UUID
    is_active: bool
    verification_status: CameraVerificationStatus
    stream_online: bool | None


class CameraResyncFailedEntry(BaseModel):
    id: uuid.UUID
    name: str


class CameraResyncAllRead(BaseModel):
    total: int
    succeeded: int
    failed: int
    failed_cameras: list[CameraResyncFailedEntry]


class CameraVerificationCheckRead(BaseModel):
    id: uuid.UUID
    verification_status: CameraVerificationStatus
    is_active: bool
    ai_vision_synced_at: datetime | None
    ai_vision_reachable: bool
    polling_restarted: bool
    anomaly_detected: bool
    note: str | None

class OnvifProbeRequest(BaseModel):
    host: str = Field(max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str = Field(max_length=255)
    password: str = Field(max_length=255)


class OnvifProfileRead(BaseModel):
    profile_token: str
    name: str
    encoding: str | None
    width: int | None
    height: int | None
    rtsp_uri: str


class OnvifProbeResponse(BaseModel):
    device_manufacturer: str | None
    device_model: str | None
    profiles: list[OnvifProfileRead]

class CameraStatusRead(BaseModel):
    id: uuid.UUID
    is_active: bool
    verification_status: CameraVerificationStatus
    stream_online: bool | None


class CameraStreamTokenRead(BaseModel):
    camera_id: uuid.UUID
    stream_url: str
    expires_at: datetime