from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database import crud
from bot.database.models import User
from bot.keyboards.user_kb import (
    ALL_DISTRICTS,
    back_menu_kb,
    back_only_kb,
    districts_kb,
    main_menu,
    org_vacancy_nav_kb,
    orgs_kb,
    regions_kb,
    top_list_kb,
    top_vacancy_kb,
)
from bot.services import currency
from bot.services.formatter import format_vacancy, top_button_label
from bot.utils.access import is_admin, is_superadmin


def _menu_for(user: User | None):
    return main_menu(
        is_admin=is_admin(user),
        is_superadmin=is_superadmin(user),
    )

router = Router(name="user")

WELCOME = (
    "👋 Assalomu alaykum, <b>{name}</b>!\n\n"
    "Bu bot orqali O'zbekiston bo'yicha <b>bo'sh ish o'rinlari</b> bilan "
    "tanishishingiz mumkin.\n\nQuyidagi tugmani tanlang 👇"
)

ABOUT_TEXT = (
    "ℹ️ <b>Bot haqida</b>\n\n"
    "Ushbu bot O'zbekiston bo'sh ish o'rinlari (vakansiyalar) haqida "
    "ma'lumot beradi. Ma'lumotlar <b>abkm.mehnat.uz</b> rasmiy bazasidan olinadi."
)


def _region_of(soato: int) -> int:
    """Tuman SOATO (7 xonali) dan viloyat SOATO (4 xonali) ni chiqaradi."""
    return soato if soato < 10000 else int(str(soato)[:4])


@router.message(CommandStart())
async def cmd_start(
    message: Message, session: AsyncSession, command: CommandObject, user: User
) -> None:
    # deep-link: /start v_{soato}_{tin}_{index} -> shu vakansiyani to'liq ochish
    payload = (command.args or "").strip()
    if payload.startswith("v_"):
        try:
            _, soato_s, tin, idx_s = payload.split("_")
            await _start_open_vacancy(
                message, session, int(soato_s), tin, int(idx_s), user
            )
            return
        except (ValueError, IndexError):
            pass

    name = message.from_user.full_name if message.from_user else "do'stim"
    await message.answer(
        WELCOME.format(name=name),
        reply_markup=_menu_for(user),
    )


async def _start_open_vacancy(
    message: Message, session: AsyncSession, soato: int, tin: str, index: int,
    user: User,
) -> None:
    region_soato = _region_of(soato)
    items = await crud.list_company_vacancies(session, region_soato, soato, tin)
    if not items:
        await message.answer(
            "😕 Vakansiya topilmadi yoki muddati o'tgan.",
            reply_markup=_menu_for(user),
        )
        return

    index = index % len(items)
    text = format_vacancy(items[index], index, len(items))
    kb = org_vacancy_nav_kb(region_soato, soato, tin, index, len(items), page=0)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery, user: User) -> None:
    await call.message.edit_text(
        WELCOME.format(name=call.from_user.full_name),
        reply_markup=_menu_for(user),
    )
    await call.answer()


@router.callback_query(F.data == "about")
async def cb_about(call: CallbackQuery) -> None:
    await call.message.edit_text(ABOUT_TEXT, reply_markup=back_menu_kb())
    await call.answer()


# ---------------------------------------------------------------- top salaries
TOP_LIMIT = 10


@router.callback_query(F.data == "top")
async def cb_top(call: CallbackQuery, session: AsyncSession) -> None:
    """Oylik maosh bo'yicha eng yuqori 10 ta vakansiyani tugma shaklida ko'rsatadi."""
    await call.answer()
    items = await crud.top_salary_vacancies(session, TOP_LIMIT)
    if not items:
        await call.message.edit_text(
            "😕 Hozircha maoshi ko'rsatilgan vakansiyalar topilmadi.",
            reply_markup=back_menu_kb(),
        )
        return
    labels = [top_button_label(v, rank=i + 1) for i, v in enumerate(items)]
    await call.message.edit_text(
        "💰 <b>Eng yuqori oylik maoshli TOP 10 ish o'rni</b>\n\n"
        "Batafsil ko'rish uchun tegishli tugmani bosing 👇",
        reply_markup=top_list_kb(labels),
    )


@router.callback_query(F.data.startswith("topv:"))
async def cb_top_vacancy(call: CallbackQuery, session: AsyncSession) -> None:
    await call.answer()
    index = int(call.data.split(":")[1])
    items = await crud.top_salary_vacancies(session, TOP_LIMIT)
    if not items:
        await call.message.edit_text(
            "😕 Vakansiyalar yangilangan, ro'yxatni qaytadan oching.",
            reply_markup=back_menu_kb(),
        )
        return
    total = len(items)
    index = index % total
    text = format_vacancy(items[index], index, total)
    try:
        await call.message.edit_text(text, reply_markup=top_vacancy_kb(index, total))
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data == "rates")
async def cb_rates(call: CallbackQuery) -> None:
    await call.answer("⏳ Kurslar yuklanmoqda...")
    text = await currency.get_rates_text()
    await call.message.edit_text(text, reply_markup=back_menu_kb())


