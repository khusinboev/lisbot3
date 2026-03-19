#!/usr/bin/env python3
"""
test_license_parser.py - License.gov.uz parser test fayli
Bitta faylda hamma narsa: parser + test

Ishga tushirish:
    python test_license_parser.py

Talablar:
    pip install undetected-chromedriver selenium pyvirtualdisplay loguru
"""

import os
import sys
import time
import random
import json
import re
from typing import List, Dict, Optional
from dataclasses import dataclass

# Stealth imports
try:
    import undetected_chromedriver as uc

    UC_AVAILABLE = True
except ImportError:
    UC_AVAILABLE = False
    print("[XATO] undetected-chromedriver o'rnatilmagan!")
    print("       O'rnatish: pip install undetected-chromedriver")
    sys.exit(1)

try:
    from pyvirtualdisplay import Display

    XVFB_AVAILABLE = True
except ImportError:
    XVFB_AVAILABLE = False
    print("[OGohlantirish] pyvirtualdisplay o'rnatilmagan (Xvfb ishlamaydi)")

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Logging
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL = "https://license.gov.uz/registry"
FILTER_PARAMS = "?filter%5Bdocument_id%5D=4409&filter%5Bdocument_type%5D=LICENSE"
API_TARGET = "api.licenses.uz/v1/register/open_source"

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_PATH = os.path.join(CURRENT_DIR, "chrome_profile_test")
os.makedirs(PROFILE_PATH, exist_ok=True)


# ── Data Classes ──────────────────────────────────────────────────────────────
@dataclass
class Certificate:
    """Sertifikat ma'lumotlari"""
    number: str = ""
    tin: str = ""
    name: str = ""
    specialization_oz: str = ""
    uuid: Optional[str] = None
    active: bool = False
    status: str = ""
    issue_date: str = ""
    expiry_date: str = ""
    address: str = ""
    document_id: str = ""
    pdf_url: str = ""


