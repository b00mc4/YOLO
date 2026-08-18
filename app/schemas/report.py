from __future__ import annotations
from datetime import date
from pydantic import BaseModel
from app.schemas.car import RepeatedPlateEntry


class HourlyBucket(BaseModel):
    hour: int
    count: int


class ReportMetrics(BaseModel):
    total_detections: int
    unique_plates: int
    blacklist_detections: int
    whitelist_detections: int
    peak_time: str
    top_repeated_plates: list[RepeatedPlateEntry]
    hourly_buckets: list[HourlyBucket]


class ReportSummaryRead(ReportMetrics):
    days: int
    date_from: date
    date_to: date


class ReportDailyRead(ReportMetrics):
    date: date