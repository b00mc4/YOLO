from __future__ import annotations
from app.core.config import get_settings
from app.core.sse_channel import ChannelService

settings = get_settings()

_MAX_CONNECTIONS_PER_USER = 5
_QUEUE_MAXSIZE = 100

alerts = ChannelService(
    ticket_expire_seconds=settings.sse_ticket_expire_seconds,
    max_connections_per_user=_MAX_CONNECTIONS_PER_USER,
    queue_maxsize=_QUEUE_MAXSIZE,
)

security_alerts = ChannelService(
    ticket_expire_seconds=settings.sse_ticket_expire_seconds,
    max_connections_per_user=_MAX_CONNECTIONS_PER_USER,
    queue_maxsize=_QUEUE_MAXSIZE,
)