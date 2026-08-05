from __future__ import annotations
import logging
import uuid
import httpx
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS = 5.0


async def push_camera_config(camera_id: uuid.UUID, stream_ai: str) -> bool:
    url = f"{settings.ai_vision_api_url.rstrip('/')}/cameras"

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                json={"camera_id": str(camera_id), "stream_ai": stream_ai},
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


async def notify_camera_deactivated(camera_id: uuid.UUID) -> bool:
    url = f"{settings.ai_vision_api_url.rstrip('/')}/cameras/{camera_id}/deactivate"

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                headers={"X-API-Key": settings.ai_vision_api_key},
            )
    except httpx.HTTPError as exc:
        logger.warning("ai vision notify_camera_deactivated request failed for %s: %s", camera_id, exc)
        return False

    if response.status_code >= 400:
        logger.warning(
            "ai vision notify_camera_deactivated rejected for %s: status=%s body=%s",
            camera_id, response.status_code, response.text,
        )
        return False

    return True


async def notify_camera_deleted(camera_id: uuid.UUID) -> bool:
    url = f"{settings.ai_vision_api_url.rstrip('/')}/cameras/{camera_id}"

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