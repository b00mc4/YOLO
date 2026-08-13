from __future__ import annotations
import uuid
from fastapi import BackgroundTasks, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.camera import Camera
from app.models.group import Group
from app.models.user import User, UserRole
from app.schemas.camera import CameraBasicRead
from app.schemas.common import PaginatedResponse
from app.schemas.village import VillageCreate, VillageDetailRead, VillageMemberSummary, VillageUpdate
from app.services import audit_service, camera_service

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


async def get_village_detail(
    db: AsyncSession,
    current_user: User,
    village_id: uuid.UUID,
) -> VillageDetailRead:
    village = await get_village(db, village_id)

    if current_user.role != UserRole.SUPERADMIN and current_user.village_id != village_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to access this village",
        )

    camera_result = await db.execute(
        select(Camera)
        .where(Camera.village_id == village_id)
        .order_by(Camera.created_at.desc())
    )
    cameras = camera_result.scalars().all()

    member_result = await db.execute(
        select(User).where(User.village_id == village_id).order_by(User.created_at.desc())
    )
    members = member_result.scalars().all()

    return VillageDetailRead(
        id=village.id,
        name=village.name,
        is_active=village.is_active,
        created_at=village.created_at,
        cameras=[CameraBasicRead.model_validate(camera) for camera in cameras],
        members=[VillageMemberSummary.model_validate(member) for member in members],
    )


async def list_villages(
    db: AsyncSession,
    current_user: User,
    is_active_filter: bool | None,
    search: str | None,
    page: int,
    page_size: int,
) -> PaginatedResponse[Group]:
    stmt = select(Group)
    count_stmt = select(func.count()).select_from(Group)

    if current_user.role != UserRole.SUPERADMIN:
        stmt = stmt.where(Group.id == current_user.village_id)
        count_stmt = count_stmt.where(Group.id == current_user.village_id)

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
    background_tasks: BackgroundTasks,
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
    is_active_changed = "is_active" in update_data and update_data["is_active"] != previous_is_active
    if is_active_changed:
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

    if is_active_changed:
        if update_data["is_active"]:
            background_tasks.add_task(camera_service.activate_village_cameras, village.id)
        else:
            background_tasks.add_task(camera_service.deactivate_village_cameras, village.id)

    return village