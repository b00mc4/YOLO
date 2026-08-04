from __future__ import annotations
import uuid
from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import verify_village_scope
from app.models.camera import Camera
from app.models.group import Group
from app.models.user import User, UserRole
from app.schemas.camera import CameraCreate, CameraUpdate
from app.schemas.common import PaginatedResponse
from app.services import audit_service

async def _get_village_or_404(db: AsyncSession, village_id: uuid.UUID) -> Group:
    result = await db.execute(select(Group).where(Group.id == village_id))
    village = result.scalar_one_or_none()
    if village is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Village not found")
    return village

async def create_camera(
    db: AsyncSession,
    request: Request,
    current_user: User,
    payload: CameraCreate,
) -> Camera:
    if current_user.role == UserRole.ADMIN:
        village_id = current_user.village_id
    else:
        village_id = payload.village_id
        await _get_village_or_404(db, village_id)

    camera = Camera(
        village_id=village_id,
        name=payload.name,
        lat=payload.lat,
        long=payload.long,
        stream_url=payload.stream_url,
        is_active=True,
    )
    db.add(camera)
    await db.flush()

    await audit_service.log_action(
        db,
        request,
        action="camera_created",
        detail=f"camera created: {camera.name}",
        user_id=current_user.id,
        village_id=village_id,
    )
    await db.commit()
    await db.refresh(camera)
    return camera

async def get_camera(db: AsyncSession, current_user: User, camera_id: uuid.UUID) -> Camera:
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()

    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    verify_village_scope(current_user, camera.village_id)
    return camera

async def list_cameras(
    db: AsyncSession,
    current_user: User,
    village_id_filter: uuid.UUID | None,
    is_active_filter: bool | None,
    page: int,
    page_size: int,
) -> PaginatedResponse[Camera]:
    stmt = select(Camera)
    count_stmt = select(func.count()).select_from(Camera)

    if current_user.role == UserRole.ADMIN:
        stmt = stmt.where(Camera.village_id == current_user.village_id)
        count_stmt = count_stmt.where(Camera.village_id == current_user.village_id)
    elif village_id_filter is not None:
        stmt = stmt.where(Camera.village_id == village_id_filter)
        count_stmt = count_stmt.where(Camera.village_id == village_id_filter)

    if is_active_filter is not None:
        stmt = stmt.where(Camera.is_active == is_active_filter)
        count_stmt = count_stmt.where(Camera.is_active == is_active_filter)

    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    stmt = stmt.order_by(Camera.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)

async def update_camera(
    db: AsyncSession,
    request: Request,
    current_user: User,
    camera_id: uuid.UUID,
    payload: CameraUpdate,
) -> Camera:
    camera = await get_camera(db, current_user, camera_id)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(camera, field, value)

    await audit_service.log_action(
        db,
        request,
        action="camera_updated",
        detail=f"camera updated: {camera.name}",
        user_id=current_user.id,
        village_id=camera.village_id,
    )
    await db.commit()
    await db.refresh(camera)
    return camera

async def delete_camera(
    db: AsyncSession,
    request: Request,
    current_user: User,
    camera_id: uuid.UUID,
) -> None:
    camera = await get_camera(db, current_user, camera_id)

    if not camera.is_active:
        return

    camera.is_active = False

    await audit_service.log_action(
        db,
        request,
        action="camera_deleted",
        detail=f"camera deleted: {camera.name}",
        user_id=current_user.id,
        village_id=camera.village_id,
    )
    await db.commit()