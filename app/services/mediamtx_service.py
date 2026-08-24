from __future__ import annotations
import logging
import uuid
import httpx
from app.core.config import get_settings
from app.services import mediamtx_auth_service

settings = get_settings()
logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS = 5.0
_PROBE_TIMEOUT_SECONDS = 5.0

def _auth() -> httpx.BasicAuth:
    return httpx.BasicAuth(settings.mediamtx_api_user, settings.mediamtx_api_password)


def _path_name(camera_id: uuid.UUID) -> str:
    return str(camera_id)


def derive_stream_url(camera_id: uuid.UUID) -> str:
    token = mediamtx_auth_service.issue_stream_token(camera_id)
    return f"{settings.mediamtx_public_url.rstrip('/')}/{camera_id}/index.m3u8?jwt={token}"


async def upsert_path(camera_id: uuid.UUID, source_rtsp_url: str) -> bool:
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
        return False

    if response.status_code >= 400:
        logger.error(
            "MediaMTX upsert_path rejected for %s: status=%s body=%s",
            camera_id, response.status_code, response.text,
        )
        return False

    return True


async def remove_path(camera_id: uuid.UUID) -> bool:
    path_name = _path_name(camera_id)
    url = f"{settings.mediamtx_api_url.rstrip('/')}/v3/config/paths/delete/{path_name}"

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.delete(url, auth=_auth())
    except httpx.HTTPError as exc:
        logger.error("MediaMTX remove_path request failed for %s: %s", camera_id, exc)
        return False

    if response.status_code >= 400 and response.status_code != 404:
        logger.error(
            "MediaMTX remove_path unexpected status for %s: status=%s body=%s",
            camera_id, response.status_code, response.text,
        )
        return False

    return True

async def check_source_alive(camera_id: uuid.UUID) -> bool:
    path_name = _path_name(camera_id)
    url = f"{settings.mediamtx_api_url.rstrip('/')}/v3/paths/get/{path_name}"

    response = None
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(url, auth=_auth())
    except httpx.HTTPError as exc:
        logger.warning("MediaMTX check_source_alive path lookup failed for %s: %s", camera_id, exc)

    if response is not None and response.status_code < 400:
        body = response.json()
        if bool(body.get("ready", False)):
            return True

    token = mediamtx_auth_service.issue_stream_token(camera_id)
    playlist_url = f"{settings.mediamtx_public_url.rstrip('/')}/{camera_id}/index.m3u8?jwt={token}"

    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_SECONDS) as client:
            probe_response = await client.get(playlist_url)
    except httpx.HTTPError as exc:
        logger.warning("MediaMTX check_source_alive probe failed for %s: %s", camera_id, exc)
        return False

    return probe_response.status_code < 400