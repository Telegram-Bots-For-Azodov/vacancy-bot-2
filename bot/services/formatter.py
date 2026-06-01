"""Vakansiya dict -> chiroyli HTML matn (Telegram uchun)."""
from __future__ import annotations

import html

_EDU = {
    "В/О": "Oliy",
    "ВО": "Oliy",
    "ССПО": "O'rta maxsus / kasb-hunar",
    "СПО": "O'rta maxsus",
    "С/С": "O'rta",
    "СС": "O'rta",
    "Н/Т": "Talab etilmaydi",
    "НТ": "Talab etilmaydi",
}

_LANG = {
    "uz": "o'zbek",
    "ru": "rus",
    "en": "ingliz",
    "kr": "qoraqalpoq",
}


def _esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def _money(value) -> str:
    """Maosh: raqam bo'lsa formatlaydi, matn bo'lsa o'zini qaytaradi."""
    if value is None:
        return "—"
    s = str(value).strip()
    try:
        num = float(s)
    except (ValueError, TypeError):
        return _esc(s)  # "Ish haqi shtat jadvaliga..." kabi matn
    if num <= 0:
        return "—"
    formatted = f"{int(round(num)):,}".replace(",", " ")
    return f"{formatted} so'm"


def _education(code) -> str:
    if not code:
        return "—"
    return _EDU.get(str(code).strip(), str(code).strip())


def _languages(value) -> str:
    if not value:
        return "—"
    parts = [p.strip() for p in str(value).split(",") if p.strip()]
    names = [_LANG.get(p.lower(), p) for p in parts]
    return ", ".join(names) if names else "—"


def _experience(value) -> str:
    try:
        years = int(float(value))
    except (ValueError, TypeError):
        return "—"
    if years <= 0:
        return "Talab etilmaydi"
    return f"{years} yil"


def format_vacancy(v: dict, index: int | None = None, total: int | None = None) -> str:
    name = _esc(v.get("position_name") or v.get("position_name_ru") or "Lavozim")
    company = _esc(v.get("company_name") or "—")
    district = _esc(v.get("structure") or "—")
    count = v.get("count_vacancy") or 1
    salary = _money(v.get("position_salary"))
    rate = _esc(v.get("position_rate") or "—")
    exp = _experience(v.get("work_experience"))
    edu = _esc(_education(v.get("min_education")))
    langs = _esc(_languages(v.get("foreign_languages")))
    phone = _esc(v.get("company_phone") or "—")
    status = _esc(v.get("vr_status") or "—")
    conditions = _esc(v.get("position_conditions") or "")

    benefits = v.get("add_benefits_for_employees")
    benefits_line = ""
    if benefits and str(benefits).strip().lower() not in {"yo'q", "йук", "йўқ", "yuq", "none"}:
        benefits_line = f"🎁 <b>Imtiyozlar:</b> {_esc(benefits)}\n"

    cond_line = ""
    if conditions:
        cond_line = f"🕒 <b>Ish sharti:</b> {conditions}\n"

    text = (
        f"💼 <b>{name}</b>\n"
        f"🏢 {company}\n"
        f"📍 {district}\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"💰 <b>Maosh:</b> {salary}\n"
        f"📊 <b>Stavka:</b> {rate}\n"
        f"🧑‍💼 <b>Tajriba:</b> {exp}\n"
        f"🎓 <b>Ma'lumot:</b> {edu}\n"
        f"🗣 <b>Tillar:</b> {langs}\n"
        f"👥 <b>O'rinlar soni:</b> {_esc(count)}\n"
        f"{cond_line}"
        f"{benefits_line}"
        f"☎️ <b>Telefon:</b> {phone}\n"
        f"✅ <b>Holati:</b> {status}"
    )
    if index is not None and total is not None:
        text += f"\n➖➖➖➖➖➖➖➖\n📄 {index + 1}/{total}"
    return text


def format_vacancy_public(v: dict) -> str:
    """Ulashish uchun qisqartirilgan kartochka — telefon va ish sharti yashirin."""
    name = _esc(v.get("position_name") or v.get("position_name_ru") or "Lavozim")
    company = _esc(v.get("company_name") or "—")
    district = _esc(v.get("structure") or "—")
    count = v.get("count_vacancy") or 1
    rate = _esc(v.get("position_rate") or "—")
    exp = _experience(v.get("work_experience"))
    edu = _esc(_education(v.get("min_education")))
    langs = _esc(_languages(v.get("foreign_languages")))

    return (
        f"💼 <b>{name}</b>\n"
        f"🏢 {company}\n"
        f"📍 {district}\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"💰 <b>Maosh:</b> 🔒 botda\n"
        f"📊 <b>Stavka:</b> {rate}\n"
        f"🧑‍💼 <b>Tajriba:</b> {exp}\n"
        f"🎓 <b>Ma'lumot:</b> {edu}\n"
        f"🗣 <b>Tillar:</b> {langs}\n"
        f"👥 <b>O'rinlar soni:</b> {_esc(count)}\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"🔒 <b>Maosh, telefon</b> va <b>ish sharti</b> — botda ko'rinadi.\n"
        f"👇 To'liq ma'lumot uchun pastdagi tugmani bosing."
    )
