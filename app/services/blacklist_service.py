from __future__ import annotations

import uuid

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import verify_village_scope
from app.models.blacklist import Blacklist
from app.models.user import User, UserRole
from app.schemas.blacklist import BlacklistCreate, BlacklistRead, BlacklistUpdate
from app.schemas.common import PaginatedResponse
from app.services import audit_service


def _resolve_village_id(current_user: User, requested_village_id: uuid.UUID | None) -> uuid.UUID:
    if current_user.role == UserRole.SUPERADMIN:
        if requested_village_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="village_id is required for superadmin",
            )
        return requested_village_id
    return current_user.village_id


async def _get_entry_or_404(db: AsyncSession, entry_id: uuid.UUID) -> Blacklist:
    result = await db.execute(select(Blacklist).where(Blacklist.id == entry_id))
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blacklist entry not found")
    return entry


async def create_blacklist_entry(
    db: AsyncSession,
    request: Request,
    current_user: User,
    payload: BlacklistCreate,
) -> BlacklistRead:
    village_id = _resolve_village_id(current_user, payload.village_id)

    entry = Blacklist(
        village_id=village_id,
        license_plate=payload.license_plate,
        province=payload.province,
        reason=payload.reason,
        added_by=current_user.id,
    )
    db.add(entry)

    await audit_service.log_action(
        db,
        request,
        action="blacklist_create",
        detail=f"added blacklist entry: {payload.license_plate} ({payload.province})",
        user_id=current_user.id,
        village_id=village_id,
    )

    await db.commit()
    await db.refresh(entry)
    return BlacklistRead.model_validate(entry)


async def list_blacklist_entries(
    db: AsyncSession,
    current_user: User,
    village_id: uuid.UUID | None,
    license_plate: str | None,
    province: str | None,
    page: int,
    page_size: int,
) -> PaginatedResponse[BlacklistRead]:
    stmt = select(Blacklist)

    if current_user.role == UserRole.SUPERADMIN:
        if village_id is not None:
            stmt = stmt.where(Blacklist.village_id == village_id)
    else:
        stmt = stmt.where(Blacklist.village_id == current_user.village_id)

    if license_plate is not None:
        stmt = stmt.where(Blacklist.license_plate.ilike(f"%{license_plate}%"))
    if province is not None:
        stmt = stmt.where(Blacklist.province == province)

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()

    stmt = (
        stmt.order_by(Blacklist.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    return PaginatedResponse[BlacklistRead](
        items=[BlacklistRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


async def update_blacklist_entry(
    db: AsyncSession,
    request: Request,
    current_user: User,
    entry_id: uuid.UUID,
    payload: BlacklistUpdate,
) -> BlacklistRead:
    entry = await _get_entry_or_404(db, entry_id)
    verify_village_scope(current_user, entry.village_id)

    entry.reason = payload.reason

    await audit_service.log_action(
        db,
        request,
        action="blacklist_update",
        detail=f"updated blacklist entry reason: {entry.license_plate} ({entry.province})",
        user_id=current_user.id,
        village_id=entry.village_id,
    )

    await db.commit()
    await db.refresh(entry)
    return BlacklistRead.model_validate(entry)


async def delete_blacklist_entry(
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
        action="blacklist_delete",
        detail=f"removed blacklist entry: {entry.license_plate} ({entry.province})",
        user_id=current_user.id,
        village_id=entry.village_id,
    )

    await db.delete(entry)
    await db.commit()