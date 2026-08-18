from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.whitelist import WhitelistCategory
from app.schemas.whitelist import WhitelistCreate, WhitelistRead, WhitelistUpdate
from app.schemas.common import MessageResponse, PaginatedResponse
from app.services import whitelist_service

router = APIRouter(prefix="/whitelist", tags=["whitelist"])


@router.post("", response_model=WhitelistRead, status_code=status.HTTP_201_CREATED)
async def create_whitelist_entry(
    request: Request,
    payload: WhitelistCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await whitelist_service.create_whitelist_entry(db, request, current_user, payload)


@router.get("", response_model=PaginatedResponse[WhitelistRead])
async def list_whitelist_entries(
    village_id: uuid.UUID | None = Query(default=None),
    category: WhitelistCategory | None = Query(default=None),
    name: str | None = Query(default=None),
    license_plate: str | None = Query(default=None),
    province: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await whitelist_service.list_whitelist_entries(
        db, current_user, village_id, category, name, license_plate, province, page, page_size
    )


@router.patch("/{entry_id}", response_model=WhitelistRead)
async def update_whitelist_entry(
    entry_id: uuid.UUID,
    request: Request,
    payload: WhitelistUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await whitelist_service.update_whitelist_entry(db, request, current_user, entry_id, payload)


@router.delete("/{entry_id}", response_model=MessageResponse)
async def delete_whitelist_entry(
    entry_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await whitelist_service.delete_whitelist_entry(db, request, current_user, entry_id)
    return MessageResponse(detail="Whitelist entry deleted successfully")