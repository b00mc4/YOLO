from __future__ import annotations
from urllib.parse import quote, urlsplit, urlunsplit
from app.core.error_messages import CameraErrors

_ALLOWED_SCHEMES = ("rtsp", "rtsps")


def normalize_rtsp_url(raw: str) -> str:
    stripped = raw.strip()
    if not stripped:
        raise ValueError(CameraErrors.INVALID_RTSP_FORMAT)

    parts = urlsplit(stripped)

    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError(CameraErrors.INVALID_RTSP_FORMAT)

    hostname = parts.hostname
    if not hostname:
        raise ValueError(CameraErrors.INVALID_RTSP_FORMAT)

    userinfo = ""
    if parts.username:
        userinfo = quote(parts.username, safe="")
        if parts.password:
            userinfo += f":{quote(parts.password, safe='')}"
        userinfo += "@"

    netloc = f"{userinfo}{hostname}"
    if parts.port:
        netloc += f":{parts.port}"

    return urlunsplit((scheme, netloc, parts.path, parts.query, parts.fragment))


def redact_rtsp_url(raw: str) -> str:
    if not raw:
        return raw
    try:
        parts = urlsplit(raw)
        if not parts.hostname:
            return raw
        
        userinfo = ""
        if parts.username or parts.password:
            userinfo = "***:***@"
            
        netloc = f"{userinfo}{parts.hostname}"
        if parts.port:
            netloc += f":{parts.port}"
            
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        return raw