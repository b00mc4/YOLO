from __future__ import annotations
import logging
import uuid
from app.db.session import async_session_maker
from app.services import ai_vision_service, audit_service, mediamtx_service, notification_service

logger = logging.getLogger(__name__)


async def push_stream_config(camera_id: uuid.UUID, stream_ai: str) -> tuple[bool, list[str]]:
    failed_services: list[str] = []

    mediamtx_ok = await mediamtx_service.upsert_path(camera_id, stream_ai)
    if not mediamtx_ok:
        failed_services.append("mediamtx")

    ai_vision_ok = await ai_vision_service.push_camera_config(camera_id, stream_ai)
    if not ai_vision_ok:
        failed_services.append("ai_vision")

    return ai_vision_ok, failed_services


async def sync_camera_online(camera_id: uuid.UUID, stream_ai: str) -> list[str]:
    failed_services: list[str] = []

    mediamtx_ok = await mediamtx_service.upsert_path(camera_id, stream_ai)
    if not mediamtx_ok:
        failed_services.append("mediamtx")

    ai_vision_ok = await ai_vision_service.set_camera_active_status(camera_id, True)
    if not ai_vision_ok:
        failed_services.append("ai_vision")

    return failed_services


async def sync_camera_offline(camera_id: uuid.UUID) -> list[str]:
    failed_services: list[str] = []

    mediamtx_ok = await mediamtx_service.remove_path(camera_id)
    if not mediamtx_ok:
        failed_services.append("mediamtx")

    ai_vision_ok = await ai_vision_service.set_camera_active_status(camera_id, False)
    if not ai_vision_ok:
        failed_services.append("ai_vision")

    return failed_services


async def notify_sync_failure(
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