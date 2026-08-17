from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from fastapi import HTTPException, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import verify_village_scope
from app.models.blacklist import Blacklist
from app.models.camera import Camera
from app.models.car import Car
from app.models.group import Group
from app.models.user import User, UserRole
from app.schemas.car import (
    CameraLiveRead,
    CameraSummary,
    CarDetailRead,
    CarRead,
    DetectionCreate,
    DetectionDashboardRead,
    DetectionEventCamera,
    DetectionEventCameraGlobal,
    DetectionEventPayload,
    DetectionEventPayloadGlobal,
    LiveCaptureEntry,
    RepeatedPlateEntry,
    DetectionCreateAck
)
from app.schemas.common import PaginatedResponse
from app.services import audit_service, camera_service, mediamtx_service, sse_service, storage_service
import logging
from app.core.timezone import BANGKOK_TZ

logger = logging.getLogger(__name__)

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
    result = await db.execute(
        select(Camera, Group.is_active)
        .join(Group, Camera.village_id == Group.id)
        .where(Camera.id == camera_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    camera, village_is_active = row

    if not village_is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Camera's village is inactive and cannot receive detections",
        )
    if not camera.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Camera is inactive and cannot receive detections",
        )
    return camera


async def _find_existing_car_by_event_id(db: AsyncSession, event_id: uuid.UUID) -> Car | None:
    result = await db.execute(select(Car).where(Car.event_id == event_id))
    return result.scalar_one_or_none()


