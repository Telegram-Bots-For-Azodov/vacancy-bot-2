"""Timezone yordamchisi — IANA bazasi topilmasa UTC'ga tushadi (Windows uchun)."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from loguru import logger

from bot.config import settings

_UTC = timezone.utc


def get_tz():
    """Sozlamadagi mintaqani qaytaradi; topilmasa UTC."""
    try:
        return ZoneInfo(settings.TIMEZONE)
    except (ZoneInfoNotFoundError, Exception):  # noqa: BLE001
        logger.warning(
            f"Timezone '{settings.TIMEZONE}' topilmadi (tzdata yo'qmi?), UTC ishlatiladi."
        )
        return _UTC


def to_local(dt: datetime):
    """Naive UTC (yoki aware) vaqtni mahalliy mintaqaga o'giradi."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_UTC)
    return dt.astimezone(get_tz())


def local_day_start_utc(now_local: datetime) -> datetime:
    """Mahalliy kun boshining naive-UTC vaqti (created_at bilan solishtirish uchun)."""
    start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(_UTC).replace(tzinfo=None)
