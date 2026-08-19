from __future__ import annotations
import uuid
from sqlalchemy import select
from app.db.session import async_session_maker
from app.models.group import Group
from app.models.user import User


async def is_session_still_valid(user_id: uuid.UUID, village_id: uuid.UUID | None) -> bool:
    async with async_session_maker() as db:
        user_result = await db.execute(select(User.is_active).where(User.id == user_id))
        user_is_active = user_result.scalar_one_or_none()

        if not user_is_active:
            return False

        if village_id is None:
            return True

        village_result = await db.execute(select(Group.is_active).where(Group.id == village_id))
        village_is_active = village_result.scalar_one_or_none()

        return bool(village_is_active)