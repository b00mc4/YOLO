from __future__ import annotations
import uuid
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit_log import AuditLog


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
        detail=detail,
        ip_address=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", ""),
    )
    db.add(entry)
    await db.flush()