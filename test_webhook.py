import asyncio
import uuid
import jwt
from datetime import datetime, timedelta, timezone

def generate_token():
    now = datetime.now(timezone.utc)
    payload = {
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(hours=24),
        "user_id": str(uuid.UUID(int=1)),
        "mediamtx_permissions": [{"action": "read", "path": str(uuid.UUID(int=2))}]
    }
    # using a dummy key, we just want to see if the webhook parses it. Wait, we need the real public key to test the webhook.
