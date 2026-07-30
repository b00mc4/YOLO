from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import Form
from pydantic import BaseModel, ConfigDict


class DetectionCreate(BaseModel):
    event_id: uuid.UUID
    camera_id: uuid.UUID
    license_plate: str
    province: str
    color: str
    time_detect: datetime

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