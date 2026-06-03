from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import (
    AppSetting,
    BroadcastFailure,
    BroadcastJob,
    DailyStat,
    District,
    Region,
    Role,
    User,
    Vacancy,
    utcnow,
)


# ---------------------------------------------------------------- users
def _role_for(tg_id: int, existing: Role | None) -> Role:
    """Rolni aniqlaydi.

    - Superadmin faqat .env orqali (dasturchi tomonidan) qo'yiladi.
    - Admin: .env ADMIN_IDS yoki DB'da allaqachon ADMIN bo'lsa (superadmin
      tomonidan tayinlangan) — saqlanadi.
    """
    if settings.is_superadmin(tg_id):
        return Role.SUPERADMIN
    if tg_id in settings.admin_ids or existing == Role.ADMIN:
        return Role.ADMIN
    return Role.USER


async def get_or_create_user(
    session: AsyncSession,
    tg_id: int,
    username: str | None,
    full_name: str | None,
) -> User | type[User]:
    user = await session.get(User, tg_id)
    if user is None:
        user = User(
            id=tg_id,
            username=username,
            full_name=full_name,
            role=_role_for(tg_id, None),
            is_active=True,
        )
        session.add(user)
        await session.commit()
        return user

    # profil + rol + kunlik faollikni yangilab turamiz
    user.username = username
    user.full_name = full_name
    user.last_active = utcnow()
    user.is_active = True
    role = _role_for(tg_id, user.role)
    if user.role != role:
        user.role = role
    await session.commit()
    return user


async def count_users(session: AsyncSession) -> int:
    res = await session.execute(select(func.count(User.id)))
    return int(res.scalar() or 0)


# ---------------------------------------------------------------- user stats
async def count_active_today(session: AsyncSession) -> int:
    res = await session.execute(
        select(func.count(User.id)).where(User.is_active.is_(True))
    )
    return int(res.scalar() or 0)


async def count_new_since(session: AsyncSession, since: datetime) -> int:
    res = await session.execute(
        select(func.count(User.id)).where(User.created_at >= since)
    )
    return int(res.scalar() or 0)


async def count_banned(session: AsyncSession) -> int:
    res = await session.execute(
        select(func.count(User.id)).where(User.is_banned.is_(True))
    )
    return int(res.scalar() or 0)


async def count_admins(session: AsyncSession) -> int:
    res = await session.execute(
        select(func.count(User.id)).where(
            User.role.in_([Role.ADMIN, Role.SUPERADMIN])
        )
    )
    return int(res.scalar() or 0)


async def all_user_ids(session: AsyncSession) -> list[int]:
    """Reklama yuborish uchun barcha (bloklanmagan) foydalanuvchi ID lari."""
    res = await session.execute(select(User.id).where(User.is_banned.is_(False)))
    return [int(x) for x in res.scalars().all()]


async def user_ids_after(
    session: AsyncSession, after_id: int, limit: int
) -> list[int]:
    """id > after_id bo'lgan (bloklanmagan) foydalanuvchilar, id bo'yicha tartibda.

    Reklamani uzilishdan keyin kursordan davom ettirish uchun.
    """
    res = await session.execute(
        select(User.id)
        .where(User.is_banned.is_(False), User.id > after_id)
        .order_by(User.id)
        .limit(limit)
    )
    return [int(x) for x in res.scalars().all()]


async def delete_user(session: AsyncSession, tg_id: int) -> None:
    await session.execute(delete(User).where(User.id == tg_id))
    await session.commit()


async def delete_users(session: AsyncSession, tg_ids: list[int]) -> int:
    if not tg_ids:
        return 0
    await session.execute(delete(User).where(User.id.in_(tg_ids)))
    await session.commit()
    return len(tg_ids)


# ---------------------------------------------------------------- broadcast job
async def create_broadcast_job(
    session: AsyncSession,
    from_chat_id: int,
    message_id: int,
    notify_chat_id: int | None,
    total: int,
) -> BroadcastJob:
    """Yangi reklama vazifasini yaratadi.

    Agar hozir boshqa vazifa ketayotgan/navbatda bo'lsa — bu yangisi `queued`
    bo'ladi va o'z navbatida ishga tushadi. Aks holda darhol `running`.
    """
    res = await session.execute(
        select(func.count(BroadcastJob.id)).where(
            BroadcastJob.status.in_(["running", "queued"])
        )
    )
    busy = int(res.scalar() or 0) > 0
    job = BroadcastJob(
        from_chat_id=from_chat_id,
        message_id=message_id,
        notify_chat_id=notify_chat_id,
        status="queued" if busy else "running",
        total=total,
    )
    session.add(job)
    await session.commit()
    return job


