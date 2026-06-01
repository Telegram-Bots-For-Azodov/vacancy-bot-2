from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database import crud
from bot.database.models import District, Region
from bot.keyboards.admin_kb import admin_back, admin_panel, cancel_token
from bot.services import notifier, token_service
from bot.services.abkm_api import fetch_totals
from bot.states import TokenStates

router = Router(name="admin")

PANEL_TEXT = (
    "🛠 <b>Admin panel</b>\n\n"
    "Bu yerda ABKM tokenni yangilashingiz va statistikani ko'rishingiz mumkin."
)


def _guard(user_id: int) -> bool:
    # admin yoki superadmin (is_admin superadmin'ni ham qamrab oladi)
    return settings.is_admin(user_id)


@router.callback_query(F.data == "adm:menu")
async def cb_panel(call: CallbackQuery, state: FSMContext) -> None:
    if not _guard(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    await state.clear()
    await call.message.edit_text(PANEL_TEXT, reply_markup=admin_panel())
    await call.answer()


@router.callback_query(F.data == "adm:stats")
async def cb_stats(call: CallbackQuery, session: AsyncSession) -> None:
    if not _guard(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    users = await crud.count_users(session)
    regions = (await session.execute(select(func.count(Region.soato)))).scalar() or 0
    active_regions = await crud.count_active_regions(session)
    districts = (await session.execute(select(func.count(District.soato)))).scalar() or 0
    token = token_service.get_token()
    token_short = f"…{token[-6:]}" if token else "—"

    await call.message.edit_text(
        "📊 <b>Statistika</b>\n\n"
        f"👤 Foydalanuvchilar: <b>{users}</b>\n"
        f"🗺 Viloyatlar: <b>{active_regions}/{regions}</b> (yoqilgan/jami)\n"
        f"🏢 Tumanlar: <b>{districts}</b>\n"
        f"🔑 Joriy token: <code>{token_short}</code>",
        reply_markup=admin_back(),
    )
    await call.answer()


@router.callback_query(F.data == "adm:token")
async def cb_token_start(call: CallbackQuery, state: FSMContext) -> None:
    if not _guard(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    await state.set_state(TokenStates.waiting_token)
    await call.message.edit_text(
        "🔑 <b>ABKM tokenni yangilash</b>\n\n"
        "Yangi tokenni (Bearer qiymati) shu yerga <b>matn</b> ko'rinishida yuboring.\n\n"
        "<i>Qayerdan olish: abkm.mehnat.uz → F12 → Network → so'rovdagi "
        "<code>Authorization: Bearer ...</code> yoki <code>abkm_token</code> cookie.</i>",
        reply_markup=cancel_token(),
    )
    await call.answer()


@router.message(TokenStates.waiting_token, F.text)
async def on_token_received(message: Message, state: FSMContext) -> None:
    if not _guard(message.from_user.id):
        await state.clear()
        return

    new_token = message.text.strip()
    # "Bearer xxx" yoki "abkm_token=xxx" ko'rinishida kelsa tozalaymiz
    if new_token.lower().startswith("bearer "):
        new_token = new_token[7:].strip()
    if new_token.lower().startswith("abkm_token="):
        new_token = new_token.split("=", 1)[1].strip()

    if len(new_token) < 10:
        await message.answer("❌ Token juda qisqa ko'rinadi. Qaytadan yuboring.")
        return

    await token_service.set_token(new_token)
    notifier.reset()
    await state.clear()

    # yangi tokenni tezda sinab ko'ramiz
    try:
        totals = await fetch_totals([1733])  # Xorazm
        ok = totals.get(1733, -1) >= 0
    except Exception:  # noqa: BLE001
        ok = False

    if ok:
        await message.answer(
            "✅ <b>Token yangilandi va ishlayapti!</b>", reply_markup=admin_back()
        )
    else:
        await message.answer(
            "⚠️ Token saqlandi, lekin sinovda ma'lumot kelmadi.\n"
            "Token to'g'riligini tekshirib, qaytadan urinib ko'ring.",
            reply_markup=admin_back(),
        )
