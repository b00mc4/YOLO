from __future__ import annotations
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import BackgroundTasks, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import verify_village_scope
from app.core.config import get_settings
from app.db.session import async_session_maker
from app.models.camera import Camera
from app.models.car import Car
from app.models.group import Group
from app.models.user import User, UserRole
from app.schemas.camera import (
    CameraCreate,
    CameraRead,
    CameraResyncAllRead,
    CameraResyncFailedEntry,
    CameraResyncRead,
    CameraUpdate,
)
from app.schemas.common import PaginatedResponse
from app.services import ai_vision_service, audit_service, mediamtx_service

settings = get_settings()
logger = logging.getLogger(__name__)

_RESYNC_CONCURRENCY_LIMIT = 10


def _to_camera_read(camera: Camera) -> CameraRead:
    return CameraRead(
        id=camera.id,
        village_id=camera.village_id,
        name=camera.name,
        lat=camera.lat,
        long=camera.long,
        stream_ai=camera.stream_ai,
        stream_url=mediamtx_service.derive_stream_url(camera.id),
        ai_vision_synced_at=camera.ai_vision_synced_at,
        created_at=camera.created_at,
        is_active=camera.is_active,
    )


async def _push_ai_vision_config(camera_id: uuid.UUID, stream_ai: str) -> None:
    synced = await ai_vision_service.push_camera_config(camera_id, stream_ai)
    if not synced:
        return

    async with async_session_maker() as db:
        result = await db.execute(select(Camera).where(Camera.id == camera_id))
        camera = result.scalar_one_or_none()
        if camera is None:
            return
        camera.ai_vision_synced_at = datetime.now(timezone.utc)
        await db.commit()


async def _get_village_or_404(db: AsyncSession, village_id: uuid.UUID) -> Group:
    result = await db.execute(select(Group).where(Group.id == village_id))
    village = result.scalar_one_or_none()
    if village is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Village not found")
    return village

async def create_camera(
    db: AsyncSession,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User,
    payload: CameraCreate,
) -> CameraRead:
    if current_user.role == UserRole.ADMIN:
        village_id = current_user.village_id
    else:
        village_id = payload.village_id
        await _get_village_or_404(db, village_id)

    camera = Camera(
        village_id=village_id,
        name=payload.name,
        lat=payload.lat,
        long=payload.long,
        stream_ai=payload.stream_ai,
        is_active=True,
    )
    db.add(camera)
    await db.flush()

    await mediamtx_service.upsert_path(camera.id, camera.stream_ai)

    await audit_service.log_action(
        db,
        request,
        action="camera_created",
        detail=f"camera created: {camera.name}",
        user_id=current_user.id,
        village_id=village_id,
    )
    await db.commit()
    await db.refresh(camera)

    background_tasks.add_task(_push_ai_vision_config, camera.id, camera.stream_ai)

    return _to_camera_read(camera)

async def get_camera(db: AsyncSession, current_user: User, camera_id: uuid.UUID) -> Camera:
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()

    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    verify_village_scope(current_user, camera.village_id)
    return camera

async def get_camera_detail(db: AsyncSession, current_user: User, camera_id: uuid.UUID) -> CameraRead:
    camera = await get_camera(db, current_user, camera_id)
    return _to_camera_read(camera)

async def list_cameras(
    db: AsyncSession,
    current_user: User,
    village_id_filter: uuid.UUID | None,
    is_active_filter: bool | None,
    page: int,
    page_size: int,
) -> PaginatedResponse[CameraRead]:
    stmt = select(Camera)
    count_stmt = select(func.count()).select_from(Camera)

    if current_user.role == UserRole.ADMIN:
        stmt = stmt.where(Camera.village_id == current_user.village_id)
        count_stmt = count_stmt.where(Camera.village_id == current_user.village_id)
    elif village_id_filter is not None:
        stmt = stmt.where(Camera.village_id == village_id_filter)
        count_stmt = count_stmt.where(Camera.village_id == village_id_filter)

    if is_active_filter is not None:
        stmt = stmt.where(Camera.is_active == is_active_filter)
        count_stmt = count_stmt.where(Camera.is_active == is_active_filter)

    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    stmt = stmt.order_by(Camera.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return PaginatedResponse(
        items=[_to_camera_read(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )

async def update_camera(
    db: AsyncSession,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User,
    camera_id: uuid.UUID,
    payload: CameraUpdate,
) -> CameraRead:
    camera = await get_camera(db, current_user, camera_id)

    update_data = payload.model_dump(exclude_unset=True)
    stream_ai_changed = "stream_ai" in update_data and update_data["stream_ai"] != camera.stream_ai
    is_active_changed = "is_active" in update_data and update_data["is_active"] != camera.is_active

    if stream_ai_changed:
        await mediamtx_service.upsert_path(camera.id, update_data["stream_ai"])

    if is_active_changed:
        synced = await ai_vision_service.set_camera_active_status(camera.id, update_data["is_active"])
        if not synced:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to sync camera status with ai vision service",
            )

    for field, value in update_data.items():
        setattr(camera, field, value)

    if is_active_changed:
        if update_data["is_active"]:
            action = "camera_activated"
            detail = f"camera activated: {camera.name}"
        else:
            action = "camera_deactivated"
            detail = f"camera deactivated: {camera.name}"
    else:
        action = "camera_updated"
        detail = f"camera updated: {camera.name}"

    await audit_service.log_action(
        db,
        request,
        action=action,
        detail=detail,
        user_id=current_user.id,
        village_id=camera.village_id,
    )
    await db.commit()
    await db.refresh(camera)

    if stream_ai_changed:
        background_tasks.add_task(_push_ai_vision_config, camera.id, camera.stream_ai)

    return _to_camera_read(camera)

async def delete_camera(
    db: AsyncSession,
    request: Request,
    current_user: User,
    camera_id: uuid.UUID,
) -> None:
    camera = await get_camera(db, current_user, camera_id)

    detection_count_result = await db.execute(
        select(func.count()).select_from(Car).where(Car.camera_id == camera_id)
    )
    if detection_count_result.scalar_one() > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Camera has detection records and cannot be deleted. "
                "Deactivate it instead."
            ),
        )

    await mediamtx_service.remove_path(camera.id)
    await ai_vision_service.notify_camera_deleted(camera.id)

    await audit_service.log_action(
        db,
        request,
        action="camera_deleted",
        detail=f"camera deleted: {camera.name}",
        user_id=current_user.id,
        village_id=camera.village_id,
    )

    await db.delete(camera)
    await db.commit()

