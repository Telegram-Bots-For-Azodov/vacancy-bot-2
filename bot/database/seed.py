"""SOATO seed loader — soato_seed.json dan viloyat/tumanlarni bazaga yozadi (upsert)."""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from bot.database.crud import upsert_district, upsert_region
from bot.database.db import SessionLocal

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "soato_seed.json"


async def seed_soato() -> None:
    if not SEED_PATH.exists():
        logger.warning(f"SOATO seed fayli topilmadi: {SEED_PATH}")
        return

    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    regions = data.get("regions", [])

    async with SessionLocal() as session:
        r_count = 0
        d_count = 0
        for ri, region in enumerate(regions):
            r_soato = int(region["soato"])
            await upsert_region(
                session,
                soato=r_soato,
                name=region["name"],
                sort_order=int(region.get("sort_order", ri)),
            )
            r_count += 1
            for di, district in enumerate(region.get("districts", [])):
                await upsert_district(
                    session,
                    soato=int(district["soato"]),
                    region_soato=r_soato,
                    name=district["name"],
                    sort_order=int(district.get("sort_order", di)),
                )
                d_count += 1

    logger.info(f"SOATO seed: {r_count} viloyat, {d_count} tuman yangilandi.")
