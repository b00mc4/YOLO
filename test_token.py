import sys
import uuid
import asyncio
from app.services import mediamtx_auth_service

def test():
    t = mediamtx_auth_service.issue_stream_token(uuid.uuid4(), uuid.uuid4())
    import jwt
    pub = mediamtx_auth_service._load_private_key().public_key()
    decoded = jwt.decode(t, pub, algorithms=["ES256"])
    print(decoded)

test()
