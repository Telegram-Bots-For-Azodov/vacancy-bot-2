from aiogram import Dispatcher

from bot.handlers import admin, inline, superadmin, user


def setup_routers(dp: Dispatcher) -> None:
    dp.include_router(superadmin.router)
    dp.include_router(admin.router)
    dp.include_router(inline.router)
    dp.include_router(user.router)