# ── LicenseParser Class ───────────────────────────────────────────────────────
class LicenseParser:
    """License.gov.uz uchun stealth parser"""

    def __init__(self):
        self.driver = None
        self.virtual_display = None
        self._warmup_done = False

    def _detect_chrome_binary(self) -> Optional[str]:
        """Chrome binary path ni aniqlash"""
        import shutil

        # Environment o'zgaruvchisi
        env_path = os.getenv("CHROME_BINARY", "").strip()
        if env_path and os.path.isfile(env_path):
            return env_path

        # OS ga mos default joylashuvlar
        if sys.platform == "win32":
            candidates = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            ]
        elif sys.platform == "darwin":
            candidates = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ]
        else:
            # Linux / Ubuntu
            candidates = [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium-browser",
                "/usr/bin/chromium",
                "/snap/bin/chromium",
            ]

        for path in candidates:
            if os.path.isfile(path):
                logger.info(f"[Chrome] Topildi: {path}")
                return path

        # PATH dan qidirish
        for name in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
            found = shutil.which(name)
            if found:
                logger.info(f"[Chrome] PATH dan: {found}")
                return found

        return None

    def _is_driver_alive(self) -> bool:
        """Driver hayotligini tekshirish"""
        if self.driver is None:
            return False
        try:
            _ = self.driver.current_url
            _ = self.driver.window_handles
            return True
        except Exception:
            return False

    def _init_driver(self):
        """Chrome driver ni ishga tushirish"""
        # Xvfb virtual display
        headless = os.getenv("CHROME_HEADLESS", "false").lower() == "true"

        if headless and XVFB_AVAILABLE:
            logger.info("[Xvfb] Virtual display ishga tushirilmoqda...")
            self.virtual_display = Display(visible=0, size=(1920, 1080), backend="xvfb")
            self.virtual_display.start()

        # Chrome options
        options = uc.ChromeOptions()
        options.add_argument(f"--user-data-dir={PROFILE_PATH}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-notifications")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        if headless:
            options.add_argument("--headless=new")
            logger.info("[Chrome] Headless mode")

        # User agent
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36")

        # Chrome binary
        chrome_path = self._detect_chrome_binary()
        if chrome_path:
            options.binary_location = chrome_path
        else:
            logger.warning("[Chrome] Binary topilmadi! O'rnatilganligini tekshiring.")

        # Performance logs
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        # Driver yaratish
        try:
            driver = uc.Chrome(options=options)
            driver.set_page_load_timeout(60)
        except Exception as e:
            logger.error(f"[Chrome] Driver yaratishda xato: {e}")
            raise

        # JS Spoofing
        self._apply_js_spoofing(driver)

        driver._virtual_display = self.virtual_display
        logger.info("[Chrome] Driver ishga tushdi ✅")
        return driver

    def _apply_js_spoofing(self, driver):
        """JavaScript orqali bot detection ni aldash"""
        spoof_script = """
            delete navigator.__proto__.webdriver;
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['uz-UZ','ru','en-US','en']});
            Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
            Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

            const origGetContext = HTMLCanvasElement.prototype.getContext;
            HTMLCanvasElement.prototype.getContext = function(type) {
                const ctx = origGetContext.apply(this, arguments);
                if (type === '2d' && ctx) {
                    const origFillText = ctx.fillText;
                    ctx.fillText = function(text, x, y) {
                        if (typeof text === 'string' && text.length > 0) {
                            arguments[0] = text + String.fromCharCode(97 + Math.random() * 26 | 0);
                        }
                        return origFillText.apply(this, arguments);
                    };
                }
                return ctx;
            };

            const origGetParam = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(p) {
                if (p === 37445) return 'Intel Inc.';
                if (p === 37446) return 'Intel Iris OpenGL Engine';
                return origGetParam.apply(this, arguments);
            };
        """
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": spoof_script})

    def _get_driver(self):
        """Driver ni olish"""
        if not self._is_driver_alive():
            self.driver = self._init_driver()
        return self.driver

    def _quit_driver(self):
        """Driver ni yopish"""
        if self.virtual_display:
            try:
                self.virtual_display.stop()
            except:
                pass
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        self.driver = None
        self._warmup_done = False

    def _human_delay(self, a=0.8, b=2.0):
        time.sleep(random.uniform(a, b))

    def warmup(self):
        """YouTube orqali warmup"""
        if self._warmup_done:
            return True

        driver = self._get_driver()
        try:
            logger.info("[Warmup] YouTube ga o'tish...")
            driver.get("https://www.youtube.com")
            time.sleep(2)

            # Search
            box = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "search_query"))
            )
            box.click()
            time.sleep(0.5)

            queries = ["python tutorial", "uzbekistan travel", "music 2024"]
            query = random.choice(queries)
            for ch in query:
                box.send_keys(ch)
                time.sleep(random.uniform(0.04, 0.16))

            box.send_keys(Keys.ENTER)
            time.sleep(2)

            # Scroll
            for _ in range(3):
                driver.execute_script(f"window.scrollBy(0, {random.randint(200, 500)});")
                time.sleep(0.5)

            logger.info("[Warmup] ✅ Tayyor")
            self._warmup_done = True
            return True

        except Exception as e:
            logger.error(f"[Warmup] Xato: {e}")
            return False

    def _open_page(self, page_num: int) -> bool:
        """Sahifani ochish"""
        url = f"{BASE_URL}{FILTER_PARAMS}&page={page_num + 1}"
        logger.info(f"[Page] Ochilmoqda: page={page_num + 1}")

        driver = self._get_driver()

        for attempt in range(3):
            try:
                driver.get(url)
                WebDriverWait(driver, 30).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
                time.sleep(3)

                if self._page_has_content(driver):
                    return True

                logger.warning(f"[Page] {attempt + 1}-urinish: kontent yo'q")
                time.sleep(5)

            except Exception as e:
                logger.error(f"[Page] {attempt + 1}-urinishda xato: {e}")
                time.sleep(5)

        return False

    def _page_has_content(self, driver) -> bool:
        """Sahifada kontent borligini tekshirish"""
        try:
            rows = driver.find_elements(By.CSS_SELECTOR, "tr.Table_row__329lz")
            if rows:
                return True

            cards = driver.find_elements(By.CSS_SELECTOR, ".RegistryPage_tableMobileWrapper__3oxDb")
            if cards:
                return True

            return False
        except:
            return False

    def _get_api_response(self, expected_page: int, timeout: int = 30) -> Optional[Dict]:
        """API response ni olish"""
        logger.info(f"[API] Response kutilmoqda (page={expected_page})...")
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                logs = self.driver.get_log("performance")
            except:
                time.sleep(0.5)
                continue

            for log in logs:
                try:
                    msg = json.loads(log["message"])["message"]

                    if msg.get("method") != "Network.responseReceived":
                        continue

                    url = msg["params"]["response"]["url"]

                    if API_TARGET not in url:
                        continue

                    status = msg["params"]["response"]["status"]
                    request_id = msg["params"]["requestId"]

                    if status != 200:
                        continue

                    result = self.driver.execute_cdp_cmd(
                        "Network.getResponseBody",
                        {"requestId": request_id}
                    )
                    body = result.get("body", "")
                    if not body:
                        continue

                    data = json.loads(body)
                    current_page = data.get("data", {}).get("currentPage", -1)

                    if current_page != expected_page:
                        continue

                    logger.info(f"[API] ✅ Response ushlandi: page={current_page}")
                    return data

                except Exception:
                    continue

            time.sleep(0.5)

        logger.warning("[API] Timeout - response kelmadi")
        return None

    def _parse_api_response(self, data: Dict) -> List[Certificate]:
        """API response dan parse qilish"""
        certificates = []
        certs_data = data.get("data", {}).get("certificates", [])

        for cert in certs_data:
            specializations = cert.get("specializations", [])
            spec_name = ""
            if specializations:
                spec = specializations[0]
                spec_name = spec.get("name", {}).get("oz", "") or spec.get("name", {}).get("uz", "")

            status_obj = cert.get("status", {})
            status_title = status_obj.get("title", {})
            status_text = status_title.get("oz", "") or status_title.get("uz", "")

            uuid = cert.get("uuid", "")
            pdf_url = f"https://doc.licenses.uz/v1/certificate/uuid/{uuid}/pdf?language=uz" if uuid else ""

            parsed = Certificate(
                number=str(cert.get("number", "")),
                tin=str(cert.get("tin", "")),
                name=cert.get("name", ""),
                specialization_oz=spec_name,
                uuid=uuid,
                active=cert.get("active", False),
                status=status_text,
                issue_date=cert.get("registration_date", ""),
                expiry_date=cert.get("expiry_date", ""),
                address=cert.get("address", ""),
                document_id=str(cert.get("document_id", "")),
                pdf_url=pdf_url
            )
            certificates.append(parsed)

        return certificates

    def _parse_html_desktop(self) -> List[Certificate]:
        """HTML dan parsing (desktop)"""
        results = []
        try:
            rows = self.driver.find_elements(
                By.CSS_SELECTOR,
                "table.Table_table__2OuB7 tbody.Table_body__3kRrD tr.Table_row__329lz"
            )

            for row in rows:
                try:
                    tds = row.find_elements(By.CSS_SELECTOR, "td.Table_cell__2s5cE")
                    if len(tds) < 6:
                        continue

                    title_cell = tds[0]
                    title_el = title_cell.find_element(By.CSS_SELECTOR, ".Table_titleCellValue__2Wjmv")
                    specialization_text = title_el.text.strip()

                    org_cell = tds[1]
                    org_wrapper = org_cell.find_element(By.CSS_SELECTOR, ".RegistryPage_cellTitle__1__HN")
                    tin_span = org_wrapper.find_element(By.TAG_NAME, "span")
                    tin_text = tin_span.text.strip()
                    name_text = org_wrapper.text.replace(tin_text, "").strip().strip('" ')

                    number_text = tds[2].text.strip()

                    active = bool(
                        tds[5].find_elements(
                            By.CSS_SELECTOR,
                            ".IconLabel_wrapper--success__iBPoQ, .Status_wrapper--success__3eEIw",
                        )
                    )

                    cert = Certificate(
                        number=number_text,
                        tin=tin_text,
                        name=name_text,
                        specialization_oz=specialization_text,
                        active=active
                    )
                    results.append(cert)
                except Exception as e:
                    logger.debug(f"[HTML] Row parse xato: {e}")
                    continue

        except Exception as e:
            logger.error(f"[HTML] Parsing xato: {e}")

        return results

    def fetch_page(self, page_num: int) -> Optional[Dict]:
        """Sahifadan ma'lumot olish"""
        # Warmup
        if not self._warmup_done:
            self.warmup()

        # Sahifani ochish
        if not self._open_page(page_num):
            logger.error(f"[Fetch] Sahifa ochilmadi: {page_num}")
            return None

        # API response
        api_data = self._get_api_response(page_num, timeout=25)

        if api_data:
            certs = self._parse_api_response(api_data)
            if certs:
                total_pages = api_data.get("data", {}).get("totalPages", 0)
                logger.info(f"[Fetch] ✅ API dan {len(certs)} ta olingan (page {page_num + 1}/{total_pages})")
                return {
                    "current_page": page_num,
                    "all_pages": total_pages,
                    "certificates": certs,
                    "source": "api"
                }

        # HTML fallback
        logger.info("[Fetch] API ishlamadi, HTML parsing...")
        html_certs = self._parse_html_desktop()

        if html_certs:
            logger.info(f"[Fetch] ✅ HTML dan {len(html_certs)} ta olingan")
            return {
                "current_page": page_num,
                "all_pages": 0,
                "certificates": html_certs,
                "source": "html"
            }

        logger.error("[Fetch] Hech narsa topilmadi")
        return None

    def close(self):
        """Brauzerni yopish"""
        self._quit_driver()