# ---------------------------------------------------------------- browse entry
@router.callback_query(F.data == "browse")
async def cb_browse(call: CallbackQuery, session: AsyncSession) -> None:
    """Superadmin sozlamasiga qarab kerakli bosqichdan boshlaydi."""
    regions = await crud.list_regions(session)  # faqat active
    if not regions:
        await call.answer(
            "😕 Hozircha hududlar mavjud emas. Keyinroq urinib ko'ring.",
            show_alert=True,
        )
        return

    if len(regions) > 1:
        await call.message.edit_text(
            "🗺 <b>Viloyatni tanlang:</b>", reply_markup=regions_kb(regions)
        )
        await call.answer()
        return

    # bitta viloyat yoqilgan -> tumanlar yoki to'g'ridan-to'g'ri tashkilotlar
    region = regions[0]
    districts = await crud.list_districts(session, region.soato)
    if len(districts) == 1:
        await _show_orgs(call, session, region.soato, districts[0].soato, page=0)
        return
    if len(districts) == 0:
        await _show_orgs(call, session, region.soato, region.soato, page=0)
        return

    await _show_districts(call, session, region.soato)


@router.callback_query(F.data == "regions")
async def cb_regions(call: CallbackQuery, session: AsyncSession) -> None:
    regions = await crud.list_regions(session)
    if not regions:
        await call.answer("Hozircha hududlar mavjud emas.", show_alert=True)
        return
    await call.message.edit_text(
        "🗺 <b>Viloyatni tanlang:</b>", reply_markup=regions_kb(regions)
    )
    await call.answer()


@router.callback_query(F.data.startswith("reg:"))
async def cb_region(call: CallbackQuery, session: AsyncSession) -> None:
    region_soato = int(call.data.split(":")[1])
    await _show_districts(call, session, region_soato)


async def _show_districts(
    call: CallbackQuery, session: AsyncSession, region_soato: int
) -> None:
    region = await crud.get_region(session, region_soato)
    districts = await crud.list_districts(session, region_soato)
    if region is None:
        await call.answer("Viloyat topilmadi.", show_alert=True)
        return

    await call.answer()

    counts = await crud.district_counts(session, region_soato)
    region_total = sum(counts.values()) if counts else -1
    multi_region = await crud.count_active_regions(session) > 1
    await call.message.edit_text(
        f"🏙 <b>{region.name}</b>\n"
        f"Jami: <b>{region_total if region_total >= 0 else '—'}</b> ta bo'sh ish o'rni\n\n"
        "Tuman yoki shaharni tanlang:",
        reply_markup=districts_kb(
            region_soato, districts, counts, region_total,
            show_regions_back=multi_region,
        ),
    )


@router.callback_query(F.data.startswith("dist:"))
async def cb_district(call: CallbackQuery, session: AsyncSession) -> None:
    _, region_s, district_s = call.data.split(":")
    region_soato = int(region_s)
    soato = region_soato if district_s == ALL_DISTRICTS else int(district_s)
    await _show_orgs(call, session, region_soato, soato, page=0)


@router.callback_query(F.data.startswith("orgs:"))
async def cb_orgs(call: CallbackQuery, session: AsyncSession) -> None:
    _, region_s, soato_s, page_s = call.data.split(":")
    await _show_orgs(call, session, int(region_s), int(soato_s), page=int(page_s))


@router.callback_query(F.data.startswith("ov:"))
async def cb_org_vacancy(call: CallbackQuery, session: AsyncSession) -> None:
    _, region_s, soato_s, tin, idx_s, page_s = call.data.split(":")
    await _show_org_vacancy(
        call, session, int(region_s), int(soato_s), tin, int(idx_s), int(page_s)
    )


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery) -> None:
    await call.answer()


async def _compute_back_target(session: AsyncSession, region_soato: int) -> str:
    if await crud.count_active_districts(session, region_soato) > 1:
        return "districts"
    if await crud.count_active_regions(session) > 1:
        return "regions"
    return "menu"


async def _area_name(session: AsyncSession, region_soato: int, soato: int) -> str:
    if soato == region_soato:
        region = await crud.get_region(session, region_soato)
        return region.name if region else "Viloyat"
    district = await crud.get_district(session, soato)
    return district.name if district else "Hudud"


async def _show_orgs(
    call: CallbackQuery,
    session: AsyncSession,
    region_soato: int,
    soato: int,
    page: int,
) -> None:
    await call.answer()
    orgs = await crud.list_companies(session, region_soato, soato)

    back_target = await _compute_back_target(session, region_soato)
    name = await _area_name(session, region_soato, soato)

    if not orgs:
        await call.message.edit_text(
            f"🏙 <b>{name}</b>\n\n😕 Bu hududda hozircha vakansiyasi bor "
            "tashkilotlar topilmadi.",
            reply_markup=back_only_kb(region_soato, back_target),
        )
        return

    total_vac = sum(int(o.get("count", 0) or 0) for o in orgs)
    await call.message.edit_text(
        f"🏙 <b>{name}</b>\n"
        f"🏢 Tashkilotlar: <b>{len(orgs)}</b>  •  💼 Vakansiyalar: <b>{total_vac}</b>\n\n"
        "Tashkilotni tanlang:",
        reply_markup=orgs_kb(region_soato, soato, orgs, page, back_target),
    )


async def _show_org_vacancy(
    call: CallbackQuery,
    session: AsyncSession,
    region_soato: int,
    soato: int,
    company_tin: str,
    index: int,
    page: int,
) -> None:
    await call.answer()
    items = await crud.list_company_vacancies(session, region_soato, soato, company_tin)
    if not items:
        await call.answer("Bu tashkilotda vakansiya topilmadi.", show_alert=True)
        return

    total = len(items)
    index = index % total
    text = format_vacancy(items[index], index, total)
    kb = org_vacancy_nav_kb(region_soato, soato, company_tin, index, total, page)
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:  # noqa: BLE001
        pass
