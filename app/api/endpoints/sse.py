from __future__ import annotations
import asyncio
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sse_starlette.sse import EventSourceResponse
from app.api.deps import require_roles
from app.core.presence_limit import PresenceConnectionLimitExceeded
from app.models.user import User, UserRole
from app.schemas.presence import PresenceTicketResponse
from app.schemas.sse import SSETicketResponse
from app.services import presence_service, sse_service

router = APIRouter(prefix="/sse", tags=["sse"])

_ALLOWED_ROLES = (UserRole.ADMIN, UserRole.USER, UserRole.SUPERADMIN)
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


@router.post(
    "/presence/ticket",
    response_model=PresenceTicketResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_presence_ticket(
    village_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_roles(*_ALLOWED_ROLES)),
):
    ticket = presence_service.issue_presence_ticket(current_user, village_id)
    return PresenceTicketResponse(ticket=ticket)


@router.get("/presence")
async def stream_presence(request: Request, ticket: str = Query(...)):
    ticket_data = presence_service.resolve_presence_ticket(ticket)

    try:
        conn_id = await presence_service.register_connection(ticket_data)
    except PresenceConnectionLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many concurrent connections for this account "
                f"(max {exc.max_connections})"
            ),
        )

    watcher_queue = presence_service.register_watcher(ticket_data)

    async def event_generator():
        try:
            initial_snapshot = await presence_service.build_snapshot_for_ticket(ticket_data)
            if initial_snapshot is not None:
                yield {
                    "event": "presence_update",
                    "data": json.dumps(initial_snapshot, default=str),
                }

            while True:
                if await request.is_disconnected():
                    break

                if watcher_queue is None:
                    await asyncio.sleep(_PING_INTERVAL_SECONDS)
                    yield {"event": "ping", "data": ""}
                    continue

                try:
                    event = await asyncio.wait_for(
                        watcher_queue.get(), timeout=_PING_INTERVAL_SECONDS
                    )
                    yield {
                        "event": event["event"],
                        "data": json.dumps(event["data"], default=str),
                    }
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            presence_service.unregister_watcher(ticket_data, watcher_queue)
            await presence_service.unregister_connection(conn_id)

    return EventSourceResponse(event_generator())