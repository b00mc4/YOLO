from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.car import CarDetailRead, CarRead, DetectionCreate
from app.schemas.common import PaginatedResponse
from app.services import detection_service

router = APIRouter(prefix="/detections", tags=["detections"])


@router.post(
    "",
    response_model=CarRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_detection(
    request: Request,
    payload: DetectionCreate = Depends(DetectionCreate.as_form),
    image_crop: UploadFile = File(...),
    image_full: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    return await detection_service.create_detection(db, request, payload, image_crop, image_full)


@router.get("", response_model=PaginatedResponse[CarRead])
async def list_detections(
    request: Request,
    village_id: uuid.UUID | None = Query(default=None),
    camera_id: uuid.UUID | None = Query(default=None),
    license_plate: str | None = Query(default=None),
    province: str | None = Query(default=None),
    time_detect_from: datetime | None = Query(default=None),
    time_detect_to: datetime | None = Query(default=None),
    is_blacklist: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await detection_service.list_detections(
        db=db,
        request=request,
        current_user=current_user,
        village_id=village_id,
        camera_id=camera_id,
        license_plate=license_plate,
        province=province,
        time_detect_from=time_detect_from,
        time_detect_to=time_detect_to,
        is_blacklist=is_blacklist,
        page=page,
        page_size=page_size,
    )


@router.get("/{detection_id}", response_model=CarDetailRead)
async def get_detection_detail(
    detection_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await detection_service.get_detection_detail(db, request, current_user, detection_id)


@router.get("/{detection_id}/image/{variant}", name="get_detection_image")
async def get_detection_image(
    detection_id: uuid.UUID,
    variant: Literal["crop", "full"],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    file_path, media_type = await detection_service.get_detection_image_path(
        db, current_user, detection_id, variant
    )
    return FileResponse(file_path, media_type=media_type)