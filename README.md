# Vakansiya bot (bo'sh ish o'rinlari)

O'zbekiston bo'sh ish o'rinlari haqida ma'lumot beruvchi Telegram bot.
Ma'lumotlar `abkm.mehnat.uz` rasmiy API'sidan olinadi.

## Rollar

Rol **`/start` bosilganda** aniqlanadi (alohida komanda yo'q). Tugmalar rolga qarab
ko'rinadi. Ierarxiya: **superadmin ⊃ admin ⊃ user**.

- **Foydalanuvchi (user):** **viloyat → tuman → tashkilot → vakansiya** zanjiri:
  - tuman tugmasida jami vakansiyalar soni ko'rinadi
  - tashkilotlar ro'yxati (sahifalangan), har birida vakansiyalar soni
  - tashkilot tanlanса — uning vakansiyalari bittalab (⬅️/➡️)
  - **📤 Ulashish** — vakansiya kartochkasini inline rejim orqali istalgan
    chatga yuborish
  - **💵 Valyuta kurslari** (cbu.uz): USD, EUR, RUB, KZT
  - hamma tugmalar inline

> **Eslatma:** Ulashish (inline) ishlashi uchun @BotFather'da inline rejim
> yoqilgan bo'lishi kerak: `/setinline` → bot → placeholder matn kiriting.
- **Yordamchi admin** (`🛠 Admin panel` tugmasi):
  - 🔑 ABKM tokenni yangilash (bot ichidan)
  - 📊 Statistika
  - + user qila oladigan hamma ish
- **Superadmin** (`👑 Superadmin panel` + `🛠 Admin panel`): admin + user ishlari,
  ustiga foydalanuvchilarga qaysi hududlar ko'rinishini boshqaradi:
  - bir nechta viloyat yoqilsa → viloyatlar ro'yxati
  - faqat 1 viloyat yoqilsa → to'g'ridan-to'g'ri uning tumanlari
  - faqat 1 tuman yoqilsa → to'g'ridan-to'g'ri vakansiyalar

### Token va 401
ABKM token DB'da saqlanadi (`.env` faqat boshlang'ich qiymat). Admin/superadmin
uni bot ichidan yangilaydi. Agar API'dan **401** kelsa, barcha admin va
superadminlarga avtomatik ogohlantirish yuboriladi (10 daqiqada bir marta).

Boshlang'ich holat: barcha hududlar yoqilgan (butun respublika).

## Strukturasi

```
bot/
  config.py            # sozlamalar (.env)
  main.py              # entrypoint
  database/
    models.py          # User, Region, District
    crud.py            # DB funksiyalari
    seed.py            # soato_seed.json -> bazaga
  data/
    soato_seed.json    # viloyat/tuman SOATO kodlari (shu yerga qo'shing)
  services/
    abkm_api.py        # abkm.mehnat.uz klienti (+ kesh)
    formatter.py       # vakansiyani chiroyli matnga aylantirish
  keyboards/user_kb.py # tugmalar
  handlers/            # user.py, admin.py
  middlewares/auth.py  # sessiya + foydalanuvchini ro'yxatga olish
```

## Ishga tushirish

```powershell
cd D:\CLAUDE-PROJECTS\vacancy-bot
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # va .env ni to'ldiring
python -m bot.main
```

## .env

| O'zgaruvchi    | Tavsif                                              |
|----------------|-----------------------------------------------------|
| `BOT_TOKEN`      | @BotFather dan olingan token                      |
| `SUPERADMIN_IDS` | Superadmin Telegram ID lari (hudud boshqaruvi)    |
| `ADMIN_IDS`      | Yordamchi admin Telegram ID lari (vergul bilan)   |
| `ABKM_TOKEN`   | abkm.mehnat.uz Bearer token (vaqti-vaqti yangilanadi)|
| `DEFAULT_YEAR` | Standart yil (bo'sh = joriy yil)                    |
| `DEFAULT_MONTH`| Standart oy (bo'sh = joriy oy)                      |

## SOATO kodlarini qo'shish

`bot/data/soato_seed.json` faylini tahrirlang. Har bir viloyat va uning
tumanlarini qo'shing, so'ng botni qayta ishga tushiring — kodlar bazaga
upsert qilinadi (mavjudlari yangilanadi, yangilari qo'shiladi).

```json
{
  "regions": [
    {
      "soato": 1733,
      "name": "Xorazm viloyati",
      "districts": [
        { "soato": 1733401, "name": "Urganch shahar" }
      ]
    }
  ]
}
```

## Eslatma — ABKM token

`ABKM_TOKEN` (Bearer) vaqti-vaqti bilan eskiradi. Agar bot
"API token eskirgan (401)" desa, brauzerdan yangi tokenni olib `.env` ga
yozing.
