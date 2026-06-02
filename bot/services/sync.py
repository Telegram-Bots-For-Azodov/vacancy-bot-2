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

    Tumanlar bittadan (parallel emas) yuklanadi. Natija birlashtirilib,
    viloyat yozuvlari atomik qayta yoziladi. Saqlangan sonni qaytaradi.

    Agar biror tuman butunlay yuklanmasa, viloyat bazasi YANGILANMAYDI —
    eski (to'liq) ma'lumot saqlanib qoladi, qisman/bo'sh yozib yuborilmaydi.
    """
    async with SessionLocal() as session:
        districts = await crud.list_districts(session, region_soato)

    soatos = [d.soato for d in districts] or [region_soato]

    failed: list[int] = []
    chunks: list[list[dict]] = []

    # tumanma-tuman, ketma-ket
    for soato in soatos:
        try:
            chunks.append(await fetch_all(soato))
        except ABKMAuthError:
            # token eskirgan — butun sinxronlashni to'xtatamiz
            raise ABKMAuthError("API token eskirgan (tuman sinxronlashda).")
        except Exception:  # noqa: BLE001
            logger.exception(f"sync: tuman {soato} yuklashda xato")
            failed.append(soato)
            chunks.append([])

    # qisman muvaffaqiyatsizlik — eski ma'lumotni saqlaymiz, ustiga yozmaymiz
    if failed:
        logger.warning(
            f"sync: viloyat {region_soato} — {len(failed)} tuman yuklanmadi "
            f"({failed[:5]}...), baza yangilanmadi (eski ma'lumot saqlandi)"
        )
        return -1

    # id bo'yicha takrorlanmas (tumanlar bo'ylab ham)
    uniq: dict[int, dict] = {}
    for chunk in chunks:
        for v in chunk:
            try:
                uniq[int(v["id"])] = v
            except (KeyError, TypeError, ValueError):
                continue

    async with SessionLocal() as session:
        n = await crud.replace_region_vacancies(
            session, region_soato, list(uniq.values())
        )
    logger.info(
        f"sync: viloyat {region_soato} ({len(soatos)} tuman, ketma-ket) "
        f"-> {n} ta saqlandi"
    )
    return n


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
