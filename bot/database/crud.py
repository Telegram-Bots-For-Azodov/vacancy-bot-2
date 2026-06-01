from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import AppSetting, District, Region, Role, User


# ---------------------------------------------------------------- users
def _role_for(tg_id: int) -> Role:
    if settings.is_superadmin(tg_id):
        return Role.SUPERADMIN
    if settings.is_admin(tg_id):
        return Role.ADMIN
    return Role.USER


async def get_or_create_user(
    session: AsyncSession,
    tg_id: int,
    username: str | None,
    full_name: str | None,
) -> User:
    user = await session.get(User, tg_id)
    role = _role_for(tg_id)
    if user is None:
        user = User(id=tg_id, username=username, full_name=full_name, role=role)
        session.add(user)
        await session.commit()
        return user

    # keep profile + role fresh
    user.username = username
    user.full_name = full_name
    user.last_active = datetime.utcnow()
    if user.role != role:
        user.role = role
    await session.commit()
    return user


async def count_users(session: AsyncSession) -> int:
    res = await session.execute(select(User.id))
    return len(res.scalars().all())


# ---------------------------------------------------------------- settings
async def get_setting(
    session: AsyncSession, key: str, default: str | None = None
) -> str | None:
    row = await session.get(AppSetting, key)
    return row.value if row else default


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=value)
        session.add(row)
    else:
        row.value = value
    await session.commit()


# ---------------------------------------------------------------- regions
async def list_regions(session: AsyncSession, only_active: bool = True) -> list[Region]:
    stmt = select(Region)
    if only_active:
        stmt = stmt.where(Region.is_active.is_(True))
    stmt = stmt.order_by(Region.sort_order, Region.name)
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_region(session: AsyncSession, soato: int) -> Region | None:
    return await session.get(Region, soato)


async def list_districts(
    session: AsyncSession, region_soato: int, only_active: bool = True
) -> list[District]:
    stmt = select(District).where(District.region_soato == region_soato)
    if only_active:
        stmt = stmt.where(District.is_active.is_(True))
    stmt = stmt.order_by(District.sort_order, District.name)
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_district(session: AsyncSession, soato: int) -> District | None:
    return await session.get(District, soato)


async def upsert_region(
    session: AsyncSession, soato: int, name: str, sort_order: int = 0
) -> Region:
    region = await session.get(Region, soato)
    if region is None:
        region = Region(soato=soato, name=name, sort_order=sort_order)
        session.add(region)
    else:
        region.name = name
        region.sort_order = sort_order
    await session.commit()
    return region


async def upsert_district(
    session: AsyncSession,
    soato: int,
    region_soato: int,
    name: str,
    sort_order: int = 0,
) -> District:
    district = await session.get(District, soato)
    if district is None:
        district = District(
            soato=soato,
            region_soato=region_soato,
            name=name,
            sort_order=sort_order,
        )
        session.add(district)
    else:
        district.region_soato = region_soato
        district.name = name
        district.sort_order = sort_order
    await session.commit()
    return district


# ---------------------------------------------------------------- visibility
async def count_active_regions(session: AsyncSession) -> int:
    res = await session.execute(
        select(func.count(Region.soato)).where(Region.is_active.is_(True))
    )
    return int(res.scalar() or 0)


async def count_active_districts(session: AsyncSession, region_soato: int) -> int:
    res = await session.execute(
        select(func.count(District.soato)).where(
            District.region_soato == region_soato, District.is_active.is_(True)
        )
    )
    return int(res.scalar() or 0)


async def set_region_active(
    session: AsyncSession, soato: int, active: bool
) -> None:
    region = await session.get(Region, soato)
    if region:
        region.is_active = active
        await session.commit()


async def set_district_active(
    session: AsyncSession, soato: int, active: bool
) -> None:
    district = await session.get(District, soato)
    if district:
        district.is_active = active
        await session.commit()


async def set_all_active(session: AsyncSession, active: bool) -> None:
    """Barcha viloyat va tumanlarni yoqadi/o'chiradi."""
    await session.execute(update(Region).values(is_active=active))
    await session.execute(update(District).values(is_active=active))
    await session.commit()


async def set_only_region(session: AsyncSession, soato: int) -> None:
    """Faqat bitta viloyatni yoqadi (qolganlarini o'chiradi), tumanlarini yoqadi."""
    await session.execute(update(Region).values(is_active=False))
    await session.execute(
        update(Region).where(Region.soato == soato).values(is_active=True)
    )
    # shu viloyat tumanlarini yoqamiz (ishlashi uchun)
    await session.execute(
        update(District)
        .where(District.region_soato == soato)
        .values(is_active=True)
    )
    await session.commit()


async def set_only_district(
    session: AsyncSession, region_soato: int, district_soato: int
) -> None:
    """Faqat bitta tumanni yoqadi: viloyatini yoqadi, qolgan viloyatlar va
    shu viloyatdagi qolgan tumanlarni o'chiradi."""
    await session.execute(update(Region).values(is_active=False))
    await session.execute(
        update(Region).where(Region.soato == region_soato).values(is_active=True)
    )
    await session.execute(
        update(District)
        .where(District.region_soato == region_soato)
        .values(is_active=False)
    )
    await session.execute(
        update(District)
        .where(District.soato == district_soato)
        .values(is_active=True)
    )
    await session.commit()
