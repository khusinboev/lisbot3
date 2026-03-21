"""
src/parser_v4.py — Camoufox + Playwright response interception
undetected_chromedriver o'rniga: Firefox + C++ level fingerprint + virtual display

O'rnatish:
    pip install camoufox[geoip] playwright
    python -m camoufox fetch

bot.py da:
    from parser_v4 import LicenseParserV4 as LicenseParser, PageFetchError
"""
import asyncio
import base64
import json
import os
import random
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
import inspect
from urllib.parse import quote_plus

from loguru import logger

try:
    from camoufox.async_api import AsyncCamoufox
except ImportError:
    raise ImportError("pip install camoufox[geoip] && python -m camoufox fetch")

from settings import BASE_URL, DOC_URL, TARGET_ACTIVITY_TYPE
from database import Certificate


# ── Constants ─────────────────────────────────────────────────────────────────

API_TARGET = "api.licenses.uz/v1/register/open_source"
REGISTRY_BY_NUMBER_URL = "https://license.gov.uz/registry?filter%5Bnumber%5D={number}"

REGISTRY_URL = (
    f"{BASE_URL}/registry"
    "?filter%5Bdocument_id%5D=4409"
    "&filter%5Bdocument_type%5D=LICENSE"
    "&page={page_1indexed}"
)

# Screenshot papkasi
_SRC_DIR = Path(__file__).parent
SCREENSHOT_DIR = _SRC_DIR.parent / "data" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


# ── Env helpers ───────────────────────────────────────────────────────────────

def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


# ── API item → Certificate ────────────────────────────────────────────────────

def _api_item_to_cert(item: Dict[str, Any]) -> Certificate:
    region     = (item.get("region")    or {}).get("uz", "")
    sub_region = (item.get("subRegion") or {}).get("uz", "")

    act_addrs    = item.get("activity_addresses") or []
    act_addrs_uz = [
        (a.get("value") or {}).get("uz", "")
        for a in act_addrs if a.get("value")
    ]

    specs      = item.get("specializations") or []
    spec_names = [
        (s.get("name") or {}).get("uz", "") or (s.get("name") or {}).get("oz", "")
        for s in specs if s.get("name")
    ]

    status_str  = (item.get("status") or {}).get("status", "")
    is_filtered = any(_activity_text_matches(TARGET_ACTIVITY_TYPE, s) for s in spec_names)

    return Certificate(
        uuid               = item.get("uuid"),
        register_id        = item.get("register_id"),
        application_id     = item.get("application_id"),
        document_id        = item.get("document_id"),
        number             = str(item.get("number") or ""),
        register_number    = item.get("register_number"),
        name               = item.get("name"),
        tin                = str(item.get("tin") or ""),
        pin                = item.get("pin"),
        region_uz          = region,
        sub_region_uz      = sub_region,
        address            = item.get("address"),
        activity_addresses = json.dumps(act_addrs_uz, ensure_ascii=False) if act_addrs_uz else None,
        registration_date  = item.get("registration_date"),
        expiry_date        = item.get("expiry_date"),
        revoke_date        = item.get("revoke_date"),
        status             = status_str,
        active             = bool(item.get("active", True)),
        specializations    = json.dumps(spec_names, ensure_ascii=False) if spec_names else None,
        specialization_ids = item.get("specialization_ids"),
        is_filtered        = is_filtered,
    )


def _normalize_number(value: Any) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    try:
        return str(int(raw))
    except (TypeError, ValueError):
        return raw


_CYR_TO_LAT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "x", "ц": "s", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "",
    "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "қ": "q", "ғ": "g", "ў": "o", "ҳ": "h",
})


def _normalize_activity_text(text: Any) -> str:
    value = str(text or "").strip().lower()
    if not value:
        return ""

    for ch in ("’", "`", "ʻ", "ʼ", "ʹ", "´", "‘"):
        value = value.replace(ch, "'")

    value = value.translate(_CYR_TO_LAT)
    return "".join(ch for ch in value if ch.isalnum())


