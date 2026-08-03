from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.contact import ContactCreate, ContactRead, ContactUpdate, UserContactsDetail
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


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await contact_service.delete_contact(db, request, current_user, contact_id)