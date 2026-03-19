"""
src/parser_v3.py
kochirish.py yondashuvi asosida: undetected_chromedriver + goog:loggingPrefs.
SeleniumBase ishlatilmaydi — performance log uchun uc.Chrome to'g'ridan ishlatiladi.

O'rnatish: pip install undetected-chromedriver selenium
bot.py da: from parser_v3 import LicenseParserV3 as LicenseParser
"""
import asyncio
import os
import time
import random
import json
import base64
from typing import List, Optional, Callable, Dict, Any, Set
from concurrent.futures import ThreadPoolExecutor
import inspect

from loguru import logger

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    raise ImportError("pip install undetected-chromedriver selenium")

from settings import BASE_URL, DOC_URL, TARGET_ACTIVITY_TYPE
from database import Certificate


# ── Constants ─────────────────────────────────────────────────────────────────

API_TARGET = "api.licenses.uz/v1/register/open_source"

REGISTRY_URL = (
    f"{BASE_URL}/registry"
    "?filter%5Bdocument_id%5D=4409"
    "&filter%5Bdocument_type%5D=LICENSE"
    "&page={page_1indexed}"
)


# ── Env helpers ───────────────────────────────────────────────────────────────

def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str) -> Optional[int]:
    raw = os.getenv(name)
    if not raw or not raw.strip():
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _human_delay(a: float = 0.8, b: float = 2.0):
    time.sleep(random.uniform(a, b))


# ── API item → Certificate ────────────────────────────────────────────────────

def _api_item_to_cert(item: Dict[str, Any]) -> Certificate:
    region     = (item.get("region")    or {}).get("uz", "")
    sub_region = (item.get("subRegion") or {}).get("uz", "")

    act_addrs     = item.get("activity_addresses") or []
    act_addrs_uz  = [
        (a.get("value") or {}).get("uz", "")
        for a in act_addrs if a.get("value")
    ]

    specs      = item.get("specializations") or []
    spec_names = [
        (s.get("name") or {}).get("uz", "") or (s.get("name") or {}).get("oz", "")
        for s in specs if s.get("name")
    ]

    status_str  = (item.get("status") or {}).get("status", "")
    is_filtered = any(TARGET_ACTIVITY_TYPE.lower() in s.lower() for s in spec_names)

    return Certificate(
        uuid              = item.get("uuid"),
        register_id       = item.get("register_id"),
        application_id    = item.get("application_id"),
        document_id       = item.get("document_id"),
        number            = str(item.get("number") or ""),
        register_number   = item.get("register_number"),
        name              = item.get("name"),
        tin               = str(item.get("tin") or ""),
        pin               = item.get("pin"),
        region_uz         = region,
        sub_region_uz     = sub_region,
        address           = item.get("address"),
        activity_addresses= json.dumps(act_addrs_uz, ensure_ascii=False) if act_addrs_uz else None,
        registration_date = item.get("registration_date"),
        expiry_date       = item.get("expiry_date"),
        revoke_date       = item.get("revoke_date"),
        status            = status_str,
        active            = bool(item.get("active", True)),
        specializations   = json.dumps(spec_names, ensure_ascii=False) if spec_names else None,
        specialization_ids= item.get("specialization_ids"),
        is_filtered       = is_filtered,
    )


# ── Sync worker (kochirish.py yondashuvi) ────────────────────────────────────

