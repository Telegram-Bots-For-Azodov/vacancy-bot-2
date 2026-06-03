"""Foydalanuvchilarga reklama/xabar yuborish — uzilishga chidamli (resume).

Imkoniyatlar:
- **Navbat (queue):** bir vaqtda bitta reklama ketadi; yangilari `queued`
  bo'lib navbatda turadi va o'z navbatida avtomatik ishga tushadi.
- **Resume:** jarayon `broadcast_jobs` jadvalida saqlanadi (kursor = oxirgi
  ishlangan user id). Bot o'chib-yonsa, tugamagan vazifa va navbat AVTOMATIK
  davom ettiriladi (kim olgan bo'lsa — qayta olmaydi).
- **Retry:** yuborilmay qolgan (tarmoq/vaqtinchalik xato) userlar alohida
  jadvalga yoziladi va asosiy o'tishdan keyin qayta yuboriladi.
- **Rate limit:** sekundiga ~25 ta; Telegram `RetryAfter` (flood) kutiladi.
- **Expired:** manba xabar o'chgan/topilmasa, vazifa `expired` deb belgilanadi
  va adminlarga xabar beriladi (har bir userni behuda urinmaymiz).
- **Realtime:** holat (yuborildi/qoldi/bloklagan/%) BARCHA adminlarga jonli
  xabarda yangilanib turadi.
"""
from __future__ import annotations

import asyncio
import time
from datetime import timedelta

import aiohttp
from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from loguru import logger

from bot.config import settings
from bot.database import crud
from bot.database.db import SessionLocal
from bot.database.models import utcnow

_DELAY = 0.04        # soniyasiga ~25 ta
_BATCH = 200         # kursor bo'yicha partiya hajmi
_PERSIST_EVERY = 25  # har nechta yuborishda DB'ga saqlash
_EDIT_EVERY = 3.0    # jonli xabarni necha soniyada yangilash
_NET_RETRIES = 4     # tarmoq xatosida bitta userga qayta urinish soni
_RETRY_ROUNDS = 3    # asosiy o'tishdan keyin failed userlarga necha marta
_EXPIRE_HOURS = 48   # bunchadan eski tugamagan vazifa "expired" (zombi himoyasi)

_lock = asyncio.Lock()
_progress: dict = {
    "total": 0, "sent": 0, "failed": 0, "blocked": 0, "done": True, "queued": 0,
}


def is_running() -> bool:
    return _lock.locked()


def get_progress() -> dict:
    p = dict(_progress)
    p["processed"] = p["sent"] + p["failed"] + p["blocked"]
    p["remaining"] = max(0, p["total"] - p["processed"])
    return p


def _text(p: dict, *, resumed: bool = False, retry: bool = False) -> str:
    total = p.get("total", 0) or 0
    processed = p["sent"] + p["failed"] + p["blocked"]
    pct = int(processed * 100 / total) if total else 0
    if retry:
        head = "🔁 <b>Yuborilmaganlarga qayta yuborilmoqda…</b>"
    elif resumed:
        head = "♻️ <b>Reklama davom ettirilmoqda…</b>"
    else:
        head = "📤 <b>Reklama yuborilmoqda…</b>"
    extra = ""
    q = p.get("queued", 0)
    if q:
        extra = f"\n🗂 Navbatda: <b>{q}</b>"
    return (
        f"{head}\n\n"
        f"📨 Jami: <b>{total}</b>\n"
        f"✅ Yuborildi: <b>{p['sent']}</b>\n"
        f"⛔️ Bloklagan: <b>{p['blocked']}</b>\n"
        f"⚠️ Xato: <b>{p['failed']}</b>\n"
        f"⏳ Qoldi: <b>{max(0, total - processed)}</b>\n"
        f"📊 <b>{pct}%</b>"
        f"{extra}"
    )


def _final_text(p: dict) -> str:
    return (
        "✅ <b>Reklama yakunlandi</b>\n\n"
        f"📨 Jami: <b>{p['total']}</b>\n"
        f"✅ Yetkazildi: <b>{p['sent']}</b>\n"
        f"⛔️ Bloklagan: <b>{p['blocked']}</b>\n"
        f"⚠️ Yetkazilmadi: <b>{p['failed']}</b>"
    )


