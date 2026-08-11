from __future__ import annotations
import uuid
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.car import CameraLiveRead, CarDetailRead, CarRead, DetectionCreate, DetectionCreateAck
from app.schemas.common import PaginatedResponse
from app.services import detection_service
import logging
from starlette.datastructures import UploadFile as StarletteUploadFile

router = APIRouter(prefix="/detections", tags=["detections"])

_MULTIPART_CONTENT_TYPE = "multipart/form-data"
_TEST_ID_CAMERA = "TEST_Camera_"
_TEST_ID_EVENT = "TEST_Event_"
logger = logging.getLogger(__name__)

def _content_type_prefix(request: Request) -> str:
    return request.headers.get("content-type", "").split(";")[0].strip().lower()


def _format_validation_error(exc: ValidationError) -> str:
    messages = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"])
        messages.append(f"{loc}: {err['msg']}" if loc else err["msg"])
    return "; ".join(messages)


def _is_webhook_test(raw_event_id: str | None, raw_camera_id: str | None) -> bool:
    return (
        isinstance(raw_event_id, str) and raw_event_id.startswith(_TEST_ID_EVENT)
    ) or (
        isinstance(raw_camera_id, str) and raw_camera_id.startswith(_TEST_ID_CAMERA)
    )


def _handle_webhook_test(raw_event_id: str | None) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"event_id": raw_event_id, "status": "test_ok"},
    )


async def _handle_real_detection(request: Request, db: AsyncSession) -> JSONResponse:
    form = await request.form()

    image_crop = form.get("image_crop")
    image_full = form.get("image_full")

    if not isinstance(image_crop, StarletteUploadFile) or not isinstance(image_full, StarletteUploadFile):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="image_crop and image_full are required files",
        )

    raw_event_id = form.get("event_id")
    raw_camera_id = form.get("camera_id")

    is_test = _is_webhook_test(raw_event_id, raw_camera_id)
    logger.warning("is_test=%s event_id=%r camera_id=%r", is_test, raw_event_id, raw_camera_id)

    if is_test:
        return _handle_webhook_test(raw_event_id)

    try:
        payload = DetectionCreate(
            event_id=raw_event_id,
            camera_id=raw_camera_id,
            license_plate=form.get("license_plate"),
            province=form.get("province"),
            color=form.get("color"),
            capture_time=form.get("capture_time"),
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_format_validation_error(exc),
        )

    car = await detection_service.create_detection(db, request, payload, image_crop, image_full)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=jsonable_encoder(car))


@router.post(
    "",
    response_model=DetectionCreateAck,
    status_code=status.HTTP_201_CREATED,
)
async def create_detection(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    content_type = _content_type_prefix(request)

    if content_type == _MULTIPART_CONTENT_TYPE:
        return await _handle_real_detection(request, db)

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=f"Unsupported Content-Type: {content_type or 'missing'}",
    )


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

@router.get("/live", response_model=CameraLiveRead)
async def get_camera_live(
    request: Request,
    camera_id: uuid.UUID = Query(...),
    limit: int = Query(default=5, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await detection_service.get_camera_live_view(db, request, current_user, camera_id, limit)

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