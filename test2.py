"""
test2.py — Nodriver (async Chrome, WebDriver-free)
Xvfb kerak bo'lishi mumkin: sudo apt install xvfb && Xvfb :99 -screen 0 1280x900x24 &
Keyin: DISPLAY=:99 BOT_TOKEN=xxx python test2.py

O'rnatish:
    pip install nodriver requests
"""
import asyncio
import json
import os
from pathlib import Path

import nodriver as uc

BOT_TOKEN  = os.getenv("BOT_TOKEN", "")
CHAT_ID    = 1918760732
API_TARGET = "api.licenses.uz/v1/register/open_source"
TARGET_URL = (
    "https://license.gov.uz/registry"
    "?filter%5Bdocument_id%5D=4409"
    "&filter%5Bdocument_type%5D=LICENSE"
)

OUT_DIR = Path("test_output")
OUT_DIR.mkdir(exist_ok=True)

SCREENSHOT_PATH = OUT_DIR / "nodriver_screenshot.png"
JSON_PATH       = OUT_DIR / "nodriver_api.json"


# ── Telegram helpers (xuddi test1.py dagi) ────────────────────────────────────

async def tg_send_photo(token, chat_id, photo_path, caption=""):
    import urllib.request
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    with open(photo_path, "rb") as f:
        data = f.read()
    boundary = "----Boundary"
    body  = f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n"
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"s.png\"\r\nContent-Type: image/png\r\n\r\n"
    body_bytes = body.encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body_bytes,
          headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        urllib.request.urlopen(req, timeout=30)
        print("✅ Screenshot Telegram ga yuborildi")
    except Exception as e:
        print(f"❌ {e}")


async def tg_send_document(token, chat_id, file_path, caption=""):
    import urllib.request
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with open(file_path, "rb") as f:
        data = f.read()
    boundary = "----Boundary"
    body  = f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n"
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"api.json\"\r\nContent-Type: application/json\r\n\r\n"
    body_bytes = body.encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body_bytes,
          headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        urllib.request.urlopen(req, timeout=30)
        print("✅ JSON Telegram ga yuborildi")
    except Exception as e:
        print(f"❌ {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    api_data   = None
    api_caught = asyncio.Event()

    print("🚀 Nodriver ishga tushmoqda...")

    browser = await uc.start(
        headless=False,           # Xvfb bilan headful ko'rinadi
        browser_args=[
            "--window-size=1280,900",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]
    )

    try:
        tab = await browser.get(TARGET_URL)

        # Nodriver da network interception — CDP orqali
        # Performance log usulini ishlatamiz (test1 dagi route yo'q)
        await asyncio.sleep(3)  # Sahifa boshlangisi uchun kut

        # JavaScript fetch ni monkey-patch qilib API ni ushlaymiz
        intercept_script = """
        (function() {
            const orig = window.fetch;
            window._apiData = null;
            window.fetch = async function(...args) {
                const res = await orig.apply(this, args);
                const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
                if (url.includes('api.licenses.uz/v1/register/open_source')) {
                    try {
                        const clone = res.clone();
                        const json = await clone.json();
                        window._apiData = JSON.stringify(json);
                    } catch(e) {}
                }
                return res;
            };
        })();
        """
        await tab.evaluate(intercept_script)

        # Sahifani yangilash (monkey-patch keyin ishlashi uchun)
        await tab.reload()
        print(f"🌐 URL: {TARGET_URL}")

        # API kelguncha kut (max 25s)
        for _ in range(50):
            await asyncio.sleep(0.5)
            result = await tab.evaluate("window._apiData")
            if result:
                api_data = json.loads(result)
                items = len((api_data.get("data") or {}).get("certificates") or [])
                print(f"✅ API ushlandi! items={items}, "
                      f"totalPages={api_data.get('data', {}).get('totalPages')}")
                break
        else:
            print("⚠️  API 25s da kelmadi")

        # Screenshot
        print("📸 Screenshot olinmoqda...")
        await tab.save_screenshot(str(SCREENSHOT_PATH))
        print(f"   Saqlandi: {SCREENSHOT_PATH}")

        # JSON saqlash
        if api_data:
            JSON_PATH.write_text(
                json.dumps(api_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"   JSON saqlandi: {JSON_PATH}")

    finally:
        browser.stop()

    # ── Telegram ───────────────────────────────────────────────────────────
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN yo'q")
        return

    await tg_send_photo(BOT_TOKEN, CHAT_ID, SCREENSHOT_PATH,
        f"📸 Nodriver test\nAPI: {'✅ ushlandi' if api_data else '❌ ushlashilmadi'}")

    if api_data and JSON_PATH.exists():
        items_count = len((api_data.get("data") or {}).get("certificates") or [])
        await tg_send_document(BOT_TOKEN, CHAT_ID, JSON_PATH,
            f"📊 API JSON — {items_count} ta sertifikat")


if __name__ == "__main__":
    asyncio.run(main())
