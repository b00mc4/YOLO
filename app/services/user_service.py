from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import verify_village_scope
from app.core.account_lockout import get_account_locker
from app.core.security import hash_password, hash_token
from app.models.audit_log import AuditLog
from app.models.blacklist import Blacklist
from app.models.contact import Contact
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole
from app.models.verify import Verify, VerifyType
from app.schemas.common import PaginatedResponse
from app.schemas.contact import ContactRead
from app.schemas.user import (
    AdminResetPasswordRequest,
    UserCreate,
    UserDetail,
    UserMeDetail,
    UserStatusUpdate,
    UserSummary,
    UserRegister
)
from app.services import audit_service, auth_service, email_service, village_service
import logging


logger = logging.getLogger(__name__)
_RESEND_INVITE_COOLDOWN = timedelta(minutes=1)


async def _get_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _verify_user_write_scope(current_user: User, target: User) -> None:
    if current_user.role == UserRole.SUPERADMIN:
        return
    if target.id == current_user.id:
        return
    if current_user.role == UserRole.ADMIN:
        if target.role != UserRole.USER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only a superadmin can modify an admin or superadmin account",
            )
        if target.village_id != current_user.village_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to manage users outside your village",
            )
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


def _verify_password_reset_scope(current_user: User, target: User) -> None:
    if target.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reset your own password here, use change-password instead",
        )
    if current_user.role == UserRole.SUPERADMIN:
        if target.role == UserRole.SUPERADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot reset another superadmin's password",
            )
        return
    if current_user.role == UserRole.ADMIN:
        if target.role != UserRole.USER or target.village_id != current_user.village_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to reset this user's password",
            )
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

def _build_user_list_village_scope_filters(
    current_user: User, village_id_filter: uuid.UUID | None
) -> list:
    if current_user.role == UserRole.SUPERADMIN:
        if village_id_filter is not None:
            return [User.village_id == village_id_filter]
        return []

    if village_id_filter is not None and village_id_filter != current_user.village_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to specify village_id for this role",
        )
    return [User.village_id == current_user.village_id]

def _build_user_list_filters(
    current_user: User,
    village_id_filter: uuid.UUID | None,
    role_filter: UserRole | None,
    is_active_filter: bool | None,
    search: str | None,
) -> list:
    filters = _build_user_list_village_scope_filters(current_user, village_id_filter)

    if role_filter is not None:
        filters.append(User.role == role_filter)
    if is_active_filter is not None:
        filters.append(User.is_active == is_active_filter)
    if search:
        pattern = f"%{search}%"
        filters.append(or_(User.fullname.ilike(pattern), User.username.ilike(pattern)))

    return filters


async def _to_user_detail(db: AsyncSession, user: User) -> UserDetail:
    contact_count_result = await db.execute(
        select(func.count()).select_from(Contact).where(Contact.user_id == user.id)
    )
    contact_count = contact_count_result.scalar_one()

    return UserDetail(
        id=user.id,
        username=user.username,
        fullname=user.fullname,
        email=user.email,
        role=user.role,
        village_id=user.village_id,
        is_active=user.is_active,
        is_verify=user.is_verify,
        created_at=user.created_at,
        contact_count=contact_count,
    )


async def _to_user_me_detail(db: AsyncSession, user: User) -> UserMeDetail:
    contacts_result = await db.execute(
        select(Contact).where(Contact.user_id == user.id).order_by(Contact.created_at.desc())
    )
    contacts = contacts_result.scalars().all()

    return UserMeDetail(
        id=user.id,
        username=user.username,
        fullname=user.fullname,
        email=user.email,
        role=user.role,
        village_id=user.village_id,
        is_active=user.is_active,
        is_verify=user.is_verify,
        created_at=user.created_at,
        contacts=[ContactRead.model_validate(contact) for contact in contacts],
    )

def _to_user_register(user: User, invite_email_sent: bool) -> UserRegister:
    return UserRegister(
        id=user.id,
        username=user.username,
        role=user.role,
        village_id=user.village_id,
        created_at=user.created_at,
        invite_email_sent=invite_email_sent,
    )


