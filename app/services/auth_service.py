from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import BackgroundTasks, HTTPException, Request, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_client_ip
from app.core.config import get_settings
from app.core.security import (
    _DUMMY_PASSWORD_HASH as hash_security_dummy,
    create_access_token,
    generate_secure_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.verify import Verify, VerifyType
from app.services import audit_service, email_service, login_security_service
from app.models.group import Group
from app.models.user import User, UserRole
from app.core.rate_limit import get_rate_limiter
from app.core.account_lockout import AccountLocked, get_account_locker
from app.core.error_messages import Auth, UserErrors

settings = get_settings()

REFRESH_TOKEN_COOKIE_NAME = "refresh_token"

_GENERIC_LOGIN_ERROR = Auth.INVALID_CREDENTIALS

_LOGIN_USERNAME_LIMIT = 50
_LOGIN_USERNAME_WINDOW_SECONDS = 30 * 60
_FORGOT_PASSWORD_EMAIL_LIMIT = 5
_FORGOT_PASSWORD_EMAIL_WINDOW_SECONDS = 24 * 60 * 60

async def authenticate_user(db: AsyncSession, request: Request, username: str, password: str):
    normalized_username = username.strip().lower()
    rate_limit_key = f"login:username:{normalized_username}"
    locker_key = normalized_username

    try:
        get_account_locker().check_locked(locker_key)
    except AccountLocked:
        await audit_service.log_action(
            db,
            request,
            action="login_blocked_locked",
            detail=f"login attempt blocked, account locked for username: {username}",
        )
        await db.commit()
        raise

    get_rate_limiter().check(rate_limit_key, _LOGIN_USERNAME_LIMIT, _LOGIN_USERNAME_WINDOW_SECONDS)

    result = await db.execute(select(User).where(User.username == normalized_username))
    user = result.scalar_one_or_none()

    village_is_active = True
    if user is not None and user.role != UserRole.SUPERADMIN:
        village_result = await db.execute(select(Group.is_active).where(Group.id == user.village_id))
        village_is_active = bool(village_result.scalar_one_or_none())

    hash_to_check = (
        user.hashpassword
        if (user is not None and user.hashpassword is not None)
        else hash_security_dummy
    )
    password_ok = verify_password(password, hash_to_check)

    credential_failed = (
    user is None
    or user.hashpassword is None
    or not password_ok
    )

    login_failed = (
    credential_failed
    or not user.is_active
    or not user.is_verify
    or not village_is_active
    )

    if login_failed:
        locked_for_seconds = None
        if credential_failed:
            locked_for_seconds = get_account_locker().register_failure(locker_key)

        await audit_service.log_action(
            db,
            request,
            action="login_failed",
            detail=(
                f"unknown username: {username}"
                if user is None
                else f"failed login attempt for username: {username}"
            ),
            user_id=user.id if user is not None else None,
            village_id=user.village_id if user is not None else None,
        )

        if locked_for_seconds is not None:
            await login_security_service.record_bruteforce_audit(
                db, request, username, user, locked_for_seconds
            )

        await db.commit()

        if locked_for_seconds is not None:
            await login_security_service.publish_bruteforce_alert(
                username, user, locked_for_seconds, get_client_ip(request)
            )

        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_LOGIN_ERROR)

    get_account_locker().reset(locker_key)
    await audit_service.log_action(
        db,
        request,
        action="login_success",
        detail=f"successful login for username: {username}",
        user_id=user.id,
        village_id=user.village_id,
    )
    await db.commit()
    get_rate_limiter().reset(rate_limit_key)
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=Auth.INVALID_OR_EXPIRED_REFRESH_TOKEN)

    result = await db.execute(select(User).where(User.id == stored_token.user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active or not user.is_verify:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=Auth.INVALID_OR_EXPIRED_REFRESH_TOKEN)

    village_is_active = True
    if user.role != UserRole.SUPERADMIN:
        village_result = await db.execute(select(Group.is_active).where(Group.id == user.village_id))
        village_is_active = bool(village_result.scalar_one_or_none())

    if not village_is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=Auth.INVALID_OR_EXPIRED_REFRESH_TOKEN)

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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=Auth.CURRENT_PASSWORD_INCORRECT)

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


