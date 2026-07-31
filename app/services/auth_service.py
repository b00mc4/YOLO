from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_secure_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.verify import Verify, VerifyType
from app.services import audit_service, email_service
from app.models.group import Group
from app.models.user import User, UserRole

settings = get_settings()

REFRESH_TOKEN_COOKIE_NAME = "refresh_token"

_GENERIC_LOGIN_ERROR = "Incorrect username or password"

async def authenticate_user(db: AsyncSession, request: Request, username: str, password: str):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if user is None:
        await audit_service.log_action(
            db,
            request,
            action="login_failed",
            detail=f"unknown username: {username}",
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_LOGIN_ERROR)

    village_is_active = True
    if user.role != UserRole.SUPERADMIN:
        village_result = await db.execute(select(Group.is_active).where(Group.id == user.village_id))
        village_is_active = bool(village_result.scalar_one_or_none())

    if (
        user.hashpassword is None
        or not user.is_active
        or not user.is_verify
        or not village_is_active
        or not verify_password(password, user.hashpassword)
    ):
        
        await audit_service.log_action(
            db,
            request,
            action="login_failed",
            detail=f"failed login attempt for username: {username}",
            user_id=user.id,
            village_id=user.village_id,
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_LOGIN_ERROR)

    await audit_service.log_action(
        db,
        request,
        action="login_success",
        detail=f"successful login for username: {username}",
        user_id=user.id,
        village_id=user.village_id,
    )
    await db.commit()
    return user


async def issue_tokens(db: AsyncSession, user: User):
    access_token = create_access_token(user.id)
    raw_refresh_token = generate_secure_token()

    refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh_token),
        expired_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(refresh_token)
    await db.commit()

    return access_token, raw_refresh_token


async def rotate_refresh_token(db: AsyncSession, raw_refresh_token: str):
    token_hash = hash_token(raw_refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored_token = result.scalar_one_or_none()

    if stored_token is None or stored_token.expired_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    result = await db.execute(select(User).where(User.id == stored_token.user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    await db.delete(stored_token)
    access_token, new_raw_refresh_token = await issue_tokens(db, user)
    return access_token, new_raw_refresh_token

async def revoke_refresh_token(db: AsyncSession, raw_refresh_token: str):
    token_hash = hash_token(raw_refresh_token)
    await db.execute(delete(RefreshToken).where(RefreshToken.token_hash == token_hash))
    await db.commit()

async def revoke_all_refresh_tokens(db: AsyncSession, user_id: uuid.UUID):
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))

async def revoke_other_refresh_tokens(
    db: AsyncSession,
    user_id: uuid.UUID,
    current_raw_refresh_token: str | None,
) -> None:
    stmt = delete(RefreshToken).where(RefreshToken.user_id == user_id)
    if current_raw_refresh_token is not None:
        stmt = stmt.where(RefreshToken.token_hash != hash_token(current_raw_refresh_token))
    await db.execute(stmt)

async def change_password(
    db: AsyncSession,
    request: Request,
    current_user: User,
    current_password: str,
    new_password: str,
    logout_all_sessions: bool,
    current_raw_refresh_token: str | None,
) -> None:
    if current_user.hashpassword is None or not verify_password(current_password, current_user.hashpassword):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    current_user.hashpassword = hash_password(new_password)

    if logout_all_sessions:
        await revoke_all_refresh_tokens(db, current_user.id)
    else:
        await revoke_other_refresh_tokens(db, current_user.id, current_raw_refresh_token)

    await audit_service.log_action(
        db,
        request,
        action="change_password",
        detail="password changed",
        user_id=current_user.id,
        village_id=current_user.village_id,
    )
    await db.commit()


async def create_verify_token(db: AsyncSession, user: User, verify_type: VerifyType) -> str:
    raw_token = generate_secure_token()
    verify_entry = Verify(
        user_id=user.id,
        type=verify_type,
        token_hash=hash_token(raw_token),
        expire_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(verify_entry)
    await db.commit()
    return raw_token


async def request_password_reset(db: AsyncSession, email: str) -> None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        return

    raw_token = await create_verify_token(db, user, VerifyType.PASSWORD_RESET)
    await run_in_threadpool(email_service.send_set_password_email, user.email, raw_token)


async def set_password(db: AsyncSession, raw_token: str, new_password: str) -> None:
    token_hash = hash_token(raw_token)
    result = await db.execute(select(Verify).where(Verify.token_hash == token_hash, Verify.used.is_(False)))
    verify_entry = result.scalar_one_or_none()

    if verify_entry is None or verify_entry.expire_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    result = await db.execute(select(User).where(User.id == verify_entry.user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    user.hashpassword = hash_password(new_password)
    user.is_verify = True
    verify_entry.used = True

    await revoke_all_refresh_tokens(db, user.id)
    await db.commit()