async def get_active_broadcast_job(session: AsyncSession) -> BroadcastJob | None:
    """Hozir ishlayotgan (running) vazifa — restartda davom ettirish uchun."""
    res = await session.execute(
        select(BroadcastJob)
        .where(BroadcastJob.status == "running")
        .order_by(BroadcastJob.id)
        .limit(1)
    )
    return res.scalar_one_or_none()


async def next_queued_job(session: AsyncSession) -> BroadcastJob | None:
    """Navbatdagi eng eski vazifani `running` qilib qaytaradi (FIFO)."""
    res = await session.execute(
        select(BroadcastJob)
        .where(BroadcastJob.status == "queued")
        .order_by(BroadcastJob.id)
        .limit(1)
    )
    job = res.scalar_one_or_none()
    if job is not None:
        job.status = "running"
        job.updated_at = utcnow()
        await session.commit()
    return job


async def count_queued_jobs(session: AsyncSession) -> int:
    res = await session.execute(
        select(func.count(BroadcastJob.id)).where(BroadcastJob.status == "queued")
    )
    return int(res.scalar() or 0)


async def save_broadcast_progress(
    session: AsyncSession,
    job_id: int,
    cursor: int,
    sent: int,
    failed: int,
    blocked: int,
    phase: str | None = None,
) -> None:
    values = dict(
        cursor=cursor, sent=sent, failed=failed, blocked=blocked,
        updated_at=utcnow(),
    )
    if phase is not None:
        values["phase"] = phase
    await session.execute(
        update(BroadcastJob).where(BroadcastJob.id == job_id).values(**values)
    )
    await session.commit()


async def finish_broadcast_job(
    session: AsyncSession, job_id: int, status: str = "done"
) -> None:
    await session.execute(
        update(BroadcastJob)
        .where(BroadcastJob.id == job_id)
        .values(status=status, updated_at=utcnow())
    )
    await session.commit()


# ------------------------------------------------------ broadcast failures (retry)
async def record_broadcast_failures(
    session: AsyncSession, job_id: int, user_ids: list[int]
) -> None:
    """Yuborilmay qolgan userlarni retry uchun yozadi (mavjudini takrorlamaydi)."""
    uniq = list(dict.fromkeys(user_ids))
    if not uniq:
        return
    res = await session.execute(
        select(BroadcastFailure.user_id).where(
            BroadcastFailure.job_id == job_id,
            BroadcastFailure.user_id.in_(uniq),
        )
    )
    existing = {int(x) for x in res.scalars().all()}
    for uid in uniq:
        if uid not in existing:
            session.add(BroadcastFailure(job_id=job_id, user_id=uid))
    await session.commit()


async def failed_user_ids(session: AsyncSession, job_id: int) -> list[int]:
    res = await session.execute(
        select(BroadcastFailure.user_id)
        .where(BroadcastFailure.job_id == job_id)
        .order_by(BroadcastFailure.user_id)
    )
    return [int(x) for x in res.scalars().all()]


async def clear_broadcast_failure(
    session: AsyncSession, job_id: int, user_id: int
) -> None:
    await session.execute(
        delete(BroadcastFailure).where(
            BroadcastFailure.job_id == job_id,
            BroadcastFailure.user_id == user_id,
        )
    )
    await session.commit()


async def bump_failure_attempt(
    session: AsyncSession, job_id: int, user_id: int
) -> None:
    await session.execute(
        update(BroadcastFailure)
        .where(
            BroadcastFailure.job_id == job_id,
            BroadcastFailure.user_id == user_id,
        )
        .values(attempts=BroadcastFailure.attempts + 1)
    )
    await session.commit()


# ---------------------------------------------------------------- admin mgmt
async def find_user(
    session: AsyncSession, query: str
) -> User | None:
    """ID yoki @username bo'yicha foydalanuvchini topadi."""
    q = query.strip().lstrip("@")
    if q.isdigit():
        return await session.get(User, int(q))
    res = await session.execute(
        select(User).where(func.lower(User.username) == q.lower())
    )
    return res.scalars().first()


