from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database import crud
from bot.database.models import User
from bot.keyboards.admin_kb import (
    admin_back,
    admin_panel,
    ads_cancel,
    ads_confirm,
    cancel_token,
)
from bot.services import broadcast, notifier, sync, token_service
from bot.services.abkm_api import fetch_totals
from bot.states import BroadcastStates, TokenStates
from bot.utils.access import is_admin
from bot.utils.timez import get_tz, local_day_start_utc, to_local

router = Router(name="admin")

PANEL_TEXT = (
    "🛠 <b>Admin panel</b>\n\n"
    "Token, sinxronlash, reklama va statistikani shu yerdan boshqarasiz."
)


def _guard(user: User | None) -> bool:
    # admin yoki superadmin (DB roli + .env)
    return is_admin(user)


@router.callback_query(F.data == "adm:menu")
async def cb_panel(call: CallbackQuery, state: FSMContext, user: User) -> None:
    if not _guard(user):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    await state.clear()
    await call.message.edit_text(PANEL_TEXT, reply_markup=admin_panel())
    await call.answer()


@router.callback_query(F.data == "adm:stats")
async def cb_stats(call: CallbackQuery, session: AsyncSession, user: User) -> None:
    if not _guard(user):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return

    tz = get_tz()
    since_utc = local_day_start_utc(datetime.now(tz))

    total = await crud.count_users(session)
    active = await crud.count_active_today(session)
    new_today = await crud.count_new_since(session, since_utc)
    banned = await crud.count_banned(session)
    admins = await crud.count_admins(session)
    vacancies = await crud.count_all_vacancies(session)
    last_sync = await crud.last_sync_at(session)
    token = token_service.get_token()
    token_short = f"…{token[-6:]}" if token else "❌ yo'q"

    sync_txt = "—"
    if last_sync:
        sync_txt = to_local(last_sync).strftime("%Y-%m-%d %H:%M")

    lines = [
        "📊 <b>Statistika</b>\n",
        f"👤 Jami foydalanuvchilar: <b>{total}</b>",
        f"🟢 Bugun aktiv: <b>{active}</b>",
        f"🆕 Bugun yangi: <b>{new_today}</b>",
        f"⛔️ Bloklangan: <b>{banned}</b>",
        f"👮 Adminlar: <b>{admins}</b>",
        f"💼 Vakansiyalar: <b>{vacancies}</b>",
        f"🔄 Oxirgi sync: <b>{sync_txt}</b>",
        f"🔑 Token: <code>{token_short}</code>",
    ]

    if broadcast.is_running():
        p = broadcast.get_progress()
        lines.append("\n📤 <b>Hozir reklama ketmoqda:</b>")
        lines.append(
            f"✅ {p['sent']}  ⛔️ {p['blocked']}  ⚠️ {p['failed']}  "
            f"⏳ {p['remaining']}/{p['total']}"
        )
        if p.get("queued"):
            lines.append(f"🗂 Navbatda: <b>{p['queued']}</b>")

    history = await crud.recent_daily_stats(session, limit=7)
    if history:
        lines.append("\n📅 <b>Oxirgi kunlar (DAU):</b>")
        for d in history:
            lines.append(
                f"• {d.day}: 🟢 {d.active_users}  🆕 {d.new_users}  👤 {d.total_users}"
            )

    await call.message.edit_text("\n".join(lines), reply_markup=admin_back())
    await call.answer()


# ---------------------------------------------------------------- broadcast
@router.callback_query(F.data == "adm:ads")
async def cb_ads_start(call: CallbackQuery, state: FSMContext, user: User) -> None:
    if not _guard(user):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    await state.set_state(BroadcastStates.waiting_content)
    note = ""
    if broadcast.is_running():
        note = (
            "\n\n⏳ Hozir boshqa reklama ketmoqda — bu yangisi "
            "<b>navbatga</b> qo'yiladi va o'z navbatida yuboriladi."
        )
    await call.message.edit_text(
        "📣 <b>Reklama yuborish</b>\n\n"
        "Yubormoqchi bo'lgan xabarni (matn, rasm, video, ...) shu yerga "
        "tashlang. Keyin tasdiqlaysiz."
        + note,
        reply_markup=ads_cancel(),
    )
    await call.answer()


@router.message(BroadcastStates.waiting_content)
async def on_ads_content(message: Message, state: FSMContext, user: User) -> None:
    if not _guard(user):
        await state.clear()
        return
    await state.update_data(
        from_chat_id=message.chat.id, message_id=message.message_id
    )
    await state.set_state(BroadcastStates.confirm)
    await message.answer(
        "👆 Mana shu xabar barcha foydalanuvchilarga yuboriladi.\n\n"
        "Tasdiqlaysizmi?",
        reply_markup=ads_confirm(),
    )


@router.callback_query(BroadcastStates.confirm, F.data == "adm:ads_go")
async def cb_ads_go(
    call: CallbackQuery, state: FSMContext, user: User
) -> None:
    if not _guard(user):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    data = await state.get_data()
    await state.clear()
    from_chat_id = data.get("from_chat_id")
    message_id = data.get("message_id")
    if not from_chat_id or not message_id:
        await call.answer("Xabar topilmadi, qaytadan boshlang.", show_alert=True)
        return

    queued = broadcast.is_running()
    await call.answer("🗂 Navbatga qo'yildi…" if queued else "📤 Yuborish boshlandi…")
    if queued:
        await call.message.edit_text(
            "🗂 <b>Reklama navbatga qo'yildi.</b>\n\n"
            "Oldingi reklama tugashi bilan avtomatik yuboriladi. "
            "Holat real-time yangilanib boradi."
        )
    else:
        await call.message.edit_text(
            "📤 <b>Reklama boshlandi.</b>\n\n"
            "Holat quyida real-time yangilanib boradi. "
            "Bot o'chib-yonsa ham jarayon avtomatik davom etadi."
        )
    # reklamani fonda boshlaymiz — jonli holatni broadcast o'zi yangilab boradi
    await broadcast.start(
        call.bot, from_chat_id, message_id, notify_chat_id=call.message.chat.id
    )


# ---------------------------------------------------------------- sync
@router.callback_query(F.data == "adm:sync")
async def cb_sync(call: CallbackQuery, user: User) -> None:
    if not _guard(user):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    if sync.is_running():
        await call.answer("⏳ Yangilash allaqachon ketmoqda.", show_alert=True)
        return
    await call.answer("🔄 Yangilash boshlandi…")
    await call.message.edit_text(
        "🔄 <b>Vakansiyalar yangilanmoqda…</b>\n\nBu biroz vaqt olishi mumkin."
    )
    try:
        await sync.sync_all(call.bot)
        await call.message.edit_text(
            "✅ <b>Vakansiyalar yangilandi.</b>", reply_markup=admin_back()
        )
    except Exception:  # noqa: BLE001
        await call.message.edit_text(
            "⚠️ Yangilashda xatolik yuz berdi. Loglarni tekshiring.",
            reply_markup=admin_back(),
        )


# ---------------------------------------------------------------- token
@router.callback_query(F.data == "adm:token")
async def cb_token_start(call: CallbackQuery, state: FSMContext, user: User) -> None:
    if not _guard(user):
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
async def on_token_received(message: Message, state: FSMContext, user: User) -> None:
    if not _guard(user):
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
