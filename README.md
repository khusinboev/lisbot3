# License Bot - Telegram Bot for license.gov.uz

Bu loyiha license.gov.uz saytidan sertifikatlar ma'lumotlarini yig'ish, saqlash va ularni Telegram orqali boshqarish uchun yaratilgan bot.

## Xususiyatlari

- 📥 **Barcha sertifikatlarni yig'ish** - Saytdan barcha sertifikat ma'lumotlarini avtomatik yig'ish
- 🔍 **Saralash** - "Олий таълим хизматлари" faoliyat turi bo'yicha saralash
- 🔄 **Yangilash** - Sertifikat ma'lumotlarini qayta o'qish va yangilash
- 📊 **Statistika** - Umumiy va saraalangan sertifikatlar sonini ko'rish
- 📄 **PDF yuklash** - Sertifikatlarning PDF fayllarini yuklab olish

## Texnologiyalar

- **aiogram 3.x** - Telegram bot framework
- **SQLite3** - Ma'lumotlar bazasi
- **Playwright** - Web scraping (Cloudflare bypass)
- **BeautifulSoup4** - HTML parsing

## O'rnatish

### 1. Loyihani klonlash

```bash
git clone <repository-url>
cd license_bot
```

### 2. Virtual muhit yaratish (tavsiya etiladi)

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# yoki
venv\Scripts\activate  # Windows
```

### 3. Kerakli paketlarni o'rnatish

```bash
pip install -r requirements.txt
```

### 4. Playwright brauzerlarini o'rnatish

```bash
playwright install chromium
```

### 5. Muhit o'zgaruvchilarini sozlash

`.env.example` faylini `.env` ga nusxalang va o'zgartiring:

```bash
cp .env.example .env
nano .env  # yoki boshqa editor
```

Kerakli o'zgaruvchilar:
- `BOT_TOKEN` - Telegram bot token (@BotFather dan oling)
- `ADMIN_IDS` - Admin foydalanuvchi IDlari (vergul bilan ajratilgan)

## Ishga tushirish

### Oddiy ishga tushirish

```bash
python main.py
```

### Ubuntu serverda (systemd orqali)

1. Service fayl yaratish:

```bash
sudo nano /etc/systemd/system/license-bot.service
```

2. Quyidagi kontentni qo'shing:

```ini
[Unit]
Description=License Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/license_bot
Environment=PATH=/path/to/license_bot/venv/bin
ExecStart=/path/to/license_bot/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

3. Service ni yoqish:

```bash
sudo systemctl daemon-reload
sudo systemctl enable license-bot
sudo systemctl start license-bot
```

4. Holatni tekshirish:

```bash
sudo systemctl status license-bot
sudo journalctl -u license-bot -f
```

## Bot buyruqlari

- `/start` - Botni ishga tushirish
- `/help` - Yordam ko'rsatish
- `/stats` - Statistikani ko'rsatish
- `/scrape` - Barcha sertifikatlarni yig'ish
- `/filter` - "Олий таълим хизматлари" bo'yicha saralash
- `/update` - Saralgan ma'lumotlarni yangilash
- `/pdfs` - PDF fayllarni yuklash

## Ma'lumotlar bazasi tuzilmasi

### certificates jadvali
- `id` - Unikal ID
- `document_id` - Hujjat ID si
- `document_number` - Hujjat raqami
- `status` - Holati
- `issue_date` - Taqdim etilgan sana
- `inserted_date` - Bazaga kiritilgan sana
- `organization_name` - Tashkilot nomi
- `address` - Manzil
- `stir` - STIR raqami
- `expiry_date` - Amal qilish muddati
- `activity_type` - Faoliyat turi
- `uuid` - UUID (PDF yuklash uchun)
- `pdf_url` - PDF fayl havolasi
- `created_at` - Yaratilgan vaqt
- `updated_at` - Yangilangan vaqt
- `is_filtered` - Saralanganligi

### filtered_certificates jadvali
Saralangan sertifikatlar uchun alohida jadval

### scraping_stats jadvali
Yig'ish statistikasi uchun

## Anti-bot himoyasini aylanish

Bu bot Playwright va quyidagi usullar orqali Cloudflare Turnstile himoyasini aylanadi:
- Real brauzer simulyatsiyasi
- User-Agent va headerlarni to'g'ri sozlash
- JavaScript execution
- Request interception

## Xavfsizlik

- Faqat admin foydalanuvchilar botdan foydalanishi mumkin
- Bot tokeni va admin IDlari `.env` faylida saqlanadi
- Ma'lumotlar bazasi lokal SQLite3 faylida saqlanadi

## Muammolar va yechimlari

### Playwright brauzeri ishlamayapti

```bash
playwright install chromium
```

### Bot ishga tushmayapti

1. `.env` faylini tekshiring
2. `BOT_TOKEN` to'g'ri ekanligini tekshiring
3. `ADMIN_IDS` to'g'ri formatda ekanligini tekshiring

### Scraping ishlamayapti

1. Internet ulanishini tekshiring
2. license.gov.uz sayti ishlayotganini tekshiring
3. Playwright brauzerini qayta o'rnatib ko'ring

## Litsenziya

MIT License

## Muallif

[Your Name]

## Aloqa

Telegram: [@your_username]
