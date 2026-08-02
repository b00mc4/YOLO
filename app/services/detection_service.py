from __future__ import annotations
import uuid
from datetime import datetime
from pathlib import Path
from fastapi import HTTPException, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import verify_village_scope
from app.models.blacklist import Blacklist
from app.models.camera import Camera
from app.models.car import Car
from app.models.group import Group
from app.models.user import User, UserRole
from app.schemas.car import CameraSummary, CarDetailRead, CarRead, DetectionCreate
from app.schemas.common import PaginatedResponse
from app.services import audit_service, storage_service


def _to_car_read(car: Car, request: Request) -> CarRead:
    return CarRead(
        id=car.id,
        event_id=car.event_id,
        camera_id=car.camera_id,
        license_plate=car.license_plate,
        province=car.province,
        color=car.color,
        image_crop=str(
            request.url_for("get_detection_image", detection_id=car.id, variant="crop")
        ),
        image_full=str(
            request.url_for("get_detection_image", detection_id=car.id, variant="full")
        ),
        time_detect=car.time_detect,
        is_blacklist=car.is_blacklist,
        created_at=car.created_at,
    )


def _to_car_detail_read(car: Car, camera: Camera, village: Group, request: Request) -> CarDetailRead:
    return CarDetailRead(
        id=car.id,
        event_id=car.event_id,
        license_plate=car.license_plate,
        province=car.province,
        color=car.color,
        image_crop=str(
            request.url_for("get_detection_image", detection_id=car.id, variant="crop")
        ),
        image_full=str(
            request.url_for("get_detection_image", detection_id=car.id, variant="full")
        ),
        time_detect=car.time_detect,
        is_blacklist=car.is_blacklist,
        created_at=car.created_at,
        camera=CameraSummary(
            id=camera.id,
            name=camera.name,
            village_id=village.id,
            village_name=village.name,
        ),
    )


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


async def _rollback_failed_detection(
    db: AsyncSession,
    car: Car,
    written_paths: list[str],
) -> None:
    for relative_path in written_paths:
        await storage_service.delete_detection_image(relative_path)

    await db.delete(car)
    await db.commit()


async def create_detection(
    db: AsyncSession,
    request: Request,
    payload: DetectionCreate,
    image_crop: UploadFile,
    image_full: UploadFile,
) -> CarRead:
    camera = await _get_camera_or_404(db, payload.camera_id)
    await _ensure_event_not_duplicate(db, payload.event_id)

    crop_content, crop_extension = await storage_service.read_and_validate_image(image_crop)
    full_content, full_extension = await storage_service.read_and_validate_image(image_full)

    crop_path = storage_service.build_detection_image_path(
        village_id=camera.village_id,
        camera_id=camera.id,
        event_id=payload.event_id,
        suffix="crop",
        extension=crop_extension,
    )
    full_path = storage_service.build_detection_image_path(
        village_id=camera.village_id,
        camera_id=camera.id,
        event_id=payload.event_id,
        suffix="full",
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

    written_paths: list[str] = []
    try:
        await storage_service.write_detection_image(crop_path, crop_content)
        written_paths.append(crop_path)
        await storage_service.write_detection_image(full_path, full_content)
        written_paths.append(full_path)
    except OSError:
        await _rollback_failed_detection(db, car, written_paths)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store detection images",
        )

    return _to_car_read(car, request)


async def list_detections(
    db: AsyncSession,
    request: Request,
    current_user: User,
    village_id: uuid.UUID | None,
    camera_id: uuid.UUID | None,
    license_plate: str | None,
    province: str | None,
    time_detect_from: datetime | None,
    time_detect_to: datetime | None,
    is_blacklist: bool | None,
    page: int,
    page_size: int,
) -> PaginatedResponse[CarRead]:
    stmt = select(Car).join(Camera, Car.camera_id == Camera.id)

    if current_user.role == UserRole.SUPERADMIN:
        if village_id is not None:
            stmt = stmt.where(Camera.village_id == village_id)
    else:
        stmt = stmt.where(Camera.village_id == current_user.village_id)

    if camera_id is not None:
        stmt = stmt.where(Car.camera_id == camera_id)
    if license_plate is not None:
        stmt = stmt.where(Car.license_plate.ilike(f"%{license_plate}%"))
    if province is not None:
        stmt = stmt.where(Car.province == province)
    if time_detect_from is not None:
        stmt = stmt.where(Car.time_detect >= time_detect_from)
    if time_detect_to is not None:
        stmt = stmt.where(Car.time_detect <= time_detect_to)
    if is_blacklist is not None:
        stmt = stmt.where(Car.is_blacklist == is_blacklist)

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()

    stmt = (
        stmt.order_by(Car.time_detect.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    return PaginatedResponse[CarRead](
        items=[_to_car_read(item, request) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_detection_detail(
    db: AsyncSession,
    request: Request,
    current_user: User,
    detection_id: uuid.UUID,
) -> CarDetailRead:
    result = await db.execute(
        select(Car, Camera, Group)
        .join(Camera, Car.camera_id == Camera.id)
        .join(Group, Camera.village_id == Group.id)
        .where(Car.id == detection_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")

    car, camera, village = row
    verify_village_scope(current_user, camera.village_id)

    return _to_car_detail_read(car, camera, village, request)


async def get_detection_image_path(
    db: AsyncSession,
    current_user: User,
    detection_id: uuid.UUID,
    variant: str,
) -> tuple[Path, str]:
    result = await db.execute(
        select(Car, Camera.village_id)
        .join(Camera, Car.camera_id == Camera.id)
        .where(Car.id == detection_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")

    car, village_id = row
    verify_village_scope(current_user, village_id)

    relative_path = car.image_crop if variant == "crop" else car.image_full
    absolute_path = storage_service.resolve_storage_path(relative_path)
    if not absolute_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image file not found")

    return absolute_path, storage_service.guess_media_type(absolute_path)