class _SyncWorker:

    def __init__(self, headless: bool = True):
        self.headless     = headless
        self.driver       = None
        self._warmup_done = False

        # Parser uchun ALOHIDA profil — mavjud Chrome bilan to'qnashmasin.
        # PARSER_V2_PROFILE_DIR / CHROME_PROFILE_DIR ni ishlatmaymiz:
        # ular odatda asosiy Chrome profiliga ishora qiladi va
        # Windows da "Chrome allaqachon ishlamoqda" dialog chiqaradi.
        src_dir = os.path.dirname(os.path.abspath(__file__))
        self._profile_dir = os.path.abspath(
            os.path.join(src_dir, "..", "data", "chrome_profile_parser_v3")
        )
        os.makedirs(self._profile_dir, exist_ok=True)

    # ── Driver ────────────────────────────────────────────────────────────────

    def _init_driver(self):
        options = uc.ChromeOptions()
        options.add_argument(f"--user-data-dir={self._profile_dir}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-notifications")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1280,900")

        if self.headless:
            options.add_argument("--headless=new")

        # Performance log — CDP response body ushlash uchun SHART
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        version_main = _env_int("CHROME_VERSION_MAIN")
        driver = (
            uc.Chrome(version_main=version_main, options=options)
            if version_main
            else uc.Chrome(options=options)
        )
        driver.set_page_load_timeout(120)
        logger.info(f"uc.Chrome ishga tushdi (headless={self.headless}, profile={self._profile_dir})")
        return driver

    def _is_alive(self) -> bool:
        try:
            _ = self.driver.current_url
            _ = self.driver.window_handles
            return True
        except Exception:
            return False

    def start(self):
        self.driver = self._init_driver()

    def stop(self):
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
        self.driver = None
        self._warmup_done = False
        logger.info("Driver yopildi")

    def _ensure_driver(self):
        if not self._is_alive():
            logger.warning("Driver o'lgan — qayta ishga tushirilmoqda")
            self.driver = self._init_driver()
            self._warmup_done = False

    # ── YouTube warmup (kochirish.py dan aynan) ───────────────────────────────

    def _youtube_warmup(self):
        if self._warmup_done or _env_bool("SKIP_WARMUP", default=False):
            return
        logger.info("YouTube warmup...")
        try:
            wait = WebDriverWait(self.driver, 30)
            self.driver.get("https://www.youtube.com")
            wait.until(lambda d: d.execute_script("return document.readyState") == "complete")

            try:
                box = wait.until(EC.presence_of_element_located((By.NAME, "search_query")))
                box.click()
                _human_delay(0.5, 1.0)
                for ch in "python tutorial":
                    box.send_keys(ch)
                    time.sleep(random.uniform(0.04, 0.12))
                box.send_keys(Keys.ENTER)
                wait.until(EC.presence_of_element_located((By.ID, "contents")))
                _human_delay(1.5, 2.5)
            except Exception:
                _human_delay(1.0, 2.0)

            self._warmup_done = True
            logger.info("YouTube warmup tugadi")
        except Exception as e:
            logger.warning(f"YouTube warmup xato (davom etiladi): {e}")

    # ── Page open (kochirish.py dan aynan) ───────────────────────────────────

    def _open_page(self, page_0indexed: int) -> bool:
        """page_0indexed: 0-based. URL da &page= 1-based."""
        url  = REGISTRY_URL.format(page_1indexed=page_0indexed + 1)
        wait = WebDriverWait(self.driver, 60)
        logger.info(f"URL ochilmoqda: {url}")

        for attempt in range(3):
            try:
                self.driver.get(url)
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
                _human_delay(1.2, 2.0)
                return True
            except Exception as e:
                logger.warning(f"_open_page xato ({attempt + 1}/3): {e}")
                _human_delay(3.0, 5.0)
        return False

    # ── CDP response ushlash (kochirish.py dan aynan) ─────────────────────────

    def _get_api_response(self, expected_page_0indexed: int, timeout: int = 40) -> Optional[Dict]:
        """CDP performance log dan API response body ni olamiz."""
        logger.debug(f"API response kutilmoqda (currentPage={expected_page_0indexed})...")
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                logs = self.driver.get_log("performance")
            except Exception:
                time.sleep(1.0)
                continue

            for entry in logs:
                try:
                    msg = json.loads(entry["message"])["message"]

                    if msg["method"] != "Network.responseReceived":
                        continue

                    url = msg["params"]["response"]["url"]

                    if API_TARGET not in url:
                        continue
                    if "stat" in url or "search" in url:
                        continue

                    status     = msg["params"]["response"]["status"]
                    request_id = msg["params"]["requestId"]

                    if status != 200:
                        logger.debug(f"API {status} qaytardi — o'tkazildi")
                        continue

                    result = self.driver.execute_cdp_cmd(
                        "Network.getResponseBody", {"requestId": request_id}
                    )
                    body = result.get("body", "")
                    if not body:
                        continue

                    if result.get("base64Encoded"):
                        body = base64.b64decode(body).decode("utf-8")

                    data         = json.loads(body)
                    inner        = data.get("data", {})
                    current_page = inner.get("currentPage", -1)

                    if current_page != expected_page_0indexed:
                        logger.debug(
                            f"Page mismatch: kutilgan={expected_page_0indexed}, "
                            f"keldi={current_page} — o'tkazildi"
                        )
                        continue

                    logger.info(
                        f"API ushlandi: currentPage={current_page}, "
                        f"items={len(inner.get('certificates', []))}, "
                        f"totalPages={inner.get('totalPages')}"
                    )
                    return data

                except Exception:
                    continue

            time.sleep(0.5)

        logger.warning(f"API response kelmadi (currentPage={expected_page_0indexed}, timeout={timeout}s)")
        return None

    # ── fetch_page (kochirish.py dan aynan) ──────────────────────────────────

    def fetch_page(self, page_0indexed: int) -> Optional[Dict]:
        self._ensure_driver()

        # Birinchi chaqiruvda warmup
        current_url = self.driver.current_url
        if "youtube" not in current_url and "license" not in current_url and "about" not in current_url:
            self._youtube_warmup()

        MAX_RETRIES = 3
        for attempt in range(MAX_RETRIES):
            logger.info(f"fetch_page({page_0indexed}) — urinish {attempt + 1}/{MAX_RETRIES}")

            if not self._open_page(page_0indexed):
                logger.warning("Sahifa ochilmadi — retry")
                _human_delay(5.0, 8.0)
                continue

            raw = self._get_api_response(page_0indexed, timeout=40)

            if raw is None:
                logger.warning("API response kelmadi — refresh...")
                try:
                    self.driver.refresh()
                    _human_delay(4.0, 6.0)
                except Exception:
                    pass
                raw = self._get_api_response(page_0indexed, timeout=30)

            if raw is None:
                logger.warning(f"{attempt + 1}-urinishda ham olinmadi")
                _human_delay(5.0, 10.0)
                continue

            return raw

        logger.error(f"fetch_page({page_0indexed}): {MAX_RETRIES} urinishdan keyin ham olinmadi")
        return None

    # ── Scraping ──────────────────────────────────────────────────────────────

    def get_total_pages(self) -> int:
        raw = self.fetch_page(0)
        if not raw:
            return 1
        inner = raw.get("data", {})
        total = int(inner.get("totalPages", 1))
        logger.info(f"totalPages={total}, totalItems={inner.get('totalItems')}")
        return max(1, total)

    def scrape_page(self, page_0indexed: int) -> List[Certificate]:
        raw = self.fetch_page(page_0indexed)
        if not raw:
            return []

        raw_certs = raw.get("data", {}).get("certificates") or []
        certs = []
        for item in raw_certs:
            try:
                cert = _api_item_to_cert(item)
                if cert.uuid:
                    certs.append(cert)
            except Exception as e:
                logger.warning(f"item parse xato: {e}")

        filtered_n = sum(1 for c in certs if c.is_filtered)
        logger.info(f"Sahifa {page_0indexed}: {len(certs)} ta ({filtered_n} ta filtered)")
        return certs

    def fetch_new_since(self, existing_numbers: Set[str], max_pages: int = 50) -> List[Certificate]:
        """Bazada yo'q yangi sertifikatlarni oladi (kochirish.py dan)."""
        new_certs: List[Certificate] = []
        page = 0

        while page < max_pages:
            logger.info(f"fetch_new_since: page {page} yuklanmoqda...")
            raw = self.fetch_page(page)
            if not raw:
                break

            items = raw.get("data", {}).get("certificates") or []
            if not items:
                break

            page_has_existing = False
            for item in items:
                number = item.get("number")
                if number is None:
                    continue
                try:
                    normalized = str(int(str(number).strip()))
                except (TypeError, ValueError):
                    normalized = str(number).strip()
                if not normalized:
                    continue

                if normalized in existing_numbers:
                    page_has_existing = True
                    continue

                try:
                    cert = _api_item_to_cert(item)
                    if cert.uuid:
                        new_certs.append(cert)
                except Exception as e:
                    logger.warning(f"item parse xato: {e}")

            if page_has_existing:
                logger.info(f"fetch_new_since: mavjud yozuv topildi, to'xtatildi (page={page})")
                break

            page += 1
            _human_delay(0.5, 1.2)

        logger.info(f"fetch_new_since: {len(new_certs)} ta yangi yozuv")
        return new_certs

    def download_pdf(self, uuid: str, output_path: str) -> bool:
        try:
            pdf_url = f"{DOC_URL}/certificate/uuid/{uuid}/pdf?language=uz"
            content = self.driver.execute_async_script("""
                const done = arguments[arguments.length - 1];
                fetch(arguments[0])
                    .then(r => r.arrayBuffer())
                    .then(buf => {
                        const b = new Uint8Array(buf);
                        let s = '';
                        for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
                        done(btoa(s));
                    })
                    .catch(() => done(null));
            """, pdf_url)

            if content:
                with open(output_path, 'wb') as f:
                    f.write(base64.b64decode(content))
                logger.info(f"PDF saqlandi: {output_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"download_pdf xato: {e}")
            return False


# ── Async wrapper ─────────────────────────────────────────────────────────────

class LicenseParserV3:
    """Async wrapper — bot.py interfeysi bilan to'liq mos."""

    def __init__(self):
        self._worker: Optional[_SyncWorker] = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ucworker")

    async def _run(self, fn, *args):
        return await asyncio.get_event_loop().run_in_executor(self._executor, fn, *args)

    async def init_browser(self, headless: bool = True):
        env = os.getenv("CHROME_HEADLESS")
        if env is not None:
            headless = env.strip().lower() in {"1", "true", "yes", "y", "on"}
        elif os.name == "nt":
            headless = False  # Windows: GUI ko'rsatish

        self._worker = _SyncWorker(headless=headless)
        await self._run(self._worker.start)

    async def close(self):
        if self._worker:
            await self._run(self._worker.stop)
            self._worker = None
        self._executor.shutdown(wait=False)

    async def scrape_all(
        self,
        progress_callback: Optional[Callable] = None,
    ) -> List[Certificate]:
        all_certs: List[Certificate] = []
        try:
            total_pages = await self._run(self._worker.get_total_pages)

            for page_0 in range(0, total_pages):
                certs = await self._run(self._worker.scrape_page, page_0)
                all_certs.extend(certs)

                if progress_callback:
                    result = progress_callback(page_0 + 1, total_pages, len(certs))
                    if inspect.isawaitable(result):
                        await result

                await asyncio.sleep(random.uniform(0.3, 0.8))

            logger.info(f"Jami yig'ildi: {len(all_certs)}")
            return all_certs
        except Exception as e:
            logger.error(f"scrape_all xato: {e}")
            return all_certs

    async def fetch_new_since(self, existing_numbers: Set[str], max_pages: int = 50) -> List[Certificate]:
        return await self._run(self._worker.fetch_new_since, existing_numbers, max_pages)

    async def download_pdf(self, uuid: str, output_path: str) -> bool:
        return await self._run(self._worker.download_pdf, uuid, output_path)

    async def get_certificate_details(self, document_id: str):
        return None