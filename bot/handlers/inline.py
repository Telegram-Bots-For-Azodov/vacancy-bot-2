from __future__ import annotations

from aiogram import Router
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from loguru import logger

from bot.database import crud
from bot.database.db import SessionLocal
from bot.services.formatter import format_vacancy_public

router = Router(name="inline")

HELP_TEXT = (
    "Vakansiyani ulashish uchun bot ichidagi vakansiya kartochkasidagi "
    "«📤 Ulashish» tugmasini bosing."
)


def _region_of(soato: int) -> int:
    """Tuman SOATO (7 xonali) dan viloyat SOATO (4 xonali) ni chiqaradi."""
    return soato if soato < 10000 else int(str(soato)[:4])


def _parse(query: str) -> tuple[int, str, int] | None:
    # format: v_{soato}_{tin}_{index}
    if not query.startswith("v_"):
        return None
    try:
        _, soato_s, tin, idx_s = query.split("_")
        return int(soato_s), tin, int(idx_s)
    except (ValueError, IndexError):
        return None


def _help_result() -> InlineQueryResultArticle:
    return InlineQueryResultArticle(
        id="help",
        title="Vakansiyani ulashish",
        description=HELP_TEXT,
        input_message_content=InputTextMessageContent(message_text=HELP_TEXT),
    )


@router.inline_query()
async def inline_share(query: InlineQuery) -> None:
    parsed = _parse(query.query.strip())

    if parsed is None:
        await query.answer(
            results=[_help_result()], cache_time=5, is_personal=True
        )
        return

    soato, tin, index = parsed
    region_soato = _region_of(soato)
    try:
        async with SessionLocal() as session:
            items = await crud.list_company_vacancies(
                session, region_soato, soato, tin
            )
    except Exception:  # noqa: BLE001
        logger.exception("inline fetch failed")
        items = []

    if not items:
        await query.answer(
            results=[
                InlineQueryResultArticle(
                    id="empty",
                    title="Vakansiya topilmadi",
                    description="Ushbu vakansiya endi mavjud emas.",
                    input_message_content=InputTextMessageContent(
                        message_text="Ushbu vakansiya endi mavjud emas."
                    ),
                )
            ],
            cache_time=5,
            is_personal=True,
        )
        return

    index = index % len(items)
    v = items[index]
    card = format_vacancy_public(v)
    title = v.get("position_name") or v.get("position_name_ru") or "Vakansiya"
    company = v.get("company_name") or ""

    # botga o'tish (deep-link) — aynan shu vakansiyani to'liq ochadi
    me = await query.bot.me()
    payload = f"v_{soato}_{tin}_{index}"
    open_bot_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔓 To'liq ko'rish (Telefon, ish sharti, Maosh)",
                    url=f"https://t.me/{me.username}?start={payload}",
                )
            ]
        ]
    )

    await query.answer(
        results=[
            InlineQueryResultArticle(
                id=f"{soato}_{tin}_{index}",
                title=str(title),
                description=str(company),
                input_message_content=InputTextMessageContent(
                    message_text=card, parse_mode="HTML"
                ),
                reply_markup=open_bot_kb,
            )
        ],
        cache_time=30,
        is_personal=True,
    )
