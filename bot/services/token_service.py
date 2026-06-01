"""ABKM tokenni runtime'da boshqarish (DB'da saqlanadi, .env faqat boshlang'ich qiymat)."""
from __future__ import annotations

from loguru import logger

from bot.config import settings
from bot.database.crud import get_setting, set_setting
from bot.database.db import SessionLocal

_TOKEN_KEY = "abkm_token"
_current_token: str = settings.ABKM_TOKEN


async def load_token() -> None:
    """Startda chaqiriladi: DB'dan tokenni o'qiydi, bo'lmasa .env qiymatini yozadi."""
    global _current_token
    async with SessionLocal() as session:
        value = await get_setting(session, _TOKEN_KEY)
        if value:
            _current_token = value
            logger.info("ABKM token DB'dan yuklandi.")
        else:
            _current_token = settings.ABKM_TOKEN
            if _current_token:
                await set_setting(session, _TOKEN_KEY, _current_token)
            logger.info("ABKM token .env'dan olindi.")


def get_token() -> str:
    return _current_token


async def set_token(value: str) -> None:
    global _current_token
    _current_token = value.strip()
    async with SessionLocal() as session:
        await set_setting(session, _TOKEN_KEY, _current_token)
    logger.info("ABKM token yangilandi.")
