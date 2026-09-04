from __future__ import annotations
import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.db.session import async_session_maker
from app.services import ai_vision_service, auth_service, camera_service, camera_verification_service, mediamtx_service, notification_service

_NOTIFICATION_CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60
_AUTH_CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60

settings = get_settings()
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

_STARTUP_RESYNC_MAX_ATTEMPTS = 3
_STARTUP_RESYNC_BACKOFF_BASE_SECONDS = 2.0


async def _notification_cleanup_loop() -> None:
    consecutive_errors = 0
    while True:
        if consecutive_errors > 0:
            backoff = min(3600, 10 * (2 ** min(consecutive_errors - 1, 10)))
            await asyncio.sleep(backoff)
        else:
            await asyncio.sleep(_NOTIFICATION_CLEANUP_INTERVAL_SECONDS)
            
        try:
            async with async_session_maker() as db:
                deleted = await notification_service.cleanup_old_notifications(db)
            if deleted:
                logger.info("Notification cleanup: removed %s expired notification(s)", deleted)
            consecutive_errors = 0
        except Exception:
            consecutive_errors += 1
            logger.exception("Notification cleanup loop iteration failed (error count: %s)", consecutive_errors)

async def _auth_cleanup_loop() -> None:
    consecutive_errors = 0
    while True:
        if consecutive_errors > 0:
            backoff = min(3600, 10 * (2 ** min(consecutive_errors - 1, 10)))
            await asyncio.sleep(backoff)
        else:
            await asyncio.sleep(_AUTH_CLEANUP_INTERVAL_SECONDS)
            
        try:
            async with async_session_maker() as db:
                deleted = await auth_service.cleanup_expired_refresh_tokens(db)
            if deleted:
                logger.info("Auth cleanup: removed %s expired refresh token(s)", deleted)
            consecutive_errors = 0
        except Exception:
            consecutive_errors += 1
            logger.exception("Auth cleanup loop iteration failed (error count: %s)", consecutive_errors)

async def _image_cleanup_loop() -> None:
    consecutive_errors = 0
    while True:
        if consecutive_errors > 0:
            backoff = min(3600, 10 * (2 ** min(consecutive_errors - 1, 10)))
            await asyncio.sleep(backoff)
        else:
            await asyncio.sleep(86400) # ทำความสะอาดรูปขยะวันละ 1 ครั้ง
            
        try:
            async with async_session_maker() as db:
                from app.services import detection_service
                deleted = await detection_service.cleanup_orphaned_images(db)
            if deleted:
                logger.info("Image cleanup: removed %s orphaned image(s)", deleted)
            consecutive_errors = 0
        except Exception:
            consecutive_errors += 1
            logger.exception("Image cleanup loop iteration failed (error count: %s)", consecutive_errors)

async def _startup_camera_resync_background() -> None:
    for attempt in range(1, _STARTUP_RESYNC_MAX_ATTEMPTS + 1):
        try:
            async with async_session_maker() as db:
                await camera_service.resync_all_cameras_on_startup(db)
            return
        except Exception:
            logger.exception(
                "Startup camera resync failed (attempt %s/%s)",
                attempt, _STARTUP_RESYNC_MAX_ATTEMPTS,
            )

        if attempt < _STARTUP_RESYNC_MAX_ATTEMPTS:
            await asyncio.sleep(_STARTUP_RESYNC_BACKOFF_BASE_SECONDS ** attempt)

    logger.error(
        "Startup camera resync gave up after %s attempts; "
        "recover manually via POST /api/cameras/resync-all",
        _STARTUP_RESYNC_MAX_ATTEMPTS,
    )


async def _resume_camera_verification_background() -> None:
    try:
        await camera_verification_service.resume_pending_verifications()
    except Exception:
        logger.exception("Failed to resume pending camera verifications on startup")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    try:
        async with async_session_maker() as db:
            restored = await auth_service.restore_active_sessions(db)
        logger.info("Restored %s active session(s) into memory", restored)
    except Exception:
        logger.exception("Failed to restore active sessions on startup")

    resync_task = asyncio.create_task(_startup_camera_resync_background())
    app.state.startup_resync_task = resync_task

    verification_resume_task = asyncio.create_task(_resume_camera_verification_background())
    app.state.startup_verification_resume_task = verification_resume_task

    clean_notification_task = asyncio.create_task(_notification_cleanup_loop())
    app.state.startup_clean_notification_task = clean_notification_task

    clean_auth_task = asyncio.create_task(_auth_cleanup_loop())
    app.state.startup_clean_auth_task = clean_auth_task

    clean_image_task = asyncio.create_task(_image_cleanup_loop())
    app.state.startup_clean_image_task = clean_image_task

    yield

    for task in (resync_task, verification_resume_task, clean_notification_task, clean_auth_task, clean_image_task):
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
    
    await mediamtx_service.close()
    await ai_vision_service.close()


app = FastAPI(
    title="License Plate Detection API", 
    lifespan=lifespan
)

@app.get("/health", include_in_schema=False)
async def health_check():
    return {"status": "ok"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router)