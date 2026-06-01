"""Bot entrypoint. Ishga tushirish: `python -m bot.main`"""
from __future__ import annotations

import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats
from loguru import logger

from bot.config import settings
from bot.database.db import close_db, init_db
from bot.database.seed import seed_soato
from bot.handlers import setup_routers
from bot.middlewares.auth import AuthMiddleware
from bot.services.daily import daily_loop
from bot.services.sync import sync_loop
from bot.services.token_service import load_token


def configure_logging() -> None:
    logger.remove()
    logger.add(sys.stderr, level=settings.LOG_LEVEL)
    logger.add(
        settings.logs_dir / "bot.log",
        rotation="20 MB",
        retention="14 days",
        level=settings.LOG_LEVEL,
        enqueue=True,
        encoding="utf-8",
    )


async def set_commands(bot: Bot) -> None:
    # Faqat /start — rollar /start bosilganda aniqlanadi, alohida komanda yo'q.
    cmds = [BotCommand(command="start", description="Botni ishga tushirish")]
    await bot.set_my_commands(cmds, scope=BotCommandScopeAllPrivateChats())


async def main() -> None:
    configure_logging()
    logger.info("Initialising database...")
    await init_db()
    await seed_soato()
    await load_token()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML, link_preview_is_disabled=True
        ),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    setup_routers(dp)
    await set_commands(bot)

    # fon: vakansiyalarni sinxronlash (darhol bir marta ishga tushadi)
    sync_task = asyncio.create_task(sync_loop(bot))
    # fon: har kuni 00:00 da DAU statistikasi va is_active reseti
    daily_task = asyncio.create_task(daily_loop())

    logger.info("Bot is up.")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        sync_task.cancel()
        daily_task.cancel()
        await close_db()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Interrupted")
