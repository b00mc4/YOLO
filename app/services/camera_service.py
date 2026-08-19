from __future__ import annotations
import asyncio
import logging
import uuid
from fastapi import BackgroundTasks, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import verify_village_scope
from app.core.config import get_settings
from app.core.rate_limit import get_rate_limiter
from app.db.session import async_session_maker
from app.models.camera import Camera, CameraVerificationStatus
from app.models.car import Car
from app.models.group import Group
from app.models.user import User, UserRole
from app.schemas.camera import (
    CameraCreate,
    CameraRead,
    CameraResyncAllRead,
    CameraResyncFailedEntry,
    CameraStatusRead,
    CameraUpdate,
    CameraVerificationCheckRead,
)
from app.schemas.common import PaginatedResponse
from app.services import ai_vision_service, audit_service, camera_verification_service, mediamtx_service, notification_service
from app.services.ai_vision_service import VerificationCheckResult

settings = get_settings()
logger = logging.getLogger(__name__)

_RESYNC_CONCURRENCY_LIMIT = 10
_MANUAL_VERIFY_RATE_LIMIT = 1
_MANUAL_VERIFY_RATE_WINDOW_SECONDS = 30.0


async def _push_stream_config(camera_id: uuid.UUID, stream_ai: str) -> tuple[bool, list[str]]:
    failed_services: list[str] = []

    mediamtx_ok = await mediamtx_service.upsert_path(camera_id, stream_ai)
    if not mediamtx_ok:
        failed_services.append("mediamtx")

    ai_vision_ok = await ai_vision_service.push_camera_config(camera_id, stream_ai)
    if not ai_vision_ok:
        failed_services.append("ai_vision")

    return ai_vision_ok, failed_services

async def _sync_camera_online(camera_id: uuid.UUID, stream_ai: str) -> tuple[bool, list[str]]:
    ai_vision_pushed, failed_services = await _push_stream_config(camera_id, stream_ai)

    should_verify = False
    if ai_vision_pushed:
        active_ok = await ai_vision_service.set_camera_active_status(camera_id, True)
        if active_ok:
            should_verify = True
        else:
            failed_services.append("ai_vision")

    return should_verify, failed_services


async def _sync_camera_offline(camera_id: uuid.UUID) -> list[str]:
    failed_services: list[str] = []

    mediamtx_ok = await mediamtx_service.remove_path(camera_id)
    if not mediamtx_ok:
        failed_services.append("mediamtx")

    ai_vision_ok = await ai_vision_service.set_camera_active_status(camera_id, False)
    if not ai_vision_ok:
        failed_services.append("ai_vision")

    return failed_services

def _to_camera_read(camera: Camera) -> CameraRead:
    return CameraRead(
        id=camera.id,
        village_id=camera.village_id,
        name=camera.name,
        lat=camera.lat,
        long=camera.long,
        stream_ai=camera.stream_ai,
        stream_url=mediamtx_service.derive_stream_url(camera.id),
        webhook_url=ai_vision_service.derive_webhook_url(),
        verification_status=camera.verification_status,
        ai_vision_synced_at=camera.ai_vision_synced_at,
        created_at=camera.created_at,
        is_active=camera.is_active,
    )


async def _notify_sync_failure(
    village_id: uuid.UUID,
    camera_id: uuid.UUID,
    camera_name: str,
    failed_services: list[str],
) -> None:
    detail = (
        f"camera sync failed for '{camera_name}' (id={camera_id}): "
        f"{', '.join(failed_services)} did not accept the update"
    )
    logger.error(detail)

    async with async_session_maker() as db:
        await audit_service.log_action(
            db,
            request=None,
            action="camera_sync_failed",
            detail=detail,
            village_id=village_id,
        )
        await notification_service.notify_village(db, village_id, "camera_sync_failed", detail)
        await db.commit()

    from app.services import channel_service

    await channel_service.alerts.publish(
        village_id,
        "camera_sync_failed",
        {
            "camera_id": str(camera_id),
            "camera_name": camera_name,
            "failed_services": failed_services,
        },
    )

