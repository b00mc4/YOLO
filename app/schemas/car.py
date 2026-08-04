from __future__ import annotations
import uuid
from datetime import date, datetime
from fastapi import Form
from pydantic import BaseModel, ConfigDict, field_validator


class DetectionCreate(BaseModel):
    event_id: uuid.UUID
    camera_id: uuid.UUID
    license_plate: str
    province: str
    color: str
    time_detect: datetime

    @field_validator("license_plate", "province")
    @classmethod
    def normalize(cls, v: str) -> str:
        return v.strip().upper()

    @classmethod
    def as_form(
        cls,
        event_id: uuid.UUID = Form(...),
        camera_id: uuid.UUID = Form(...),
        license_plate: str = Form(...),
        province: str = Form(...),
        color: str = Form(...),
        time_detect: datetime = Form(...),
    ) -> DetectionCreate:
        return cls(
            event_id=event_id,
            camera_id=camera_id,
            license_plate=license_plate,
            province=province,
            color=color,
            time_detect=time_detect,
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