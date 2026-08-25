import base64
from datetime import datetime, timedelta, timezone
import jwt
from cryptography.hazmat.primitives import serialization
from app.core.config import get_settings

settings = get_settings()
pem_bytes = base64.b64decode(settings.mediamtx_jwt_private_key_b64)
private_key = serialization.load_pem_private_key(pem_bytes, password=None)

now = datetime.now(timezone.utc)
payload = {
    "iat": now,
    "exp": now + timedelta(minutes=180),
    "mediamtx_permissions": [
        {"action": "read", "path": "raw-test-cam-1"},
    ],
}
token = jwt.encode(payload, private_key, algorithm="ES256")
print(token)