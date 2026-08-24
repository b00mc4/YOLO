from __future__ import annotations
from fastapi import APIRouter
from app.services import mediamtx_auth_service

router = APIRouter(prefix="/mediamtx", tags=["mediamtx"])


@router.get("/jwks")
async def get_jwks() -> dict:
    return mediamtx_auth_service.get_jwks()