async def _sync_camera_create(
    camera_id: uuid.UUID,
    village_id: uuid.UUID,
    camera_name: str,
    stream_ai: str,
) -> None:
    should_verify, failed_services = await _sync_camera_online(camera_id, stream_ai)

    if should_verify:
        camera_verification_service.start_verification(camera_id)

    if failed_services:
        await _notify_sync_failure(village_id, camera_id, camera_name, list(dict.fromkeys(failed_services)))


async def _sync_camera_delete(camera_id: uuid.UUID, village_id: uuid.UUID, camera_name: str) -> None:
    mediamtx_ok, ai_vision_ok = await asyncio.gather(
        mediamtx_service.remove_path(camera_id),
        ai_vision_service.notify_camera_deleted(camera_id),
    )

    failed_services = []
    if not mediamtx_ok:
        failed_services.append("mediamtx")
    if not ai_vision_ok:
        failed_services.append("ai_vision")

    if failed_services:
        await _notify_sync_failure(village_id, camera_id, camera_name, failed_services)


async def _sync_camera_update(
    camera_id: uuid.UUID,
    village_id: uuid.UUID,
    camera_name: str,
    stream_ai: str | None,
    is_active: bool | None,
) -> None:
    failed_services: list[str] = []
    should_verify = False

    if stream_ai is not None:
        ai_vision_pushed, stream_failed = await _push_stream_config(camera_id, stream_ai)
        failed_services.extend(stream_failed)
        if ai_vision_pushed:
            should_verify = True

    if is_active is not None:
        status_ok = await ai_vision_service.set_camera_active_status(camera_id, is_active)
        if not status_ok:
            failed_services.append("ai_vision")

    if should_verify:
        camera_verification_service.start_verification(camera_id)

    if failed_services:
        await _notify_sync_failure(village_id, camera_id, camera_name, list(dict.fromkeys(failed_services)))


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
    village = await _get_village_or_404(db, village_id)

    camera = Camera(
        village_id=village_id,
        name=payload.name,
        lat=payload.lat,
        long=payload.long,
        stream_ai=payload.stream_ai,
        is_active=True,
        verification_status=CameraVerificationStatus.PENDING,
    )
    db.add(camera)
    await db.flush()

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

    if village.is_active:
        background_tasks.add_task(
            _sync_camera_create, camera.id, camera.village_id, camera.name, camera.stream_ai
        )
    else:
        logger.info(
            "Skipping camera sync for %s: village %s is inactive", camera.id, village_id
        )

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

async def get_camera_status(db: AsyncSession, current_user: User, camera_id: uuid.UUID) -> CameraStatusRead:
    camera = await get_camera(db, current_user, camera_id)
    stream_online = await mediamtx_service.get_path_status(camera.id)

    return CameraStatusRead(
        id=camera.id,
        is_active=camera.is_active,
        verification_status=camera.verification_status,
        stream_online=stream_online,
    )

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

    if current_user.role == UserRole.SUPERADMIN:
        if village_id_filter is not None:
            stmt = stmt.where(Camera.village_id == village_id_filter)
            count_stmt = count_stmt.where(Camera.village_id == village_id_filter)
    else:
        if village_id_filter is not None and village_id_filter != current_user.village_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to specify village_id for this role",
            )
        stmt = stmt.where(Camera.village_id == current_user.village_id)
        count_stmt = count_stmt.where(Camera.village_id == current_user.village_id)

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
    village = await _get_village_or_404(db, camera.village_id)

    update_data = payload.model_dump(exclude_unset=True)
    stream_ai_changed = "stream_ai" in update_data and update_data["stream_ai"] != camera.stream_ai
    is_active_changed = "is_active" in update_data and update_data["is_active"] != camera.is_active

    for field, value in update_data.items():
        setattr(camera, field, value)

    if stream_ai_changed:
        camera.verification_status = CameraVerificationStatus.PENDING

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

    if (stream_ai_changed or is_active_changed) and village.is_active:
        background_tasks.add_task(
            _sync_camera_update,
            camera.id,
            camera.village_id,
            camera.name,
            camera.stream_ai if stream_ai_changed else None,
            camera.is_active if is_active_changed else None,
        )
    elif stream_ai_changed or is_active_changed:
        logger.info(
            "Skipping camera sync for %s: village %s is inactive", camera.id, camera.village_id
        )

    return _to_camera_read(camera)

