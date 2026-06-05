"""Bot entrypoint.

Ikki rejim (env orqali):
  * polling (standart)        -> `python -m bot.main`
  * webhook  (WEBHOOK_MODE=1) -> self-hosted telegram-bot-api bilan ishlaydi

Qo'shimcha env o'zgaruvchilari:
  TELEGRAM_API_BASE  -> local Bot API server, masalan http://telegram-bot-api:8081
  WEBHOOK_MODE       -> "1" bo'lsa webhook rejimi
  WEBHOOK_URL        -> telegram-bot-api shu manzilga update yuboradi (masalan https://azodov.uz)
  WEBHOOK_PATH       -> webhook yo'li, masalan /webhook/<secret>
  WEBHOOK_SECRET     -> X-Telegram-Bot-Api-Secret-Token (ixtiyoriy, lekin tavsiya etiladi)
  WEBAPP_HOST/PORT   -> aiohttp server (standart 0.0.0.0:8080)
"""
from __future__ import annotations

import asyncio
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from loguru import logger

from bot.config import settings
from bot.database.db import close_db, init_db
from bot.database.seed import seed_soato
from bot.handlers import setup_routers
from bot.middlewares.auth import AuthMiddleware
from bot.services import broadcast
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
    cmds = [BotCommand(command="start", description="Botni ishga tushirish")]
    await bot.set_my_commands(cmds, scope=BotCommandScopeAllPrivateChats())


def build_bot() -> Bot:
    """Bot obyektini sessiya (local API server / proxy) bilan tayyorlaydi."""
    proxy = settings.TELEGRAM_PROXY or None
    api_base = os.getenv("TELEGRAM_API_BASE", "").strip()
    if api_base:
        api = TelegramAPIServer.from_base(api_base, is_local=False)
        session = AiohttpSession(api=api, proxy=proxy, timeout=60)
        logger.info(f"Local Bot API server ishlatiladi: {api_base}")
    else:
        session = AiohttpSession(proxy=proxy, timeout=60)
        if proxy:
            logger.info("Telegram proxy orqali ishlaydi.")
    return Bot(
        token=settings.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML, link_preview_is_disabled=True
        ),
    )


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    setup_routers(dp)
    return dp


async def _common_startup(bot: Bot) -> list[asyncio.Task]:
    """Baza, komandalar, fon vazifalari — har ikki rejim uchun umumiy."""
    logger.info("Initialising database...")
    await init_db()
    await seed_soato()
    await load_token()

    try:
        await set_commands(bot)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"set_commands o'tkazib yuborildi (tarmoq?): {e}")

    try:
        await broadcast.resume_pending(bot)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"broadcast resume xato: {e}")

    return [
        asyncio.create_task(sync_loop(bot)),
        asyncio.create_task(daily_loop()),
    ]


async def _common_shutdown(bot: Bot, tasks: list[asyncio.Task]) -> None:
    for t in tasks:
        t.cancel()
    await close_db()
    await bot.session.close()
    logger.info("Bot stopped.")


# ------------------------- POLLING -------------------------

async def run_polling() -> None:
    bot = build_bot()
    dp = build_dispatcher()
    tasks = await _common_startup(bot)
    logger.info("Bot is up (polling).")
    try:
        await dp.start_polling(
            bot, allowed_updates=dp.resolve_used_update_types()
        )
    finally:
        await _common_shutdown(bot, tasks)


# ------------------------- WEBHOOK -------------------------

def run_webhook() -> None:
    bot = build_bot()
    dp = build_dispatcher()

    path = os.getenv("WEBHOOK_PATH", "/webhook").strip()
    base_url = os.getenv("WEBHOOK_URL", "").strip().rstrip("/")
    secret = os.getenv("WEBHOOK_SECRET", "").strip() or None
    host = os.getenv("WEBAPP_HOST", "0.0.0.0")
    port = int(os.getenv("WEBAPP_PORT", "8080"))

    if not base_url:
        raise RuntimeError("WEBHOOK_URL o'rnatilmagan (webhook rejimi uchun majburiy).")

    tasks: list[asyncio.Task] = []

    async def _on_startup(**_: object) -> None:
        tasks.extend(await _common_startup(bot))
        await bot.set_webhook(
            url=base_url + path,
            secret_token=secret,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True,
        )
        logger.info(f"Webhook o'rnatildi: {base_url + path}")
        logger.info("Bot is up (webhook).")

    async def _on_shutdown(**_: object) -> None:
        await _common_shutdown(bot, tasks)

    dp.startup.register(_on_startup)
    dp.shutdown.register(_on_shutdown)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=secret).register(
        app, path=path
    )
    # /healthz — oddiy tekshiruv uchun
    async def _health(_req: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_get("/healthz", _health)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host=host, port=port, print=None)


def main() -> None:
    configure_logging()
    if os.getenv("WEBHOOK_MODE", "").strip() in {"1", "true", "True", "yes"}:
        run_webhook()
    else:
        try:
            asyncio.run(run_polling())
        except (KeyboardInterrupt, SystemExit):
            logger.info("Interrupted")


if __name__ == "__main__":
    main()
