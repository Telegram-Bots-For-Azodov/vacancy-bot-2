"""Har bir update uchun DB sessiya ochadi va foydalanuvchini ro'yxatga oladi."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User as TgUser

from bot.database.crud import get_or_create_user
from bot.database.db import SessionLocal


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")

        async with SessionLocal() as session:
            data["session"] = session
            # `user` HAR DOIM data'da bo'lsin — from_user yo'q updatelar (kanal
            # postlari va h.k.) uchun handler "missing argument 'user'" bermasin.
            data["user"] = None
            if tg_user is not None and not tg_user.is_bot:
                user = await get_or_create_user(
                    session,
                    tg_id=tg_user.id,
                    username=tg_user.username,
                    full_name=tg_user.full_name,
                )
                if user.is_banned:
                    if isinstance(event, Message):
                        await event.answer("⛔️ Siz bloklangansiz.")
                    elif isinstance(event, CallbackQuery):
                        await event.answer("⛔️ Bloklangansiz.", show_alert=True)
                    return None
                data["user"] = user
            return await handler(event, data)