async def create_user(
    db: AsyncSession,
    request: Request,
    current_user: User,
    payload: UserCreate,
) -> UserRegister:
    if current_user.role == UserRole.ADMIN:
        if payload.role == UserRole.SUPERADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to create a superadmin account",
            )
        village_id = current_user.village_id
    else:
        village_id = payload.village_id
        if payload.role != UserRole.SUPERADMIN:
            await village_service.get_village(db, village_id)

    user = User(
        username=payload.username,
        fullname=payload.fullname,
        email=payload.email,
        role=payload.role,
        village_id=village_id,
        hashpassword=None,
        is_active=True,
        is_verify=False,
    )
    db.add(user)
    await db.flush()

    await audit_service.log_action(
        db,
        request,
        action="user_created",
        detail=f"created user: {user.username} (role={user.role.value})",
        user_id=current_user.id,
        village_id=village_id,
    )

    raw_token = await auth_service.create_verify_token(db, user, VerifyType.INITIAL_SETUP)

    await db.commit()
    await db.refresh(user)

    invite_email_sent = True
    try:
        await run_in_threadpool(email_service.send_invite_email, user.email, raw_token)
    except Exception:
        invite_email_sent = False
        logger.warning("Failed to send invite email to new user: %s", user.username)

    return _to_user_register(user, invite_email_sent)


async def list_users(
    db: AsyncSession,
    current_user: User,
    village_id_filter: uuid.UUID | None,
    role_filter: UserRole | None,
    is_active_filter: bool | None,
    search: str | None,
    page: int,
    page_size: int,
) -> PaginatedResponse[UserSummary]:
    filters = _build_user_list_filters(
        current_user, village_id_filter, role_filter, is_active_filter, search
    )

    count_result = await db.execute(select(func.count()).select_from(User).where(*filters))
    total = count_result.scalar_one()

    stmt = (
        select(User)
        .where(*filters)
        .order_by(User.fullname)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    return PaginatedResponse[UserSummary](
        items=[UserSummary.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_own_user_detail(db: AsyncSession, current_user: User) -> UserMeDetail:
    return await _to_user_me_detail(db, current_user)


async def get_user_detail(db: AsyncSession, current_user: User, user_id: uuid.UUID) -> UserDetail:
    user = await _get_user_or_404(db, user_id)
    verify_village_scope(current_user, user.village_id)
    return await _to_user_detail(db, user)


async def set_user_active_status(
    db: AsyncSession,
    request: Request,
    current_user: User,
    user_id: uuid.UUID,
    payload: UserStatusUpdate,
) -> UserDetail:
    target = await _get_user_or_404(db, user_id)
    _verify_user_write_scope(current_user, target)

    previous_is_active = target.is_active
    target.is_active = payload.is_active

    if payload.is_active == previous_is_active:
        action = "user_updated"
        detail = f"updated user: {target.username}"
    elif payload.is_active:
        action = "user_activated"
        detail = f"user activated: {target.username}"
    else:
        action = "user_deactivated"
        detail = f"user deactivated: {target.username}"

    await audit_service.log_action(
        db,
        request,
        action=action,
        detail=detail,
        user_id=current_user.id,
        village_id=target.village_id,
    )

    await db.commit()
    await db.refresh(target)
    return await _to_user_detail(db, target)


async def reset_user_password(
    db: AsyncSession,
    request: Request,
    current_user: User,
    user_id: uuid.UUID,
    payload: AdminResetPasswordRequest,
) -> str:
    target = await _get_user_or_404(db, user_id)
    _verify_password_reset_scope(current_user, target)

    if target.hashpassword is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account has not set a password yet, use resend-invite instead",
        )

    target.hashpassword = hash_password(payload.new_password)
    await auth_service.revoke_all_refresh_tokens(db, target.id)

    await audit_service.log_action(
        db,
        request,
        action="user_password_reset",
        detail=f"password reset for user: {target.username}",
        user_id=current_user.id,
        village_id=target.village_id,
    )

    await db.commit()
    await db.refresh(target)
    return target.username


async def resend_invite(
    db: AsyncSession,
    request: Request,
    current_user: User,
    user_id: uuid.UUID,
) -> UserDetail:
    target = await _get_user_or_404(db, user_id)
    _verify_user_write_scope(current_user, target)

    if target.is_verify:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already verified",
        )

    last_sent_result = await db.execute(
        select(Verify.created_at)
        .where(Verify.user_id == target.id, Verify.type == VerifyType.INITIAL_SETUP)
        .order_by(Verify.created_at.desc())
        .limit(1)
    )
    last_sent_at = last_sent_result.scalar_one_or_none()
    if last_sent_at is not None and datetime.now(timezone.utc) - last_sent_at < _RESEND_INVITE_COOLDOWN:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait before requesting another invite",
        )

    raw_token = await auth_service.create_verify_token(db, target, VerifyType.INITIAL_SETUP)

    try:
        await run_in_threadpool(email_service.send_invite_email, target.email, raw_token)
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send invite email",
        )

    await auth_service.invalidate_pending_verify_tokens(
        db, target.id, VerifyType.INITIAL_SETUP, exclude_token_hash=hash_token(raw_token)
    )

    await audit_service.log_action(
        db,
        request,
        action="user_invite_resent",
        detail=f"resent invite email: {target.username}",
        user_id=current_user.id,
        village_id=target.village_id,
    )

    await db.commit()
    await db.refresh(target)
    return await _to_user_detail(db, target)


