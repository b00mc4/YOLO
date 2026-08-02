from __future__ import annotations

import uuid

from fastapi import HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group
from app.models.user import User, UserRole
from app.models.verify import VerifyType
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserCreate, UserUpdate
from app.services import audit_service, auth_service, email_service


async def _get_village_or_404(db: AsyncSession, village_id: uuid.UUID) -> Group:
    result = await db.execute(select(Group).where(Group.id == village_id))
    village = result.scalar_one_or_none()
    if village is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Village not found")
    return village


async def _get_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _resolve_role_and_village(
    current_user: User,
    payload: UserCreate,
) -> tuple[UserRole, uuid.UUID | None]:
    if current_user.role == UserRole.ADMIN:
        if payload.role is not None or payload.village_id is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admins cannot set role or village_id when creating a user",
            )
        return UserRole.USER, current_user.village_id

    if payload.role is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="role is required")
    return payload.role, payload.village_id


def _verify_target_scope(current_user: User, target: User) -> None:
    if current_user.role == UserRole.SUPERADMIN:
        return
    if target.village_id != current_user.village_id or target.role != UserRole.USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to manage this user",
        )


async def create_user(
    db: AsyncSession,
    request: Request,
    current_user: User,
    payload: UserCreate,
) -> User:
    role, village_id = _resolve_role_and_village(current_user, payload)

    if village_id is not None:
        village = await _get_village_or_404(db, village_id)
        if not village.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot invite a user into an inactive village",
            )

    user = User(
        username=payload.username,
        fullname=payload.fullname,
        email=payload.email,
        role=role,
        village_id=village_id,
        hashpassword=None,
        is_active=True,
        is_verify=False,
    )
    db.add(user)
    await db.flush()

    raw_token = await auth_service.create_verify_token(db, user, VerifyType.INITIAL_SETUP)

    await audit_service.log_action(
        db,
        request,
        action="user_created",
        detail=f"created {role.value} user: {payload.username}",
        user_id=current_user.id,
        village_id=village_id,
    )

    await db.commit()
    await db.refresh(user)

    await run_in_threadpool(email_service.send_set_password_email, user.email, raw_token)

    return user


async def get_user(db: AsyncSession, current_user: User, user_id: uuid.UUID) -> User:
    target = await _get_user_or_404(db, user_id)
    if current_user.role != UserRole.SUPERADMIN and target.village_id != current_user.village_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to access this user")
    return target


async def list_users(
    db: AsyncSession,
    current_user: User,
    village_id_filter: uuid.UUID | None,
    role_filter: UserRole | None,
    is_active_filter: bool | None,
    search: str | None,
    page: int,
    page_size: int,
) -> PaginatedResponse[User]:
    stmt = select(User)
    count_stmt = select(func.count()).select_from(User)

    if current_user.role == UserRole.SUPERADMIN:
        if village_id_filter is not None:
            stmt = stmt.where(User.village_id == village_id_filter)
            count_stmt = count_stmt.where(User.village_id == village_id_filter)
    else:
        stmt = stmt.where(User.village_id == current_user.village_id)
        count_stmt = count_stmt.where(User.village_id == current_user.village_id)

    if role_filter is not None:
        stmt = stmt.where(User.role == role_filter)
        count_stmt = count_stmt.where(User.role == role_filter)
    if is_active_filter is not None:
        stmt = stmt.where(User.is_active == is_active_filter)
        count_stmt = count_stmt.where(User.is_active == is_active_filter)
    if search:
        pattern = f"%{search}%"
        search_clause = or_(
            User.username.ilike(pattern),
            User.fullname.ilike(pattern),
            User.email.ilike(pattern),
        )
        stmt = stmt.where(search_clause)
        count_stmt = count_stmt.where(search_clause)

    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    stmt = stmt.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


async def update_user(
    db: AsyncSession,
    request: Request,
    current_user: User,
    user_id: uuid.UUID,
    payload: UserUpdate,
) -> User:
    target = await _get_user_or_404(db, user_id)
    _verify_target_scope(current_user, target)

    update_data = payload.model_dump(exclude_unset=True)

    if "is_active" in update_data and update_data["is_active"] is False and target.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot suspend your own account",
        )

    previous_is_active = target.is_active
    for field, value in update_data.items():
        setattr(target, field, value)

    if "is_active" in update_data and update_data["is_active"] != previous_is_active:
        if update_data["is_active"] is False:
            await auth_service.revoke_all_refresh_tokens(db, target.id)
            action, detail = "user_suspended", f"suspended user: {target.username}"
        else:
            action, detail = "user_reactivated", f"reactivated user: {target.username}"
    else:
        action, detail = "user_updated", f"updated user: {target.username}"

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
    return target