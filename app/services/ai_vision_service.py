from __future__ import annotations
import logging
import uuid
import httpx
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS = 5.0

def derive_webhook_url() -> str:
    return f"{settings.backend_public_url.rstrip('/')}/api/detections"

async def push_camera_config(camera_id: uuid.UUID, stream_ai: str) -> bool:
    url = f"{settings.ai_vision_api_url.rstrip('/')}/partner/cameras"

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                json={
    "camera_id": str(camera_id),
    "camera_url": stream_ai,
    "webhook_url": derive_webhook_url(),
},
                headers={"X-API-Key": settings.ai_vision_api_key},
            )
    except httpx.HTTPError as exc:
        logger.warning("ai vision push_camera_config request failed for %s: %s", camera_id, exc)
        return False

    if response.status_code >= 400:
        logger.warning(
            "ai vision push_camera_config rejected for %s: status=%s body=%s",
            camera_id, response.status_code, response.text,
        )
        return False

    return True


async def set_camera_active_status(camera_id: uuid.UUID, is_active: bool) -> bool:
    url = f"{settings.ai_vision_api_url.rstrip('/')}/partner/cameras/status"

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                json={"camera_id": str(camera_id), "is_active": is_active},
                headers={"X-API-Key": settings.ai_vision_api_key},
            )
    except httpx.HTTPError as exc:
        logger.warning("ai vision set_camera_active_status request failed for %s: %s", camera_id, exc)
        return False

    if response.status_code >= 400:
        logger.warning(
            "ai vision set_camera_active_status rejected for %s: status=%s body=%s",
            camera_id, response.status_code, response.text,
        )
        return False

    return True

async def notify_camera_deleted(camera_id: uuid.UUID) -> bool:
    url = f"{settings.ai_vision_api_url.rstrip('/')}/partner/cameras/{camera_id}"

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.delete(
                url,
                headers={"X-API-Key": settings.ai_vision_api_key},
            )
    except httpx.HTTPError as exc:
        logger.warning("ai vision notify_camera_deleted request failed for %s: %s", camera_id, exc)
        return False

    if response.status_code >= 400:
        logger.warning(
            "ai vision notify_camera_deleted rejected for %s: status=%s body=%s",
            camera_id, response.status_code, response.text,
        )
        return False

    return True