async def create_verify_token(
    db: AsyncSession, user: User, verify_type: VerifyType, new_email: str | None = None
) -> str:
    raw_token = generate_secure_token()
    verify_entry = Verify(
        user_id=user.id,
        type=verify_type,
        new_email=new_email,
        token_hash=hash_token(raw_token),
        expire_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(verify_entry)
    await db.flush()
    return raw_token


async def invalidate_pending_verify_tokens(
    db: AsyncSession,
    user_id: uuid.UUID,
    verify_type: VerifyType,
    exclude_token_hash: str | None = None,
) -> None:
    stmt = (
        update(Verify)
        .where(Verify.user_id == user_id, Verify.type == verify_type, Verify.used.is_(False))
        .values(used=True)
    )
    if exclude_token_hash is not None:
        stmt = stmt.where(Verify.token_hash != exclude_token_hash)
    await db.execute(stmt)


async def request_password_reset(
    db: AsyncSession, background_tasks: BackgroundTasks, email: str
) -> None:
    normalized_email = email.strip().lower()
    get_rate_limiter().check(
        f"forgot_password:email:{normalized_email}",
        _FORGOT_PASSWORD_EMAIL_LIMIT,
        _FORGOT_PASSWORD_EMAIL_WINDOW_SECONDS,
    )

    if email_service.is_email_service_degraded():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ระบบส่งอีเมลขัดข้องชั่วคราว กรุณาลองใหม่ภายหลัง",
        )

    result = await db.execute(select(User).where(User.email == normalized_email))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        return

    raw_token = await create_verify_token(db, user, VerifyType.PASSWORD_RESET)
    await invalidate_pending_verify_tokens(
        db, user.id, VerifyType.PASSWORD_RESET, exclude_token_hash=hash_token(raw_token)
    )
    await db.commit()
    background_tasks.add_task(
        email_service.send_set_password_email_background, user.email, raw_token
    )


async def set_password(db: AsyncSession, raw_token: str, new_password: str) -> str:
    token_hash = hash_token(raw_token)
    result = await db.execute(select(Verify).where(Verify.token_hash == token_hash, Verify.used.is_(False)))
    verify_entry = result.scalar_one_or_none()

    if verify_entry is None or verify_entry.expire_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=Auth.INVALID_OR_EXPIRED_TOKEN)

    result = await db.execute(select(User).where(User.id == verify_entry.user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=Auth.INVALID_OR_EXPIRED_TOKEN)

    user.hashpassword = hash_password(new_password)
    user.is_verify = True
    verify_entry.used = True

    await invalidate_pending_verify_tokens(
        db, user.id, verify_entry.type, exclude_token_hash=token_hash
    )
    await revoke_all_refresh_tokens(db, user.id)
    await db.commit()

    return user.username

async def confirm_email_change(db: AsyncSession, request: Request, raw_token: str) -> tuple[str, str]:
    token_hash = hash_token(raw_token)
    result = await db.execute(
        select(Verify).where(
            Verify.token_hash == token_hash,
            Verify.type == VerifyType.EMAIL_CHANGE,
            Verify.used.is_(False),
        )
    )
    verify_entry = result.scalar_one_or_none()

    if verify_entry is None or verify_entry.expire_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=Auth.INVALID_OR_EXPIRED_TOKEN)

    result = await db.execute(select(User).where(User.id == verify_entry.user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=Auth.INVALID_OR_EXPIRED_TOKEN)

    existing_email_result = await db.execute(
        select(User.id).where(User.email == verify_entry.new_email, User.id != user.id)
    )
    if existing_email_result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=UserErrors.EMAIL_ALREADY_IN_USE)

    old_email = user.email
    user.email = verify_entry.new_email
    verify_entry.used = True

    await invalidate_pending_verify_tokens(db, user.id, VerifyType.EMAIL_CHANGE, exclude_token_hash=token_hash)

    await audit_service.log_action(
        db,
        request,
        action="email_changed",
        detail=f"email changed from {old_email} to {user.email} for username: {user.username}",
        user_id=user.id,
        village_id=user.village_id,
    )

    await db.commit()

    return user.username, user.email