async def _check_is_blacklisted(
    db: AsyncSession,
    village_id: uuid.UUID,
    license_plate: str,
    province: str,
) -> bool:
    result = await db.execute(
        select(Blacklist.id)
        .where(
            Blacklist.village_id == village_id,
            Blacklist.license_plate == license_plate,
            Blacklist.province == province,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None

async def _cleanup_written_images(written_paths: list[str]) -> None:
    for relative_path in written_paths:
        await storage_service.delete_detection_image(relative_path)


def _build_detection_event_payload(request: Request, camera: Camera, car: Car) -> DetectionEventPayload:
    return DetectionEventPayload(
        detection_id=car.id,
        license_plate=car.license_plate,
        province=car.province,
        color=car.color,
        time_detect=car.time_detect,
        is_blacklist=car.is_blacklist,
        camera=DetectionEventCamera(
            id=camera.id,
            name=camera.name,
            lat=camera.lat,
            long=camera.long,
        ),
        image_crop=str(
            request.url_for("get_detection_image", detection_id=car.id, variant="crop")
        ),
        image_full=str(
            request.url_for("get_detection_image", detection_id=car.id, variant="full")
        ),
    )


def _build_global_detection_event_payload(
    request: Request, camera: Camera, car: Car
) -> DetectionEventPayloadGlobal:
    return DetectionEventPayloadGlobal(
        detection_id=car.id,
        license_plate=car.license_plate,
        province=car.province,
        color=car.color,
        time_detect=car.time_detect,
        is_blacklist=car.is_blacklist,
        camera=DetectionEventCameraGlobal(
            id=camera.id,
            name=camera.name,
            lat=camera.lat,
            long=camera.long,
            village_id=camera.village_id,
        ),
        image_crop=str(
            request.url_for("get_detection_image", detection_id=car.id, variant="crop")
        ),
        image_full=str(
            request.url_for("get_detection_image", detection_id=car.id, variant="full")
        ),
    )


async def create_detection(
    db: AsyncSession,
    request: Request,
    payload: DetectionCreate,
    image_crop: UploadFile,
    image_full: UploadFile,
) -> tuple[DetectionCreateAck, bool]:
    """
    สร้าง detection ใหม่จาก webhook ของ AI vision

    Idempotent ตาม event_id: ถ้า event_id นี้เคยถูกบันทึกไปแล้ว (ไม่ว่าจะจากการ
    ประมวลผลสำเร็จรอบก่อน หรือจาก request คู่แข่งที่ insert ไปพร้อมกัน) จะไม่สร้าง
    record ใหม่ ไม่เขียนรูปซ้ำ ไม่ publish SSE ซ้ำ แต่ return ack ของ record เดิมกลับไป
    โดยตัวที่สองของ tuple ที่ return คือ is_new (True = สร้างจริง, False = replay)
    ผู้เรียกใช้ค่านี้เพื่อเลือกตอบ 201 หรือ 200 กลับไปยัง AI vision
    """
    existing = await _find_existing_car_by_event_id(db, payload.event_id)
    if existing is not None:
        logger.info(
            "duplicate detection event replay: event_id=%s detection_id=%s",
            payload.event_id, existing.id,
        )
        return DetectionCreateAck(event_id=existing.event_id), False

    camera = await _get_camera_or_404(db, payload.camera_id)

    car_id = uuid.uuid4()

    crop_content, crop_extension = await storage_service.read_and_validate_image(image_crop)
    full_content, full_extension = await storage_service.read_and_validate_image(image_full)

    crop_path = storage_service.build_detection_image_path(
        village_id=camera.village_id,
        camera_id=camera.id,
        image_id=car_id,
        suffix="crop",
        extension=crop_extension,
    )
    full_path = storage_service.build_detection_image_path(
        village_id=camera.village_id,
        camera_id=camera.id,
        image_id=car_id,
        suffix="full",
        extension=full_extension,
    )

    is_blacklist = await _check_is_blacklisted(
        db, camera.village_id, payload.license_plate, payload.province
    )

    written_paths: list[str] = []
    try:
        await storage_service.write_detection_image(crop_path, crop_content)
        written_paths.append(crop_path)
        await storage_service.write_detection_image(full_path, full_content)
        written_paths.append(full_path)
    except OSError:
        await _cleanup_written_images(written_paths)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store detection images",
        )

    car = Car(
        id=car_id,
        event_id=payload.event_id,
        camera_id=camera.id,
        license_plate=payload.license_plate,
        province=payload.province,
        color=payload.color,
        image_crop=crop_path,
        image_full=full_path,
        time_detect=payload.capture_time,
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

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()

        sqlstate = getattr(exc.orig, "sqlstate", None)
        if sqlstate != "23505":
            await _cleanup_written_images(written_paths)
            raise

        await _cleanup_written_images(written_paths)

        existing = await _find_existing_car_by_event_id(db, payload.event_id)
        logger.info(
            "race on duplicate detection event, returning existing record: event_id=%s",
            payload.event_id,
        )
        return DetectionCreateAck(event_id=existing.event_id), False

    await db.refresh(car)

    try:
        event_payload = _build_detection_event_payload(request, camera, car)
        event_data = event_payload.model_dump(mode="json")
        await sse_service.publish(camera.village_id, "detection_created", event_data)
        if is_blacklist:
            await sse_service.publish(camera.village_id, "blacklist_alert", event_data)

        global_payload = _build_global_detection_event_payload(request, camera, car)
        await sse_service.publish_global("detection_created", global_payload.model_dump(mode="json"))
    except Exception:
        logger.exception(
            "Failed to publish SSE event for detection_id=%s event_id=%s",
            car.id, car.event_id,
        )

    return DetectionCreateAck(event_id=car.event_id), True


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
        if village_id is not None:
            stmt = stmt.where(Camera.village_id == village_id)

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

def _today_bangkok_bounds() -> tuple[datetime, datetime, datetime]:
    now_bangkok = datetime.now(BANGKOK_TZ)
    start_of_day_bangkok = now_bangkok.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day_bangkok = start_of_day_bangkok + timedelta(days=1)
    return (
        start_of_day_bangkok,
        start_of_day_bangkok.astimezone(timezone.utc),
        end_of_day_bangkok.astimezone(timezone.utc),
    )


def _build_dashboard_scope_filters(current_user: User, village_id_filter: uuid.UUID | None) -> list:
    if current_user.role == UserRole.SUPERADMIN:
        if village_id_filter is not None:
            return [Camera.village_id == village_id_filter]
        return []
    return [Camera.village_id == current_user.village_id]


async def get_today_dashboard(
    db: AsyncSession,
    request: Request,
    current_user: User,
    village_id: uuid.UUID | None,
    latest_limit: int,
) -> DetectionDashboardRead:
    start_of_day_bangkok, start_utc, end_utc = _today_bangkok_bounds()
    scope_filters = _build_dashboard_scope_filters(current_user, village_id)
    base_filters = [Car.time_detect >= start_utc, Car.time_detect < end_utc, *scope_filters]

    total_result = await db.execute(
        select(func.count())
        .select_from(Car)
        .join(Camera, Car.camera_id == Camera.id)
        .where(*base_filters)
    )
    total_detections_today = total_result.scalar_one()

    unique_subquery = (
        select(Car.license_plate, Car.province)
        .join(Camera, Car.camera_id == Camera.id)
        .where(*base_filters)
        .distinct()
        .subquery()
    )
    unique_result = await db.execute(select(func.count()).select_from(unique_subquery))
    unique_plates_today = unique_result.scalar_one()

    blacklist_result = await db.execute(
        select(func.count())
        .select_from(Car)
        .join(Camera, Car.camera_id == Camera.id)
        .where(*base_filters, Car.is_blacklist.is_(True))
    )
    blacklist_detections_today = blacklist_result.scalar_one()

    top_repeated_result = await db.execute(
        select(Car.license_plate, Car.province, func.count())
        .join(Camera, Car.camera_id == Camera.id)
        .where(*base_filters)
        .group_by(Car.license_plate, Car.province)
        .having(func.count() > 1)
        .order_by(func.count().desc())
        .limit(10)
    )
    top_repeated_plates = [
        RepeatedPlateEntry(license_plate=plate, province=province, count=count)
        for plate, province, count in top_repeated_result.all()
    ]

    latest_result = await db.execute(
        select(Car)
        .join(Camera, Car.camera_id == Camera.id)
        .where(*base_filters)
        .order_by(Car.time_detect.desc())
        .limit(latest_limit)
    )
    latest_detections = [_to_car_read(item, request) for item in latest_result.scalars().all()]

    return DetectionDashboardRead(
        date=start_of_day_bangkok.date(),
        total_detections_today=total_detections_today,
        unique_plates_today=unique_plates_today,
        blacklist_detections_today=blacklist_detections_today,
        top_repeated_plates=top_repeated_plates,
        latest_detections=latest_detections,
    )

async def get_camera_live_view(
    db: AsyncSession,
    request: Request,
    current_user: User,
    camera_id: uuid.UUID,
    limit: int,
) -> CameraLiveRead:
    camera = await camera_service.get_camera(db, current_user, camera_id)

    result = await db.execute(
        select(Car)
        .where(Car.camera_id == camera.id)
        .order_by(Car.time_detect.desc())
        .limit(limit)
    )

    latest_captures = [
        LiveCaptureEntry(
            id=car.id,
            time_detect=car.time_detect,
            license_plate=car.license_plate,
            province=car.province,
            color=car.color,
            image_crop=str(
                request.url_for("get_detection_image", detection_id=car.id, variant="crop")
            ),
            image_full=str(
                request.url_for("get_detection_image", detection_id=car.id, variant="full")
            ),
        )
        for car in result.scalars().all()
    ]

    return CameraLiveRead(
        camera_id=camera.id,
        camera_name=camera.name,
        is_active=camera.is_active,
        stream_url=mediamtx_service.derive_stream_url(camera.id),
        latest_captures=latest_captures,
    )