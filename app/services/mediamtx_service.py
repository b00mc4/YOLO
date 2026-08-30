from __future__ import annotations
import asyncio
import logging
import uuid
import httpx
from app.core.config import get_settings
from app.services import mediamtx_auth_service

settings = get_settings()
logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS = 5.0
_TRIGGER_PULL_TIMEOUT_SECONDS = 3.0

_client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS)


async def close() -> None:
    await _client.aclose()


_SOURCE_ON_DEMAND_START_TIMEOUT_SECONDS = 10.0
_COLD_START_POLL_INTERVAL_SECONDS = 1.0
_COLD_START_POLL_BUFFER_SECONDS = 2.0
_COLD_START_MAX_WAIT_SECONDS = _SOURCE_ON_DEMAND_START_TIMEOUT_SECONDS + _COLD_START_POLL_BUFFER_SECONDS
_BYTES_CONFIRM_WINDOW_SECONDS = 2.0


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
        response = await _client.post(
            url,
            json={
                "source": source_rtsp_url,
                "sourceOnDemand": True,
                "sourceOnDemandStartTimeout": f"{int(_SOURCE_ON_DEMAND_START_TIMEOUT_SECONDS)}s",
            },
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
        response = await _client.delete(url, auth=_auth())
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


async def _get_path_info(camera_id: uuid.UUID) -> dict | None:
    path_name = _path_name(camera_id)
    url = f"{settings.mediamtx_api_url.rstrip('/')}/v3/paths/get/{path_name}"

    try:
        response = await _client.get(url, auth=_auth())
    except httpx.HTTPError as exc:
        logger.warning("MediaMTX get_path_info request failed for %s: %s", camera_id, exc)
        return None

    if response.status_code == 404:
        return {"exists": False}

    if response.status_code >= 400:
        logger.warning(
            "MediaMTX get_path_info unexpected status for %s: status=%s body=%s",
            camera_id, response.status_code, response.text,
        )
        return None

    body = response.json()
    return {
        "exists": True,
        "ready": bool(body.get("ready", False)),
        "bytes_received": int(body.get("bytesReceived", 0)),
    }


async def _trigger_on_demand_pull(camera_id: uuid.UUID) -> None:
    token = mediamtx_auth_service.issue_stream_token(camera_id)
    playlist_url = f"{settings.mediamtx_public_url.rstrip('/')}/{camera_id}/index.m3u8?jwt={token}"

    try:
        await _client.get(playlist_url, timeout=_TRIGGER_PULL_TIMEOUT_SECONDS)
    except httpx.HTTPError:
        pass


async def _wait_for_ready_after_trigger(camera_id: uuid.UUID) -> bool:
    await _trigger_on_demand_pull(camera_id)

    elapsed = 0.0
    while elapsed < _COLD_START_MAX_WAIT_SECONDS:
        await asyncio.sleep(_COLD_START_POLL_INTERVAL_SECONDS)
        elapsed += _COLD_START_POLL_INTERVAL_SECONDS

        info = await _get_path_info(camera_id)
        if info is not None and info.get("exists") and info.get("ready"):
            return True

    return False


async def _confirm_bytes_flowing(camera_id: uuid.UUID, baseline_bytes: int) -> bool:
    await asyncio.sleep(_BYTES_CONFIRM_WINDOW_SECONDS)

    info = await _get_path_info(camera_id)
    if info is None or not info.get("exists"):
        return False

    return info["bytes_received"] > baseline_bytes


async def check_source_alive(camera_id: uuid.UUID) -> bool | None:
    baseline = await _get_path_info(camera_id)

    if baseline is None:
        return None

    if not baseline.get("exists"):
        logger.warning("MediaMTX path missing for camera_id=%s during status check", camera_id)
        return False

    if baseline["ready"]:
        return await _confirm_bytes_flowing(camera_id, baseline["bytes_received"])

    became_ready = await _wait_for_ready_after_trigger(camera_id)
    if not became_ready:
        return False

    post_trigger_info = await _get_path_info(camera_id)
    if post_trigger_info is None or not post_trigger_info.get("exists"):
        return False

    return await _confirm_bytes_flowing(camera_id, post_trigger_info["bytes_received"])