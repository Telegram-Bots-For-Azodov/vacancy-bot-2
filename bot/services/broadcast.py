"""Foydalanuvchilarga reklama/xabar yuborish.

Telegram cheklovlari inobatga olinadi:
- soniyasiga ~30 ta xabar (turli chatlarga) — sekin yuboriladi;
- `RetryAfter` (flood) — ko'rsatilgan vaqt kutiladi;
- botni bloklagan / o'chirilgan foydalanuvchilar bazadan o'chiriladi.
"""
from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramBadRequest,
)
from loguru import logger

from bot.database import crud
from bot.database.db import SessionLocal

# soniyasiga ~25 ta (xavfsiz chegara, 30 dan past)
_DELAY = 0.04
# bir vaqtning o'zida faqat bitta reklama ketsin
_lock = asyncio.Lock()


def is_running() -> bool:
    return _lock.locked()


async def broadcast(bot: Bot, from_chat_id: int, message_id: int) -> dict:
    """Berilgan xabarni barcha foydalanuvchilarga nusxalab yuboradi.

    Natija: {"total", "sent", "failed", "deleted"}.
    """
    async with _lock:
        async with SessionLocal() as session:
            user_ids = await crud.all_user_ids(session)

        sent = failed = 0
        to_delete: list[int] = []

        for uid in user_ids:
            try:
                await bot.copy_message(
                    chat_id=uid,
                    from_chat_id=from_chat_id,
                    message_id=message_id,
                )
                sent += 1
            except TelegramRetryAfter as e:
                # flood limit — kutib, shu foydalanuvchiga qayta urinamiz
                logger.warning(f"broadcast: RetryAfter {e.retry_after}s")
                await asyncio.sleep(e.retry_after + 1)
                try:
                    await bot.copy_message(
                        chat_id=uid,
                        from_chat_id=from_chat_id,
                        message_id=message_id,
                    )
                    sent += 1
                except Exception:  # noqa: BLE001
                    failed += 1
            except TelegramForbiddenError:
                # bot bloklangan yoki akkaunt o'chirilgan — bazadan olib tashlaymiz
                to_delete.append(uid)
            except TelegramBadRequest as e:
                # chat topilmadi / user deactivated — o'chiramiz, aks holda xato
                msg = str(e).lower()
                if "chat not found" in msg or "user is deactivated" in msg:
                    to_delete.append(uid)
                else:
                    failed += 1
            except Exception:  # noqa: BLE001
                failed += 1

            await asyncio.sleep(_DELAY)

        deleted = 0
        if to_delete:
            async with SessionLocal() as session:
                deleted = await crud.delete_users(session, to_delete)

        logger.info(
            f"broadcast: jami={len(user_ids)} yuborildi={sent} "
            f"xato={failed} o'chirildi={deleted}"
        )
        return {
            "total": len(user_ids),
            "sent": sent,
            "failed": failed,
            "deleted": deleted,
        }
