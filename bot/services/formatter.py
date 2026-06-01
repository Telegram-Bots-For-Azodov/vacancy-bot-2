"""Vakansiya dict -> chiroyli HTML matn (Telegram uchun).

Ma'lumot manbai: abkm.mehnat.uz `service_vacancies`. Matnlar asosan o'zbek-kirill
yozuvida keladi, shuning uchun ko'rsatishdan oldin lotinga o'giriladi.
"""
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

# Kirill -> lotin (uzun/maxsus belgilar avval keladi)
_CYR_LATIN = [
    ("Ё", "Yo"), ("ё", "yo"), ("Ж", "J"), ("ж", "j"), ("Ч", "Ch"), ("ч", "ch"),
    ("Ш", "Sh"), ("ш", "sh"), ("Щ", "Sh"), ("щ", "sh"), ("Ю", "Yu"), ("ю", "yu"),
    ("Я", "Ya"), ("я", "ya"), ("Ц", "S"), ("ц", "s"), ("Ў", "Oʻ"), ("ў", "oʻ"),
    ("Қ", "Q"), ("қ", "q"), ("Ғ", "Gʻ"), ("ғ", "gʻ"), ("Ҳ", "H"), ("ҳ", "h"),
    ("А", "A"), ("а", "a"), ("Б", "B"), ("б", "b"), ("В", "V"), ("в", "v"),
    ("Г", "G"), ("г", "g"), ("Д", "D"), ("д", "d"), ("Е", "E"), ("е", "e"),
    ("З", "Z"), ("з", "z"), ("И", "I"), ("и", "i"), ("Й", "Y"), ("й", "y"),
    ("К", "K"), ("к", "k"), ("Л", "L"), ("л", "l"), ("М", "M"), ("м", "m"),
    ("Н", "N"), ("н", "n"), ("О", "O"), ("о", "o"), ("П", "P"), ("п", "p"),
    ("Р", "R"), ("р", "r"), ("С", "S"), ("с", "s"), ("Т", "T"), ("т", "t"),
    ("У", "U"), ("у", "u"), ("Ф", "F"), ("ф", "f"), ("Х", "X"), ("х", "x"),
    ("Ъ", "ʼ"), ("ъ", "ʼ"), ("Ь", ""), ("ь", ""), ("Ы", "I"), ("ы", "i"),
    ("Э", "E"), ("э", "e"),
]


def _translit(value) -> str:
    """Kirill matnni lotinga o'giradi. Lotin matn o'zgarmaydi."""
    if value is None:
        return ""
    s = str(value)
    for cyr, lat in _CYR_LATIN:
        if cyr in s:
            s = s.replace(cyr, lat)
    return s


def _esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def _text(value) -> str:
    """Kirill -> lotin -> HTML-escape."""
    return _esc(_translit(value))


def _money(value) -> str:
    """Maosh: raqam bo'lsa formatlaydi, matn bo'lsa o'zini qaytaradi."""
    if value is None:
        return "—"
    s = str(value).strip()
    try:
        num = float(s)
    except (ValueError, TypeError):
        return _text(s)
    if num <= 0:
        return "—"
    formatted = f"{int(round(num)):,}".replace(",", " ")
    return f"{formatted} so'm"


def _education(code) -> str:
    if not code:
        return "—"
    key = str(code).strip()
    return _EDU.get(key, _translit(key))


def _experience(value) -> str:
    try:
        years = int(float(value))
    except (ValueError, TypeError):
        return "Talab etilmaydi"
    if years <= 0:
        return "Talab etilmaydi"
    return f"{years} yil"


def _phone(value) -> str:
    if not value:
        return "—"
    s = str(value).strip()
    if s.startswith("+"):
        return _esc(s)
    return _esc("+" + s) if s.isdigit() else _esc(s)


def _rate(value) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):g}"
    except (ValueError, TypeError):
        return _esc(value)


def _location(v: dict) -> str:
    """Mahalla + manzil."""
    makhalla = _translit(v.get("makhalla") or "")
    cdata = (v.get("company") or {}).get("data") or {}
    addr = _translit(cdata.get("SOATO_DESC_UZ") or cdata.get("ADDR") or "")
    parts = [p for p in (makhalla, addr) if p and p.strip()]
    # takror bo'lsa bittasini qoldiramiz
    seen: list[str] = []
    for p in parts:
        if p not in seen:
            seen.append(p)
    return _esc(", ".join(seen)) if seen else "—"


