from __future__ import annotations
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.db.session import async_session_maker
from app.services import camera_service

settings = get_settings()
logger = logging.getLogger(__name__)


async def _startup_camera_resync() -> None:
    try:
        async with async_session_maker() as db:
            await camera_service.resync_all_cameras_on_startup(db)
    except Exception:
        logger.exception("Startup camera resync with MediaMTX failed")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await _startup_camera_resync()
    yield


app = FastAPI(title="License Plate Detection API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router)