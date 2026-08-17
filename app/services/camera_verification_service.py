from __future__ import annotations
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from time import monotonic
from fastapi import Request
from sqlalchemy import select
from app.db.session import async_session_maker
from app.models.camera import Camera, CameraVerificationStatus
from app.services import ai_vision_service, audit_service
from app.services.ai_vision_service import VerificationCheckResult

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 60.0
_MAX_VERIFY_DURATION_SECONDS = 5 * 60.0

_verification_tasks: dict[uuid.UUID, asyncio.Task] = {}


def start_verification(camera_id: uuid.UUID) -> None:
    existing_task = _verification_tasks.get(camera_id)
    if existing_task is not None and not existing_task.done():
        existing_task.cancel()

    task = asyncio.create_task(_run_verification_loop(camera_id))
    _verification_tasks[camera_id] = task


def cancel_verification(camera_id: uuid.UUID) -> None:
    task = _verification_tasks.pop(camera_id, None)
    if task is not None and not task.done():
        task.cancel()


def is_verification_running(camera_id: uuid.UUID) -> bool:
    task = _verification_tasks.get(camera_id)
    return task is not None and not task.done()


async def _run_verification_loop(camera_id: uuid.UUID) -> None:
    """
    Poll AI vision ทุก 1 นาทีจนกว่าจะได้ verified หรือ not_found (404)
    ถ้าเกิน 5 นาทีไม่ได้ผลชัดเจน ตัดสินเป็น failed เอง (timeout ฝั่งเรา)
    เน็ตเราเองมีปัญหาตอน poll ไม่ถือเป็น not_found เด็ดขาด แค่รอรอบถัดไป
    """
    deadline = monotonic() + _MAX_VERIFY_DURATION_SECONDS

    try:
        while True:
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

            result = await ai_vision_service.check_camera_verification(camera_id)

            if result == VerificationCheckResult.VERIFIED:
                await _finalize(camera_id, verified=True, reason="verified by ai vision service")
                return

            if result == VerificationCheckResult.NOT_FOUND:
                await _finalize(
                    camera_id,
                    verified=False,
                    reason="ai vision service exceeded its verification retry quota and removed the camera",
                )
                return

            if monotonic() >= deadline:
                await _finalize(
                    camera_id,
                    verified=False,
                    reason="timed out waiting for ai vision service to confirm verification",
                )
                return
    except asyncio.CancelledError:
        raise
    finally:
        _verification_tasks.pop(camera_id, None)


async def _finalize(
    camera_id: uuid.UUID,
    verified: bool,
    reason: str,
    request: Request | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    async with async_session_maker() as db:
        result = await db.execute(select(Camera).where(Camera.id == camera_id))
        camera = result.scalar_one_or_none()
        if camera is None:
            return

        if verified:
            camera.verification_status = CameraVerificationStatus.VERIFIED
            camera.ai_vision_synced_at = datetime.now(timezone.utc)
            action = "camera_verified"
            detail = f"camera verified: {camera.name}"
        else:
            camera.verification_status = CameraVerificationStatus.FAILED
            camera.is_active = False
            action = "camera_verification_failed"
            detail = f"camera verification failed for '{camera.name}': {reason}"

        if user_id is not None:
            detail = f"{detail} (manual check)"

        await audit_service.log_action(
            db,
            request,
            action=action,
            detail=detail,
            user_id=user_id,
            village_id=camera.village_id,
        )
        await db.commit()

        village_id = camera.village_id
        camera_id_value = camera.id
        camera_name = camera.name
        is_active = camera.is_active
        verification_status = camera.verification_status

    from app.services import sse_service

    event = "camera_verified" if verified else "camera_verification_failed"
    payload = {
        "camera_id": str(camera_id_value),
        "camera_name": camera_name,
        "verification_status": verification_status.value,
        "is_active": is_active,
    }
    await sse_service.publish(village_id, event, payload)
    await sse_service.publish_global(event, {**payload, "village_id": str(village_id)})


async def finalize_verification(
    camera_id: uuid.UUID,
    verified: bool,
    reason: str,
    request: Request | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    await _finalize(camera_id, verified=verified, reason=reason, request=request, user_id=user_id)


async def resume_pending_verifications() -> None:
    async with async_session_maker() as db:
        result = await db.execute(
            select(Camera.id).where(Camera.verification_status == CameraVerificationStatus.PENDING)
        )
        camera_ids = list(result.scalars().all())

    for camera_id in camera_ids:
        start_verification(camera_id)

    if camera_ids:
        logger.info("Resumed camera verification polling for %s camera(s)", len(camera_ids))