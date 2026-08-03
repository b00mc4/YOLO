from __future__ import annotations

import uuid

from fastapi import HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import verify_village_scope
from app.models.contact import Contact
from app.models.user import User, UserRole
from app.models.verify import VerifyType
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserCreate, UserDetail, UserStatusUpdate, UserSummary
from app.services import audit_service, auth_service, email_service, village_service


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
        if target.role == UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only a superadmin can modify another admin's account",
            )
        if target.village_id != current_user.village_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to manage users outside your village",
            )
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


def _build_user_list_filters(
    current_user: User,
    village_id_filter: uuid.UUID | None,
    role_filter: UserRole | None,
    is_active_filter: bool | None,
    search: str | None,
) -> list:
    filters = []

    if current_user.role == UserRole.SUPERADMIN:
        if village_id_filter is not None:
            filters.append(User.village_id == village_id_filter)
    else:
        filters.append(User.village_id == current_user.village_id)

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


async def create_user(
    db: AsyncSession,
    request: Request,
    current_user: User,
    payload: UserCreate,
) -> UserDetail:
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

    await db.commit()
    await db.refresh(user)

    raw_token = await auth_service.create_verify_token(db, user, VerifyType.INITIAL_SETUP)
    await run_in_threadpool(email_service.send_invite_email, user.email, raw_token)

    return await _to_user_detail(db, user)


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