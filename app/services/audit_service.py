from __future__ import annotations
import uuid
from datetime import datetime
from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit_log import AuditLog
from app.models.user import User, UserRole
from app.schemas.audit_log import AuditLogRead
from app.schemas.common import PaginatedResponse
from app.api.deps import get_client_ip


_DETAIL_MAX_LENGTH = 1000
_USER_AGENT_MAX_LENGTH = 512


async def log_action(
    db: AsyncSession,
    request: Request,
    action: str,
    detail: str,
    user_id: uuid.UUID | None = None,
    village_id: uuid.UUID | None = None,
):
    entry = AuditLog(
        village_id=village_id,
        user_id=user_id,
        action=action,
        detail=detail[:_DETAIL_MAX_LENGTH],
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent", "")[:_USER_AGENT_MAX_LENGTH],
    )
    db.add(entry)
    await db.flush()


async def list_audit_logs(
    db: AsyncSession,
    current_user: User,
    village_id_filter: uuid.UUID | None,
    user_id_filter: uuid.UUID | None,
    action_filter: str | None,
    created_at_from: datetime | None,
    created_at_to: datetime | None,
    page: int,
    page_size: int,
) -> PaginatedResponse[AuditLogRead]:
    stmt = select(AuditLog)

    if current_user.role == UserRole.SUPERADMIN:
        if village_id_filter is not None:
            stmt = stmt.where(AuditLog.village_id == village_id_filter)
    else:
        stmt = stmt.where(AuditLog.village_id == current_user.village_id)

    if user_id_filter is not None:
        stmt = stmt.where(AuditLog.user_id == user_id_filter)
    if action_filter is not None:
        stmt = stmt.where(AuditLog.action == action_filter)
    if created_at_from is not None:
        stmt = stmt.where(AuditLog.created_at >= created_at_from)
    if created_at_to is not None:
        stmt = stmt.where(AuditLog.created_at <= created_at_to)

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()

    stmt = (
        stmt.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    return PaginatedResponse[AuditLogRead](
        items=[AuditLogRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )