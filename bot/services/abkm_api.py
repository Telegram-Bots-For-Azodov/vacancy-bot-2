"""abkm.mehnat.uz `service_vacancies` API klienti.

Bitta endpoint: `service_vacancies` — `filter` (JSON massiv) + `page/start/limit`
bilan ishlaydi. SOATO ham viloyat (4 xonali), ham tuman (7 xonali) darajasini
qabul qiladi. Faqat e'lon qilingan (`is_published=true`) vakansiyalar olinadi.

Navigatsiya API sahifalashiga tayanadi: global indeks -> sahifa raqami ->
sahifadagi element. Har sahifa alohida keshlanadi.
"""
from __future__ import annotations

import asyncio
import json
import math
import time

import aiohttp
from loguru import logger

from bot.config import settings
from bot.services.token_service import get_token

_CACHE_TTL = 600  # 10 daqiqa
_SYNC_PER_PAGE = 500  # sinxronlashda bitta sahifada nechta olish
_MAX_PAGES = 1000  # himoya chegarasi
_RETRIES = 3  # tarmoq xatosida qayta urinish soni

# kesh: (soato, published) -> (ts, total)
_count_cache: dict[tuple, tuple[float, int]] = {}

# 401 yuz berganini eslab qolish (xatoni yutadigan joylar uchun)
_auth_error: bool = False


class ABKMError(Exception):
    pass


class ABKMAuthError(ABKMError):
    """401 Unauthenticated — token eskirgan."""


def _flag_auth_error() -> None:
    global _auth_error
    _auth_error = True


def consume_auth_error() -> bool:
    """Oxirgi so'rovlarda 401 bo'lganmi? O'qigach bayroqni tozalaydi."""
    global _auth_error
    v = _auth_error
    _auth_error = False
    return v


def _headers() -> dict:
    return {
        "Accept": "application/json, text/plain, */*",
        "Authorization": f"Bearer {get_token()}",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        ),
        "Referer": "https://abkm.mehnat.uz/",
    }


def _build_filter(
    soato: int,
    *,
    published_only: bool = True,
    company_inn: str | None = None,
    position_name: str | None = None,
) -> str:
    """`filter` parametri uchun JSON satr."""
    f: list[dict] = [
        {"property": "DIRECTION", "operator": "=", "value": "0"},
        {"property": "ReqSalaryMinimum", "operator": "=", "value": ""},
        {"property": "WORK_RATE", "operator": "=", "value": "0"},
        {"property": "SOATO", "operator": "=", "value": soato},
    ]
    if published_only:
        f.append({"property": "is_published", "operator": "=", "value": 1})
    if company_inn:
        f.append({"property": "COMPANY_INN", "operator": "=", "value": company_inn})
    if position_name:
        f.append({"property": "position_name", "operator": "=", "value": position_name})
    return json.dumps(f, ensure_ascii=False)


async def _get_page_once(
    session: aiohttp.ClientSession,
    soato: int,
    page: int,
    limit: int,
    published_only: bool,
) -> tuple[list[dict], int]:
    """Bitta sahifa (bitta urinish): (items, total)."""
    params = {
        "page": page,
        "start": (page - 1) * limit,
        "limit": limit,
        "filter": _build_filter(soato, published_only=published_only),
        "_dc": int(time.time() * 1000),
    }
    cookies = {"abkm_token": get_token()}
    async with session.get(
        settings.ABKM_BASE_URL,
        params=params,
        headers=_headers(),
        cookies=cookies,
        timeout=aiohttp.ClientTimeout(total=60),
    ) as resp:
        if resp.status == 401:
            _flag_auth_error()
            raise ABKMAuthError("API token eskirgan yoki noto'g'ri (401).")
        if resp.status != 200:
            raise ABKMError(f"API xatosi: HTTP {resp.status}")
        payload = await resp.json()
    if not payload.get("success"):
        raise ABKMError("API muvaffaqiyatsiz javob qaytardi.")
    data = payload.get("data", {}) or {}
    return data.get("data", []) or [], int(data.get("total", 0) or 0)


async def _get_page(
    session: aiohttp.ClientSession,
    soato: int,
    page: int,
    limit: int,
    published_only: bool,
) -> tuple[list[dict], int]:
    """Tarmoq xatolarida qayta uringan holda bitta sahifani oladi.

    401 (auth) darhol uzatiladi — qayta urinishdan foyda yo'q.
    Timeout / ulanish xatolarida eksponensial kutib qayta uriniladi.
    """
    last_exc: Exception | None = None
    for attempt in range(1, _RETRIES + 1):
        try:
            return await _get_page_once(session, soato, page, limit, published_only)
        except ABKMAuthError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_exc = e
            if attempt < _RETRIES:
                await asyncio.sleep(attempt * 2)  # 2s, 4s
                logger.warning(
                    f"abkm: soato={soato} page={page} urinish {attempt} xato: {e}"
                )
    raise ABKMError(f"API so'rovi {_RETRIES} marta muvaffaqiyatsiz: {last_exc}")


# ---------------------------------------------------------------- fetch all
async def fetch_all(
    soato: int,
    published_only: bool = True,
    per_page: int = _SYNC_PER_PAGE,
) -> list[dict]:
    """SOATO (odatda viloyat) bo'yicha BARCHA vakansiyalarni yig'adi.

    Sahifalar KETMA-KET o'qiladi (parallel emas).
    """
    items: list[dict] = []
    async with aiohttp.ClientSession() as session:
        first, total = await _get_page(session, soato, 1, per_page, published_only)
        _count_cache[(soato, published_only)] = (time.time(), total)
        last_page = math.ceil(total / per_page) if total else 1
        last_page = min(last_page, _MAX_PAGES)

        items.extend(first)
        for page in range(2, last_page + 1):
            chunk, _ = await _get_page(session, soato, page, per_page, published_only)
            items.extend(chunk)

    logger.info(f"abkm: fetch_all soato={soato} -> {len(items)}/{total} ta")
    return items


# ---------------------------------------------------------------- counts
async def fetch_total(soato: int, published_only: bool = True) -> int:
    """SOATO bo'yicha vakansiyalar soni (limit=1 bilan tez)."""
    cached = _count_cache.get((soato, published_only))
    if cached and (time.time() - cached[0] < _CACHE_TTL):
        return cached[1]
    async with aiohttp.ClientSession() as session:
        _, total = await _get_page(session, soato, 1, 1, published_only)
    _count_cache[(soato, published_only)] = (time.time(), total)
    return total


async def fetch_totals(
    soatos: list[int],
    published_only: bool = True,
) -> dict[int, int]:
    """Bir nechta SOATO bo'yicha vakansiyalar sonini parallel oladi. Xato -> -1."""
    result: dict[int, int] = {}
    to_fetch: list[int] = []
    for s in soatos:
        cached = _count_cache.get((s, published_only))
        if cached and (time.time() - cached[0] < _CACHE_TTL):
            result[s] = cached[1]
        else:
            to_fetch.append(s)

    if to_fetch:
        async with aiohttp.ClientSession() as session:

            async def one(s: int) -> None:
                try:
                    _, total = await _get_page(session, s, 1, 1, published_only)
                except Exception:  # noqa: BLE001
                    total = -1
                _count_cache[(s, published_only)] = (time.time(), total)
                result[s] = total

            await asyncio.gather(*(one(s) for s in to_fetch))

    return result