async def set_admin(session: AsyncSession, tg_id: int, make_admin: bool) -> User | None:
    """Foydalanuvchini admin qiladi yoki adminlikdan oladi (superadmin uchun)."""
    user = await session.get(User, tg_id)
    if user is None:
        return None
    if user.role == Role.SUPERADMIN:
        return user  # superadmin rolini o'zgartirmaymiz
    user.role = Role.ADMIN if make_admin else Role.USER
    await session.commit()
    return user


async def list_admins(session: AsyncSession) -> list[User]:
    res = await session.execute(
        select(User)
        .where(User.role.in_([Role.ADMIN, Role.SUPERADMIN]))
        .order_by(User.role, User.id)
    )
    return list(res.scalars().all())


# ---------------------------------------------------------------- daily reset
async def record_daily_and_reset(
    session: AsyncSession, day: str, since: datetime
) -> dict:
    """Kun yakunida statistikani yozadi va is_active bayroqlarini tozalaydi.

    `day` — yoziladigan sana (YYYY-MM-DD). `since` — shu kun boshining UTC vaqti
    (yangi foydalanuvchilarni sanash uchun). Yozilgan qiymatlarni qaytaradi.
    """
    active = await count_active_today(session)
    total = await count_users(session)
    new = await count_new_since(session, since)

    row = await session.get(DailyStat, day)
    if row is None:
        row = DailyStat(
            day=day, active_users=active, new_users=new, total_users=total
        )
        session.add(row)
    else:
        row.active_users = active
        row.new_users = new
        row.total_users = total

    await session.execute(update(User).values(is_active=False))
    await session.commit()
    return {"day": day, "active": active, "new": new, "total": total}


async def recent_daily_stats(session: AsyncSession, limit: int = 7) -> list[DailyStat]:
    res = await session.execute(
        select(DailyStat).order_by(DailyStat.day.desc()).limit(limit)
    )
    return list(res.scalars().all())


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


# ---------------------------------------------------------------- vacancies
async def count_all_vacancies(session: AsyncSession) -> int:
    res = await session.execute(select(func.count(Vacancy.id)))
    return int(res.scalar() or 0)


async def last_sync_at(session: AsyncSession) -> datetime | None:
    res = await session.execute(select(func.max(Vacancy.synced_at)))
    return res.scalar()


def _is_region(soato: int) -> bool:
    """4 xonali kod -> viloyat, 7 xonali -> tuman."""
    return soato < 10_000


def _scope(soato: int, region_soato: int):
    """So'rov sharti: viloyat darajasida region_soato, aks holda soato bo'yicha."""
    if _is_region(soato):
        return Vacancy.region_soato == region_soato
    return Vacancy.soato == soato


def _parse_salary(value) -> int:
    """position_salary ("1300000.00" kabi) -> butun son so'mda. Xato -> 0."""
    if value is None:
        return 0
    try:
        num = float(str(value).strip())
    except (ValueError, TypeError):
        return 0
    return int(num) if num > 0 else 0


async def replace_region_vacancies(
    session: AsyncSession, region_soato: int, vacancies: list[dict]
) -> int:
    """Viloyatning eski vakansiyalarini o'chirib, yangilarini yozadi (atomik)."""
    await session.execute(
        delete(Vacancy).where(Vacancy.region_soato == region_soato)
    )
    objs: list[Vacancy] = []
    for v in vacancies:
        try:
            vid = int(v["id"])
        except (KeyError, TypeError, ValueError):
            continue
        try:
            soato = int(v.get("vacancy_soato_code") or v.get("company_soato_code") or region_soato)
        except (TypeError, ValueError):
            soato = region_soato
        objs.append(
            Vacancy(
                id=vid,
                region_soato=region_soato,
                soato=soato,
                company_tin=str(v.get("company_tin") or ""),
                company_name=(v.get("company_name") or "")[:256],
                position_name=(v.get("position_name") or "")[:256],
                order_key=str(v.get("created_at") or ""),
                salary=_parse_salary(v.get("position_salary")),
                raw=json.dumps(v, ensure_ascii=False),
            )
        )
    session.add_all(objs)
    await session.commit()
    return len(objs)


