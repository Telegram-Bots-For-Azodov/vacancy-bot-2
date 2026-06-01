"""Token muammosi (401) yuz berganda admin/superadminlarni ogohlantirish."""
from __future__ import annotations

import time

from aiogram import Bot
from loguru import logger

from bot.config import settings

_COOLDOWN = 600  # 10 daqiqada bir martadan ko'p ogohlantirmaymiz
_last_notified: float = 0.0
_notified: bool = False

ALERT_TEXT = (
    "⚠️ <b>ABKM token eskirgan!</b>\n\n"
    "Ma'lumot olishda <code>401 Unauthenticated</code> xatosi qaytdi.\n"
    "Iltimos yangi tokenni kiriting:\n\n"
    "🛠 <b>Admin panel → 🔑 ABKM tokenni yangilash</b>"
)


def reset() -> None:
    """Token yangilangach chaqiriladi — keyingi 401'da yana ogohlantiramiz."""
    global _notified, _last_notified
    _notified = False
    _last_notified = 0.0


async def notify_token_issue(bot: Bot) -> None:
    global _last_notified, _notified
    now = time.time()
    if _notified and (now - _last_notified) < _COOLDOWN:
        return
    _last_notified = now
    _notified = True

    recipients = list(dict.fromkeys(settings.superadmin_ids + settings.admin_ids))
    for uid in recipients:
        try:
            await bot.send_message(uid, ALERT_TEXT)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"token alert -> {uid} yuborilmadi: {e}")
    if recipients:
        logger.warning("ABKM token 401 — adminlar ogohlantirildi.")
