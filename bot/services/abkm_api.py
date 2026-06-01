"""abkm.mehnat.uz API klienti.

Ikkita endpoint:
- vacancy-reports : SOATO (yoki report_id) bo'yicha vakansiya (lavozim) ro'yxati
- v-reports       : SOATO bo'yicha tashkilotlar (har biri count_vacancy bilan)

API `soato` ni viloyat va tuman darajasida qabul qiladi (serverda filtrlaydi).
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime

import aiohttp
from loguru import logger

from bot.config import settings
from bot.services.token_service import get_token

_CACHE_TTL = 600  # 10 daqiqa
_MAX_PAGES = 100
_PER_PAGE = 50

# kesh
_cache: dict[tuple, tuple[float, list[dict]]] = {}
_org_cache: dict[tuple[int, int, int], tuple[float, list[dict]]] = {}
_count_cache: dict[tuple[int, int, int], tuple[float, int]] = {}

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


def _now_ym() -> tuple[int, int]:
    now = datetime.now()
    year = settings.DEFAULT_YEAR or now.year
    month = settings.DEFAULT_MONTH or now.month
    return year, month


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


async def _get_data(
    session: aiohttp.ClientSession, url: str, params: dict
) -> dict:
    params = {**params, "_dc": int(time.time() * 1000)}
    cookies = {"abkm_token": get_token()}
    async with session.get(
        url,
        params=params,
        headers=_headers(),
        cookies=cookies,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        if resp.status == 401:
            _flag_auth_error()
            raise ABKMAuthError("API token eskirgan yoki noto'g'ri (401).")
        if resp.status != 200:
            raise ABKMError(f"API xatosi: HTTP {resp.status}")
        payload = await resp.json()
    if not payload.get("success"):
        raise ABKMError("API muvaffaqiyatsiz javob qaytardi.")
    return payload.get("data", {})


# ---------------------------------------------------------------- vacancies
async def _fetch_all_pages(
    url: str, base_params: dict, log_label: str
) -> list[dict]:
    items: list[dict] = []
    async with aiohttp.ClientSession() as session:
        first = await _get_data(session, url, {**base_params, "page": 1, "start": 0})
        items.extend(first.get("data", []))
        last_page = int(first.get("last_page", 1) or 1)
        for page in range(2, min(last_page, _MAX_PAGES) + 1):
            data = await _get_data(
                session,
                url,
                {**base_params, "page": page, "start": (page - 1) * _PER_PAGE},
            )
            items.extend(data.get("data", []))
    logger.info(f"abkm: {log_label} -> {len(items)} ta")
    return items


async def fetch_vacancies(
    soato: int,
    year: int | None = None,
    month: int | None = None,
    force: bool = False,
) -> list[dict]:
    """SOATO bo'yicha barcha vakansiyalar (lavozimlar)."""
    if year is None or month is None:
        year, month = _now_ym()
    key = ("vac", soato, year, month)
    cached = _cache.get(key)
    if cached and not force and (time.time() - cached[0] < _CACHE_TTL):
        return cached[1]

    base = {"limit": _PER_PAGE, "year": year, "month": month, "tin": "", "soato": soato}
    items = await _fetch_all_pages(
        settings.ABKM_BASE_URL, base, f"vac soato={soato} {year}-{month:02d}"
    )
    _cache[key] = (time.time(), items)
    return items


async def fetch_district_vacancies(
    region_soato: int,
    district_soato: int | None,
    year: int | None = None,
    month: int | None = None,
    force: bool = False,
) -> list[dict]:
    target = district_soato if district_soato is not None else region_soato
    return await fetch_vacancies(target, year, month, force)


async def fetch_report_vacancies(
    soato: int,
    report_id: int,
    year: int | None = None,
    month: int | None = None,
    force: bool = False,
) -> list[dict]:
    """Bitta tashkilot (report_id) vakansiyalari."""
    if year is None or month is None:
        year, month = _now_ym()
    key = ("rep", soato, report_id, year, month)
    cached = _cache.get(key)
    if cached and not force and (time.time() - cached[0] < _CACHE_TTL):
        return cached[1]

    base = {
        "limit": _PER_PAGE,
        "year": year,
        "month": month,
        "tin": "",
        "soato": soato,
        "report_id": report_id,
    }
    items = await _fetch_all_pages(
        settings.ABKM_BASE_URL, base, f"rep report_id={report_id}"
    )
    _cache[key] = (time.time(), items)
    return items


# ---------------------------------------------------------------- organizations
async def fetch_organizations(
    soato: int,
    year: int | None = None,
    month: int | None = None,
    force: bool = False,
) -> list[dict]:
    """SOATO bo'yicha vakansiyasi bor tashkilotlar (report_id bo'yicha takrorlanmas)."""
    if year is None or month is None:
        year, month = _now_ym()
    key = (soato, year, month)
    cached = _org_cache.get(key)
    if cached and not force and (time.time() - cached[0] < _CACHE_TTL):
        return cached[1]

    base = {
        "limit": _PER_PAGE,
        "year": year,
        "month": month,
        "company_tin": "",
        "soato": soato,
    }
    raw = await _fetch_all_pages(
        settings.ABKM_VREPORTS_URL, base, f"orgs soato={soato} {year}-{month:02d}"
    )

    seen: set = set()
    orgs: list[dict] = []
    for it in raw:
        if not it.get("has_vacancy") or int(it.get("count_vacancy", 0) or 0) <= 0:
            continue
        rid = it.get("report_id")
        if rid in seen:
            continue
        seen.add(rid)
        orgs.append(it)

    _org_cache[key] = (time.time(), orgs)
    return orgs


# ---------------------------------------------------------------- counts
async def _fetch_total(
    session: aiohttp.ClientSession, soato: int, year: int, month: int
) -> int:
    data = await _get_data(
        session,
        settings.ABKM_BASE_URL,
        {"page": 1, "start": 0, "limit": 1, "year": year, "month": month,
         "tin": "", "soato": soato},
    )
    return int(data.get("total", 0) or 0)


async def fetch_totals(
    soatos: list[int],
    year: int | None = None,
    month: int | None = None,
) -> dict[int, int]:
    """Bir nechta SOATO bo'yicha vakansiyalar sonini parallel oladi. Xato -> -1."""
    if year is None or month is None:
        year, month = _now_ym()

    result: dict[int, int] = {}
    to_fetch: list[int] = []
    for s in soatos:
        cached = _count_cache.get((s, year, month))
        if cached and (time.time() - cached[0] < _CACHE_TTL):
            result[s] = cached[1]
        else:
            to_fetch.append(s)

    if to_fetch:
        async with aiohttp.ClientSession() as session:

            async def one(s: int) -> None:
                try:
                    total = await _fetch_total(session, s, year, month)
                except Exception:  # noqa: BLE001
                    total = -1
                _count_cache[(s, year, month)] = (time.time(), total)
                result[s] = total

            await asyncio.gather(*(one(s) for s in to_fetch))

    return result