def _expired_text() -> str:
    return (
        "🛑 <b>Reklama to'xtatildi</b>\n\n"
        "Manba xabar o'chirilgan yoki mavjud emas — nusxalab bo'lmadi.\n"
        "Iltimos, reklamani qaytadan yuboring."
    )


async def _admin_chat_ids() -> list[int]:
    """Barcha admin va superadminlar (env + DB), takrorlanmas."""
    ids = list(settings.superadmin_ids) + list(settings.admin_ids)
    try:
        async with SessionLocal() as session:
            ids += [a.id for a in await crud.list_admins(session)]
    except Exception:  # noqa: BLE001
        pass
    return list(dict.fromkeys(ids))


_BLOCKED_HINTS = (
    "user is deactivated",
    "bot was blocked",
    "bot can't initiate",
    "peer_id_invalid",
    "user not found",
    "chat_id is empty",
)
# manba xabar o'chgan/yo'q — butun vazifa uchun halokatli (har userda takrorlanmaydi)
_SOURCE_GONE_HINTS = (
    "message to copy not found",
    "message_id_invalid",
    "message to forward not found",
    "message can't be copied",
)


async def _send_one(bot: Bot, uid: int, from_chat_id: int, message_id: int) -> str:
    """Bitta foydalanuvchiga yuboradi.

    Natija: 'sent' | 'failed' | 'blocked' | 'expired'.
    - 'expired' — manba xabar yo'q/o'chgan (butun vazifa to'xtaydi).
    - tarmoq xatolari darhol 'failed' emas: bir necha marta qayta uriniladi.
    - 'failed' userlar keyin retry o'tishida qayta yuboriladi.
    """
    for attempt in range(1, _NET_RETRIES + 1):
        try:
            await bot.copy_message(
                chat_id=uid, from_chat_id=from_chat_id, message_id=message_id
            )
            return "sent"
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)  # flood — kutib qayta
            continue
        except TelegramForbiddenError:
            return "blocked"
        except TelegramBadRequest as e:
            msg = str(e).lower()
            if any(h in msg for h in _SOURCE_GONE_HINTS):
                return "expired"
            if any(h in msg for h in _BLOCKED_HINTS) or "chat not found" in msg:
                return "blocked"
            return "failed"
        except (TelegramNetworkError, aiohttp.ClientError, asyncio.TimeoutError):
            # tarmoq uzilishi — kutib qayta urinamiz (xato deb sanamaymiz)
            if attempt < _NET_RETRIES:
                await asyncio.sleep(attempt * 2)  # 2s, 4s, 6s
                continue
            return "failed"
        except Exception:  # noqa: BLE001
            return "failed"
    return "failed"


class _Expired(Exception):
    """Manba xabar topilmadi — vazifa to'xtatiladi."""


async def _status_channel(bot: Bot, init_text: str):
    """Barcha adminlarga jonli xabar yuboradi; (yangilash, yopish) funksiyalarini qaytaradi."""
    status_msgs: list[tuple[int, int]] = []  # (chat_id, message_id)
    for cid in await _admin_chat_ids():
        try:
            m = await bot.send_message(cid, init_text)
            status_msgs.append((cid, m.message_id))
        except Exception:  # noqa: BLE001
            pass

    last_text = {"v": init_text}

    async def update(text: str) -> None:
        # matn o'zgarmagan bo'lsa — tahrir qilmaymiz ("message is not modified"
        # Bad Request'ini va keraksiz API chaqiruvlarini oldini olamiz)
        if text == last_text["v"]:
            return
        last_text["v"] = text
        for cid, mid in status_msgs:
            try:
                await bot.edit_message_text(text, chat_id=cid, message_id=mid)
            except TelegramBadRequest:
                pass
            except Exception:  # noqa: BLE001
                pass

    return status_msgs, update


async def _queued_count() -> int:
    try:
        async with SessionLocal() as session:
            return await crud.count_queued_jobs(session)
    except Exception:  # noqa: BLE001
        return 0


