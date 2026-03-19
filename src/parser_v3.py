"""
src/parser_v3.py
SeleniumBase UC (Undetected Chrome) mode — Turnstile bypass.

O'rnatish:
    pip install seleniumbase

bot.py da:
    from parser_v3 import LicenseParserV3 as LicenseParser
"""
import asyncio
import os
import random
import json
import base64
from dataclasses import dataclass
from typing import List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor
import inspect

from loguru import logger

try:
    from seleniumbase import SB
except ImportError:
    raise ImportError("seleniumbase o'rnatilmagan: pip install seleniumbase")

from settings import BASE_URL, DOC_URL


@dataclass
class ParsedCertificate:
    document_id: Optional[str] = None
    document_number: Optional[str] = None
    status: Optional[str] = None
    issue_date: Optional[str] = None
    inserted_date: Optional[str] = None
    organization_name: Optional[str] = None
    address: Optional[str] = None
    stir: Optional[str] = None
    expiry_date: Optional[str] = None
    activity_type: Optional[str] = None
    uuid: Optional[str] = None
    pdf_url: Optional[str] = None


_PARSE_JS = r"""
return (function() {
    const results = [];
    const cards = document.querySelectorAll(
        'tr.Table_row__329lz, [class*="tableMobileWrapper"] > *, tr'
    );
    for (const card of cards) {
        const cert = {};
        const text = card.textContent || '';

        for (const a of card.querySelectorAll('a[href]')) {
            const href = a.getAttribute('href') || '';
            const m = href.match(/certificate\/uuid\/([a-f0-9\-]{36})/i);
            if (m) {
                cert.uuid = m[1];
                cert.pdf_url = 'https://doc.licenses.uz/v1/certificate/uuid/' + m[1] + '/pdf?language=uz';
            }
            const dm = href.match(/filter%5Bnumber%5D=(\d+)/);
            if (dm) cert.document_id = dm[1];
        }

        if (!cert.uuid) continue;

        const nm = text.match(/[NNo\u2116]\s*(\d+)/);
        if (nm) cert.document_number = nm[1];

        const sm = text.match(/\b(\d{9})\b/);
        if (sm) cert.stir = sm[1];

        const org = card.querySelector('a, strong, b, [class*="title"]');
        if (org) cert.organization_name = (org.textContent || '').trim().slice(0, 200);

        const dates = text.match(/\d{2}\.\d{2}\.\d{4}/g);
        if (dates) {
            cert.issue_date = dates[0];
            if (dates[1]) cert.expiry_date = dates[1];
        }

        if (text.indexOf('\u041e\u043b\u0438\u0439 \u0442\u0430\u044a\u043b\u0438\u043c') !== -1 ||
            text.indexOf('\u0412\u044b\u0441\u0448\u0435\u0435') !== -1) {
            cert.activity_type = '\u041e\u043b\u0438\u0439 \u0442\u0430\u044a\u043b\u0438\u043c \u0445\u0438\u0437\u043c\u0430\u0442\u043b\u0430\u0440\u0438';
        }

        results.push(cert);
    }
    return JSON.stringify(results);
})()
"""

_TOTAL_PAGES_JS = r"""
return (function() {
    for (const el of document.querySelectorAll('*')) {
        const t = el.textContent || '';
        const m = t.match(/(\d+)\s*(\u0438\u0437|of)\s*(\d+)/);
        if (m) return parseInt(m[3]);
    }
    let max = 1;
    for (const el of document.querySelectorAll('button, a')) {
        const t = (el.textContent || '').trim();
        if (/^\d+$/.test(t)) max = Math.max(max, parseInt(t));
    }
    return max;
})()
"""


