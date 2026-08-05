from __future__ import annotations
import secrets
import uuid
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.group import Group
from app.core.rate_limit import RateLimitExceeded, get_rate_limiter

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
api_key_scheme = APIKeyHeader(name=settings.api_key_header_name, auto_error=False)

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}

_API_KEY_FAILURE_LIMIT = 3
_API_KEY_FAILURE_WINDOW_SECONDS = 5 * 60

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    try:
        user_id = decode_access_token(token)
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers=_UNAUTHORIZED_HEADERS,
        )

    result = await db.execute(
        select(User, Group.is_active.label("village_is_active"))
        .outerjoin(Group, User.village_id == Group.id)
        .where(User.id == user_id)
    )
    row = result.one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers=_UNAUTHORIZED_HEADERS,
        )

    user, village_is_active = row


    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers=_UNAUTHORIZED_HEADERS,
        )

    if not user.is_verify:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is not verified",
            headers=_UNAUTHORIZED_HEADERS,
        )
    
    if user.role != UserRole.SUPERADMIN and not village_is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Village is inactive",
            headers=_UNAUTHORIZED_HEADERS,
        )

    return user

def require_roles(*roles: UserRole):
    async def checker(user: User = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return checker


def verify_village_scope(user: User, target_village_id: uuid.UUID) -> None:
    if user.role == UserRole.SUPERADMIN:
        return
    if user.village_id != target_village_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to access this village's data",
        )


async def verify_api_key(
    request: Request,
    api_key: str | None = Depends(api_key_scheme),
    db: AsyncSession = Depends(get_db),
) -> None:
    if api_key is None or not secrets.compare_digest(api_key, settings.api_key):
        get_rate_limiter().check(
            f"api_key_rejected:ip:{get_client_ip(request)}",
            _API_KEY_FAILURE_LIMIT,
            _API_KEY_FAILURE_WINDOW_SECONDS,
        )

        from app.services import audit_service

        await audit_service.log_action(
            db,
            request,
            action="api_key_rejected",
            detail=f"invalid or missing API key on {request.method} {request.url.path}",
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

def get_client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else ""


def rate_limit_by_ip(prefix: str, limit: int, window_seconds: float):
    async def checker(request: Request):
        client_ip = get_client_ip(request)
        get_rate_limiter().check(f"{prefix}:ip:{client_ip}", limit, window_seconds)

    return checker