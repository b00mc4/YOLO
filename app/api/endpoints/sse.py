from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request, status
from sse_starlette.sse import EventSourceResponse

from app.api.deps import require_roles
from app.models.user import User, UserRole
from app.schemas.sse import SSETicketResponse
from app.services import sse_service

router = APIRouter(prefix="/sse", tags=["sse"])

_ALLOWED_ROLES = (UserRole.ADMIN, UserRole.USER)
_PING_INTERVAL_SECONDS = 15


@router.post("/ticket", response_model=SSETicketResponse, status_code=status.HTTP_201_CREATED)
async def create_sse_ticket(
    current_user: User = Depends(require_roles(*_ALLOWED_ROLES)),
):
    ticket = sse_service.issue_ticket(current_user)
    return SSETicketResponse(ticket=ticket)


@router.get("/alerts")
async def stream_alerts(request: Request, ticket: str = Query(...)):
    village_id = sse_service.resolve_ticket(ticket)
    queue = sse_service.subscribe(village_id)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_PING_INTERVAL_SECONDS)
                    yield {"event": event["event"], "data": json.dumps(event["data"], default=str)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            sse_service.unsubscribe(village_id, queue)

    return EventSourceResponse(event_generator())