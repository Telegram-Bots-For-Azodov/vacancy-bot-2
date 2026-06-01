from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    BigInteger,
    String,
    Integer,
    DateTime,
    Boolean,
    ForeignKey,
    Enum,
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_active: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AppSetting(Base):
    """Runtime sozlamalar (kalit-qiymat). Masalan: abkm_token."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(1024), default="")


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
