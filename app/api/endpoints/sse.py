from __future__ import annotations
import asyncio
import json
import uuid
from time import monotonic
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sse_starlette.sse import EventSourceResponse
from app.api.deps import require_roles
from app.core.config import get_settings
from app.core.connection_limit import ConnectionLimitExceeded
from app.core.sse_channel import CLOSE_SENTINEL
from app.models.user import User, UserRole
from app.schemas.presence import PresenceTicketResponse
from app.schemas.sse import SSETicketResponse
from app.services import channel_service, presence_service, session_validation_service
from app.core.error_messages import RealtimeErrors

router = APIRouter(prefix="/sse", tags=["sse"])

settings = get_settings()

_ALLOWED_ROLES = (UserRole.ADMIN, UserRole.USER, UserRole.SUPERADMIN)
_SECURITY_ALLOWED_ROLES = (UserRole.ADMIN, UserRole.SUPERADMIN)
_PING_INTERVAL_SECONDS = 15


def _connection_limit_exceeded_response(exc: ConnectionLimitExceeded) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=RealtimeErrors.too_many_connections(exc.max_connections),
    )


def _revalidation_due(last_revalidated_at: float) -> bool:
    return monotonic() - last_revalidated_at >= settings.sse_revalidation_interval_seconds


async def _base_event_generator(request: Request, user_id: uuid.UUID, village_id: uuid.UUID | None, ticket_password_changed_at: datetime, queue: asyncio.Queue | None):
    last_revalidated_at = monotonic()
    while True:
        if _revalidation_due(last_revalidated_at):
            if not await session_validation_service.is_session_still_valid(user_id, village_id, ticket_password_changed_at):
                break
            last_revalidated_at = monotonic()

        if queue is None:
            await asyncio.sleep(_PING_INTERVAL_SECONDS)
            continue

        if await request.is_disconnected():
            break

        try:
            event = await asyncio.wait_for(queue.get(), timeout=_PING_INTERVAL_SECONDS)
            if event is CLOSE_SENTINEL:
                break
            yield {"event": event["event"], "data": json.dumps(event["data"], default=str)}
        except asyncio.TimeoutError:
            yield {"event": "ping", "data": ""}


@router.post("/ticket", response_model=SSETicketResponse, status_code=status.HTTP_201_CREATED)
async def create_sse_ticket(
    current_user: User = Depends(require_roles(*_ALLOWED_ROLES)),
):
    ticket = channel_service.alerts.issue_ticket(current_user)
    return SSETicketResponse(ticket=ticket)


@router.get("/alerts")
async def stream_alerts(request: Request, ticket: str = Query(...)):
    user_id, village_id, password_changed_at = channel_service.alerts.resolve_ticket(ticket)

    try:
        channel_service.alerts.register_connection(user_id)
    except ConnectionLimitExceeded as exc:
        raise _connection_limit_exceeded_response(exc)

    queue = channel_service.alerts.subscribe(village_id)

    async def event_generator():
        try:
            async for event in _base_event_generator(request, user_id, village_id, password_changed_at, queue):
                yield event
        finally:
            channel_service.alerts.unsubscribe(village_id, queue)
            channel_service.alerts.unregister_connection(user_id)

    return EventSourceResponse(event_generator())


@router.post(
    "/security-alerts/ticket",
    response_model=SSETicketResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_security_alert_ticket(
    current_user: User = Depends(require_roles(*_SECURITY_ALLOWED_ROLES)),
):
    ticket = channel_service.security_alerts.issue_ticket(current_user)
    return SSETicketResponse(ticket=ticket)


@router.get("/security-alerts")
async def stream_security_alerts(request: Request, ticket: str = Query(...)):
    user_id, village_id, password_changed_at = channel_service.security_alerts.resolve_ticket(ticket)

    try:
        channel_service.security_alerts.register_connection(user_id)
    except ConnectionLimitExceeded as exc:
        raise _connection_limit_exceeded_response(exc)

    queue = channel_service.security_alerts.subscribe(village_id)

    async def event_generator():
        try:
            async for event in _base_event_generator(request, user_id, village_id, password_changed_at, queue):
                yield event
        finally:
            channel_service.security_alerts.unsubscribe(village_id, queue)
            channel_service.security_alerts.unregister_connection(user_id)

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
    except ConnectionLimitExceeded as exc:
        raise _connection_limit_exceeded_response(exc)

    watcher_queue = presence_service.register_watcher(ticket_data)

    async def event_generator():
        try:
            initial_snapshot = await presence_service.build_snapshot_for_ticket(ticket_data)
            if initial_snapshot is not None:
                yield {
                    "event": "presence_update",
                    "data": json.dumps(initial_snapshot, default=str),
                }

            async for event in _base_event_generator(request, ticket_data.user_id, ticket_data.village_id, ticket_data.password_changed_at, watcher_queue):
                yield event
        finally:
            presence_service.unregister_watcher(ticket_data, watcher_queue)
            await presence_service.unregister_connection(conn_id)

    return EventSourceResponse(event_generator())