async def _run_main(bot: Bot, job, update, status_msgs, resumed: bool) -> tuple[int, int, int]:
    """Asosiy o'tish: kursordan oxirigacha. Failed userlar DB'ga yoziladi."""
    sent, failed, blocked = job.sent, job.failed, job.blocked
    cursor = job.cursor
    last_edit = time.time()
    since_persist = 0

    while True:
        async with SessionLocal() as session:
            batch = await crud.user_ids_after(session, cursor, _BATCH)
        if not batch:
            break

        to_delete: list[int] = []
        new_failed: list[int] = []
        for uid in batch:
            res = await _send_one(bot, uid, job.from_chat_id, job.message_id)
            if res == "expired":
                raise _Expired
            if res == "sent":
                sent += 1
            elif res == "blocked":
                blocked += 1
                to_delete.append(uid)
            else:
                failed += 1
                new_failed.append(uid)
            cursor = uid
            since_persist += 1
            _progress.update(sent=sent, failed=failed, blocked=blocked)

            if since_persist >= _PERSIST_EVERY:
                since_persist = 0
                async with SessionLocal() as session:
                    await crud.save_broadcast_progress(
                        session, job.id, cursor, sent, failed, blocked
                    )

            now = time.time()
            if status_msgs and (now - last_edit) >= _EDIT_EVERY:
                last_edit = now
                await update(_text(get_progress(), resumed=resumed))

            await asyncio.sleep(_DELAY)

        # partiya oxirida: bloklaganlarni o'chirish, failedlarni yozish, DB saqlash
        if to_delete:
            async with SessionLocal() as session:
                await crud.delete_users(session, to_delete)
        if new_failed:
            async with SessionLocal() as session:
                await crud.record_broadcast_failures(session, job.id, new_failed)
        async with SessionLocal() as session:
            await crud.save_broadcast_progress(
                session, job.id, cursor, sent, failed, blocked
            )

    return sent, failed, blocked


async def _run_retry(bot: Bot, job, update, status_msgs, sent: int, failed: int, blocked: int) -> tuple[int, int, int]:
    """Yuborilmay qolganlarga qayta yuborish o'tishi (bir necha marta)."""
    async with SessionLocal() as session:
        await crud.save_broadcast_progress(
            session, job.id, job.cursor, sent, failed, blocked, phase="retry"
        )
    last_edit = time.time()
    for _round in range(_RETRY_ROUNDS):
        async with SessionLocal() as session:
            pending = await crud.failed_user_ids(session, job.id)
        if not pending:
            break
        to_delete: list[int] = []
        for uid in pending:
            res = await _send_one(bot, uid, job.from_chat_id, job.message_id)
            if res == "expired":
                raise _Expired
            if res == "sent":
                sent += 1
                failed = max(0, failed - 1)
                async with SessionLocal() as session:
                    await crud.clear_broadcast_failure(session, job.id, uid)
            elif res == "blocked":
                blocked += 1
                failed = max(0, failed - 1)
                to_delete.append(uid)
                async with SessionLocal() as session:
                    await crud.clear_broadcast_failure(session, job.id, uid)
            else:
                # hali ham xato — keyingi raundga qoldiramiz
                async with SessionLocal() as session:
                    await crud.bump_failure_attempt(session, job.id, uid)
            _progress.update(sent=sent, failed=failed, blocked=blocked)
            now = time.time()
            if status_msgs and (now - last_edit) >= _EDIT_EVERY:
                last_edit = now
                await update(_text(get_progress(), retry=True))
            await asyncio.sleep(_DELAY)
        if to_delete:
            async with SessionLocal() as session:
                await crud.delete_users(session, to_delete)
        async with SessionLocal() as session:
            await crud.save_broadcast_progress(
                session, job.id, job.cursor, sent, failed, blocked, phase="retry"
            )
    return sent, failed, blocked


