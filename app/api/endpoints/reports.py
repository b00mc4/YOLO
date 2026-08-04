from __future__ import annotations
import uuid
from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.report import ReportDailyRead, ReportSummaryRead
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary", response_model=ReportSummaryRead)
async def get_report_summary(
    village_id: uuid.UUID | None = Query(default=None),
    days: int = Query(default=7, ge=1, le=60),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await report_service.get_report_summary(db, current_user, village_id, days)


@router.get("/daily", response_model=ReportDailyRead)
async def get_report_daily(
    village_id: uuid.UUID | None = Query(default=None),
    target_date: date = Query(alias="date"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await report_service.get_report_daily(db, current_user, village_id, target_date)