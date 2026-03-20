"""
test1.py — Camoufox + virtual display
Sayt ochiladi, screenshot olinadi, API JSON ushlandi → Telegram ga yuboriladi.

O'rnatish:
    pip install camoufox[geoip] python-telegram-bot requests
    python -m camoufox fetch  # Firefox binary yuklab oladi

Ishlatish:
    BOT_TOKEN=xxx python test1.py
"""
import asyncio
import json
import os
import time
import base64
from pathlib import Path

BOT_TOKEN  = os.getenv("BOT_TOKEN", "")   # .env dan yoki to'g'ridan
CHAT_ID    = 1918760732
API_TARGET = "api.licenses.uz/v1/register/open_source"
TARGET_URL = (
    "https://license.gov.uz/registry"
    "?filter%5Bdocument_id%5D=4409"
    "&filter%5Bdocument_type%5D=LICENSE"
)

OUT_DIR = Path("test_output")
OUT_DIR.mkdir(exist_ok=True)

SCREENSHOT_PATH = OUT_DIR / "camoufox_screenshot.png"
JSON_PATH       = OUT_DIR / "camoufox_api.json"


# ── Telegram helpers ──────────────────────────────────────────────────────────

async def tg_send_photo(token: str, chat_id: int, photo_path: Path, caption: str = ""):
    import urllib.request, urllib.parse, urllib.error
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    with open(photo_path, "rb") as f:
        photo_data = f.read()

    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    body  = f"--{boundary}\r\n"
    body += f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'
    body += f"--{boundary}\r\n"
    body += f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'
    body += f"--{boundary}\r\n"
    body += f'Content-Disposition: form-data; name="photo"; filename="{photo_path.name}"\r\nContent-Type: image/png\r\n\r\n'
    body_bytes = body.encode() + photo_data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        url, data=body_bytes,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    try:
        urllib.request.urlopen(req, timeout=30)
        print("✅ Screenshot Telegram ga yuborildi")
    except Exception as e:
        print(f"❌ Screenshot yuborishda xato: {e}")


async def tg_send_document(token: str, chat_id: int, file_path: Path, caption: str = ""):
    import urllib.request
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with open(file_path, "rb") as f:
        file_data = f.read()

    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    body  = f"--{boundary}\r\n"
    body += f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'
    body += f"--{boundary}\r\n"
    body += f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'
    body += f"--{boundary}\r\n"
    body += f'Content-Disposition: form-data; name="document"; filename="{file_path.name}"\r\nContent-Type: application/json\r\n\r\n'
    body_bytes = body.encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        url, data=body_bytes,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    try:
        urllib.request.urlopen(req, timeout=30)
        print("✅ JSON Telegram ga yuborildi")
    except Exception as e:
        print(f"❌ JSON yuborishda xato: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError:
        print("pip install camoufox[geoip] && python -m camoufox fetch")
        return

    api_data   = None
    api_caught = asyncio.Event()

    print("🦊 Camoufox ishga tushmoqda (headless=virtual)...")

    async with AsyncCamoufox(
        headless="virtual",       # Xvfb — serverda ham headful ko'rinadi
        geoip=True,               # IP ga mos geo fingerprint
        humanize=True,            # human-like harakatlar
        os="windows",             # Windows fingerprint
        window=(1280, 900),
    ) as browser:

        context = await browser.new_context()

        # ── API interception via route ──────────────────────────────────────
        async def handle_response(response):
            nonlocal api_data
            if api_caught.is_set():
                return
            try:
                if API_TARGET in response.url and response.status == 200:
                    if "stat" not in response.url and "search" not in response.url:
                        body = await response.json()
                        api_data = body
                        api_caught.set()
                        items = len((body.get("data") or {}).get("certificates") or [])
                        print(f"✅ API ushlandi! URL: {response.url[:80]}")
                        print(f"   items={items}, "
                              f"totalPages={body.get('data', {}).get('totalPages')}")
            except Exception as e:
                print(f"   response parse xato: {e}")

        page = await context.new_page()
        page.on("response", handle_response)

        # ── Sahifani och ───────────────────────────────────────────────────
        print(f"🌐 URL ochilmoqda: {TARGET_URL}")
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60_000)

        # To'liq yuklanishini kut (max 20s) yoki API kelguncha
        try:
            await asyncio.wait_for(api_caught.wait(), timeout=20)
        except asyncio.TimeoutError:
            print("⚠️  API 20s da kelmadi, networkidle kutilmoqda...")
            try:
                await page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass

        # ── Screenshot ─────────────────────────────────────────────────────
        print("📸 Screenshot olinmoqda...")
        await page.screenshot(path=str(SCREENSHOT_PATH), full_page=False)
        print(f"   Saqlandi: {SCREENSHOT_PATH}")

        # ── JSON saqlash ───────────────────────────────────────────────────
        if api_data:
            JSON_PATH.write_text(
                json.dumps(api_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"   JSON saqlandi: {JSON_PATH}")
        else:
            print("⚠️  API JSON ushlash muvaffaqiyatsiz — faqat screenshot yuboriladi")

        await context.close()

    # ── Telegram ───────────────────────────────────────────────────────────
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN yo'q — Telegram ga yuborib bo'lmaydi")
        return

    caption_photo = (
        "📸 <b>Camoufox test — license.gov.uz</b>\n"
        f"API: {'✅ ushlandi' if api_data else '❌ ushlashilmadi'}"
    )
    await tg_send_photo(BOT_TOKEN, CHAT_ID, SCREENSHOT_PATH, caption_photo)

    if api_data and JSON_PATH.exists():
        items_count = len((api_data.get("data") or {}).get("certificates") or [])
        await tg_send_document(
            BOT_TOKEN, CHAT_ID, JSON_PATH,
            f"📊 API JSON — {items_count} ta sertifikat"
        )


if __name__ == "__main__":
    asyncio.run(main())