async def _run_job(bot: Bot, job, resumed: bool) -> None:
    """Bitta vazifani to'liq bajaradi: main o'tish + retry o'tishi."""
    # zombi himoyasi: juda eski tugamagan vazifani expired qilamiz
    try:
        age_ok = job.created_at is None or (
            utcnow().replace(tzinfo=None) - job.created_at
        ) < timedelta(hours=_EXPIRE_HOURS)
    except Exception:  # noqa: BLE001
        age_ok = True
    _progress.update(
        total=job.total, sent=job.sent, failed=job.failed, blocked=job.blocked,
        done=False, queued=await _queued_count(),
    )

    retry_phase = job.phase == "retry"
    init_text = _text(get_progress(), resumed=resumed, retry=retry_phase)
    status_msgs, update = await _status_channel(bot, init_text)

    if not age_ok:
        async with SessionLocal() as session:
            await crud.finish_broadcast_job(session, job.id, "expired")
        logger.warning(f"broadcast: vazifa eskirgan (id={job.id}) — expired")
        if status_msgs:
            await update(_expired_text())
        return

    try:
        sent, failed, blocked = job.sent, job.failed, job.blocked
        if not retry_phase:
            sent, failed, blocked = await _run_main(
                bot, job, update, status_msgs, resumed
            )
        sent, failed, blocked = await _run_retry(
            bot, job, update, status_msgs, sent, failed, blocked
        )
    except _Expired:
        async with SessionLocal() as session:
            await crud.finish_broadcast_job(session, job.id, "expired")
        logger.warning(f"broadcast: manba xabar yo'q (id={job.id}) — expired")
        if status_msgs:
            await update(_expired_text())
        return

    _progress.update(total=job.total, sent=sent, failed=failed, blocked=blocked, done=True)
    async with SessionLocal() as session:
        await crud.save_broadcast_progress(
            session, job.id, job.cursor, sent, failed, blocked
        )
        await crud.finish_broadcast_job(session, job.id, "done")
    logger.info(
        f"broadcast: tugadi id={job.id} jami={job.total} yuborildi={sent} "
        f"bloklagan={blocked} xato={failed}"
    )
    if status_msgs:
        await update(_final_text(get_progress()))


async def _worker(bot: Bot) -> None:
    """Navbatni to'liq oqizadi: running -> keyin queued vazifalarni ketma-ket."""
    if _lock.locked():
        logger.warning("broadcast: worker allaqachon ketmoqda")
        return
    async with _lock:
        first = True
        while True:
            async with SessionLocal() as session:
                job = await crud.get_active_broadcast_job(session)
                if job is None:
                    job = await crud.next_queued_job(session)
            if job is None:
                break
            resumed = first and ((job.cursor or 0) > 0 or job.phase == "retry")
            first = False
            try:
                await _run_job(bot, job, resumed)
            except Exception:  # noqa: BLE001
                # kutilmagan xato — vazifa 'running' qoladi, keyingi startda davom etadi
                logger.exception("broadcast: xato (keyingi startda davom etadi)")
                break
        _progress.update(done=True, queued=0)


def _ensure_worker(bot: Bot) -> None:
    """Worker ketmayotgan bo'lsa — ishga tushiradi (navbatni o'zi topadi)."""
    if _lock.locked():
        return  # ketayotgan worker navbatni o'zi oladi
    asyncio.create_task(_worker(bot))


async def start(bot: Bot, from_chat_id: int, message_id: int, notify_chat_id: int) -> None:
    """Yangi reklamani navbatga qo'yadi va kerak bo'lsa workerni uyg'otadi."""
    async with SessionLocal() as session:
        total = await crud.count_users(session)
        await crud.create_broadcast_job(
            session, from_chat_id, message_id, notify_chat_id, total
        )
    _ensure_worker(bot)


async def resume_pending(bot: Bot) -> None:
    """Startda chaqiriladi: tugamagan/navbatdagi reklama bo'lsa, davom ettiradi."""
    async with SessionLocal() as session:
        active = await crud.get_active_broadcast_job(session)
        queued = await crud.count_queued_jobs(session)
    if active is None and queued == 0:
        return
    logger.info(
        f"broadcast: tugamagan ish topildi (running={active.id if active else None}, "
        f"navbatda={queued}) — davom ettirilmoqda"
    )
    _ensure_worker(bot)