class _SyncWorker:
    """SeleniumBase sync driver — thread pool da ishlaydi."""

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

    def _wait_content(self, timeout: int = 25) -> bool:
        """Jadval/karta elementlari paydo bo'lishini kut."""
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                count = self._sb.execute_script(
                    "return document.querySelectorAll('tr, [class*=\"row\"], [class*=\"card\"]').length;"
                )
                if count and int(count) > 3:
                    return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def goto(self, url: str, retries: int = 3) -> bool:
        import time
        for attempt in range(1, retries + 1):
            try:
                # UC mode: Cloudflare ni avtomatik bypass qiladi
                self._sb.uc_open_with_reconnect(url, reconnect_time=4)

                # Turnstile checkbox bo'lsa bosib o'tish
                try:
                    self._sb.uc_gui_click_captcha()
                except Exception:
                    pass

                if self._wait_content():
                    return True

                logger.warning(f"Kontent yo'q (attempt {attempt}/{retries}): {url}")
                time.sleep(random.uniform(2, 4))

            except Exception as e:
                logger.warning(f"goto xato (attempt {attempt}/{retries}): {e}")
                time.sleep(random.uniform(2, 5))

        return False

    def get_total_pages(self) -> int:
        try:
            url = (
                f"{BASE_URL}/registry?filter%5Bdocument_id%5D=4409"
                "&filter%5Bdocument_type%5D=LICENSE&page=1"
            )
            if not self.goto(url):
                return 1

            result = self._sb.execute_script(_TOTAL_PAGES_JS)
            if not result:
                return 1

            val = int(result)
            # val > 100 bo'lsa bu items soni, sahifaga aylantir
            if val > 100:
                return (val + 9) // 10
            return max(1, val)

        except Exception as e:
            logger.error(f"get_total_pages xato: {e}")
            return 1

    def scrape_page(self, page_num: int) -> List[ParsedCertificate]:
        url = (
            f"{BASE_URL}/registry?filter%5Bdocument_id%5D=4409"
            f"&filter%5Bdocument_type%5D=LICENSE&page={page_num}"
        )
        if not self.goto(url):
            return []

        try:
            raw = self._sb.execute_script(_PARSE_JS)
            items = json.loads(raw) if raw else []

            certs = []
            for item in items:
                if not isinstance(item, dict) or not item.get('uuid'):
                    continue
                certs.append(ParsedCertificate(
                    document_id=item.get('document_id'),
                    document_number=item.get('document_number'),
                    stir=item.get('stir'),
                    organization_name=item.get('organization_name'),
                    issue_date=item.get('issue_date'),
                    expiry_date=item.get('expiry_date'),
                    activity_type=item.get('activity_type'),
                    uuid=item['uuid'],
                    pdf_url=item.get('pdf_url'),
                ))

            logger.info(f"Sahifa {page_num}: {len(certs)} ta sertifikat")
            return certs

        except Exception as e:
            logger.error(f"scrape_page {page_num} xato: {e}")
            return []

    def get_certificate_details(self, document_id: str) -> Optional[ParsedCertificate]:
        url = f"{BASE_URL}/registry?filter%5Bnumber%5D={document_id}"
        if not self.goto(url):
            return None

        try:
            data = self._sb.execute_script(r"""
                return (function() {
                    const text = document.body ? document.body.textContent : '';
                    const cert = {};
                    const um = text.match(/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/i);
                    if (um) cert.uuid = um[1];
                    const nm = text.match(/[NNo\u2116]\s*(\d+)/);
                    if (nm) cert.document_number = nm[1];
                    const sm = text.match(/\b(\d{9})\b/);
                    if (sm) cert.stir = sm[1];
                    const dates = text.match(/\d{2}\.\d{2}\.\d{4}/g);
                    if (dates) { cert.issue_date=dates[0]; if(dates[1]) cert.expiry_date=dates[1]; }
                    return cert;
                })()
            """)

            cert = ParsedCertificate(document_id=document_id)
            if data:
                cert.document_number = data.get('document_number')
                cert.stir = data.get('stir')
                cert.issue_date = data.get('issue_date')
                cert.expiry_date = data.get('expiry_date')
                cert.uuid = data.get('uuid')
                if cert.uuid:
                    cert.pdf_url = f"{DOC_URL}/certificate/uuid/{cert.uuid}/pdf?language=uz"
            return cert

        except Exception as e:
            logger.error(f"get_certificate_details xato: {e}")
            return None

    def download_pdf(self, uuid: str, output_path: str) -> bool:
        try:
            pdf_url = f"{DOC_URL}/certificate/uuid/{uuid}/pdf?language=uz"

            content = self._sb.execute_async_script("""
                const done = arguments[arguments.length - 1];
                fetch(arguments[0])
                    .then(r => r.arrayBuffer())
                    .then(buf => {
                        const bytes = new Uint8Array(buf);
                        let s = '';
                        for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
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


class LicenseParserV3:
    """
    Async wrapper — bot.py bilan to'liq mos interfeys.
    SeleniumBase sync driver ThreadPoolExecutor da ishlaydi.
    """

    def __init__(self):
        self._worker: Optional[_SyncWorker] = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sbworker")

    async def _run(self, fn, *args):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, fn, *args)

    async def init_browser(self, headless: bool = True):
        # .env dan override
        env_val = os.getenv("CHROME_HEADLESS")
        if env_val is not None:
            headless = env_val.strip().lower() in {"1", "true", "yes", "y", "on"}
        elif os.name == "nt":
            # Windows: default GUI (debug qulay)
            headless = False

        self._worker = _SyncWorker(headless=headless)
        await self._run(self._worker.start)

    async def close(self):
        if self._worker:
            await self._run(self._worker.stop)
            self._worker = None
        self._executor.shutdown(wait=False)

    async def get_total_pages(self) -> int:
        return await self._run(self._worker.get_total_pages)

    async def scrape_page(self, page_num: int) -> List[ParsedCertificate]:
        return await self._run(self._worker.scrape_page, page_num)

    async def scrape_all(
        self,
        progress_callback: Optional[Callable] = None,
    ) -> List[ParsedCertificate]:
        all_certs = []
        try:
            total_pages = await self.get_total_pages()
            logger.info(f"Jami sahifalar: {total_pages}")

            for page_num in range(1, total_pages + 1):
                certs = await self.scrape_page(page_num)
                all_certs.extend(certs)

                if progress_callback:
                    result = progress_callback(page_num, total_pages, len(certs))
                    if inspect.isawaitable(result):
                        await result

                await asyncio.sleep(random.uniform(0.5, 1.2))

            logger.info(f"Jami yig'ildi: {len(all_certs)}")
            return all_certs

        except Exception as e:
            logger.error(f"scrape_all xato: {e}")
            return all_certs

    async def get_certificate_details(self, document_id: str) -> Optional[ParsedCertificate]:
        return await self._run(self._worker.get_certificate_details, document_id)

    async def download_pdf(self, uuid: str, output_path: str) -> bool:
        return await self._run(self._worker.download_pdf, uuid, output_path)