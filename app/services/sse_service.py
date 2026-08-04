from __future__ import annotations
import asyncio
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from app.core.config import get_settings
from app.core.security import generate_secure_token, hash_token
from app.models.user import User, UserRole

settings = get_settings()

_subscribers: dict[uuid.UUID, set[asyncio.Queue]] = defaultdict(set)
_global_subscribers: set[asyncio.Queue] = set()
_tickets: dict[str, tuple[uuid.UUID | None, datetime]] = {}


def issue_ticket(current_user: User) -> str:
    raw_token = generate_secure_token()
    expire_at = datetime.now(timezone.utc) + timedelta(seconds=settings.sse_ticket_expire_seconds)
    scope_village_id = None if current_user.role == UserRole.SUPERADMIN else current_user.village_id
    _tickets[hash_token(raw_token)] = (scope_village_id, expire_at)
    return raw_token


def resolve_ticket(raw_token: str) -> uuid.UUID | None:
    ticket = _tickets.pop(hash_token(raw_token), None)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired ticket")

    village_id, expire_at = ticket
    if expire_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired ticket")

    return village_id


def subscribe(village_id: uuid.UUID | None) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    if village_id is None:
        _global_subscribers.add(queue)
    else:
        _subscribers[village_id].add(queue)
    return queue


def unsubscribe(village_id: uuid.UUID | None, queue: asyncio.Queue) -> None:
    if village_id is None:
        _global_subscribers.discard(queue)
        return

    subscribers = _subscribers.get(village_id)
    if subscribers is None:
        return
    subscribers.discard(queue)
    if not subscribers:
        _subscribers.pop(village_id, None)


async def publish(village_id: uuid.UUID, event: str, data: dict) -> None:
    subscribers = _subscribers.get(village_id)
    if not subscribers:
        return
    for queue in list(subscribers):
        await queue.put({"event": event, "data": data})


async def publish_global(event: str, data: dict) -> None:
    if not _global_subscribers:
        return
    for queue in list(_global_subscribers):
        await queue.put({"event": event, "data": data})