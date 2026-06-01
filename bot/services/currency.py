"""Valyuta kurslari — cbu.uz rasmiy API'sidan."""
from __future__ import annotations

import time

import aiohttp
from loguru import logger

_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"
_CACHE_TTL = 1800  # 30 daqiqa
_cache: tuple[float, str] | None = None

# Ko'rsatiladigan valyutalar va ularning nomlari (tartib bilan)
_WANTED = [
    ("USD", "АҚШ доллари"),
    ("EUR", "EВРО"),
    ("RUB", "Россия рубли"),
    ("KZT", "Қозоғистон тенгеси"),
]


async def get_rates_text(force: bool = False) -> str:
    """Tayyor matn (HTML) qaytaradi. Xato bo'lsa tushunarli xabar."""
    global _cache
    if _cache and not force and (time.time() - _cache[0] < _CACHE_TTL):
        return _cache[1]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                _URL, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                data = await resp.json(content_type=None)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"valyuta kursini olishda xato: {e}")
        return "⚠️ Valyuta kurslarini olishda xatolik. Keyinroq urinib ko'ring."

    rates = {item.get("Ccy"): item.get("Rate") for item in data}

    lines = ["💵 <b>Валюталар курслари</b>\n"]
    for ccy, name in _WANTED:
        rate = rates.get(ccy)
        if rate:
            lines.append(f"📈 {name} - {rate} so'm")
    text = "\n".join(lines)

    _cache = (time.time(), text)
    return text
