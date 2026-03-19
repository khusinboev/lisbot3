# License Bot - Loyiha Xulosasi

## Umumiy ma'lumot

Bu loyiha license.gov.uz saytidan sertifikatlar ma'lumotlarini avtomatik yig'ish, saqlash va Telegram orqali boshqarish uchun yaratilgan.

## Asosiy vazifalar

1. **Barcha sertifikatlarni yig'ish** - Saytdan barcha sertifikat ma'lumotlarini avtomatik yig'ish
2. **Saralash** - "Олий таълим хизматлари" faoliyat turi bo'yicha saralash
3. **Yangilash** - Sertifikat ma'lumotlarini qayta o'qish va yangilash
4. **Statistika** - Umumiy va saraalangan sertifikatlar sonini ko'rish
5. **PDF yuklash** - Sertifikatlarning PDF fayllarini yuklab olish

## Texnologik stack

- **aiogram 3.4.1** - Telegram bot framework
- **SQLite3 (aiosqlite)** - Asinxron ma'lumotlar bazasi
- **Playwright 1.42.0** - Web scraping (Cloudflare bypass)
- **BeautifulSoup4** - HTML parsing
- **loguru** - Logging

## Loyiha strukturasi

```
license_bot/
├── data/                       # Ma'lumotlar bazasi va yuklanmalar
│   ├── certificates.db        # SQLite3 ma'lumotlar bazasi
│   └── downloads/             # PDF fayllar
├── src/                        # Manba kodi
│   ├── database.py            # Database operations
│   ├── parser.py              # Basic parser
│   ├── parser_v2.py           # Improved parser with stealth
│   └── bot.py                 # Telegram bot
├── main.py                     # Asosiy kirish nuqtasi
├── test_setup.py              # Test skripti
├── requirements.txt           # Python paketlari
├── .env.example               # Muhit o'zgaruvchilari namunasi
├── install.sh                 # O'rnatish skripti
├── license-bot.service        # Systemd service
└── README.md                  # To'liq dokumentatsiya
```

## Ma'lumotlar bazasi tuzilmasi

### certificates jadvali
| Maydon | Tavsif |
|--------|--------|
| id | Unikal ID (PRIMARY KEY) |
| document_id | Hujjat ID si |
| document_number | Hujjat raqami |
| status | Holati |
| issue_date | Taqdim etilgan sana |
| inserted_date | Bazaga kiritilgan sana |
| organization_name | Tashkilot nomi |
| address | Manzil |
| stir | STIR raqami |
| expiry_date | Amal qilish muddati |
| activity_type | Faoliyat turi |
| uuid | UUID (PDF yuklash uchun) |
| pdf_url | PDF fayl havolasi |
| created_at | Yaratilgan vaqt |
| updated_at | Yangilangan vaqt |
| is_filtered | Saralanganligi (0/1) |

### filtered_certificates jadvali
Saralangan sertifikatlar uchun alohida jadval. Asosiy jadval bilan FOREIGN KEY orqali bog'langan.

## Anti-bot himoyasini aylanish

### Cloudflare Turnstile himoyasi
Sayt Cloudflare Turnstile dan foydalanadi. Quyidagi usullar bilan aylaniladi:

1. **Playwright stealth mode**:
   - Real brauzer simulyatsiyasi
   - `webdriver` xususiyatini yashirish
   - Pluginlarni simulyatsiya qilish

2. **Realistik sozlamalar**:
   - To'g'ri User-Agent
   - Joylashuv (Toshkent)
   - Vaqt zonasi
   - Ekran o'lchami

3. **Request interception**:
   - API chaqiruvlarini ushlash
   - Ma'lumotlarni real vaqtda olish

4. **Random delays**:
   - Sahifalar orasida tasodifiy kechikish
   - Bot kabi ko'rinmaslik uchun

## Bot funksiyalari

### Asosiy tugmalar
1. 📥 **Барча сертфикатларни йиғиш** - Barcha sertifikatlarni yig'ish
2. 🔍 **Саралаш** - "Олий таълим хизматлари" bo'yicha saralash
3. 🔄 **Янгилаш** - Ma'lumotlarni yangilash
4. 📊 **Статистика** - Statistikani ko'rish
5. 📄 **PDF юклаш** - PDF fayllarni yuklash

### Buyruqlar
- `/start` - Botni ishga tushirish
- `/help` - Yordam
- `/stats` - Statistika
- `/scrape` - Yig'ish
- `/filter` - Saralash
- `/update` - Yangilash
- `/pdfs` - PDF yuklash

## O'rnatish va ishga tushirish

### 1. Ubuntu serverda o'rnatish

```bash
# Loyihani klonlash
git clone <repository-url>
cd license_bot

# O'rnatish skriptini ishga tushirish
chmod +x install.sh
./install.sh

# .env faylini tahrirlash
nano .env

# Botni ishga tushirish
sudo systemctl start license-bot@$USER
```

### 2. Docker orqali (tavsiya etilmaydi)

Playwright brauzerlari uchun Docker konteyneri talab qiladi.

## Xavfsizlik

1. **Admin tekshiruvi** - Faqat ro'yxatdan o'tgan adminlar foydalanishi mumkin
2. **Token xavfsizligi** - Bot tokeni `.env` faylida saqlanadi
3. **Ma'lumotlar xavfsizligi** - Ma'lumotlar lokal SQLite3 faylida saqlanadi

## Muammolar va yechimlari

### 1. Playwright ishlamayapti
```bash
playwright install chromium
```

### 2. Cloudflare bloklayapti
- Stealth mode yoqilgan
- IP manzilni tekshiring
- Vaqtinchalik kuting va qayta urining

### 3. Bot javob bermayapti
```bash
sudo journalctl -u license-bot@$USER -f
```

## Rivojlantirish rejasi

1. **Redis keshlash** - Tezkor ma'lumotlar olish uchun
2. **Web interface** - Brauzer orqali boshqarish
3. **API endpoint** - Tashqi tizimlar bilan integratsiya
4. **Bir necha filtrlar** - Ko'proq faoliyat turlari bo'yicha saralash
5. **Avtomatik yangilash** - Rejalashtirilgan yangilanishlar

## Foydalanilgan manbalar

- [aiogram documentation](https://docs.aiogram.dev/)
- [Playwright documentation](https://playwright.dev/python/)
- [license.gov.uz](https://license.gov.uz)

## Litsenziya

MIT License
