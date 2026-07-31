from __future__ import annotations
import uuid
from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.group import Group
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.village import VillageCreate, VillageUpdate
from app.services import audit_service

async def create_village(
    db: AsyncSession,
    request: Request,
    current_user: User,
    payload: VillageCreate,
) -> Group:
    village = Group(name=payload.name, is_active=True)
    db.add(village)
    await db.flush()

    await audit_service.log_action(
        db,
        request,
        action="village_created",
        detail=f"village created: {village.name}",
        user_id=current_user.id,
        village_id=village.id,
    )
    await db.commit()
    await db.refresh(village)
    return village


async def get_village(db: AsyncSession, village_id: uuid.UUID) -> Group:
    result = await db.execute(select(Group).where(Group.id == village_id))
    village = result.scalar_one_or_none()

    if village is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Village not found")

    return village


async def list_villages(
    db: AsyncSession,
    is_active_filter: bool | None,
    search: str | None,
    page: int,
    page_size: int,
) -> PaginatedResponse[Group]:
    stmt = select(Group)
    count_stmt = select(func.count()).select_from(Group)

    if is_active_filter is not None:
        stmt = stmt.where(Group.is_active == is_active_filter)
        count_stmt = count_stmt.where(Group.is_active == is_active_filter)

    if search:
        stmt = stmt.where(Group.name.ilike(f"%{search}%"))
        count_stmt = count_stmt.where(Group.name.ilike(f"%{search}%"))

    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    stmt = stmt.order_by(Group.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


async def update_village(
    db: AsyncSession,
    request: Request,
    current_user: User,
    village_id: uuid.UUID,
    payload: VillageUpdate,
) -> Group:
    village = await get_village(db, village_id)

    update_data = payload.model_dump(exclude_unset=True)
    previous_is_active = village.is_active

    for field, value in update_data.items():
        setattr(village, field, value)

    action = "village_updated"
    detail = f"village updated: {village.name}"
    if "is_active" in update_data and update_data["is_active"] != previous_is_active:
        if update_data["is_active"]:
            action = "village_activated"
            detail = f"village activated: {village.name}"
        else:
            action = "village_deactivated"
            detail = f"village deactivated: {village.name}"

    await audit_service.log_action(
        db,
        request,
        action=action,
        detail=detail,
        user_id=current_user.id,
        village_id=village.id,
    )
    await db.commit()
    await db.refresh(village)
    return village