async def delete_camera(
    db: AsyncSession,
    request: Request,
    background_tasks: BackgroundTasks,
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

    if camera.ai_vision_synced_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Camera is already linked with the AI vision service and cannot be deleted. "
                "Deactivate it instead."
            ),
        )

    camera_id_value = camera.id
    village_id = camera.village_id
    camera_name = camera.name

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

    camera_verification_service.cancel_verification(camera_id_value)
    background_tasks.add_task(_sync_camera_delete, camera_id_value, village_id, camera_name)


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
) -> tuple[Camera, bool]:
    async with semaphore:
        ok = await mediamtx_service.upsert_path(camera.id, camera.stream_ai)
        return camera, ok


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
        for camera, ok in outcomes
        if not ok
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
) -> CameraRead:
    camera = await get_camera(db, current_user, camera_id)

    pushed = await ai_vision_service.push_camera_config(camera.id, camera.stream_ai)
    if not pushed:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to sync camera with ai vision service",
        )

    active_ok = await ai_vision_service.set_camera_active_status(camera.id, True)
    if not active_ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to sync camera with ai vision service",
        )

    camera.verification_status = CameraVerificationStatus.PENDING

    await audit_service.log_action(
        db,
        request,
        action="camera_resync_ai_vision",
        detail=f"triggered re-verification with ai vision service: {camera.name}",
        user_id=current_user.id,
        village_id=camera.village_id,
    )

    await db.commit()
    await db.refresh(camera)

    camera_verification_service.start_verification(camera.id)

    return _to_camera_read(camera)


async def check_camera_verification_now(
    db: AsyncSession,
    request: Request,
    current_user: User,
    camera_id: uuid.UUID,
) -> CameraVerificationCheckRead:
    camera = await get_camera(db, current_user, camera_id)

    get_rate_limiter().check(
        f"manual_verify_check:{camera_id}",
        _MANUAL_VERIFY_RATE_LIMIT,
        _MANUAL_VERIFY_RATE_WINDOW_SECONDS,
    )

    result = await ai_vision_service.check_camera_verification(camera.id)
    ai_vision_reachable = result != VerificationCheckResult.UNREACHABLE
    is_pending_locally = camera.verification_status == CameraVerificationStatus.PENDING

    polling_restarted = False
    anomaly_detected = False
    note: str | None = None

    if result == VerificationCheckResult.UNREACHABLE:
        note = "ไม่สามารถติดต่อ ai vision service ได้ในขณะนี้ กรุณาลองใหม่ภายหลัง"

    elif result == VerificationCheckResult.PENDING:
        if not camera_verification_service.is_verification_running(camera.id):
            camera_verification_service.start_verification(camera.id)
            polling_restarted = True

    elif result == VerificationCheckResult.VERIFIED:
        if is_pending_locally:
            await camera_verification_service.finalize_verification(
                camera.id,
                verified=True,
                reason="verified by ai vision service",
                request=request,
                user_id=current_user.id,
            )
            await db.refresh(camera)
        elif camera.verification_status == CameraVerificationStatus.FAILED:
            anomaly_detected = True
            note = (
                f"ai vision service รายงานว่ากล้อง '{camera.name}' verified แล้ว แต่ในระบบเราบันทึกสถานะเป็น "
                "failed อยู่ ระบบไม่ได้แก้สถานะให้อัตโนมัติ กรุณาใช้ resync-ai-vision หากต้องการยืนยันซ้ำ"
            )

    elif result == VerificationCheckResult.NOT_FOUND:
        if is_pending_locally:
            await camera_verification_service.finalize_verification(
                camera.id,
                verified=False,
                reason="ai vision service exceeded its verification retry quota and removed the camera",
                request=request,
                user_id=current_user.id,
            )
            await db.refresh(camera)
        elif camera.verification_status == CameraVerificationStatus.VERIFIED:
            anomaly_detected = True
            note = (
                f"ai vision service ไม่พบกล้อง '{camera.name}' แล้ว (อาจถูกลบฝั่งเขา) แต่ในระบบเรายังบันทึกสถานะ"
                f" เป็น verified และ is_active={camera.is_active} อยู่ ระบบไม่ได้ปิดกล้องอัตโนมัติเพื่อป้องกัน "
                "false negative กรุณาตรวจสอบด้วยตนเองก่อนตัดสินใจ"
            )

    if anomaly_detected:
        await audit_service.log_action(
            db,
            request,
            action="camera_verification_anomaly",
            detail=(
                f"anomaly on manual verification check for '{camera.name}': ai vision reports "
                f"{result.value} but local status is {camera.verification_status.value} "
                f"(is_active={camera.is_active}); no changes applied"
            ),
            user_id=current_user.id,
            village_id=camera.village_id,
        )
        await db.commit()

    return CameraVerificationCheckRead(
        id=camera.id,
        verification_status=camera.verification_status,
        is_active=camera.is_active,
        ai_vision_synced_at=camera.ai_vision_synced_at,
        ai_vision_reachable=ai_vision_reachable,
        polling_restarted=polling_restarted,
        anomaly_detected=anomaly_detected,
        note=note,
    )


