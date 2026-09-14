from __future__ import annotations
import base64
import uuid
from datetime import datetime, timedelta, timezone
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
from app.core.config import get_settings

settings = get_settings()

_JWT_ALGORITHM = "ES256"
_MEDIAMTX_PERMISSIONS_CLAIM = "mediamtx_permissions"
_READ_ACTION = "read"


_PRIVATE_KEY: EllipticCurvePrivateKey | None = None

def _load_private_key() -> EllipticCurvePrivateKey:
    global _PRIVATE_KEY
    if _PRIVATE_KEY is None:
        pem_bytes = base64.b64decode(settings.mediamtx_jwt_private_key_b64)
        key = serialization.load_pem_private_key(pem_bytes, password=None)
        if not isinstance(key, EllipticCurvePrivateKey):
            raise ValueError("mediamtx_jwt_private_key_b64 must decode to an EC private key")
        _PRIVATE_KEY = key
    return _PRIVATE_KEY


def issue_stream_token(camera_id: uuid.UUID, user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=15),
        "user_id": str(user_id),
        _MEDIAMTX_PERMISSIONS_CLAIM: [
            {"action": _READ_ACTION, "path": str(camera_id)},
        ],
    }
    return jwt.encode(payload, _load_private_key(), algorithm=_JWT_ALGORITHM)