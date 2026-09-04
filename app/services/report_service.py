from __future__ import annotations
import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.camera import CameraDirection
from app.models.car import Car
from app.models.user import User, UserRole
from app.schemas.car import RepeatedPlateEntry
from app.schemas.report import HourlyBucket, ReportDailyRead, ReportSummaryRead
from app.core.timezone import BANGKOK_TZ
from app.core.error_messages import Common
import time

_REPORT_CACHE: dict[str, dict] = {}
_REPORT_CACHE_TTL = 60  # เก็บแคช 60 วินาที
_cache_lock = asyncio.Lock()

_BANGKOK_TZ = ZoneInfo("Asia/Bangkok")
_TOP_PLATES_LIMIT = 5


def _bangkok_midnight(local_date: date) -> datetime:
    return datetime(local_date.year, local_date.month, local_date.day, tzinfo=BANGKOK_TZ)

def _bangkok_day_range_bounds(days: int) -> tuple[date, date, datetime, datetime]:
    today_bangkok = datetime.now(_BANGKOK_TZ).date()
    date_from = today_bangkok - timedelta(days=days - 1)
    date_to = today_bangkok

    start_utc = _bangkok_midnight(date_from).astimezone(timezone.utc)
    end_utc = (_bangkok_midnight(date_to) + timedelta(days=1)).astimezone(timezone.utc)

    return date_from, date_to, start_utc, end_utc

def _bangkok_single_day_bounds(target_date: date) -> tuple[datetime, datetime]:
    start_utc = _bangkok_midnight(target_date).astimezone(timezone.utc)
    end_utc = start_utc + timedelta(days=1)
    return start_utc, end_utc


def _build_report_scope_filters(current_user: User, village_id_filter: uuid.UUID | None) -> list:
    if current_user.role == UserRole.SUPERADMIN:
        if village_id_filter is not None:
            return [Car.village_id == village_id_filter]
        return []

    if village_id_filter is not None and village_id_filter != current_user.village_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=Common.VILLAGE_ID_NOT_ALLOWED_FOR_ROLE,
        )
    return [Car.village_id == current_user.village_id]


async def _collect_report_metrics(db: AsyncSession, base_filters: list) -> dict:
    # --- single aggregated counts query (replaces 6 separate queries) ---
    unique_plates_sub = (
        select(func.count())
        .select_from(
            select(Car.license_plate, Car.province)
            .where(*base_filters)
            .distinct()
            .subquery()
        )
    )
    agg_query = (
        select(
            func.count().label("total"),
            func.count(case((Car.is_blacklist.is_(True), 1))).label("blacklist"),
            func.count(case((Car.is_whitelist.is_(True), 1))).label("whitelist"),
            func.count(case((Car.direction == CameraDirection.ENTRY, 1))).label("entry"),
            func.count(case((Car.direction == CameraDirection.EXIT, 1))).label("exit"),
        )
        .select_from(Car)
        .where(*base_filters)
    )

    top_repeated_query = (
        select(Car.license_plate, Car.province, func.count())
        .where(*base_filters)
        .group_by(Car.license_plate, Car.province)
        .having(func.count() > 1)
        .order_by(func.count().desc())
        .limit(_TOP_PLATES_LIMIT)
    )

    bangkok_hour = func.extract(
        "hour", func.timezone("Asia/Bangkok", Car.time_detect)
    )
    hourly_query = (
        select(bangkok_hour.label("hour"), func.count())
        .select_from(Car)
        .where(*base_filters)
        .group_by(bangkok_hour)
    )

    # --- execute 4 queries sequentially to prevent MissingGreenlet ---
    agg_result = await db.execute(agg_query)
    unique_result = await db.execute(unique_plates_sub)
    top_repeated_result = await db.execute(top_repeated_query)
    hourly_result = await db.execute(hourly_query)

    row = agg_result.one()

    top_repeated_plates = [
        RepeatedPlateEntry(license_plate=plate, province=province, count=count)
        for plate, province, count in top_repeated_result.all()
    ]

    counts_by_hour = {int(hour): count for hour, count in hourly_result.all()}
    hourly_buckets = [
        HourlyBucket(hour=hour, count=counts_by_hour.get(hour, 0))
        for hour in range(24)
    ]

    return {
        "total_detections": row.total,
        "unique_plates": unique_result.scalar_one(),
        "blacklist_detections": row.blacklist,
        "whitelist_detections": row.whitelist,
        "entry_detections": row.entry,
        "exit_detections": row.exit,
        "top_repeated_plates": top_repeated_plates,
        "hourly_buckets": hourly_buckets,
        "peak_time": _compute_peak_time(hourly_buckets),
    }

def _compute_peak_time(hourly_buckets: list[HourlyBucket]) -> str:
    peak_bucket = max(hourly_buckets, key=lambda b: b.count)
    if peak_bucket.count == 0:
        return "N/A"
    return f"{peak_bucket.hour:02d}:00-{peak_bucket.hour:02d}:59"


async def get_report_summary(
    db: AsyncSession,
    current_user: User,
    village_id: uuid.UUID | None,
    days: int,
) -> ReportSummaryRead:
    cache_key = f"summary:{current_user.id}:{village_id}:{days}"
    async with _cache_lock:
        if cache_key in _REPORT_CACHE:
            entry = _REPORT_CACHE[cache_key]
            if time.time() - entry["time"] < _REPORT_CACHE_TTL:
                return entry["data"]

    date_from, date_to, start_utc, end_utc = _bangkok_day_range_bounds(days)
    scope_filters = _build_report_scope_filters(current_user, village_id)
    base_filters = [Car.time_detect >= start_utc, Car.time_detect < end_utc, *scope_filters]

    metrics = await _collect_report_metrics(db, base_filters)

    result = ReportSummaryRead(
        days=days,
        date_from=date_from,
        date_to=date_to,
        **metrics,
    )

    async with _cache_lock:
        _REPORT_CACHE[cache_key] = {"time": time.time(), "data": result}
        
    return result


async def get_report_daily(
    db: AsyncSession,
    current_user: User,
    village_id: uuid.UUID | None,
    target_date: date,
) -> ReportDailyRead:
    cache_key = f"daily:{current_user.id}:{village_id}:{target_date.isoformat()}"
    async with _cache_lock:
        if cache_key in _REPORT_CACHE:
            entry = _REPORT_CACHE[cache_key]
            if time.time() - entry["time"] < _REPORT_CACHE_TTL:
                return entry["data"]

    start_utc, end_utc = _bangkok_single_day_bounds(target_date)
    scope_filters = _build_report_scope_filters(current_user, village_id)
    base_filters = [Car.time_detect >= start_utc, Car.time_detect < end_utc, *scope_filters]

    metrics = await _collect_report_metrics(db, base_filters)

    result = ReportDailyRead(
        date=target_date,
        **metrics,
    )

    async with _cache_lock:
        _REPORT_CACHE[cache_key] = {"time": time.time(), "data": result}

    return result