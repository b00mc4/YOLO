from __future__ import annotations
import uuid
from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import verify_village_scope
from app.models.blacklist import Blacklist
from app.models.whitelist import Whitelist, WhitelistCategory
from app.models.user import User, UserRole
from app.schemas.common import PaginatedResponse
from app.schemas.whitelist import WhitelistCreate, WhitelistRead, WhitelistUpdate
from app.services import audit_service, village_service


async def _resolve_village_id(
    db: AsyncSession,
    current_user: User,
    requested_village_id: uuid.UUID | None,
) -> uuid.UUID:
    if current_user.role == UserRole.SUPERADMIN:
        if requested_village_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="village_id is required for superadmin",
            )
        await village_service.get_village(db, requested_village_id)
        return requested_village_id
    return current_user.village_id


async def _get_entry_or_404(db: AsyncSession, entry_id: uuid.UUID) -> Whitelist:
    result = await db.execute(select(Whitelist).where(Whitelist.id == entry_id))
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Whitelist entry not found")
    return entry


def _build_whitelist_list_scope_filters(
    current_user: User, village_id_filter: uuid.UUID | None
) -> list:
    if current_user.role == UserRole.SUPERADMIN:
        if village_id_filter is not None:
            return [Whitelist.village_id == village_id_filter]
        return []

    if village_id_filter is not None and village_id_filter != current_user.village_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to specify village_id for this role",
        )
    return [Whitelist.village_id == current_user.village_id]


async def _check_not_blacklisted(
    db: AsyncSession,
    village_id: uuid.UUID,
    license_plate: str,
    province: str,
) -> None:
    result = await db.execute(
        select(Blacklist.id)
        .where(
            Blacklist.village_id == village_id,
            Blacklist.license_plate == license_plate,
            Blacklist.province == province,
        )
        .limit(1)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This license plate is currently blacklisted in this village",
        )


async def create_whitelist_entry(
    db: AsyncSession,
    request: Request,
    current_user: User,
    payload: WhitelistCreate,
) -> WhitelistRead:
    village_id = await _resolve_village_id(db, current_user, payload.village_id)
    await _check_not_blacklisted(db, village_id, payload.license_plate, payload.province)

    entry = Whitelist(
        village_id=village_id,
        category=payload.category,
        name=payload.name,
        license_plate=payload.license_plate,
        province=payload.province,
        note=payload.note,
        added_by=current_user.id,
    )
    db.add(entry)

    await audit_service.log_action(
        db,
        request,
        action="whitelist_create",
        detail=(
            f"added whitelist entry ({payload.category.value}): "
            f"{payload.name} - {payload.license_plate} ({payload.province})"
        ),
        user_id=current_user.id,
        village_id=village_id,
    )

    await db.commit()
    await db.refresh(entry)
    return WhitelistRead.model_validate(entry)


async def list_whitelist_entries(
    db: AsyncSession,
    current_user: User,
    village_id: uuid.UUID | None,
    category: WhitelistCategory | None,
    name: str | None,
    license_plate: str | None,
    province: str | None,
    page: int,
    page_size: int,
) -> PaginatedResponse[WhitelistRead]:
    scope_filters = _build_whitelist_list_scope_filters(current_user, village_id)
    stmt = select(Whitelist).where(*scope_filters)

    if category is not None:
        stmt = stmt.where(Whitelist.category == category)
    if name is not None:
        stmt = stmt.where(Whitelist.name.ilike(f"%{name}%"))
    if license_plate is not None:
        stmt = stmt.where(Whitelist.license_plate.ilike(f"%{license_plate}%"))
    if province is not None:
        stmt = stmt.where(Whitelist.province == province)

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()

    stmt = (
        stmt.order_by(Whitelist.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    return PaginatedResponse[WhitelistRead](
        items=[WhitelistRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


async def update_whitelist_entry(
    db: AsyncSession,
    request: Request,
    current_user: User,
    entry_id: uuid.UUID,
    payload: WhitelistUpdate,
) -> WhitelistRead:
    entry = await _get_entry_or_404(db, entry_id)
    verify_village_scope(current_user, entry.village_id)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entry, field, value)

    await _check_not_blacklisted(db, entry.village_id, entry.license_plate, entry.province)

    await audit_service.log_action(
        db,
        request,
        action="whitelist_update",
        detail=(
            f"updated whitelist entry ({entry.category.value}): "
            f"{entry.name} - {entry.license_plate} ({entry.province})"
        ),
        user_id=current_user.id,
        village_id=entry.village_id,
    )

    await db.commit()
    await db.refresh(entry)
    return WhitelistRead.model_validate(entry)


async def delete_whitelist_entry(
    db: AsyncSession,
    request: Request,
    current_user: User,
    entry_id: uuid.UUID,
) -> None:
    entry = await _get_entry_or_404(db, entry_id)
    verify_village_scope(current_user, entry.village_id)

    await audit_service.log_action(
        db,
        request,
        action="whitelist_delete",
        detail=(
            f"removed whitelist entry ({entry.category.value}): "
            f"{entry.name} - {entry.license_plate} ({entry.province})"
        ),
        user_id=current_user.id,
        village_id=entry.village_id,
    )

    await db.delete(entry)
    await db.commit()