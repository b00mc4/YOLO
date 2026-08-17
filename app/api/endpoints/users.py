from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.user import (
    AdminResetPasswordRequest,
    AdminResetPasswordResponse,
    UserCreate,
    UserDetail,
    UserMeDetail,
    UserStatusUpdate,
    UserSummary,
    UserRegister
)
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])

_ALLOWED_ROLES = (UserRole.ADMIN, UserRole.SUPERADMIN)


@router.post("", response_model=UserRegister, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    request: Request,
    current_user: User = Depends(require_roles(*_ALLOWED_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await user_service.create_user(db, request, current_user, payload)


@router.get("", response_model=PaginatedResponse[UserSummary])
async def list_users(
    village_id: uuid.UUID | None = Query(default=None),
    role: UserRole | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_roles(*_ALLOWED_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await user_service.list_users(
        db, current_user, village_id, role, is_active, search, page, page_size
    )


@router.get("/me", response_model=UserMeDetail)
async def get_my_detail(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    ดูข้อมูลของบัญชีตัวเอง

    ใช้ได้ทุก role ที่ login สำเร็จ (รวมถึง role `user` เช่นยามที่ไม่มีสิทธิ์
    เรียก endpoint อื่นในกลุ่มนี้) เพราะเช็คแค่ตัวตนจาก token ไม่เช็ค role
    """
    return await user_service.get_own_user_detail(db, current_user)


@router.get("/{user_id}", response_model=UserDetail)
async def get_user_detail(
    user_id: uuid.UUID,
    current_user: User = Depends(require_roles(*_ALLOWED_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await user_service.get_user_detail(db, current_user, user_id)


@router.patch("/{user_id}", response_model=UserDetail)
async def update_user_status(
    user_id: uuid.UUID,
    payload: UserStatusUpdate,
    request: Request,
    current_user: User = Depends(require_roles(*_ALLOWED_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await user_service.set_user_active_status(db, request, current_user, user_id, payload)


@router.post("/{user_id}/reset-password", response_model=AdminResetPasswordResponse)
async def reset_user_password(
    user_id: uuid.UUID,
    payload: AdminResetPasswordRequest,
    request: Request,
    current_user: User = Depends(require_roles(*_ALLOWED_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    username = await user_service.reset_user_password(db, request, current_user, user_id, payload)
    return AdminResetPasswordResponse(
        detail=f"เปลี่ยนรหัสผ่านให้ {username} สำเร็จ",
        username=username,
    )


@router.post("/{user_id}/resend-invite", response_model=UserDetail)
async def resend_invite(
    user_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_roles(*_ALLOWED_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await user_service.resend_invite(db, request, current_user, user_id)


@router.post("/{user_id}/unlock-account", response_model=MessageResponse)
async def unlock_user_account(
    user_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_roles(*_ALLOWED_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    username = await user_service.unlock_user_account(db, request, current_user, user_id)
    return MessageResponse(detail=f"ปลดล็อคบัญชี {username} สำเร็จ")


@router.delete("/{user_id}", response_model=MessageResponse)
async def delete_user(
    user_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_roles(*_ALLOWED_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    await user_service.delete_user(db, request, current_user, user_id)
    return MessageResponse(detail="ลบบัญชีผู้ใช้ถาวรสำเร็จ")