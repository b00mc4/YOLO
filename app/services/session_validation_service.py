from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import select
from app.db.session import async_session_maker
from app.models.group import Group
from app.models.user import User


async def is_session_still_valid(user_id: uuid.UUID, village_id: uuid.UUID | None, ticket_password_changed_at: datetime) -> bool:
    async with async_session_maker() as db:
        user_result = await db.execute(select(User.is_active, User.password_changed_at).where(User.id == user_id))
        user_row = user_result.one_or_none()
        
        if user_row is None:
            return False
            
        user_is_active, db_password_changed_at = user_row

        if not user_is_active:
            return False
            
        from datetime import timezone
        if db_password_changed_at.tzinfo is None:
            db_password_changed_at = db_password_changed_at.replace(tzinfo=timezone.utc)
        if ticket_password_changed_at.tzinfo is None:
            ticket_password_changed_at = ticket_password_changed_at.replace(tzinfo=timezone.utc)
            
        if db_password_changed_at > ticket_password_changed_at:
            return False

        if village_id is None:
            return True

        village_result = await db.execute(select(Group.is_active).where(Group.id == village_id))
        village_is_active = village_result.scalar_one_or_none()

        return bool(village_is_active)