# ── Test Function ─────────────────────────────────────────────────────────────
def test_parser():
    """Parser ni test qilish"""
    print("=" * 70)
    print("  LICENSE.GOV.UZ PARSER TEST")
    print("=" * 70)
    print()

    # Chrome o'rnatilganligini tekshirish
    import shutil
    chrome_found = shutil.which("google-chrome") or shutil.which("chromium-browser") or shutil.which("chromium")
    if not chrome_found:
        print("[XATO] Chrome topilmadi!")
        print("       O'rnatish: sudo apt install google-chrome-stable")
        return
    print(f"[OK] Chrome: {chrome_found}")
    print()

    parser = LicenseParser()

    try:
        # Warmup
        print("[1] YouTube warmup...")
        parser.warmup()
        print("[OK] Warmup tayyor")
        print()

        # Birinchi sahifani olish
        print("[2] Birinchi sahifa olinmoqda...")
        result = parser.fetch_page(0)

        if result:
            certs = result["certificates"]
            source = result["source"]
            total_pages = result["all_pages"]

            print(f"[OK] Sahifa olingan! (source: {source})")
            print(f"     Jami sahifalar: {total_pages or '?'}")
            print(f"     Sertifikatlar: {len(certs)}")
            print()

            # Natijalarni chiqarish
            print("-" * 70)
            print("  NATIJALAR:")
            print("-" * 70)

            for i, cert in enumerate(certs[:5], 1):  # Faqat 5 tasini ko'rsatish
                print(f"\n  [{i}] Sertifikat:")
                print(f"      📋 Raqam: {cert.number}")
                print(f"      🏢 Tashkilot: {cert.name}")
                print(f"      🔢 STIR: {cert.tin}")
                print(f"      📚 Yo'nalish: {cert.specialization_oz[:80]}...")
                print(f"      ✅ Faol: {'Ha' if cert.active else 'Yo\'q'}")
                if cert.uuid:
                    print(f"      🔗 UUID: {cert.uuid}")

            if len(certs) > 5:
                print(f"\n  ... va yana {len(certs) - 5} ta")

            print()
            print("-" * 70)
            print(f"  JAMI: {len(certs)} ta sertifikat olindi")
            print("-" * 70)

        else:
            print("[XATO] Sahifa olinmadi!")
            print("       Sabablar:")
            print("       - Anti-bot himoya")
            print("       - Internet muammosi")
            print("       - Sayt vaqtinchalik ishlamayapti")

    except KeyboardInterrupt:
        print("\n[Test] To'xtatildi")
    except Exception as e:
        print(f"\n[XATO] {e}")
        import traceback
        traceback.print_exc()
    finally:
        print()
        print("[3] Brauzer yopilmoqda...")
        parser.close()
        print("[OK] Brauzer yopildi")

    print()
    print("=" * 70)
    print("  TEST YAKUNLANDI")
    print("=" * 70)


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Environment sozlamalari
    os.environ.setdefault("CHROME_HEADLESS", "false")  # Test uchun GUI ko'rsatish

    test_parser()