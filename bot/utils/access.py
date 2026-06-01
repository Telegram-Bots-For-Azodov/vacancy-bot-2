"""Rol tekshiruvi — DB roli va .env ikkisini ham hisobga oladi.

- Superadmin: faqat .env orqali (dasturchi) qo'yiladi.
- Admin: .env yoki superadmin tomonidan DB'da ADMIN qilib belgilangan.
"""
from __future__ import annotations

from bot.config import settings
from bot.database.models import Role, User


def is_superadmin(user: User | None) -> bool:
    if user is None:
        return False
    return user.role == Role.SUPERADMIN or settings.is_superadmin(user.id)


def is_admin(user: User | None) -> bool:
    if user is None:
        return False
    if user.role in (Role.ADMIN, Role.SUPERADMIN):
        return True
    return settings.is_admin(user.id)
