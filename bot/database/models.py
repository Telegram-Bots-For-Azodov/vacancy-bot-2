from datetime import datetime, timezone
from enum import Enum as PyEnum


def utcnow() -> datetime:
    """Timezone-aware UTC vaqt (datetime.utcnow eskirgan)."""
    return datetime.now(timezone.utc)

from sqlalchemy import (
    BigInteger,
    String,
    Integer,
    DateTime,
    Boolean,
    ForeignKey,
    Enum,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Role(str, PyEnum):
    USER = "user"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # telegram id
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.USER)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    # kunlik faollik bayrog'i (DAU): har kuni 00:00 da false, foydalansa true
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_active: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AppSetting(Base):
    """Runtime sozlamalar (kalit-qiymat). Masalan: abkm_token."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(1024), default="")


class DailyStat(Base):
    """Kunlik foydalanuvchi statistikasi (DAU). Har kuni 00:00 da yoziladi."""

    __tablename__ = "daily_stats"

    day: Mapped[str] = mapped_column(String(10), primary_key=True)  # YYYY-MM-DD
    active_users: Mapped[int] = mapped_column(Integer, default=0)
    new_users: Mapped[int] = mapped_column(Integer, default=0)
    total_users: Mapped[int] = mapped_column(Integer, default=0)


class BroadcastJob(Base):
    """Reklama yuborish vazifasi — restartdan keyin davom ettirish uchun DB'da.

    status:  queued  — navbatda kutmoqda (oldidagi tugaguncha)
             running — hozir yuborilmoqda
             done    — yakunlandi
             cancelled — admin bekor qildi
             expired — manba xabar o'chgan yoki vazifa eskirgan
    phase:   main    — barcha userlar bo'yicha asosiy o'tish (kursor)
             retry   — yuborilmay qolganlarni qayta yuborish o'tishi
    """

    __tablename__ = "broadcast_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_chat_id: Mapped[int] = mapped_column(BigInteger)  # manba chat (admin)
    message_id: Mapped[int] = mapped_column(BigInteger)  # nusxalanadigan xabar
    notify_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    phase: Mapped[str] = mapped_column(String(8), default="main")  # main/retry
    total: Mapped[int] = mapped_column(Integer, default=0)
    sent: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    blocked: Mapped[int] = mapped_column(Integer, default=0)
    cursor: Mapped[int] = mapped_column(BigInteger, default=0)  # oxirgi ishlangan user id
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BroadcastFailure(Base):
    """Reklama yuborilmay qolgan foydalanuvchilar — qayta yuborish (retry) uchun.

    Asosiy o'tishda yuborib bo'lmagan (tarmoq/vaqtinchalik xato) user shu yerga
    yoziladi. Retry o'tishida muvaffaqiyatli yuborilsa — o'chiriladi. Restartdan
    keyin ham saqlanib qoladi, shuning uchun qayta yuborish uzilmaydi.
    """

    __tablename__ = "broadcast_failures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("broadcast_jobs.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)


class Region(Base):
    """Viloyat — SOATO kodi (masalan 1733 = Xorazm)."""

    __tablename__ = "regions"

    soato: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    districts: Mapped[list["District"]] = relationship(
        back_populates="region", cascade="all, delete-orphan"
    )


class Vacancy(Base):
    """API'dan sinxronlangan vakansiya. `raw` — to'liq JSON (formatter uchun)."""

    __tablename__ = "vacancies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # API vacancy id
    region_soato: Mapped[int] = mapped_column(Integer, index=True)
    soato: Mapped[int] = mapped_column(Integer, index=True)  # vacancy_soato_code (tuman)
    company_tin: Mapped[str] = mapped_column(String(20), index=True, default="")
    company_name: Mapped[str] = mapped_column(String(256), default="")
    position_name: Mapped[str] = mapped_column(String(256), default="")
    order_key: Mapped[str] = mapped_column(String(40), default="")  # saralash uchun (created_at)
    raw: Mapped[str] = mapped_column(Text)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class District(Base):
    """Tuman/shahar — SOATO kodi (masalan 1733401 = Urganch shahar)."""

    __tablename__ = "districts"

    soato: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_soato: Mapped[int] = mapped_column(
        ForeignKey("regions.soato", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    region: Mapped["Region"] = relationship(back_populates="districts")