async def resync_camera(
    db: AsyncSession,
    current_user: User,
    camera_id: uuid.UUID,
) -> CameraResyncRead:
    camera = await get_camera(db, current_user, camera_id)

    synced = await ai_vision_service.push_camera_config(camera.id, camera.stream_ai)
    if not synced:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to sync camera with ai vision service",
        )

    camera.ai_vision_synced_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(camera)

    return CameraResyncRead(id=camera.id, ai_vision_synced_at=camera.ai_vision_synced_at)


def _build_resync_scope_filters(
    current_user: User, village_id_filter: uuid.UUID | None
) -> list:
    if current_user.role == UserRole.SUPERADMIN:
        if village_id_filter is not None:
            return [Camera.village_id == village_id_filter]
        return []

    if village_id_filter is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to specify village_id for this role",
        )
    return [Camera.village_id == current_user.village_id]


async def _upsert_path_guarded(
    semaphore: asyncio.Semaphore, camera: Camera
) -> tuple[Camera, Exception | None]:
    async with semaphore:
        try:
            await mediamtx_service.upsert_path(camera.id, camera.stream_ai)
        except Exception as exc:
            return camera, exc
        return camera, None


async def _resync_cameras(db: AsyncSession, scope_filters: list) -> CameraResyncAllRead:
    result = await db.execute(
        select(Camera)
        .join(Group, Camera.village_id == Group.id)
        .where(Camera.is_active.is_(True), Group.is_active.is_(True), *scope_filters)
    )
    cameras = list(result.scalars().all())

    semaphore = asyncio.Semaphore(_RESYNC_CONCURRENCY_LIMIT)
    outcomes = await asyncio.gather(
        *(_upsert_path_guarded(semaphore, camera) for camera in cameras)
    )

    failed_cameras = [
        CameraResyncFailedEntry(id=camera.id, name=camera.name)
        for camera, error in outcomes
        if error is not None
    ]

    return CameraResyncAllRead(
        total=len(cameras),
        succeeded=len(cameras) - len(failed_cameras),
        failed=len(failed_cameras),
        failed_cameras=failed_cameras,
    )


async def resync_all_cameras(
    db: AsyncSession,
    request: Request,
    current_user: User,
    village_id_filter: uuid.UUID | None,
) -> CameraResyncAllRead:
    scope_filters = _build_resync_scope_filters(current_user, village_id_filter)

    if village_id_filter is not None:
        await _get_village_or_404(db, village_id_filter)

    resync_result = await _resync_cameras(db, scope_filters)

    await audit_service.log_action(
        db,
        request,
        action="camera_resync_all",
        detail=(
            f"resynced {resync_result.total} camera(s) with MediaMTX: "
            f"{resync_result.succeeded} succeeded, {resync_result.failed} failed"
        ),
        user_id=current_user.id,
        village_id=village_id_filter,
    )
    await db.commit()

    return resync_result


async def resync_all_cameras_on_startup(db: AsyncSession) -> CameraResyncAllRead:
    resync_result = await _resync_cameras(db, scope_filters=[])
    logger.info(
        "Startup camera resync completed: total=%s succeeded=%s failed=%s",
        resync_result.total,
        resync_result.succeeded,
        resync_result.failed,
    )
    return resync_result

async def resync_camera_ai_vision(
    db: AsyncSession,
    request: Request,
    current_user: User,
    camera_id: uuid.UUID,
) -> CameraResyncRead:
    camera = await get_camera(db, current_user, camera_id)

    synced = await ai_vision_service.push_camera_config(camera.id, camera.stream_ai)
    if not synced:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to sync camera with ai vision service",
        )

    camera.ai_vision_synced_at = datetime.now(timezone.utc)

    await audit_service.log_action(
        db,
        request,
        action="camera_resync_ai_vision",
        detail=f"resynced camera with ai vision service: {camera.name}",
        user_id=current_user.id,
        village_id=camera.village_id,
    )

    await db.commit()
    await db.refresh(camera)

    return CameraResyncRead(id=camera.id, ai_vision_synced_at=camera.ai_vision_synced_at)