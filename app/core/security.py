import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError
import re
from app.core.error_messages import ValidationErrors
from app.core.config import get_settings

settings = get_settings()
_password_hasher = PasswordHasher()

_DUMMY_PASSWORD_HASH = _password_hasher.hash(secrets.token_urlsafe(32))
_ALLOWED_PASSWORD_CHARS = re.compile(r"^[A-Za-z0-9!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?~]*$")


def hash_password(password: str):
    return _password_hasher.hash(password)


def verify_password(password: str, hashed: str):
    try:
        return _password_hasher.verify(hashed, password)
    except (VerificationError, InvalidHash):
        return False


def create_access_token(user_id: uuid.UUID):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> tuple[uuid.UUID, datetime]:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    issued_at = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
    return uuid.UUID(payload["sub"]), issued_at


def generate_secure_token():
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

def validate_password_policy(value: str) -> str:
    if not _ALLOWED_PASSWORD_CHARS.fullmatch(value):
        raise ValueError(ValidationErrors.PASSWORD_INVALID_CHARACTERS)
    if len(value) < 8:
        raise ValueError(ValidationErrors.PASSWORD_MIN_LENGTH)
    if len(value) > 36:
        raise ValueError(ValidationErrors.PASSWORD_MAX_LENGTH)
    if not re.search(r"[A-Za-z]", value):
        raise ValueError(ValidationErrors.PASSWORD_NEED_LETTER)
    if not re.search(r"\d", value):
        raise ValueError(ValidationErrors.PASSWORD_NEED_DIGIT)
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?~]", value):
        raise ValueError(ValidationErrors.PASSWORD_NEED_SYMBOL)
    return value