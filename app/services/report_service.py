from __future__ import annotations
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.camera import Camera
from app.models.car import Car
from app.models.user import User, UserRole
from app.schemas.car import RepeatedPlateEntry
from app.schemas.report import HourlyBucket, ReportDailyRead, ReportSummaryRead
from app.core.timezone import BANGKOK_TZ

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
            return [Camera.village_id == village_id_filter]
        return []
    filters = [Camera.village_id == current_user.village_id]
    if village_id_filter is not None:
        filters.append(Camera.village_id == village_id_filter)
    return filters


async def _count_total(db: AsyncSession, base_filters: list) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Car)
        .join(Camera, Car.camera_id == Camera.id)
        .where(*base_filters)
    )
    return result.scalar_one()


async def _count_unique_plates(db: AsyncSession, base_filters: list) -> int:
    unique_subquery = (
        select(Car.license_plate, Car.province)
        .join(Camera, Car.camera_id == Camera.id)
        .where(*base_filters)
        .distinct()
        .subquery()
    )
    result = await db.execute(select(func.count()).select_from(unique_subquery))
    return result.scalar_one()


async def _count_blacklist(db: AsyncSession, base_filters: list) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Car)
        .join(Camera, Car.camera_id == Camera.id)
        .where(*base_filters, Car.is_blacklist.is_(True))
    )
    return result.scalar_one()


async def _top_repeated_plates(db: AsyncSession, base_filters: list) -> list[RepeatedPlateEntry]:
    result = await db.execute(
        select(Car.license_plate, Car.province, func.count())
        .join(Camera, Car.camera_id == Camera.id)
        .where(*base_filters)
        .group_by(Car.license_plate, Car.province)
        .having(func.count() > 1)
        .order_by(func.count().desc())
        .limit(_TOP_PLATES_LIMIT)
    )
    return [
        RepeatedPlateEntry(license_plate=plate, province=province, count=count)
        for plate, province, count in result.all()
    ]


async def _hourly_buckets(db: AsyncSession, base_filters: list) -> list[HourlyBucket]:
    bangkok_hour = func.extract(
        "hour", func.timezone("Asia/Bangkok", Car.time_detect)
    )

    result = await db.execute(
        select(bangkok_hour.label("hour"), func.count())
        .select_from(Car)
        .join(Camera, Car.camera_id == Camera.id)
        .where(*base_filters)
        .group_by(bangkok_hour)
    )
    counts_by_hour = {int(hour): count for hour, count in result.all()}

    return [
        HourlyBucket(hour=hour, count=counts_by_hour.get(hour, 0))
        for hour in range(24)
    ]


async def _collect_report_metrics(db: AsyncSession, base_filters: list) -> dict:
    hourly_buckets = await _hourly_buckets(db, base_filters)
    return {
        "total_detections": await _count_total(db, base_filters),
        "unique_plates": await _count_unique_plates(db, base_filters),
        "blacklist_detections": await _count_blacklist(db, base_filters),
        "top_repeated_plates": await _top_repeated_plates(db, base_filters),
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
    date_from, date_to, start_utc, end_utc = _bangkok_day_range_bounds(days)
    scope_filters = _build_report_scope_filters(current_user, village_id)
    base_filters = [Car.time_detect >= start_utc, Car.time_detect < end_utc, *scope_filters]

    metrics = await _collect_report_metrics(db, base_filters)

    return ReportSummaryRead(
        days=days,
        date_from=date_from,
        date_to=date_to,
        **metrics,
    )


async def get_report_daily(
    db: AsyncSession,
    current_user: User,
    village_id: uuid.UUID | None,
    target_date: date,
) -> ReportDailyRead:
    start_utc, end_utc = _bangkok_single_day_bounds(target_date)
    scope_filters = _build_report_scope_filters(current_user, village_id)
    base_filters = [Car.time_detect >= start_utc, Car.time_detect < end_utc, *scope_filters]

    metrics = await _collect_report_metrics(db, base_filters)

    return ReportDailyRead(
        date=target_date,
        **metrics,
    )