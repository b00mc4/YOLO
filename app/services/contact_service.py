from __future__ import annotations

import uuid

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact, ContactType
from app.models.user import User, UserRole
from app.schemas.common import PaginatedResponse
from app.schemas.contact import ContactCreate, ContactRead, ContactUpdate
from app.services import audit_service


async def _get_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _verify_write_scope(current_user: User, target_village_id: uuid.UUID | None) -> None:
    if current_user.role == UserRole.SUPERADMIN:
        return
    if current_user.role == UserRole.ADMIN:
        if target_village_id != current_user.village_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to manage contacts outside your village",
            )
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


async def _resolve_target_user(
    db: AsyncSession,
    current_user: User,
    requested_user_id: uuid.UUID | None,
) -> User:
    if requested_user_id is None or requested_user_id == current_user.id:
        return current_user

    target = await _get_user_or_404(db, requested_user_id)
    _verify_write_scope(current_user, target.village_id)
    return target


async def _get_contact_or_404(db: AsyncSession, contact_id: uuid.UUID) -> tuple[Contact, uuid.UUID | None]:
    result = await db.execute(
        select(Contact, User.village_id)
        .join(User, Contact.user_id == User.id)
        .where(Contact.id == contact_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return row[0], row[1]


def _verify_contact_write_scope(
    current_user: User,
    contact: Contact,
    owner_village_id: uuid.UUID | None,
) -> None:
    if current_user.role == UserRole.SUPERADMIN:
        return
    if current_user.role == UserRole.ADMIN:
        if owner_village_id != current_user.village_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to manage contacts outside your village",
            )
        return
    if contact.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to manage another user's contact",
        )


def _validate_content_type_consistency(content_type: ContactType, custom_label: str | None) -> None:
    if content_type == ContactType.OTHER:
        if not custom_label:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="custom_label is required when content_type is 'other'",
            )
    elif custom_label is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="custom_label must not be set unless content_type is 'other'",
        )


async def create_contact(
    db: AsyncSession,
    request: Request,
    current_user: User,
    payload: ContactCreate,
) -> ContactRead:
    target_user = await _resolve_target_user(db, current_user, payload.user_id)

    contact = Contact(
        user_id=target_user.id,
        content_type=payload.content_type,
        custom_label=payload.custom_label,
        value=payload.value,
    )
    db.add(contact)

    await audit_service.log_action(
        db,
        request,
        action="contact_create",
        detail=f"added contact ({payload.content_type.value}) for user_id={target_user.id}",
        user_id=current_user.id,
        village_id=target_user.village_id,
    )

    await db.commit()
    await db.refresh(contact)
    return ContactRead.model_validate(contact)


async def list_contacts(
    db: AsyncSession,
    current_user: User,
    user_id_filter: uuid.UUID | None,
    village_id_filter: uuid.UUID | None,
    content_type_filter: ContactType | None,
    page: int,
    page_size: int,
) -> PaginatedResponse[ContactRead]:
    stmt = select(Contact).join(User, Contact.user_id == User.id)

    if current_user.role == UserRole.SUPERADMIN:
        if village_id_filter is not None:
            stmt = stmt.where(User.village_id == village_id_filter)
    else:
        stmt = stmt.where(User.village_id == current_user.village_id)

    if user_id_filter is not None:
        stmt = stmt.where(Contact.user_id == user_id_filter)
    if content_type_filter is not None:
        stmt = stmt.where(Contact.content_type == content_type_filter)

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()

    stmt = (
        stmt.order_by(Contact.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    return PaginatedResponse[ContactRead](
        items=[ContactRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


async def update_contact(
    db: AsyncSession,
    request: Request,
    current_user: User,
    contact_id: uuid.UUID,
    payload: ContactUpdate,
) -> ContactRead:
    contact, owner_village_id = await _get_contact_or_404(db, contact_id)
    _verify_contact_write_scope(current_user, contact, owner_village_id)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(contact, field, value)

    _validate_content_type_consistency(contact.content_type, contact.custom_label)

    await audit_service.log_action(
        db,
        request,
        action="contact_update",
        detail=f"updated contact ({contact.content_type.value}) id={contact.id}",
        user_id=current_user.id,
        village_id=owner_village_id,
    )

    await db.commit()
    await db.refresh(contact)
    return ContactRead.model_validate(contact)


async def delete_contact(
    db: AsyncSession,
    request: Request,
    current_user: User,
    contact_id: uuid.UUID,
) -> None:
    contact, owner_village_id = await _get_contact_or_404(db, contact_id)
    _verify_contact_write_scope(current_user, contact, owner_village_id)

    await audit_service.log_action(
        db,
        request,
        action="contact_delete",
        detail=f"removed contact ({contact.content_type.value}) id={contact.id}",
        user_id=current_user.id,
        village_id=owner_village_id,
    )

    await db.delete(contact)
    await db.commit()