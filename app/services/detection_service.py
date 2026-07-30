from __future__ import annotations
import uuid
from fastapi import HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.blacklist import Blacklist
from app.models.camera import Camera
from app.models.car import Car
from app.schemas.car import DetectionCreate
from app.services import audit_service, storage_service


async def _get_camera_or_404(db: AsyncSession, camera_id: uuid.UUID) -> Camera:
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    return camera


async def _ensure_event_not_duplicate(db: AsyncSession, event_id: uuid.UUID) -> None:
    result = await db.execute(select(Car.id).where(Car.event_id == event_id))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Detection event already recorded",
        )


async def _check_is_blacklisted(
    db: AsyncSession,
    village_id: uuid.UUID,
    license_plate: str,
    province: str,
) -> bool:
    result = await db.execute(
        select(Blacklist.id).where(
            Blacklist.village_id == village_id,
            Blacklist.license_plate == license_plate,
            Blacklist.province == province,
        )
    )
    return result.scalar_one_or_none() is not None


async def create_detection(
    db: AsyncSession,
    request: Request,
    payload: DetectionCreate,
    image_crop: UploadFile,
    image_full: UploadFile,
) -> Car:
    camera = await _get_camera_or_404(db, payload.camera_id)
    await _ensure_event_not_duplicate(db, payload.event_id)

    crop_extension = storage_service.validate_image_content_type(image_crop)
    full_extension = storage_service.validate_image_content_type(image_full)

    crop_path = await storage_service.save_detection_image(
        village_id=camera.village_id,
        camera_id=camera.id,
        event_id=payload.event_id,
        suffix="crop",
        upload=image_crop,
        extension=crop_extension,
    )
    full_path = await storage_service.save_detection_image(
        village_id=camera.village_id,
        camera_id=camera.id,
        event_id=payload.event_id,
        suffix="full",
        upload=image_full,
        extension=full_extension,
    )

    is_blacklist = await _check_is_blacklisted(
        db, camera.village_id, payload.license_plate, payload.province
    )

    car = Car(
        event_id=payload.event_id,
        camera_id=camera.id,
        license_plate=payload.license_plate,
        province=payload.province,
        color=payload.color,
        image_crop=crop_path,
        image_full=full_path,
        time_detect=payload.time_detect,
        is_blacklist=is_blacklist,
    )
    db.add(car)

    if is_blacklist:
        await audit_service.log_action(
            db,
            request,
            action="blacklist_detection",
            detail=f"blacklisted plate detected: {payload.license_plate} ({payload.province})",
            village_id=camera.village_id,
        )

    await db.commit()
    await db.refresh(car)
    return car