async def replace_district_vacancies(
    session: AsyncSession,
    region_soato: int,
    district_soato: int,
    vacancies: list[dict],
) -> int:
    """Faqat bitta tumanning vakansiyalarini o'chirib, yangilarini yozadi.

    Har tuman javobi kelganda alohida chaqiriladi (butun viloyat kutilmaydi).
    """
    await session.execute(
        delete(Vacancy).where(
            Vacancy.region_soato == region_soato,
            Vacancy.soato == district_soato,
        )
    )
    objs: list[Vacancy] = []
    seen: set[int] = set()
    for v in vacancies:
        try:
            vid = int(v["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if vid in seen:
            continue
        seen.add(vid)
        objs.append(
            Vacancy(
                id=vid,
                region_soato=region_soato,
                soato=district_soato,
                company_tin=str(v.get("company_tin") or ""),
                company_name=(v.get("company_name") or "")[:256],
                position_name=(v.get("position_name") or "")[:256],
                order_key=str(v.get("created_at") or ""),
                salary=_parse_salary(v.get("position_salary")),
                raw=json.dumps(v, ensure_ascii=False),
            )
        )
    session.add_all(objs)
    await session.commit()
    return len(objs)


async def district_counts(
    session: AsyncSession, region_soato: int
) -> dict[int, int]:
    """Viloyatdagi har tuman (soato) bo'yicha vakansiyalar soni."""
    res = await session.execute(
        select(Vacancy.soato, func.count(Vacancy.id))
        .where(Vacancy.region_soato == region_soato)
        .group_by(Vacancy.soato)
    )
    return {int(s): int(c) for s, c in res.all()}


async def count_vacancies(
    session: AsyncSession, region_soato: int, soato: int
) -> int:
    res = await session.execute(
        select(func.count(Vacancy.id)).where(_scope(soato, region_soato))
    )
    return int(res.scalar() or 0)


async def list_companies(
    session: AsyncSession, region_soato: int, soato: int
) -> list[dict]:
    """Hudud bo'yicha korxonalar (company_tin bo'yicha guruhlangan)."""
    res = await session.execute(
        select(
            Vacancy.company_tin,
            func.max(Vacancy.company_name),
            func.count(Vacancy.id),
        )
        .where(_scope(soato, region_soato))
        .group_by(Vacancy.company_tin)
        .order_by(func.max(Vacancy.company_name))
    )
    return [
        {"tin": tin, "name": name or "Tashkilot", "count": int(cnt)}
        for tin, name, cnt in res.all()
    ]


async def list_company_vacancies(
    session: AsyncSession, region_soato: int, soato: int, company_tin: str
) -> list[dict]:
    """Bitta korxonaning hududdagi vakansiyalari (yangi -> eski)."""
    res = await session.execute(
        select(Vacancy.raw)
        .where(_scope(soato, region_soato), Vacancy.company_tin == company_tin)
        .order_by(Vacancy.order_key.desc(), Vacancy.id.desc())
    )
    out: list[dict] = []
    for (raw,) in res.all():
        try:
            out.append(json.loads(raw))
        except (TypeError, ValueError):
            continue
    return out


async def top_salary_vacancies(
    session: AsyncSession, limit: int = 10
) -> list[dict]:
    """Eng yuqori oylik maoshli vakansiyalar (maosh kamayish tartibida).

    Faqat maoshi ko'rsatilgan (salary > 0) yozuvlar. Har korxonadan ko'p
    takror bo'lmasligi uchun bir xil (tin, lavozim, maosh) bittasi qoldiriladi.
    """
    res = await session.execute(
        select(Vacancy.raw)
        .where(Vacancy.salary > 0)
        .order_by(Vacancy.salary.desc(), Vacancy.id.desc())
        .limit(limit * 4)  # takrorlarni filtrlash uchun biroz ko'proq olamiz
    )
    out: list[dict] = []
    seen: set[tuple] = set()
    for (raw,) in res.all():
        try:
            v = json.loads(raw)
        except (TypeError, ValueError):
            continue
        key = (
            str(v.get("company_tin") or ""),
            str(v.get("position_name") or ""),
            str(v.get("position_salary") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
        if len(out) >= limit:
            break
    return out


async def last_synced(
    session: AsyncSession, region_soato: int
) -> datetime | None:
    res = await session.execute(
        select(func.max(Vacancy.synced_at)).where(
            Vacancy.region_soato == region_soato
        )
    )
    return res.scalar()