async def unlock_user_account(
    db: AsyncSession,
    request: Request,
    current_user: User,
    user_id: uuid.UUID,
) -> str:
    target = await _get_user_or_404(db, user_id)
    _verify_user_write_scope(current_user, target)

    get_account_locker().reset(target.username.strip().lower())

    await audit_service.log_action(
        db,
        request,
        action="account_unlocked",
        detail=f"unlocked account: {target.username}",
        user_id=current_user.id,
        village_id=target.village_id,
    )

    await db.commit()
    return target.username

async def _verify_hard_delete_eligible(db: AsyncSession, target: User) -> None:
    if target.hashpassword is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="บัญชีนี้เคยตั้งรหัสผ่านและใช้งานแล้ว ไม่สามารถลบถาวรได้ กรุณาปิดการใช้งานแทน",
        )

    contact_count = await db.execute(
        select(func.count()).select_from(Contact).where(Contact.user_id == target.id)
    )
    if contact_count.scalar_one() > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="บัญชีนี้มีข้อมูลช่องทางติดต่อผูกอยู่ ไม่สามารถลบถาวรได้ กรุณาปิดการใช้งานแทน",
        )

    refresh_token_count = await db.execute(
        select(func.count()).select_from(RefreshToken).where(RefreshToken.user_id == target.id)
    )
    if refresh_token_count.scalar_one() > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="บัญชีนี้มีเซสชันการเข้าสู่ระบบผูกอยู่ ไม่สามารถลบถาวรได้ กรุณาปิดการใช้งานแทน",
        )

    blacklist_count = await db.execute(
        select(func.count()).select_from(Blacklist).where(Blacklist.added_by == target.id)
    )
    if blacklist_count.scalar_one() > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="บัญชีนี้มีรายการ blacklist ที่เคยเพิ่มไว้ผูกอยู่ ไม่สามารถลบถาวรได้ กรุณาปิดการใช้งานแทน",
        )


async def delete_user(
    db: AsyncSession,
    request: Request,
    current_user: User,
    user_id: uuid.UUID,
) -> None:
    target = await _get_user_or_404(db, user_id)

    if target.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ไม่สามารถลบบัญชีตัวเองได้",
        )

    _verify_user_write_scope(current_user, target)
    await _verify_hard_delete_eligible(db, target)

    await audit_service.log_action(
        db,
        request,
        action="user_deleted",
        detail=f"permanently deleted unused user: {target.username}",
        user_id=current_user.id,
        village_id=target.village_id,
    )

    await db.execute(
        update(AuditLog).where(AuditLog.user_id == target.id).values(user_id=None)
    )
    await db.execute(delete(Verify).where(Verify.user_id == target.id))

    await db.delete(target)
    await db.commit()