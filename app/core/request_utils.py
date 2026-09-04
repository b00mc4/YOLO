from fastapi import Request
from app.core.config import get_settings

settings = get_settings()

def get_client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            hops = [hop.strip() for hop in forwarded_for.split(",")]
            if len(hops) >= settings.trusted_proxy_hops:
                return hops[-settings.trusted_proxy_hops]
    return request.client.host if request.client else ""
