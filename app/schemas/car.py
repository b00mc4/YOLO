from __future__ import annotations
import uuid
from datetime import date, datetime
from fastapi import Form
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.core.timezone import BANGKOK_TZ

_CAPTURE_TIME_FORMAT = "%Y/%m/%d %H:%M:%S"


class DetectionCreate(BaseModel):
    event_id: uuid.UUID
    camera_id: uuid.UUID
    license_plate: str = Field(max_length=255)
    province: str = Field(max_length=255)
    color: str = Field(max_length=255)
    capture_time: datetime

    @field_validator("license_plate", "province")
    @classmethod
    def normalize(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("capture_time", mode="before")
    @classmethod
    def parse_capture_time(cls, v):
        if isinstance(v, str):
            try:
                parsed = datetime.strptime(v, _CAPTURE_TIME_FORMAT)
            except ValueError:
                raise ValueError(f"capture_time must be in format YYYY/MM/DD HH:MM:SS, got: {v!r}")
            return parsed.replace(tzinfo=BANGKOK_TZ)
        return v

    @classmethod
    def as_form(
        cls,
        event_id: uuid.UUID = Form(...),
        camera_id: uuid.UUID = Form(...),
        license_plate: str = Form(..., max_length=255),
        province: str = Form(..., max_length=255),
        color: str = Form(..., max_length=255),
        capture_time: str = Form(...),
    ) -> DetectionCreate:
        return cls(
            event_id=event_id,
            camera_id=camera_id,
            license_plate=license_plate,
            province=province,
            color=color,
            capture_time=capture_time,
        )


class CarRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    camera_id: uuid.UUID
    license_plate: str
    province: str
    color: str
    image_crop: str
    image_full: str
    time_detect: datetime
    is_blacklist: bool
    created_at: datetime


class CameraSummary(BaseModel):
    id: uuid.UUID
    name: str
    village_id: uuid.UUID
    village_name: str


class CarDetailRead(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    license_plate: str
    province: str
    color: str
    image_crop: str
    image_full: str
    time_detect: datetime
    is_blacklist: bool
    created_at: datetime
    camera: CameraSummary

class RepeatedPlateEntry(BaseModel):
    license_plate: str
    province: str
    count: int


class DetectionDashboardRead(BaseModel):
    date: date
    total_detections_today: int
    unique_plates_today: int
    blacklist_detections_today: int
    top_repeated_plates: list[RepeatedPlateEntry]
    latest_detections: list[CarRead]


class DetectionEventCamera(BaseModel):
    id: uuid.UUID
    name: str
    lat: float
    long: float


class DetectionEventPayload(BaseModel):
    detection_id: uuid.UUID
    license_plate: str
    province: str
    color: str
    time_detect: datetime
    is_blacklist: bool
    camera: DetectionEventCamera
    image_crop: str
    image_full: str

class DetectionEventCameraGlobal(DetectionEventCamera):
    village_id: uuid.UUID
 
 
class DetectionEventPayloadGlobal(DetectionEventPayload):
    camera: DetectionEventCameraGlobal

class LiveCaptureEntry(BaseModel):
    id: uuid.UUID
    time_detect: datetime
    license_plate: str
    province: str
    color: str
    image_crop: str
    image_full: str


class CameraLiveRead(BaseModel):
    camera_id: uuid.UUID
    camera_name: str
    is_active: bool
    stream_url: str
    latest_captures: list[LiveCaptureEntry]

class DetectionCreateAck(BaseModel):
    event_id: uuid.UUID