async def _deactivate_camera_guarded(
    semaphore: asyncio.Semaphore, camera: Camera
) -> tuple[Camera, list[str]]:
    async with semaphore:
        failed_services = await _sync_camera_offline(camera.id)
        return camera, failed_services

async def deactivate_village_cameras(village_id: uuid.UUID) -> None:
    """
    Village ถูกปิดใช้งาน (is_active: true -> false) ตัด mediamtx path และปิดสถานะ
    active ฝั่ง ai_vision ของทุกกล้องที่ยัง is_active อยู่ในหมู่บ้านนี้ เพื่อไม่ให้สตรีม
    หรือการรับ detection ยังเปิดค้างต่อได้หลัง village ถูกปิดแล้ว
    """
    async with async_session_maker() as db:
        result = await db.execute(
            select(Camera).where(Camera.village_id == village_id, Camera.is_active.is_(True))
        )
        cameras = list(result.scalars().all())
 
    if not cameras:
        return
 
    semaphore = asyncio.Semaphore(_RESYNC_CONCURRENCY_LIMIT)
    outcomes = await asyncio.gather(
        *(_deactivate_camera_guarded(semaphore, camera) for camera in cameras)
    )
 
    for camera, failed_services in outcomes:
        if failed_services:
            await _notify_sync_failure(village_id, camera.id, camera.name, list(dict.fromkeys(failed_services)))

async def _activate_camera_guarded(
    semaphore: asyncio.Semaphore, camera: Camera
) -> tuple[Camera, bool, list[str]]:
    async with semaphore:
        should_verify, failed_services = await _sync_camera_online(camera.id, camera.stream_ai)
        return camera, should_verify, failed_services


async def activate_village_cameras(village_id: uuid.UUID) -> None:
    """
    Village ถูกเปิดใช้งานกลับมา (is_active: false -> true) resync mediamtx path
    และ ai_vision config ของทุกกล้องที่ is_active อยู่ในหมู่บ้านนี้ ให้กลับมาใช้งานได้
    เหมือนเดิม โดยไม่ต้องรอ admin สั่ง resync-all เอง เพราะ re-POST ไปหา ai_vision
    ใหม่ ทุกตัวจะถูก reset เป็น pending แล้วเข้า verify loop เหมือนสร้างกล้องใหม่
    """
    async with async_session_maker() as db:
        result = await db.execute(
            select(Camera).where(Camera.village_id == village_id, Camera.is_active.is_(True))
        )
        cameras = list(result.scalars().all())
 
    if not cameras:
        return
 
    semaphore = asyncio.Semaphore(_RESYNC_CONCURRENCY_LIMIT)
    outcomes = await asyncio.gather(
        *(_activate_camera_guarded(semaphore, camera) for camera in cameras)
    )
 
    verifying_camera_ids = [camera.id for camera, should_verify, _ in outcomes if should_verify]
    if verifying_camera_ids:
        async with async_session_maker() as db:
            result = await db.execute(select(Camera).where(Camera.id.in_(verifying_camera_ids)))
            for db_camera in result.scalars().all():
                db_camera.verification_status = CameraVerificationStatus.PENDING
            await db.commit()
        for camera_id in verifying_camera_ids:
            camera_verification_service.start_verification(camera_id)
 
    for camera, _, failed_services in outcomes:
        if failed_services:
            await _notify_sync_failure(village_id, camera.id, camera.name, list(dict.fromkeys(failed_services)))