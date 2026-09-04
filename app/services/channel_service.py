from __future__ import annotations
from app.core.config import get_settings
from app.core.sse_channel import ChannelService

settings = get_settings()

alerts = ChannelService(
    ticket_expire_seconds=settings.sse_ticket_expire_seconds,
    max_connections_per_user=settings.channel_max_connections_per_user,
    queue_maxsize=settings.channel_queue_size,
)

security_alerts = ChannelService(
    ticket_expire_seconds=settings.sse_ticket_expire_seconds,
    max_connections_per_user=settings.channel_max_connections_per_user,
    queue_maxsize=settings.channel_queue_size,
)