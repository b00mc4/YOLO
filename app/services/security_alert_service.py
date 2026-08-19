from __future__ import annotations
import asyncio
import uuid
from app.core.config import get_settings
from app.core.sse_channel import SSEChannel
from app.models.user import User, UserRole

settings = get_settings()

_channel = SSEChannel(ticket_expire_seconds=settings.sse_ticket_expire_seconds)


def issue_ticket(current_user: User) -> str:
    scope_village_id = None if current_user.role == UserRole.SUPERADMIN else current_user.village_id
    return _channel.issue_ticket(scope_village_id)


def resolve_ticket(raw_token: str) -> uuid.UUID | None:
    return _channel.resolve_ticket(raw_token)


def subscribe(village_id: uuid.UUID | None) -> asyncio.Queue:
    return _channel.subscribe(village_id)


def unsubscribe(village_id: uuid.UUID | None, queue: asyncio.Queue) -> None:
    _channel.unsubscribe(village_id, queue)


async def publish(village_id: uuid.UUID, event: str, data: dict) -> None:
    await _channel.publish(village_id, event, data)


async def publish_global(event: str, data: dict) -> None:
    await _channel.publish_global(event, data)