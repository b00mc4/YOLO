from __future__ import annotations
import logging
import uuid
import httpx
from fastapi import HTTPException, status
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS = 5.0


def _auth() -> httpx.BasicAuth:
    return httpx.BasicAuth(settings.mediamtx_api_user, settings.mediamtx_api_password)


def _path_name(camera_id: uuid.UUID) -> str:
    return str(camera_id)


def derive_stream_url(camera_id: uuid.UUID) -> str:
    return f"{settings.mediamtx_public_url.rstrip('/')}/{camera_id}/index.m3u8"


async def upsert_path(camera_id: uuid.UUID, source_rtsp_url: str) -> None:
    path_name = _path_name(camera_id)
    url = f"{settings.mediamtx_api_url.rstrip('/')}/v3/config/paths/replace/{path_name}"

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                json={"source": source_rtsp_url, "sourceOnDemand": True},
                auth=_auth(),
            )
    except httpx.HTTPError as exc:
        logger.error("MediaMTX upsert_path request failed for %s: %s", camera_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to sync camera stream with MediaMTX",
        )

    if response.status_code >= 400:
        logger.error(
            "MediaMTX upsert_path rejected for %s: status=%s body=%s",
            camera_id, response.status_code, response.text,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="MediaMTX rejected the camera stream configuration",
        )


async def remove_path(camera_id: uuid.UUID) -> None:
    path_name = _path_name(camera_id)
    url = f"{settings.mediamtx_api_url.rstrip('/')}/v3/config/paths/delete/{path_name}"

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.delete(url, auth=_auth())
    except httpx.HTTPError as exc:
        logger.error("MediaMTX remove_path request failed for %s: %s", camera_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to remove camera stream from MediaMTX",
        )


    if response.status_code >= 400 and response.status_code != status.HTTP_404_NOT_FOUND:
        logger.error(
            "MediaMTX remove_path unexpected status for %s: status=%s body=%s",
            camera_id, response.status_code, response.text,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="MediaMTX rejected the camera stream removal",
        )