from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])

_MANAGER_ROLES = (UserRole.ADMIN, UserRole.SUPERADMIN)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    request: Request,
    current_user: User = Depends(require_roles(*_MANAGER_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await user_service.create_user(db, request, current_user, payload)


@router.get("", response_model=PaginatedResponse[UserRead])
async def list_users(
    village_id: uuid.UUID | None = Query(default=None),
    role: UserRole | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_roles(*_MANAGER_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await user_service.list_users(
        db, current_user, village_id, role, is_active, search, page, page_size
    )


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_roles(*_MANAGER_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await user_service.get_user(db, current_user, user_id)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    request: Request,
    current_user: User = Depends(require_roles(*_MANAGER_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await user_service.update_user(db, request, current_user, user_id, payload)