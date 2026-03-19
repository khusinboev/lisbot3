"""
src/parser_v3.py
SeleniumBase UC mode + CDP Network interception.

API endpoint: api.licenses.uz/v1/register/open_source
- page_num: 0-indexed (API currentPage = 0, 1, 2 ...)
- URL da &page= 1-indexed (&page=1 → currentPage=0)

O'rnatish: pip install seleniumbase
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
    from seleniumbase import SB
except ImportError:
    raise ImportError("pip install seleniumbase")

from settings import BASE_URL, DOC_URL, TARGET_ACTIVITY_TYPE
from database import Certificate


# ── Constants ─────────────────────────────────────────────────────────────────

API_TARGET = "api.licenses.uz/v1/register/open_source"
REGISTRY_BASE = (
    f"{BASE_URL}/registry"
    "?filter%5Bdocument_id%5D=4409"
    "&filter%5Bdocument_type%5D=LICENSE"
    "&page={page_1indexed}"
)


# ── API item → Certificate ────────────────────────────────────────────────────

def _api_item_to_cert(item: Dict[str, Any]) -> Certificate:
    region = (item.get("region") or {}).get("uz", "")
    sub_region = (item.get("subRegion") or {}).get("uz", "")

    act_addrs = item.get("activity_addresses") or []
    act_addrs_uz = [
        (a.get("value") or {}).get("uz", "")
        for a in act_addrs if a.get("value")
    ]

    specs = item.get("specializations") or []
    spec_names = [
        (s.get("name") or {}).get("uz", "") or (s.get("name") or {}).get("oz", "")
        for s in specs if s.get("name")
    ]

    status_str = (item.get("status") or {}).get("status", "")

    is_filtered = any(
        TARGET_ACTIVITY_TYPE.lower() in s.lower()
        for s in spec_names
    )

    return Certificate(
        uuid=item.get("uuid"),
        register_id=item.get("register_id"),
        application_id=item.get("application_id"),
        document_id=item.get("document_id"),
        number=str(item.get("number") or ""),
        register_number=item.get("register_number"),
        name=item.get("name"),
        tin=str(item.get("tin") or ""),
        pin=item.get("pin"),
        region_uz=region,
        sub_region_uz=sub_region,
        address=item.get("address"),
        activity_addresses=json.dumps(act_addrs_uz, ensure_ascii=False) if act_addrs_uz else None,
        registration_date=item.get("registration_date"),
        expiry_date=item.get("expiry_date"),
        revoke_date=item.get("revoke_date"),
        status=status_str,
        active=bool(item.get("active", True)),
        specializations=json.dumps(spec_names, ensure_ascii=False) if spec_names else None,
        specialization_ids=item.get("specialization_ids"),
        is_filtered=is_filtered,
    )


# ── Sync worker ───────────────────────────────────────────────────────────────

class _SyncWorker:

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._sb_ctx = None
        self._sb = None

    def start(self):
        is_linux = os.name != "nt"
        self._sb_ctx = SB(
            uc=True,
            headless=self.headless,
            xvfb=is_linux,
            locale_code="uz",
        )
        self._sb = self._sb_ctx.__enter__()
        self._sb.execute_cdp_cmd("Network.enable", {})
        logger.info(f"SeleniumBase UC ishga tushdi (headless={self.headless})")

    def stop(self):
        try:
            if self._sb_ctx:
                self._sb_ctx.__exit__(None, None, None)
        except Exception:
            pass
        self._sb_ctx = None
        self._sb = None
        logger.info("SeleniumBase yopildi")

    def _open_page(self, page_0indexed: int, retries: int = 3) -> bool:
        """
        page_0indexed: 0-based (birinchi sahifa = 0).
        URL da &page= 1-based bo'ladi.
        """
        url = REGISTRY_BASE.format(page_1indexed=page_0indexed + 1)
        logger.info(f"URL ochilmoqda: {url}")

        for attempt in range(1, retries + 1):
            try:
                self._sb.uc_open_with_reconnect(url, reconnect_time=4)
                try:
                    self._sb.uc_gui_click_captcha()
                except Exception:
                    pass
                time.sleep(2)
                return True
            except Exception as e:
                logger.warning(f"_open_page xato ({attempt}/{retries}): {e}")
                time.sleep(random.uniform(2, 4))
        return False

    def _get_api_response(self, expected_page_0indexed: int, timeout: int = 40) -> Optional[Dict]:
        """
        CDP performance logs dan API response body ni olamiz.
        expected_page_0indexed: API currentPage qiymati (0-based).
        """
        logger.debug(f"API response kutilmoqda (currentPage={expected_page_0indexed})...")
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                logs = self._sb.driver.get_log("performance")
            except Exception:
                time.sleep(0.5)
                continue

            for entry in logs:
                try:
                    msg = json.loads(entry["message"])["message"]

                    if msg.get("method") != "Network.responseReceived":
                        continue

                    url = msg["params"]["response"]["url"]

                    # Aniq endpoint ni tekshiramiz
                    if API_TARGET not in url:
                        continue
                    # Stats yoki search endpointlarini o'tkazib yuboramiz
                    if "stat" in url or "search" in url:
                        continue

                    if msg["params"]["response"]["status"] != 200:
                        continue

                    request_id = msg["params"]["requestId"]
                    result = self._sb.execute_cdp_cmd(
                        "Network.getResponseBody", {"requestId": request_id}
                    )
                    body = result.get("body", "")
                    if not body:
                        continue

                    if result.get("base64Encoded"):
                        body = base64.b64decode(body).decode("utf-8")

                    data = json.loads(body)
                    inner = data.get("data", {})

                    if "certificates" not in inner:
                        continue

                    current_page = inner.get("currentPage", -1)
                    if current_page != expected_page_0indexed:
                        logger.debug(
                            f"Page mismatch: kutilgan={expected_page_0indexed}, keldi={current_page} — o'tkazildi"
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

    def fetch_page(self, page_0indexed: int) -> Optional[Dict]:
        """
        Bitta sahifani ochib, raw API data qaytaradi.
        Ichida retry va refresh logikasi bor (kochirish.py dan).
        """
        MAX_RETRIES = 3
        for attempt in range(1, MAX_RETRIES + 1):
            logger.info(f"fetch_page(page={page_0indexed}) — urinish {attempt}/{MAX_RETRIES}")

            if not self._open_page(page_0indexed):
                logger.warning("Sahifa ochilmadi — retry")
                time.sleep(random.uniform(5, 8))
                continue

            raw = self._get_api_response(page_0indexed, timeout=40)

            if raw is None:
                logger.warning("API response kelmadi — refresh...")
                try:
                    self._sb.driver.refresh()
                    time.sleep(random.uniform(4, 6))
                except Exception:
                    pass
                raw = self._get_api_response(page_0indexed, timeout=30)

            if raw is None:
                logger.warning(f"Urinish {attempt} muvaffaqiyatsiz")
                time.sleep(random.uniform(5, 10))
                continue

            return raw

        logger.error(f"fetch_page({page_0indexed}): {MAX_RETRIES} urinishdan keyin ham olinmadi")
        return None

    def get_total_pages(self) -> int:
        raw = self.fetch_page(0)
        if not raw:
            return 1
        total = int(raw.get("data", {}).get("totalPages", 1))
        items = raw.get("data", {}).get("totalItems", "?")
        logger.info(f"totalPages={total}, totalItems={items}")
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
        """
        Bazada mavjud bo'lmagan yangi sertifikatlarni oladi.
        Birinchi sahifadan boshlab, bazada mavjud raqam uchragan sahifada to'xtaydi.
        Botda "Yangilarni tekshirish" uchun.
        """
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
            time.sleep(random.uniform(0.5, 1.2))

        logger.info(f"fetch_new_since: {len(new_certs)} ta yangi yozuv topildi")
        return new_certs

    def download_pdf(self, uuid: str, output_path: str) -> bool:
        try:
            pdf_url = f"{DOC_URL}/certificate/uuid/{uuid}/pdf?language=uz"
            content = self._sb.execute_async_script("""
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
    """Async wrapper — bot.py bilan to'liq mos interfeys."""

    def __init__(self):
        self._worker: Optional[_SyncWorker] = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sbworker")

    async def _run(self, fn, *args):
        return await asyncio.get_event_loop().run_in_executor(self._executor, fn, *args)

    async def init_browser(self, headless: bool = True):
        env = os.getenv("CHROME_HEADLESS")
        if env is not None:
            headless = env.strip().lower() in {"1", "true", "yes", "y", "on"}
        elif os.name == "nt":
            headless = False  # Windows: GUI ko'rsatish (debug)
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

            # get_total_pages ichida page=0 allaqachon ochildi
            # birinchi sahifa natijasini qaytarib olish uchun scrape_page(0) ni chaqiramiz
            # lekin fetch_page(0) qayta so'rov yuborar — shuning uchun
            # get_total_pages o'zida scrape qilib qaytarsa yaxshi bo'lardi,
            # ammo hozir sodda variant: page 0 dan boshamiz
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
        """Bot da yangilarni tekshirish uchun."""
        return await self._run(self._worker.fetch_new_since, existing_numbers, max_pages)

    async def download_pdf(self, uuid: str, output_path: str) -> bool:
        return await self._run(self._worker.download_pdf, uuid, output_path)

    async def get_certificate_details(self, document_id: str):
        return None