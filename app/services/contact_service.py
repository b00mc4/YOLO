from __future__ import annotations
import uuid
from fastapi import HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.contact import Contact, ContactType
from app.models.group import Group
from app.models.user import User, UserRole
from app.schemas.common import PaginatedResponse
from app.schemas.contact import (
    ContactCreate,
    ContactDirectoryEntry,
    ContactRead,
    ContactUpdate,
    UserContactsDetail,
)
from app.services import audit_service

_MAX_CONTACTS_PER_USER = 10

async def _get_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _verify_write_scope(current_user: User, target: User) -> None:
    if current_user.role == UserRole.SUPERADMIN:
        return
    if target.id == current_user.id:
        return
    if current_user.role == UserRole.ADMIN:
        if target.role != UserRole.USER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only a superadmin can manage an admin or superadmin's contacts",
            )
        if target.village_id != current_user.village_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to manage contacts outside your village",
            )
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


def _verify_directory_scope(current_user: User, target_village_id: uuid.UUID | None) -> None:
    if current_user.role == UserRole.SUPERADMIN:
        return
    if target_village_id is None:
        return
    if target_village_id != current_user.village_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to access this user's data",
        )


async def _resolve_target_user(
    db: AsyncSession,
    current_user: User,
    requested_user_id: uuid.UUID | None,
) -> User:
    if requested_user_id is None or requested_user_id == current_user.id:
        return current_user

    target = await _get_user_or_404(db, requested_user_id)
    _verify_write_scope(current_user, target)
    return target


async def _get_contact_or_404(db: AsyncSession, contact_id: uuid.UUID) -> tuple[Contact, User]:
    result = await db.execute(
        select(Contact, User)
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
    owner: User,
) -> None:
    if current_user.role == UserRole.SUPERADMIN:
        return
    if contact.user_id == current_user.id:
        return
    if current_user.role == UserRole.ADMIN:
        if owner.role != UserRole.USER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only a superadmin can manage an admin or superadmin's contacts",
            )
        if owner.village_id != current_user.village_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to manage contacts outside your village",
            )
        return
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

    count_result = await db.execute(
        select(func.count()).select_from(Contact).where(Contact.user_id == target_user.id)
    )
    if count_result.scalar_one() >= _MAX_CONTACTS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User already has the maximum of {_MAX_CONTACTS_PER_USER} contacts",
        )

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


async def get_user_contacts_detail(
    db: AsyncSession,
    current_user: User,
    user_id: uuid.UUID,
) -> UserContactsDetail:
    result = await db.execute(
        select(User, Group.name)
        .outerjoin(Group, User.village_id == Group.id)
        .where(User.id == user_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    target_user, village_name = row
    _verify_directory_scope(current_user, target_user.village_id)

    contacts_result = await db.execute(
        select(Contact)
        .where(Contact.user_id == target_user.id)
        .order_by(Contact.created_at.desc())
    )
    contacts = contacts_result.scalars().all()

    return UserContactsDetail(
        user_id=target_user.id,
        username=target_user.username,
        fullname=target_user.fullname,
        village_id=target_user.village_id,
        village_name=village_name,
        contacts=[ContactRead.model_validate(contact) for contact in contacts],
    )


def _build_directory_scope_filter(current_user: User, village_id_filter: uuid.UUID | None):
    if current_user.role == UserRole.SUPERADMIN:
        if village_id_filter is None:
            return None
        return or_(User.village_id == village_id_filter, User.role == UserRole.SUPERADMIN)
    return or_(User.village_id == current_user.village_id, User.role == UserRole.SUPERADMIN)


async def list_contact_directory(
    db: AsyncSession,
    current_user: User,
    village_id_filter: uuid.UUID | None,
    search: str | None,
    page: int,
    page_size: int,
) -> PaginatedResponse[ContactDirectoryEntry]:
    contact_count_subquery = (
        select(func.count())
        .select_from(Contact)
        .where(Contact.user_id == User.id)
        .scalar_subquery()
    )

    stmt = select(User, Group.name, contact_count_subquery.label("contact_count")).outerjoin(
        Group, User.village_id == Group.id
    )
    count_stmt = select(func.count()).select_from(User)

    scope_filter = _build_directory_scope_filter(current_user, village_id_filter)
    if scope_filter is not None:
        stmt = stmt.where(scope_filter)
        count_stmt = count_stmt.where(scope_filter)

    if search:
        pattern = f"%{search}%"
        search_filter = or_(User.fullname.ilike(pattern), User.username.ilike(pattern))
        stmt = stmt.where(search_filter)
        count_stmt = count_stmt.where(search_filter)

    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    stmt = stmt.order_by(User.fullname).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    rows = result.all()

    items = [
        ContactDirectoryEntry(
            user_id=user.id,
            username=user.username,
            fullname=user.fullname,
            role=user.role,
            village_id=user.village_id,
            village_name=village_name,
            contact_count=contact_count,
        )
        for user, village_name, contact_count in rows
    ]

    return PaginatedResponse[ContactDirectoryEntry](
        items=items,
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
    contact, owner = await _get_contact_or_404(db, contact_id)
    _verify_contact_write_scope(current_user, contact, owner)

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
        village_id=owner.village_id,
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
    contact, owner = await _get_contact_or_404(db, contact_id)
    _verify_contact_write_scope(current_user, contact, owner)

    await audit_service.log_action(
        db,
        request,
        action="contact_delete",
        detail=f"removed contact ({contact.content_type.value}) id={contact.id}",
        user_id=current_user.id,
        village_id=owner.village_id,
    )

    await db.delete(contact)
    await db.commit()