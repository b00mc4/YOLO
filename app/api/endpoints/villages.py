from __future__ import annotations
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.village import VillageCreate, VillageDetailRead, VillageRead, VillageUpdate
from app.services import village_service

router = APIRouter(prefix="/villages", tags=["villages"])


@router.post("", response_model=VillageRead, status_code=status.HTTP_201_CREATED)
async def create_village(
    payload: VillageCreate,
    request: Request,
    current_user: User = Depends(require_roles(UserRole.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await village_service.create_village(db, request, current_user, payload)


@router.get("", response_model=PaginatedResponse[VillageRead])
async def list_villages(
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await village_service.list_villages(db,current_user, is_active, search, page, page_size)


@router.get("/{village_id}", response_model=VillageDetailRead)
async def get_village(
    village_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await village_service.get_village_detail(db, current_user, village_id)


@router.patch("/{village_id}", response_model=VillageRead)
async def update_village(
    village_id: uuid.UUID,
    payload: VillageUpdate,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_roles(UserRole.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await village_service.update_village(db, request, background_tasks, current_user, village_id, payload)


@router.delete("/{village_id}", response_model=MessageResponse)
async def delete_village(
    village_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    confirm: bool = Query(False, description="ยืนยันการลบแบบถอนรากถอนโคน (จะลบทั้งกล้อง ผู้ใช้ และประวัติทั้งหมด)"),
    current_user: User = Depends(require_roles(UserRole.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="กรุณาส่ง confirm=true เพื่อยืนยันการลบหมู่บ้านถาวร",
        )
    await village_service.delete_village(db, request, background_tasks, current_user, village_id)
    return MessageResponse(detail="ลบหมู่บ้านถาวรสำเร็จ")