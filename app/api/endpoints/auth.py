from __future__ import annotations
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import OAuth2PasswordRequestForm
from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginResponse,
    SetPasswordRequest,
    SetPasswordResponse,
    TokenResponse,
)
from app.schemas.common import MessageResponse
from app.services import auth_service
from app.api.deps import get_current_user, rate_limit_by_ip
from app.core.error_messages import Auth

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

_REFRESH_COOKIE_PATH = "/api/auth"

_LOGIN_IP_LIMIT = 99999999999
_LOGIN_IP_WINDOW_SECONDS = 30 * 60
_FORGOT_PASSWORD_IP_LIMIT = 20
_FORGOT_PASSWORD_IP_WINDOW_SECONDS = 60 * 60

def _set_refresh_cookie(response: Response, raw_refresh_token: str) -> None:
    response.set_cookie(
        key=auth_service.REFRESH_TOKEN_COOKIE_NAME,
        value=raw_refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path=_REFRESH_COOKIE_PATH,
    )

def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=auth_service.REFRESH_TOKEN_COOKIE_NAME,
        domain=settings.cookie_domain,
        path=_REFRESH_COOKIE_PATH,
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    dependencies=[Depends(rate_limit_by_ip("login", _LOGIN_IP_LIMIT, _LOGIN_IP_WINDOW_SECONDS))],
)
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Login ธรรมดาทั่วไป"""
    user = await auth_service.authenticate_user(db, request, form_data.username, form_data.password)
    access_token, raw_refresh_token = await auth_service.issue_tokens(db, user)
    _set_refresh_cookie(response, raw_refresh_token)
    return LoginResponse(access_token=access_token, user=user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """แลก Refresh TOken โดยใช้ Cookie"""
    raw_refresh_token = request.cookies.get(auth_service.REFRESH_TOKEN_COOKIE_NAME)
    if raw_refresh_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=Auth.MISSING_REFRESH_TOKEN)

    access_token, new_raw_refresh_token = await auth_service.rotate_refresh_token(db, raw_refresh_token)
    _set_refresh_cookie(response, new_raw_refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    raw_refresh_token = request.cookies.get(auth_service.REFRESH_TOKEN_COOKIE_NAME)
    if raw_refresh_token is not None:
        await auth_service.revoke_refresh_token(db, raw_refresh_token)
    _clear_refresh_cookie(response)
    return MessageResponse(detail="Logged out successfully")


@router.post(
    "/forgot-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(rate_limit_by_ip("forgot_password", _FORGOT_PASSWORD_IP_LIMIT, _FORGOT_PASSWORD_IP_WINDOW_SECONDS))
    ],
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    await auth_service.request_password_reset(db, background_tasks, payload.email)

@router.post("/set-password", response_model=SetPasswordResponse)
async def set_password(
    payload: SetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """ต่อจาก endpoint forgot-password เอา token url มาใส่ในนี้ user สามารถตั้งรหัสผ่านเองได้"""
    username = await auth_service.set_password(db, payload.token, payload.new_password)
    return SetPasswordResponse(
        detail=f"ยินดีด้วย คุณสมัครสำเร็จ สามารถเข้าสู่ระบบได้เลยโดยใช้ username: {username}",
        username=username,
    )


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """อันนี้คือเปลี่ยนรหัสผ่านเองได้เมื่อ login เข้ามาแล้ว"""
    current_raw_refresh_token = request.cookies.get(auth_service.REFRESH_TOKEN_COOKIE_NAME)
    await auth_service.change_password(
        db=db,
        request=request,
        current_user=current_user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        logout_all_sessions=payload.logout_all_sessions,
        current_raw_refresh_token=current_raw_refresh_token,
    )
    if payload.logout_all_sessions:
        _clear_refresh_cookie(response)
    return MessageResponse(detail="Password changed successfully")