def _clip(value, limit: int) -> str:
    s = _translit(value).strip()
    if len(s) > limit:
        s = s[: limit - 1].rstrip() + "…"
    return _esc(s)


def format_vacancy(v: dict, index: int | None = None, total: int | None = None) -> str:
    info = v.get("additional_info") or {}

    name = _text(v.get("position_name") or v.get("position_name_ru") or "Lavozim")
    company = _text(v.get("company_name") or "—")
    structure = _text(v.get("structure_name") or v.get("structure_name_ru") or "")
    specialty = _text(info.get("eligible_specialties") or "")
    location = _location(v)
    salary = _money(v.get("position_salary"))
    rate = _rate(v.get("position_rate"))
    exp = _experience(info.get("work_exparence"))
    edu = _education(info.get("min_education"))
    phone = _phone(v.get("phone"))
    date_start = _esc(v.get("date_start") or "—")
    conditions = _clip(v.get("position_conditions"), 300)
    duties = _clip(v.get("position_duties"), 500)
    requirements = _clip(v.get("position_requirements"), 300)

    benefits = info.get("add_benefits_for_employees")
    benefits_line = ""
    if benefits and str(benefits).strip().lower() not in {"yo'q", "йук", "йўқ", "yuq", "none"}:
        benefits_line = f"🎁 <b>Imtiyozlar:</b> {_text(benefits)}\n"

    struct_line = f"🏷 <b>Bo'linma:</b> {structure}\n" if structure else ""
    spec_line = f"🧩 <b>Mos kasb:</b> {specialty}\n" if specialty else ""
    cond_line = f"🕒 <b>Ish sharti:</b> {conditions}\n" if conditions else ""
    duties_line = f"📋 <b>Vazifalar:</b> {duties}\n" if duties else ""
    req_line = f"✅ <b>Talablar:</b> {requirements}\n" if requirements else ""

    text = (
        f"💼 <b>{name}</b>\n"
        f"🏢 {company}\n"
        f"{struct_line}"
        f"📍 {location}\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"💰 <b>Maosh:</b> {salary}\n"
        f"📊 <b>Stavka:</b> {rate}\n"
        f"🧑‍💼 <b>Tajriba:</b> {exp}\n"
        f"🎓 <b>Ma'lumot:</b> {edu}\n"
        f"{spec_line}"
        f"{cond_line}"
        f"{duties_line}"
        f"{req_line}"
        f"{benefits_line}"
        f"☎️ <b>Telefon:</b> {phone}\n"
        f"📅 <b>E'lon sanasi:</b> {date_start}"
    )
    if index is not None and total is not None:
        text += f"\n➖➖➖➖➖➖➖➖\n📄 {index + 1}/{total}"
    return text


def format_vacancy_public(v: dict) -> str:
    """Ulashish uchun qisqartirilgan kartochka — telefon va ish sharti yashirin."""
    info = v.get("additional_info") or {}

    name = _text(v.get("position_name") or v.get("position_name_ru") or "Lavozim")
    company = _text(v.get("company_name") or "—")
    structure = _text(v.get("structure_name") or v.get("structure_name_ru") or "")
    location = _location(v)
    rate = _rate(v.get("position_rate"))
    exp = _experience(info.get("work_exparence"))
    edu = _education(info.get("min_education"))

    struct_line = f"🏷 <b>Bo'linma:</b> {structure}\n" if structure else ""

    return (
        f"💼 <b>{name}</b>\n"
        f"🏢 {company}\n"
        f"{struct_line}"
        f"📍 {location}\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"💰 <b>Maosh:</b> 🔒 botda\n"
        f"📊 <b>Stavka:</b> {rate}\n"
        f"🧑‍💼 <b>Tajriba:</b> {exp}\n"
        f"🎓 <b>Ma'lumot:</b> {edu}\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"🔒 <b>Maosh, telefon</b> va <b>ish sharti</b> — botda ko'rinadi.\n"
        f"👇 To'liq ma'lumot uchun pastdagi tugmani bosing."
    )
