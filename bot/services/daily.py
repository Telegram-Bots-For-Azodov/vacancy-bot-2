"""Kunlik foydalanuvchi statistikasi (DAU) va is_active bayrog'ini yangilash.

Har kuni 00:00 (Asia/Tashkent) da:
- tugagan kun uchun DailyStat yoziladi (aktiv/yangi/jami);
- barcha foydalanuvchilar is_active = false bo'ladi.
Foydalanuvchi botdan foydalansa is_active = true bo'ladi (middleware/crud).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from loguru import logger

from bot.database import crud
from bot.database.db import SessionLocal
from bot.utils.timez import get_tz, local_day_start_utc


def _seconds_until_midnight(now_local: datetime) -> float:
    nxt = (now_local + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return (nxt - now_local).total_seconds()


async def _run_once() -> None:
    """Tugagan kun statistikasi yoziladi va bayroqlar tozalanadi."""
    tz = get_tz()
    now_local = datetime.now(tz)
    # Loop yarim tundan ~1s keyin uyg'onadi. Endigina TUGAGAN kun = kechagi sana.
    # 1 soniya ayirsak hali ham yangi kun chiqadi (00:00:00) — shuning uchun
    # bemalol kechaga tushish uchun 1 daqiqa ayiramiz.
    ended = now_local - timedelta(minutes=1)
    day = ended.strftime("%Y-%m-%d")
    # shu kun boshining UTC vaqti (yangi foydalanuvchilarni sanash uchun)
    since_utc = local_day_start_utc(ended)

    async with SessionLocal() as session:
        stats = await crud.record_daily_and_reset(session, day, since_utc)
    logger.info(
        f"daily: {stats['day']} aktiv={stats['active']} "
        f"yangi={stats['new']} jami={stats['total']} — is_active tozalandi"
    )


async def daily_loop() -> None:
    """Fon vazifa: har kuni yarim tunda statistikani yozadi va resetlaydi."""
    tz = get_tz()
    while True:
        delay = _seconds_until_midnight(datetime.now(tz))
        await asyncio.sleep(delay + 1)  # yarim tundan biroz keyin
        try:
            await _run_once()
        except Exception:  # noqa: BLE001
            logger.exception("daily_loop: statistika yozishda xato")
