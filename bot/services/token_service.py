"""ABKM tokenni runtime'da boshqarish. Faqat DB'da saqlanadi (.env ishlatilmaydi)."""
from __future__ import annotations

from loguru import logger

from bot.database.crud import get_setting, set_setting
from bot.database.db import SessionLocal

_TOKEN_KEY = "abkm_token"
_current_token: str = ""


async def load_token() -> None:
    """Startda chaqiriladi: tokenni faqat DB'dan o'qiydi.

    Token .env'dan olinmaydi — admin panel orqali kiritiladi va DB'da saqlanadi.
    """
    global _current_token
    async with SessionLocal() as session:
        value = await get_setting(session, _TOKEN_KEY)
    _current_token = value or ""
    if _current_token:
        logger.info("ABKM token DB'dan yuklandi.")
    else:
        logger.warning("ABKM token DB'da yo'q — admin panel orqali kiriting.")


def get_token() -> str:
    return _current_token


async def set_token(value: str) -> None:
    global _current_token
    _current_token = value.strip()
    async with SessionLocal() as session:
        await set_setting(session, _TOKEN_KEY, _current_token)
    logger.info("ABKM token yangilandi.")
