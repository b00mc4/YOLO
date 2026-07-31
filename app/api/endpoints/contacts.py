from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.contact import ContactType
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.contact import ContactCreate, ContactRead, ContactUpdate
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


@router.get("", response_model=PaginatedResponse[ContactRead])
async def list_contacts(
    user_id: uuid.UUID | None = Query(default=None),
    village_id: uuid.UUID | None = Query(default=None),
    content_type: ContactType | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await contact_service.list_contacts(
        db, current_user, user_id, village_id, content_type, page, page_size
    )


@router.patch("/{contact_id}", response_model=ContactRead)
async def update_contact(
    contact_id: uuid.UUID,
    request: Request,
    payload: ContactUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await contact_service.update_contact(db, request, current_user, contact_id, payload)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await contact_service.delete_contact(db, request, current_user, contact_id)