import datetime
from app.services import mediamtx_auth_service
import uuid
import jwt

def test():
    token = mediamtx_auth_service.issue_stream_token(uuid.uuid4(), uuid.uuid4())
    pub = mediamtx_auth_service._load_private_key().public_key()
    decoded = jwt.decode(token, pub, algorithms=["ES256"], options={"verify_exp": False})
    
    exp = decoded["exp"]
    iat = decoded["iat"]
    print("Token valid for hours:", (exp - iat) / 3600)

test()
