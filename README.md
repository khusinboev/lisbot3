# License Bot

`license.gov.uz` saytidan litsenziya ma'lumotlarini avtomatik yig'ib, Telegram orqali boshqaruvchi bot.

## Qanday ishlaydi

Bot saytni ochadi → Cloudflare Turnstile dan o'tadi → background API response ni CDP orqali ushlaydi → ma'lumotlarni bazaga yozadi. HTML parse qilinmaydi — to'g'ridan API JSON dan olinadi.

## Texnologiyalar

- **aiogram 3.x** — Telegram bot
- **undetected_chromedriver** — Cloudflare bypass
- **CDP performance log** — API response interception
- **SQLite + aiosqlite** — Ma'lumotlar bazasi

## Loyiha tuzilmasi

```
license_bot/
├── src/
│   ├── bot.py              # Telegram bot handlers
│   ├── bot_helpers.py      # Yordamchi funksiyalar
│   ├── database.py         # SQLite operatsiyalar
│   ├── parser_v3.py        # Asosiy scraper
│   ├── fingerprint_patch.py # Browser fingerprint hardening
│   └── settings.py         # Sozlamalar
├── data/
│   ├── certificates.db     # SQLite baza
│   └── chrome_profile_parser_v3/  # Chrome profili
├── downloads/              # PDF fayllar
├── main.py                 # Kirish nuqtasi
├── requirements.txt
├── .env                    # Sozlamalar (git da yo'q)
├── .env.example
├── install.sh              # Ubuntu o'rnatish skripti
├── license-bot.service     # Systemd service
└── xvfb.service            # Xvfb systemd service
```

## Ma'lumotlar bazasi

`certificates` jadvali:

| Ustun | Ma'lumot |
|-------|----------|
| `uuid` | PDF token, UNIQUE |
| `number` | Hujjat raqami |
| `register_number` | L-XXXXXXXX |
| `name` | Tashkilot nomi |
| `tin` | STIR raqami |
| `region_uz` | Viloyat |
| `sub_region_uz` | Tuman |
| `address` | Manzil |
| `activity_addresses` | Faoliyat manzillari (JSON) |
| `registration_date` | Berilgan sana |
| `expiry_date` | Muddati |
| `status` | ACTIVE / REVOKED |
| `specializations` | Faoliyat turlari (JSON) |
| `is_filtered` | Saralangan (0/1) |

## O'rnatish (Ubuntu Server)

```bash
git clone <repo-url> license_bot
cd license_bot
chmod +x install.sh
sudo ./install.sh
```

Keyin `.env` ni tahrirlang:

```bash
nano .env
```

Botni ishga tushiring:

```bash
sudo systemctl start xvfb
sudo systemctl start license-bot
sudo journalctl -u license-bot -f
```

## O'rnatish (Windows, lokal)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# .env ni tahrirlang
python main.py
```

## .env sozlamalari

```env
BOT_TOKEN=...           # @BotFather dan
ADMIN_IDS=123456789     # Telegram ID

# Ubuntu serverda
CHROME_HEADLESS=true
SKIP_WARMUP=true
DISPLAY=:99

# Windows lokalda
CHROME_HEADLESS=false
SKIP_WARMUP=false
```

## Bot buyruqlari

| Tugma | Vazifa |
|-------|--------|
| 📥 Барча сертификатларни йиғиш | API dan barcha ma'lumotlarni olish |
| 📊 Статистика | Baza statistikasini ko'rish |
| 📄 PDF юклаш | Saralgan sertifikatlar PDF larini yuborish |

Scraping jarayonida har sahifa tugagach darrov bazaga yoziladi. Xato bo'lsa, o'sha vaqtgacha yig'ilganlar saqlanib qoladi.

## Muammolar

**`chrome not reachable`** — Chrome profil papkasini tozalang:
```bash
rm -rf data/chrome_profile_parser_v3
sudo systemctl restart license-bot
```

**ChromeDriver versiya mos kelmaydi** — `.env` dan `CHROME_VERSION_MAIN` ni o'chiring, uc o'zi topadi.

**Xvfb ishlamaydi** — mavjud processni tekshiring:
```bash
ps aux | grep Xvfb
ls /tmp/.X99-lock
```

## Loglar

```bash
sudo journalctl -u license-bot -f
sudo journalctl -u xvfb -f
```