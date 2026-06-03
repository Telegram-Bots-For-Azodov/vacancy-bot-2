from __future__ import annotations

import math

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database.models import District, Region

ALL_DISTRICTS = "all"
ORGS_PER_PAGE = 8


def _short(name: str, limit: int = 30) -> str:
    name = (name or "").strip()
    return name if len(name) <= limit else name[: limit - 1] + "…"


def _fmt_count(total: int) -> str:
    """Vakansiya sonini chiroyli ko'rsatish."""
    if total is None or total < 0:
        return "—"
    return f"{total} ta"


def main_menu(is_admin: bool = False, is_superadmin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🔍 Bo'sh ish o'rinlari", callback_data="browse")],
        [InlineKeyboardButton(text="💰 Eng yuqori maoshli (TOP 10)", callback_data="top")],
        [InlineKeyboardButton(text="💵 Valyuta kurslari", callback_data="rates")],
        [InlineKeyboardButton(text="ℹ️ Bot haqida", callback_data="about")],
    ]
    if is_superadmin:
        rows.append(
            [InlineKeyboardButton(text="👑 Superadmin panel", callback_data="sa:menu")]
        )
    if is_admin or is_superadmin:
        rows.append(
            [InlineKeyboardButton(text="🛠 Admin panel", callback_data="adm:menu")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu")]
        ]
    )


def top_list_kb(labels: list[str]) -> InlineKeyboardMarkup:
    """TOP-10 maoshli vakansiyalar — har biri tugma (topv:{index})."""
    rows: list[list[InlineKeyboardButton]] = []
    for i, label in enumerate(labels):
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"topv:{i}")]
        )
    rows.append([InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def top_vacancy_kb(index: int, total: int) -> InlineKeyboardMarkup:
    """Bitta TOP vakansiya kartochkasi — oldingi/keyingi + ro'yxatga qaytish."""
    rows: list[list[InlineKeyboardButton]] = []
    if total > 1:
        prev_idx = (index - 1) % total
        next_idx = (index + 1) % total
        rows.append(
            [
                InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"topv:{prev_idx}"),
                InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="noop"),
                InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"topv:{next_idx}"),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="⬅️ TOP ro'yxat", callback_data="top"),
            InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def regions_kb(regions: list[Region]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for r in regions:
        row.append(
            InlineKeyboardButton(text=f"📍 {r.name}", callback_data=f"reg:{r.soato}")
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def districts_kb(
    region_soato: int,
    districts: list[District],
    counts: dict[int, int],
    region_total: int,
    show_regions_back: bool = True,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"📋 Barcha tumanlar  •  {_fmt_count(region_total)}",
                callback_data=f"dist:{region_soato}:{ALL_DISTRICTS}",
            )
        ]
    ]
    for d in districts:
        total = counts.get(d.soato, -1)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🏢 {d.name}  •  {_fmt_count(total)}",
                    callback_data=f"dist:{region_soato}:{d.soato}",
                )
            ]
        )
    if show_regions_back:
        rows.append(
            [InlineKeyboardButton(text="⬅️ Viloyatlar", callback_data="regions")]
        )
    else:
        rows.append(
            [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def orgs_kb(
    region_soato: int,
    soato: int,
    orgs: list[dict],
    page: int,
    back_target: str = "districts",
) -> InlineKeyboardMarkup:
    """Korxonalar ro'yxati (sahifalangan). orgs: {tin, name, count}."""
    total = len(orgs)
    pages = max(1, math.ceil(total / ORGS_PER_PAGE))
    page = max(0, min(page, pages - 1))
    start = page * ORGS_PER_PAGE
    chunk = orgs[start : start + ORGS_PER_PAGE]

    rows: list[list[InlineKeyboardButton]] = []
    for o in chunk:
        name = _short(o.get("name") or "Tashkilot")
        cnt = int(o.get("count", 0) or 0)
        tin = o.get("tin")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🏢 {name}  •  {cnt} ta",
                    callback_data=f"ov:{region_soato}:{soato}:{tin}:0:{page}",
                )
            ]
        )

    if pages > 1:
        prev_p = (page - 1) % pages
        next_p = (page + 1) % pages
        rows.append(
            [
                InlineKeyboardButton(
                    text="⬅️", callback_data=f"orgs:{region_soato}:{soato}:{prev_p}"
                ),
                InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"),
                InlineKeyboardButton(
                    text="➡️", callback_data=f"orgs:{region_soato}:{soato}:{next_p}"
                ),
            ]
        )

    rows.append([_back_button(region_soato, back_target)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def org_vacancy_nav_kb(
    region_soato: int,
    soato: int,
    company_tin: str,
    index: int,
    total: int,
    page: int,
) -> InlineKeyboardMarkup:
    """Korxona vakansiyalarini aylantiruvchi klaviatura."""
    rows: list[list[InlineKeyboardButton]] = []
    if total > 1:
        prev_idx = (index - 1) % total
        next_idx = (index + 1) % total
        rows.append(
            [
                InlineKeyboardButton(
                    text="⬅️ Oldingi",
                    callback_data=f"ov:{region_soato}:{soato}:{company_tin}:{prev_idx}:{page}",
                ),
                InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="noop"),
                InlineKeyboardButton(
                    text="Keyingi ➡️",
                    callback_data=f"ov:{region_soato}:{soato}:{company_tin}:{next_idx}:{page}",
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="📤 Ulashish",
                switch_inline_query=f"v_{soato}_{company_tin}_{index}",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Tashkilotlar",
                callback_data=f"orgs:{region_soato}:{soato}:{page}",
            ),
            InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _back_button(region_soato: int, back_target: str) -> InlineKeyboardButton:
    if back_target == "districts":
        return InlineKeyboardButton(text="⬅️ Tumanlar", callback_data=f"reg:{region_soato}")
    if back_target == "regions":
        return InlineKeyboardButton(text="⬅️ Viloyatlar", callback_data="regions")
    return InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu")


def back_only_kb(region_soato: int, back_target: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_back_button(region_soato, back_target)]]
    )
