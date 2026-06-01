from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database.models import District, Region, Role, User


def _mark(active: bool) -> str:
    return "✅" if active else "▫️"


def sa_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗺 Hududlarni boshqarish", callback_data="sa:regions")],
            [
                InlineKeyboardButton(text="✅ Butun respublika", callback_data="sa:all_on"),
                InlineKeyboardButton(text="❌ Hammasini o'chirish", callback_data="sa:all_off"),
            ],
            [InlineKeyboardButton(text="👮 Adminlar", callback_data="sa:admins")],
            [InlineKeyboardButton(text="🛠 Admin panel", callback_data="adm:menu")],
            [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu")],
        ]
    )


def sa_admins_kb(admins: list[User]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for u in admins:
        if u.role == Role.SUPERADMIN:
            label = f"👑 {u.full_name or u.username or u.id}"
            rows.append([InlineKeyboardButton(text=label, callback_data="sa:noop")])
        else:
            label = f"🛠 {u.full_name or u.username or u.id}"
            rows.append(
                [
                    InlineKeyboardButton(text=label, callback_data="sa:noop"),
                    InlineKeyboardButton(
                        text="❌ olib tashlash", callback_data=f"sa:adm_del:{u.id}"
                    ),
                ]
            )
    rows.append([InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="sa:adm_add")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="sa:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sa_regions_kb(regions: list[Region]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="✅ Hammasi", callback_data="sa:all_on"),
            InlineKeyboardButton(text="❌ Hammasi", callback_data="sa:all_off"),
        ]
    ]
    for r in regions:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{_mark(r.is_active)} {r.name}",
                    callback_data=f"sa:rtog:{r.soato}",
                ),
                InlineKeyboardButton(text="🎯", callback_data=f"sa:ronly:{r.soato}"),
                InlineKeyboardButton(text="🏢", callback_data=f"sa:rdist:{r.soato}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="sa:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sa_districts_kb(
    region_soato: int, districts: list[District]
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="✅ Hammasi", callback_data=f"sa:dall_on:{region_soato}"
            ),
            InlineKeyboardButton(
                text="❌ Hammasi", callback_data=f"sa:dall_off:{region_soato}"
            ),
        ]
    ]
    for d in districts:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{_mark(d.is_active)} {d.name}",
                    callback_data=f"sa:dtog:{region_soato}:{d.soato}",
                ),
                InlineKeyboardButton(
                    text="🎯", callback_data=f"sa:donly:{region_soato}:{d.soato}"
                ),
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="⬅️ Viloyatlar", callback_data="sa:regions")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