def _activity_text_matches(target: str, candidate: str) -> bool:
    t = _normalize_activity_text(target)
    c = _normalize_activity_text(candidate)
    if not t or not c:
        return False
    return t in c or c in t


# ── Custom exception ──────────────────────────────────────────────────────────

class PageFetchError(Exception):
    """API dan ma'lumot olinmadi + screenshot mavjud."""
    def __init__(self, message: str, screenshot_path: Optional[str] = None):
        super().__init__(message)
        self.screenshot_path = screenshot_path


# ── Main parser ───────────────────────────────────────────────────────────────

class LicenseParserV4:
    """
    Camoufox async parser.
    bot.py bilan to'liq mos interfeys: init_browser, close, scrape_all,
    fetch_new_since, download_pdf, take_screenshot.
    """

    def __init__(self):
        self._camoufox: Optional[AsyncCamoufox] = None
        self._browser  = None
        self._context  = None
        self._page     = None

        # Kelgan API response larni saqlash uchun queue
        # handle_response → _response_queue → fetch_page polling
        self._response_queue: asyncio.Queue = asyncio.Queue()

    # ── Browser lifecycle ─────────────────────────────────────────────────────

    async def init_browser(self, headless: bool = True):
        # Linux VPS da har doim virtual, Windows da headful
        cf_headless = "virtual" if os.name != "nt" else False

        logger.info(f"Camoufox ishga tushmoqda (headless={cf_headless!r})...")

        self._camoufox = AsyncCamoufox(
            headless=cf_headless,
            geoip=True,
            humanize=True,
            os="windows",
            window=(1280, 900),
        )
        self._browser = await self._camoufox.__aenter__()
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()

        self._page.on("response", self._handle_response)

        logger.info("Camoufox tayyor ✅")

    async def close(self):
        """Brauzerni yopish."""
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._camoufox:
                await self._camoufox.__aexit__(None, None, None)
        except Exception:
            pass
        self._browser  = None
        self._context  = None
        self._page     = None
        self._camoufox = None
        logger.info("Camoufox yopildi")

    # ── Response interception ─────────────────────────────────────────────────

    async def _handle_response(self, response):
        """
        Playwright response event. API ga mos kelsa → queue ga qo'shadi.
        Turnstile / CDN / stat / search calllar o'tkaziladi.
        """
        try:
            url = response.url
            if API_TARGET not in url:
                return
            if "stat" in url or "search" in url:
                return
            if response.status != 200:
                return

            data = await response.json()
            inner = data.get("data") or {}

            # Faqat certificatesli responselar kerak
            if "certificates" not in inner:
                return

            current_page = inner.get("currentPage", -1)
            items        = len(inner.get("certificates") or [])
            logger.debug(f"API response ushlandi: page={current_page}, items={items}")

            await self._response_queue.put(data)

        except Exception as e:
            logger.debug(f"_handle_response xato (o'tkazildi): {e}")

    # ── Screenshot ────────────────────────────────────────────────────────────

    async def take_screenshot(self, label: str = "debug") -> Optional[str]:
        if not self._page:
            return None
        try:
            ts       = int(time.time())
            path     = str(SCREENSHOT_DIR / f"{label}_{ts}.png")
            await self._page.screenshot(path=path, full_page=False)
            logger.info(f"Screenshot: {path}")
            return path
        except Exception as e:
            logger.error(f"Screenshot xato: {e}")
            return None

    # ── Page fetch ────────────────────────────────────────────────────────────

    async def _open_page(self, page_0indexed: int) -> bool:
        url = REGISTRY_URL.format(page_1indexed=page_0indexed + 1)
        logger.info(f"URL: {url}")
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            return True
        except Exception as e:
            logger.warning(f"goto xato: {e}")
            return False

    async def _drain_old_responses(self):
        """Eski / stale responselarni queue dan tozalash."""
        drained = 0
        while not self._response_queue.empty():
            try:
                self._response_queue.get_nowait()
                drained += 1
            except asyncio.QueueEmpty:
                break
        if drained:
            logger.debug(f"Queue tozalandi: {drained} ta eski response")

    async def _wait_for_api(self, expected_page_0indexed: int, timeout: float = 35.0) -> Optional[Dict]:
        """
        Queue dan kutilgan page response ni olish.
        Boshqa page response kelsa — o'tkazib yuboriladi.
        """
        deadline = asyncio.get_event_loop().time() + timeout

        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            try:
                data = await asyncio.wait_for(
                    self._response_queue.get(), timeout=min(2.0, remaining)
                )
            except asyncio.TimeoutError:
                continue

            inner        = data.get("data") or {}
            current_page = inner.get("currentPage", -1)

            if current_page == expected_page_0indexed:
                logger.info(
                    f"API: page={current_page}, "
                    f"items={len(inner.get('certificates') or [])}, "
                    f"totalPages={inner.get('totalPages')}"
                )
                return data

            # Boshqa page — queue ga qayta qo'ymaymiz (stale)
            logger.debug(f"Stale response: expected={expected_page_0indexed}, got={current_page}")

        logger.warning(f"API timeout (expected page={expected_page_0indexed}, {timeout}s)")
        return None

    async def fetch_page(self, page_0indexed: int) -> Optional[Dict]:
        """
        Bitta sahifani ochib API response qaytaradi.
        3 urinish. Muvaffaqiyatsiz bo'lsa → PageFetchError (screenshot bilan).
        """
        MAX_RETRIES = 3

        for attempt in range(MAX_RETRIES):
            logger.info(f"fetch_page({page_0indexed}) — {attempt + 1}/{MAX_RETRIES}")

            # Eski responselarni tozala
            await self._drain_old_responses()

            if not await self._open_page(page_0indexed):
                logger.warning("Sahifa ochilmadi")
                await asyncio.sleep(random.uniform(5.0, 8.0))
                continue

            raw = await self._wait_for_api(page_0indexed, timeout=35.0)

            if raw is None:
                logger.warning("API response kelmadi — refresh...")
                try:
                    await self._page.reload(wait_until="domcontentloaded", timeout=30_000)
                    await asyncio.sleep(random.uniform(2.0, 4.0))
                except Exception:
                    pass
                raw = await self._wait_for_api(page_0indexed, timeout=25.0)

            if raw:
                return raw

            logger.warning(f"{attempt + 1}-urinish muvaffaqiyatsiz")
            await asyncio.sleep(random.uniform(5.0, 10.0))

        # Barcha urinish tugadi
        screenshot_path = await self.take_screenshot(label=f"fail_page{page_0indexed}")
        raise PageFetchError(
            f"Sahifa {page_0indexed} olinmadi ({MAX_RETRIES} urinish)",
            screenshot_path=screenshot_path,
        )

    # ── Scraping ──────────────────────────────────────────────────────────────

    async def _get_total_pages(self) -> int:
        raw = await self.fetch_page(0)
        inner = raw.get("data") or {}
        total = int(inner.get("totalPages") or 1)
        logger.info(f"totalPages={total}, totalItems={inner.get('totalItems')}")
        return max(1, total)

    def _parse_page(self, raw: Dict) -> List[Certificate]:
        """API JSON → Certificate list."""
        raw_certs = (raw.get("data") or {}).get("certificates") or []
        certs = []
        for item in raw_certs:
            try:
                cert = _api_item_to_cert(item)
                if cert.uuid:
                    certs.append(cert)
            except Exception as e:
                logger.warning(f"item parse xato: {e}")
        return certs

    async def scrape_all(
        self,
        progress_callback: Optional[Callable] = None,
        start_page_1indexed: int = 1,
        continue_on_page_error: bool = False,
        error_callback: Optional[Callable] = None,
        cooldown_every_pages: int = 0,
        cooldown_seconds: float = 0.0,
    ) -> List[Certificate]:
        """
        Barcha sahifalarni ketma-ket o'qiydi.
        progress_callback(page, total, page_certs) — har sahifadan keyin chaqiriladi.
        continue_on_page_error=True bo'lsa, muvaffaqiyatsiz sahifalar skip qilinadi.
        """
        all_certs: List[Certificate] = []

        start_page_0 = max(0, int(start_page_1indexed) - 1)

        # Boshlang'ich sahifa — totalPages ni bilib olish
        raw0 = await self.fetch_page(start_page_0)
        inner = raw0.get("data") or {}
        total_pages = max(1, int(inner.get("totalPages") or 1))

        if start_page_0 >= total_pages:
            logger.warning(
                f"start_page={start_page_1indexed} total_pages={total_pages} dan katta, skip"
            )
            return all_certs

        certs0 = self._parse_page(raw0)
        all_certs.extend(certs0)
        logger.info(
            f"Sahifa {start_page_0}: {len(certs0)} ta (jami {total_pages} sahifa, start={start_page_1indexed})"
        )

        if progress_callback:
            result = progress_callback(start_page_0 + 1, total_pages, certs0)
            if inspect.isawaitable(result):
                await result

        # Qolgan sahifalar
        for page_0 in range(start_page_0 + 1, total_pages):
            try:
                raw = await self.fetch_page(page_0)
            except PageFetchError as e:
                if not continue_on_page_error:
                    raise

                logger.warning(f"Sahifa skip qilindi: page={page_0 + 1}, reason={e}")
                if error_callback:
                    result = error_callback(page_0 + 1, total_pages, e)
                    if inspect.isawaitable(result):
                        await result
                continue

            certs = self._parse_page(raw)
            all_certs.extend(certs)

            filtered_n = sum(1 for c in certs if c.is_filtered)
            logger.info(f"Sahifa {page_0}: {len(certs)} ta ({filtered_n} filtered)")

            if progress_callback:
                result = progress_callback(page_0 + 1, total_pages, certs)
                if inspect.isawaitable(result):
                    await result

            await asyncio.sleep(random.uniform(0.4, 1.0))

            # Saytni haddan ortiq yuklamaslik uchun periodik sovitish pauzasi
            if (
                cooldown_every_pages > 0
                and cooldown_seconds > 0
                and (page_0 + 1) % cooldown_every_pages == 0
                and (page_0 + 1) < total_pages
            ):
                logger.info(
                    f"Cooldown: {page_0 + 1}-sahifadan keyin {cooldown_seconds:.1f}s pauza"
                )
                await asyncio.sleep(cooldown_seconds)

        logger.info(f"scrape_all yakunlandi: jami {len(all_certs)} ta")
        return all_certs

    async def fetch_new_since(
        self,
        existing_numbers: Set[str],
        max_pages: int = 50,
    ) -> List[Certificate]:
        """
        Yangi yozuvlarni olish. Mavjud number topilsa — to'xtatiladi.
        Botda yangilanish tekshiruvi uchun.
        """
        new_certs: List[Certificate] = []

        for page_0 in range(max_pages):
            logger.info(f"fetch_new_since: page {page_0}...")
            raw   = await self.fetch_page(page_0)
            items = (raw.get("data") or {}).get("certificates") or []

            if not items:
                break

            page_has_existing = False
            for item in items:
                normalized = _normalize_number(item.get("number"))
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
                logger.info(f"Mavjud yozuv topildi (page={page_0}) — to'xtatildi")
                break

            await asyncio.sleep(random.uniform(0.5, 1.2))

        logger.info(f"fetch_new_since: {len(new_certs)} ta yangi")
        return new_certs

    async def fetch_by_document_numbers(
        self,
        target_numbers: Set[str],
        max_pages: int = 300,
        progress_callback: Optional[Callable] = None,
        continue_on_page_error: bool = True,
        error_callback: Optional[Callable] = None,
        cooldown_every_pages: int = 0,
        cooldown_seconds: float = 0.0,
    ) -> Dict[str, Certificate]:
        """
        Hujjat raqamlari bo'yicha registry sahifasini ochib tekshiradi.
        Har bir number uchun:
        1) https://license.gov.uz/registry?filter%5Bnumber%5D=<number> ochiladi
        2) Shu sahifadan ketadigan background API response interception qilinadi

        Qaytish formati: {normalized_number: Certificate}
        """
        normalized_targets = {_normalize_number(n) for n in target_numbers if _normalize_number(n)}
        found: Dict[str, Certificate] = {}

        if not normalized_targets:
            return found

        ordered_numbers = sorted(normalized_targets)
        total = len(ordered_numbers)
        for idx, number in enumerate(ordered_numbers, 1):
            registry_url = REGISTRY_BY_NUMBER_URL.format(number=quote_plus(number))
            try:
                await self._drain_old_responses()

                logger.debug(f"Auto-update number lookup: {number} | {registry_url}")
                await self._page.goto(registry_url, wait_until="domcontentloaded", timeout=60_000)

                payload = await self._wait_for_registry_number_api(number, timeout=25.0)
                items = (payload.get("data") or {}).get("certificates") or []

                chosen: Optional[Dict[str, Any]] = None
                for item in items:
                    if _normalize_number(item.get("number")) == number:
                        chosen = item
                        break
                if not chosen and items:
                    chosen = items[0]

                if chosen:
                    cert = _api_item_to_cert(chosen)
                    if cert.uuid:
                        found[number] = cert

            except Exception as e:
                if not continue_on_page_error:
                    raise
                logger.warning(f"fetch_by_document_numbers number={number} xato: {e}")
                if error_callback:
                    result = error_callback(idx, total, e)
                    if inspect.isawaitable(result):
                        await result

            if progress_callback:
                result = progress_callback(idx, total, len(found), len(normalized_targets))
                if inspect.isawaitable(result):
                    await result

            await asyncio.sleep(random.uniform(0.25, 0.6))
            if (
                cooldown_every_pages > 0
                and cooldown_seconds > 0
                and idx % cooldown_every_pages == 0
                and idx < total
            ):
                await asyncio.sleep(cooldown_seconds)

        logger.info(
            f"fetch_by_document_numbers yakunlandi: found={len(found)}/{len(normalized_targets)}"
        )
        return found

    async def _wait_for_registry_number_api(self, expected_number: str, timeout: float = 25.0) -> Dict[str, Any]:
        """
        Registry sahifasidan ketgan API response ni queue dan topadi.
        expected_number ga mos certificates response kelmaguncha kutadi.
        """
        expected = _normalize_number(expected_number)
        deadline = asyncio.get_event_loop().time() + timeout

        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            try:
                payload = await asyncio.wait_for(
                    self._response_queue.get(), timeout=min(2.0, remaining)
                )
            except asyncio.TimeoutError:
                continue

            items = (payload.get("data") or {}).get("certificates") or []
            if not items:
                continue

            for item in items:
                if _normalize_number(item.get("number")) == expected:
                    return payload

        raise TimeoutError(f"Registry background API timeout, number={expected}")

    # ── PDF yuklash ───────────────────────────────────────────────────────────

    async def download_pdf(self, uuid: str, output_path: str) -> bool:
        """
        PDF ni brauzer orqali fetch qilib saqlaydi.
        Brauzer sessiyasi va cookielari ishlatiladi — Cloudflare bypass avtomatik.
        """
        try:
            pdf_url = f"{DOC_URL}/certificate/uuid/{uuid}/pdf?language=uz"

            content_b64: Optional[str] = await self._page.evaluate("""
                async (url) => {
                    try {
                        const res = await fetch(url);
                        if (!res.ok) return null;
                        const buf = await res.arrayBuffer();
                        const bytes = new Uint8Array(buf);
                        let binary = '';
                        for (let i = 0; i < bytes.length; i++) {
                            binary += String.fromCharCode(bytes[i]);
                        }
                        return btoa(binary);
                    } catch (e) {
                        return null;
                    }
                }
            """, pdf_url)

            if content_b64:
                Path(output_path).write_bytes(base64.b64decode(content_b64))
                logger.info(f"PDF saqlandi: {output_path}")
                return True

            logger.warning(f"PDF bo'sh keldi: {uuid}")
            return False

        except Exception as e:
            logger.error(f"download_pdf xato: {e}")
            return False

    # ── Stub (bot.py bilan mos) ───────────────────────────────────────────────

    async def get_certificate_details(self, document_id: str):
        return None
