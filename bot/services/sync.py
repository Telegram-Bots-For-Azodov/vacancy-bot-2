"""Vakansiyalarni API'dan lokal bazaga sinxronlash.

Faqat faol viloyatlar sinxronlanadi (viloyat darajasidagi SOATO — bitta
o'tishda uning barcha tumanlari qamrab olinadi). Har soatda yangilanadi.
"""
from __future__ import annotations

import asyncio

from aiogram import Bot
from loguru import logger

from bot.database import crud
from bot.database.db import SessionLocal
from bot.services import notifier
from bot.services.abkm_api import ABKMAuthError, fetch_all

_SYNC_INTERVAL = 6 * 3600  # 6 soat

# bir vaqtda faqat bitta to'liq sinxronlash ketsin (qo'lda + avtomatik)
_sync_lock = asyncio.Lock()


def is_running() -> bool:
    """Hozir sinxronlash ketyaptimi?"""
    return _sync_lock.locked()


async def sync_region(region_soato: int) -> int:
    """Bitta viloyatni tumanlar kesimida KETMA-KET sinxronlaydi.

    Har tuman javobi kelishi bilan O'SHA TUMAN darrov bazaga yoziladi
    (butun viloyat kutilmaydi). Tuman yuklanmasa — uning eski ma'lumoti
    saqlanib qoladi (boshqa tumanlarga ta'sir qilmaydi). Jami saqlangan
    vakansiyalar sonini qaytaradi.
    """
    async with SessionLocal() as session:
        districts = await crud.list_districts(session, region_soato)

    # tumanlar bo'lmasa — viloyat darajasida bitta o'tish (kamdan-kam holat)
    if not districts:
        items = await fetch_all(region_soato)
        async with SessionLocal() as session:
            n = await crud.replace_region_vacancies(session, region_soato, items)
        logger.info(f"sync: viloyat {region_soato} (tumansiz) -> {n} ta saqlandi")
        return n

    total_saved = 0
    failed: list[int] = []

    for d in districts:
        try:
            items = await fetch_all(d.soato)
        except ABKMAuthError:
            # token eskirgan — butun sinxronlashni to'xtatamiz
            raise ABKMAuthError("API token eskirgan (tuman sinxronlashda).")
        except Exception:  # noqa: BLE001
            logger.exception(f"sync: tuman {d.soato} yuklashda xato — o'tkazildi")
            failed.append(d.soato)
            continue

        # javob keldi — darrov shu tumanni yozamiz
        try:
            async with SessionLocal() as session:
                n = await crud.replace_district_vacancies(
                    session, region_soato, d.soato, items
                )
            total_saved += n
            logger.info(f"sync: tuman {d.soato} -> {n} ta saqlandi")
        except Exception:  # noqa: BLE001
            logger.exception(f"sync: tuman {d.soato} yozishda xato")
            failed.append(d.soato)

    if failed:
        logger.warning(
            f"sync: viloyat {region_soato} — {len(failed)} tuman yuklanmadi/yozilmadi "
            f"({failed[:5]}...), ularning eski ma'lumoti saqlandi"
        )
    logger.info(
        f"sync: viloyat {region_soato} ({len(districts)} tuman, ketma-ket) "
        f"-> jami {total_saved} ta saqlandi"
    )
    return total_saved


async def sync_all(bot: Bot | None = None) -> None:
    """Barcha faol viloyatlarni sinxronlaydi (bir vaqtda bittadan)."""
    async with _sync_lock:
        async with SessionLocal() as session:
            regions = await crud.list_regions(session)  # faqat active

        if not regions:
            logger.info("sync: faol viloyat yo'q, o'tkazib yuborildi")
            return

        for r in regions:
            try:
                await sync_region(r.soato)
            except ABKMAuthError:
                logger.warning("sync: 401 — ABKM token eskirgan, to'xtatildi")
                if bot is not None:
                    await notifier.notify_token_issue(bot)
                break
            except Exception:  # noqa: BLE001
                logger.exception(f"sync: viloyat {r.soato} sinxronlashda xato")


async def sync_loop(bot: Bot) -> None:
    """Fon vazifa: darhol bir marta, so'ng har 6 soatda sinxronlaydi."""
    while True:
        try:
            await sync_all(bot)
        except Exception:  # noqa: BLE001
            logger.exception("sync_loop: kutilmagan xato")
        await asyncio.sleep(_SYNC_INTERVAL)
