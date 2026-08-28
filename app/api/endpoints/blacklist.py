from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.blacklist import BlacklistCreate, BlacklistRead, BlacklistUpdate
from app.schemas.common import MessageResponse, PaginatedResponse
from app.services import blacklist_service

router = APIRouter(prefix="/blacklist", tags=["blacklist"])


@router.post("", response_model=BlacklistRead, status_code=status.HTTP_201_CREATED)
async def create_blacklist_entry(
    request: Request,
    payload: BlacklistCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await blacklist_service.create_blacklist_entry(db, request, current_user, payload)


@router.get("", response_model=PaginatedResponse[BlacklistRead])
async def list_blacklist_entries(
    village_id: uuid.UUID | None = Query(default=None),
    license_plate: str | None = Query(default=None),
    province: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await blacklist_service.list_blacklist_entries(
        db, current_user, village_id, license_plate, province, page, page_size
    )


@router.patch("/{entry_id}", response_model=BlacklistRead)
async def update_blacklist_entry(
    entry_id: uuid.UUID,
    request: Request,
    payload: BlacklistUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await blacklist_service.update_blacklist_entry(db, request, current_user, entry_id, payload)


@router.delete("/{entry_id}", response_model=MessageResponse)
async def delete_blacklist_entry(
    entry_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await blacklist_service.delete_blacklist_entry(db, request, current_user, entry_id)
    return MessageResponse(detail="ลบข้อมูลบัญชีดำสำเร็จ")