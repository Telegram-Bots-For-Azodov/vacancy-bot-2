from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database import crud
from bot.keyboards.superadmin_kb import (
    sa_admins_kb,
    sa_districts_kb,
    sa_panel,
    sa_regions_kb,
)
from bot.states import AdminMgmtStates

router = Router(name="superadmin")

ADMINS_TEXT = (
    "👮 <b>Adminlar</b>\n\n"
    "👑 — superadmin (o'zgartirib bo'lmaydi)\n"
    "🛠 — admin\n\n"
    "Admin qo'shish uchun «➕ Admin qo'shish» tugmasini bosing."
)

PANEL_TEXT = (
    "👑 <b>Superadmin panel</b>\n\n"
    "Bu yerda foydalanuvchilarga qaysi hududlar ko'rinishini boshqarasiz.\n\n"
    "• Bir nechta viloyat yoqilsa — foydalanuvchi viloyatlar ro'yxatini ko'radi\n"
    "• Faqat 1 viloyat yoqilsa — to'g'ridan-to'g'ri uning tumanlari ochiladi\n"
    "• Faqat 1 tuman yoqilsa — to'g'ridan-to'g'ri vakansiyalarga o'tadi"
)

REGIONS_TEXT = (
    "🗺 <b>Hududlar</b>\n\n"
    "✅ — yoqilgan, ▫️ — o'chirilgan\n"
    "Nomni bossangiz — holati o'zgaradi\n"
    "🎯 — faqat shu viloyat qolsin\n"
    "🏢 — tumanlarini boshqarish"
)


def _guard(user_id: int) -> bool:
    return settings.is_superadmin(user_id)


@router.message(Command("superadmin"))
async def cmd_superadmin(message: Message) -> None:
    if not _guard(message.from_user.id):
        return
    await message.answer(PANEL_TEXT, reply_markup=sa_panel())


