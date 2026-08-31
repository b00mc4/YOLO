from __future__ import annotations
import asyncio
import logging
from fastapi import HTTPException, status
from onvif import ONVIFCamera
from yarl import URL
from zeep.exceptions import Fault, TransportError
from app.core.error_messages import OnvifErrors

logger = logging.getLogger(__name__)

_PROBE_TIMEOUT_SECONDS = 15.0
_STREAM_SETUP = {
    "Stream": "RTP-Unicast",
    "Transport": {"Protocol": "RTSP"},
}


async def _fetch_device_info(camera: ONVIFCamera) -> tuple[str | None, str | None]:
    try:
        device_info = await camera.devicemgmt.GetDeviceInformation()
    except Exception:
        return None, None
    return getattr(device_info, "Manufacturer", None), getattr(device_info, "Model", None)


async def _fetch_stream_uri(media_service, profile_token: str) -> str:
    request = media_service.create_type("GetStreamUri")
    request.ProfileToken = profile_token
    request.StreamSetup = _STREAM_SETUP
    response = await media_service.GetStreamUri(request)
    return response.Uri


def _build_profile_entry(profile, rtsp_uri: str) -> dict:
    video_encoder = getattr(profile, "VideoEncoderConfiguration", None)
    resolution = getattr(video_encoder, "Resolution", None) if video_encoder else None

    return {
        "profile_token": profile.token,
        "name": profile.Name,
        "encoding": getattr(video_encoder, "Encoding", None) if video_encoder else None,
        "width": getattr(resolution, "Width", None) if resolution else None,
        "height": getattr(resolution, "Height", None) if resolution else None,
        "rtsp_uri": rtsp_uri,
    }


def _with_rtsp_credentials(rtsp_uri: str, username: str, password: str) -> str:
    if not username:
        return rtsp_uri
    return str(URL(rtsp_uri).with_user(username).with_password(password))


async def _probe(host: str, port: int, username: str, password: str) -> dict:
    camera = ONVIFCamera(host, port, username, password)

    try:
        await camera.update_xaddrs()

        manufacturer, model = await _fetch_device_info(camera)

        media_service = await camera.create_media_service()
        profiles = await media_service.GetProfiles()

        if not profiles:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=OnvifErrors.NO_MEDIA_PROFILES,
            )

        profile_results = []
        for profile in profiles:
            rtsp_uri = await _fetch_stream_uri(media_service, profile.token)
            rtsp_uri = _with_rtsp_credentials(rtsp_uri, username, password)
            profile_results.append(_build_profile_entry(profile, rtsp_uri))

        return {
            "device_manufacturer": manufacturer,
            "device_model": model,
            "profiles": profile_results,
        }
    finally:
        try:
            await camera.close()
        except Exception:
            logger.warning(
                "onvif probe failed to close camera session cleanly for host=%s port=%s",
                host, port,
            )


async def probe_camera(host: str, port: int, username: str, password: str) -> dict:
    if host.lower() == "mock":
        return {
            "device_manufacturer": "MockVision",
            "device_model": "MV-1080P",
            "profiles": [
                {
                    "profile_token": "profile_1",
                    "name": "MainStream",
                    "encoding": "H264",
                    "width": 1920,
                    "height": 1080,
                    "rtsp_uri": f"rtsp://{username}:{password}@192.168.1.100:554/stream1" if username else "rtsp://192.168.1.100:554/stream1",
                }
            ],
        }

    try:
        return await asyncio.wait_for(
            _probe(host, port, username, password), timeout=_PROBE_TIMEOUT_SECONDS
        )
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        logger.warning("onvif probe timed out for host=%s port=%s", host, port)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=OnvifErrors.CONNECTION_FAILED,
        )
    except Fault as exc:
        message = str(exc).lower()
        if "not authorized" in message or "auth" in message:
            logger.warning("onvif probe auth failed for host=%s port=%s", host, port)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=OnvifErrors.INVALID_CREDENTIALS,
            )
        logger.warning("onvif probe SOAP fault for host=%s port=%s: %s", host, port, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=OnvifErrors.UNSUPPORTED_OR_UNREACHABLE,
        )
    except TransportError as exc:
        logger.warning("onvif probe transport error for host=%s port=%s: %s", host, port, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=OnvifErrors.CONNECTION_FAILED,
        )
    except Exception as exc:
        logger.warning("onvif probe unexpected error for host=%s port=%s: %s", host, port, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=OnvifErrors.UNSUPPORTED_OR_UNREACHABLE,
        )