from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.contact import (
    ContactCreate,
    ContactDirectoryEntry,
    ContactRead,
    ContactUpdate,
    UserContactsDetail,
)
from app.services import contact_service

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.post("", response_model=ContactRead, status_code=status.HTTP_201_CREATED)
async def create_contact(
    request: Request,
    payload: ContactCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await contact_service.create_contact(db, request, current_user, payload)


@router.get("", response_model=PaginatedResponse[ContactDirectoryEntry])
async def list_contacts(
    village_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await contact_service.list_contact_directory(
        db, current_user, village_id, search, page, page_size
    )


@router.get("/users/{user_id}", response_model=UserContactsDetail)
async def get_user_contacts_detail(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await contact_service.get_user_contacts_detail(db, current_user, user_id)


@router.patch("/{contact_id}", response_model=ContactRead)
async def update_contact(
    contact_id: uuid.UUID,
    request: Request,
    payload: ContactUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await contact_service.update_contact(db, request, current_user, contact_id, payload)


@router.delete("/{contact_id}", response_model=MessageResponse)
async def delete_contact(
    contact_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await contact_service.delete_contact(db, request, current_user, contact_id)
    return MessageResponse(detail="Contact deleted successfully")