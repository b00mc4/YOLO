from __future__ import annotations
from datetime import datetime, timezone
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User, UserRole
from app.schemas.security_alert import LoginBruteforceAlertPayload, LoginBruteforceAlertPayloadGlobal
from app.services import audit_service, notification_service, security_alert_service
from app.db.session import async_session_maker


async def record_bruteforce_audit(
    db: AsyncSession,
    request: Request,
    username: str,
    user: User | None,
    locked_for_seconds: float,
) -> None:
    await audit_service.log_action(
        db,
        request,
        action="login_bruteforce_detected",
        detail=(
            f"account locked for {locked_for_seconds:.0f}s after repeated failed "
            f"login attempts for username: {username}"
        ),
        user_id=user.id if user is not None else None,
        village_id=user.village_id if user is not None else None,
    )


async def publish_bruteforce_alert(
    username: str,
    user: User | None,
    locked_for_seconds: float,
    ip_address: str,
) -> None:
    occurred_at = datetime.now(timezone.utc)
    user_id = user.id if user is not None else None
    village_id = user.village_id if user is not None else None

    detail = (
        f"account locked for {locked_for_seconds:.0f}s after repeated failed "
        f"login attempts for username: {username}"
    )
    async with async_session_maker() as db:
        if village_id is not None:
            await notification_service.notify_village(
                db, village_id, "login_bruteforce_detected", detail, roles=(UserRole.ADMIN,)
            )
        await notification_service.notify_superadmins(db, "login_bruteforce_detected", detail)
        await db.commit()


    if village_id is not None:
        village_payload = LoginBruteforceAlertPayload(
            username=username,
            user_id=user_id,
            ip_address=ip_address,
            locked_for_seconds=locked_for_seconds,
            occurred_at=occurred_at,
        )
        await security_alert_service.publish(
            village_id,
            "login_bruteforce_detected",
            village_payload.model_dump(mode="json"),
        )

    global_payload = LoginBruteforceAlertPayloadGlobal(
        username=username,
        user_id=user_id,
        ip_address=ip_address,
        locked_for_seconds=locked_for_seconds,
        occurred_at=occurred_at,
        village_id=village_id,
    )
    await security_alert_service.publish_global(
        "login_bruteforce_detected",
        global_payload.model_dump(mode="json"),
    )