@router.callback_query(F.data == "sa:menu")
async def cb_panel(call: CallbackQuery) -> None:
    if not _guard(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    await call.message.edit_text(PANEL_TEXT, reply_markup=sa_panel())
    await call.answer()


@router.callback_query(F.data == "sa:noop")
async def cb_noop(call: CallbackQuery) -> None:
    await call.answer()


# ------------------------------------------------------------- admins mgmt
@router.callback_query(F.data == "sa:admins")
async def cb_admins(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not _guard(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    await state.clear()
    admins = await crud.list_admins(session)
    await call.message.edit_text(ADMINS_TEXT, reply_markup=sa_admins_kb(admins))
    await call.answer()


@router.callback_query(F.data == "sa:adm_add")
async def cb_admin_add(call: CallbackQuery, state: FSMContext) -> None:
    if not _guard(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    await state.set_state(AdminMgmtStates.waiting_add)
    await call.message.edit_text(
        "➕ <b>Admin qo'shish</b>\n\n"
        "Foydalanuvchining <b>ID</b> raqami yoki <b>@username</b> ni yuboring.\n\n"
        "<i>Eslatma: u avval botda /start bosgan bo'lishi kerak.</i>"
    )
    await call.answer()


@router.message(AdminMgmtStates.waiting_add, F.text)
async def on_admin_add(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not _guard(message.from_user.id):
        await state.clear()
        return
    target = await crud.find_user(session, message.text)
    if target is None:
        await message.answer(
            "😕 Bunday foydalanuvchi topilmadi. U avval botda /start bosganmi?\n"
            "ID yoki @username ni qaytadan yuboring."
        )
        return
    await crud.set_admin(session, target.id, make_admin=True)
    await state.clear()
    admins = await crud.list_admins(session)
    name = target.full_name or target.username or target.id
    await message.answer(
        f"✅ <b>{name}</b> admin qilib belgilandi.",
        reply_markup=sa_admins_kb(admins),
    )


@router.callback_query(F.data.startswith("sa:adm_del:"))
async def cb_admin_del(call: CallbackQuery, session: AsyncSession) -> None:
    if not _guard(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    tg_id = int(call.data.split(":")[2])
    await crud.set_admin(session, tg_id, make_admin=False)
    admins = await crud.list_admins(session)
    await call.message.edit_reply_markup(reply_markup=sa_admins_kb(admins))
    await call.answer("Adminlikdan olindi.")


@router.callback_query(F.data == "sa:regions")
async def cb_regions(call: CallbackQuery, session: AsyncSession) -> None:
    if not _guard(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    regions = await crud.list_regions(session, only_active=False)
    await call.message.edit_text(REGIONS_TEXT, reply_markup=sa_regions_kb(regions))
    await call.answer()


@router.callback_query(F.data.startswith("sa:rtog:"))
async def cb_region_toggle(call: CallbackQuery, session: AsyncSession) -> None:
    if not _guard(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    soato = int(call.data.split(":")[2])
    region = await crud.get_region(session, soato)
    if region:
        await crud.set_region_active(session, soato, not region.is_active)
    regions = await crud.list_regions(session, only_active=False)
    await call.message.edit_reply_markup(reply_markup=sa_regions_kb(regions))
    await call.answer("Holat o'zgartirildi.")


@router.callback_query(F.data.startswith("sa:ronly:"))
async def cb_region_only(call: CallbackQuery, session: AsyncSession) -> None:
    if not _guard(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    soato = int(call.data.split(":")[2])
    await crud.set_only_region(session, soato)
    region = await crud.get_region(session, soato)
    regions = await crud.list_regions(session, only_active=False)
    await call.message.edit_reply_markup(reply_markup=sa_regions_kb(regions))
    name = region.name if region else ""
    await call.answer(f"Faqat «{name}» yoqildi.", show_alert=True)


@router.callback_query(F.data.startswith("sa:rdist:"))
async def cb_region_districts(call: CallbackQuery, session: AsyncSession) -> None:
    if not _guard(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    soato = int(call.data.split(":")[2])
    region = await crud.get_region(session, soato)
    districts = await crud.list_districts(session, soato, only_active=False)
    title = (
        f"🏢 <b>{region.name if region else ''}</b> — tumanlar\n\n"
        "✅ yoqilgan, ▫️ o'chirilgan. 🎯 — faqat shu tuman qolsin."
    )
    await call.message.edit_text(title, reply_markup=sa_districts_kb(soato, districts))
    await call.answer()


@router.callback_query(F.data.startswith("sa:dtog:"))
async def cb_district_toggle(call: CallbackQuery, session: AsyncSession) -> None:
    if not _guard(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    _, _, region_s, district_s = call.data.split(":")
    region_soato, district_soato = int(region_s), int(district_s)
    district = await crud.get_district(session, district_soato)
    if district:
        await crud.set_district_active(session, district_soato, not district.is_active)
    districts = await crud.list_districts(session, region_soato, only_active=False)
    await call.message.edit_reply_markup(
        reply_markup=sa_districts_kb(region_soato, districts)
    )
    await call.answer("Holat o'zgartirildi.")


@router.callback_query(F.data.startswith("sa:donly:"))
async def cb_district_only(call: CallbackQuery, session: AsyncSession) -> None:
    if not _guard(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    _, _, region_s, district_s = call.data.split(":")
    region_soato, district_soato = int(region_s), int(district_s)
    await crud.set_only_district(session, region_soato, district_soato)
    district = await crud.get_district(session, district_soato)
    districts = await crud.list_districts(session, region_soato, only_active=False)
    await call.message.edit_reply_markup(
        reply_markup=sa_districts_kb(region_soato, districts)
    )
    name = district.name if district else ""
    await call.answer(f"Faqat «{name}» yoqildi.", show_alert=True)


@router.callback_query(F.data.startswith("sa:dall_on:"))
async def cb_district_all_on(call: CallbackQuery, session: AsyncSession) -> None:
    if not _guard(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    region_soato = int(call.data.split(":")[2])
    districts = await crud.list_districts(session, region_soato, only_active=False)
    for d in districts:
        if not d.is_active:
            await crud.set_district_active(session, d.soato, True)
    districts = await crud.list_districts(session, region_soato, only_active=False)
    await call.message.edit_reply_markup(
        reply_markup=sa_districts_kb(region_soato, districts)
    )
    await call.answer("Barcha tumanlar yoqildi.")


@router.callback_query(F.data.startswith("sa:dall_off:"))
async def cb_district_all_off(call: CallbackQuery, session: AsyncSession) -> None:
    if not _guard(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    region_soato = int(call.data.split(":")[2])
    districts = await crud.list_districts(session, region_soato, only_active=False)
    for d in districts:
        if d.is_active:
            await crud.set_district_active(session, d.soato, False)
    districts = await crud.list_districts(session, region_soato, only_active=False)
    await call.message.edit_reply_markup(
        reply_markup=sa_districts_kb(region_soato, districts)
    )
    await call.answer("Barcha tumanlar o'chirildi.")


@router.callback_query(F.data == "sa:all_on")
async def cb_all_on(call: CallbackQuery, session: AsyncSession) -> None:
    if not _guard(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    await crud.set_all_active(session, True)
    regions = await crud.list_regions(session, only_active=False)
    await call.message.edit_text(REGIONS_TEXT, reply_markup=sa_regions_kb(regions))
    await call.answer("Butun respublika yoqildi.", show_alert=True)


@router.callback_query(F.data == "sa:all_off")
async def cb_all_off(call: CallbackQuery, session: AsyncSession) -> None:
    if not _guard(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    await crud.set_all_active(session, False)
    regions = await crud.list_regions(session, only_active=False)
    await call.message.edit_text(REGIONS_TEXT, reply_markup=sa_regions_kb(regions))
    await call.answer("Hammasi o'chirildi.", show_alert=True)
