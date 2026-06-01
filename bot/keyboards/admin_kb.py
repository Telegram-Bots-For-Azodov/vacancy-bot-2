from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔑 ABKM tokenni yangilash", callback_data="adm:token")],
            [InlineKeyboardButton(text="🔄 Vakansiyalarni yangilash", callback_data="adm:sync")],
            [InlineKeyboardButton(text="📣 Reklama yuborish", callback_data="adm:ads")],
            [InlineKeyboardButton(text="📊 Statistika", callback_data="adm:stats")],
            [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="menu")],
        ]
    )


def ads_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yuborish", callback_data="adm:ads_go"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:menu"),
            ]
        ]
    )


def ads_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:menu")]
        ]
    )


def admin_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Admin panel", callback_data="adm:menu")]
        ]
    )


def cancel_token() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:menu")]
        ]
    )
