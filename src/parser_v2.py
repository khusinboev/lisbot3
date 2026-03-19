"""
Improved Parser module for scraping license.gov.uz
Uses Playwright with stealth mode to bypass Cloudflare protection
"""
import asyncio
import os
from typing import List, Dict, Optional, Callable
from playwright.async_api import async_playwright, Page, Route
from bs4 import BeautifulSoup
import json
import re
from dataclasses import dataclass
from datetime import datetime
from loguru import logger
import random
import inspect

from settings import BASE_URL, API_URL, DOC_URL
from fingerprint_patch import STEALTH_INIT_SCRIPT


@dataclass
class ParsedCertificate:
    """Parsed certificate data"""
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


class LicenseParserV2:
    """Improved parser for license.gov.uz with better Cloudflare bypass"""

    BASE_URL = BASE_URL
    API_URL = API_URL
    DOC_URL = DOC_URL

    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        self.captured_data = []
        self.profile_dir = self._resolve_profile_dir()

    @staticmethod
    def _env_bool(name: str, default: bool = False) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "y", "on"}

    def _resolve_profile_dir(self) -> str:
        """Resolve a dedicated persistent profile directory for parser v2."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        default_dir = os.path.abspath(
            os.path.join(current_dir, "..", "data", "chrome_profile_parser_v2")
        )
        profile_dir = (
            os.getenv("PARSER_V2_PROFILE_DIR")
            or os.getenv("CHROME_PROFILE_DIR")
            or default_dir
        )
        os.makedirs(profile_dir, exist_ok=True)
        return profile_dir

    async def _human_delay(self, min_seconds: float = 0.4, max_seconds: float = 1.2):
        await asyncio.sleep(random.uniform(min_seconds, max_seconds))

    async def _human_mouse_move(self, steps: int | None = None):
        """Random mouse movement to mimic real browsing behavior."""
        if not self.page:
            return

        width, height = 1920, 1080
        if self.page.viewport_size:
            width = self.page.viewport_size.get("width", width)
            height = self.page.viewport_size.get("height", height)

        points = steps or random.randint(3, 7)
        for _ in range(points):
            x = random.randint(80, max(120, width - 80))
            y = random.randint(80, max(120, height - 80))
            await self.page.mouse.move(x, y, steps=random.randint(8, 20))
            await self._human_delay(0.08, 0.3)

    async def _human_scroll(self):
        """Scroll down/up with random increments like a human."""
        if not self.page:
            return

        for _ in range(random.randint(2, 4)):
            await self.page.mouse.wheel(0, random.randint(220, 550))
            await self._human_delay(0.25, 0.75)

        await self.page.mouse.wheel(0, -random.randint(140, 320))
        await self._human_delay(0.2, 0.5)

    async def _type_humanlike(self, text: str):
        """Type text with per-character delay."""
        if not self.page:
            return

        for ch in text:
            await self.page.keyboard.type(ch, delay=random.randint(35, 140))

    async def _human_browse_noise(self):
        """Small set of random interactions to reduce deterministic behavior."""
        await self._human_mouse_move()
        await self._human_scroll()

    async def _goto_with_retries(
        self,
        url: str,
        wait_until: str = 'domcontentloaded',
        timeout: int = 60000,
        retries: int = 3,
    ) -> bool:
        for attempt in range(1, retries + 1):
            try:
                await self.page.goto(url, timeout=timeout, wait_until=wait_until)
                if random.random() < 0.7:
                    await self._human_browse_noise()
                return True
            except Exception as e:
                logger.warning(f"Navigation failed (attempt {attempt}/{retries}) for {url}: {e}")
                await asyncio.sleep(random.uniform(1.8, 3.5) + (attempt * 0.4))
        return False

    async def _youtube_warmup(self):
        """Optional warmup flow before target site to reduce early blocking."""
        if self._env_bool("SKIP_WARMUP", default=False):
            logger.info("Warmup skipped by SKIP_WARMUP=true")
            return

        try:
            await self.page.goto("https://www.youtube.com", timeout=45000, wait_until='domcontentloaded')
            await self._human_delay(1.2, 2.2)

            for selector in [
                "button[aria-label*='Accept']",
                "button[aria-label*='agree']",
                "button[aria-label*='Reject']",
                "ytd-button-renderer button",
            ]:
                try:
                    btn = self.page.locator(selector).first
                    if await btn.count() > 0:
                        await btn.click(timeout=1200)
                        await self._human_delay(0.6, 1.2)
                        break
                except Exception:
                    continue

            await self._human_mouse_move()

            search_box = self.page.locator("input[name='search_query']")
            if await search_box.count() > 0:
                await search_box.first.click()
                await self._human_delay(0.35, 0.85)
                await self._type_humanlike(random.choice([
                    "python tutorial",
                    "uzbekistan",
                    "telegram bot",
                    "news today",
                ]))
                await self._human_delay(0.5, 1.0)
                await self.page.keyboard.press("Enter")
                await self._human_delay(1.4, 2.8)
                await self._human_scroll()
                await self._human_mouse_move()

            logger.info("Warmup completed")
        except Exception as e:
            logger.debug(f"Warmup skipped due to transient error: {e}")

    async def init_browser(self, headless: bool = True):
        """Initialize Playwright browser with stealth options"""
        self.playwright = await async_playwright().start()

        if os.getenv("CHROME_HEADLESS") is not None:
            headless = self._env_bool("CHROME_HEADLESS", default=headless)
        elif self._env_bool("IN_DOCKER", default=False):
            headless = True
        elif os.name == "nt":
            headless = False

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            headless=headless,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-accelerated-2d-canvas',
                '--disable-accelerated-jpeg-decoding',
                '--disable-accelerated-mjpeg-decode',
                '--disable-accelerated-video-decode',
                '--disable-app-list-dismiss-on-blur',
                '--disable-canvas-aa',
                '--disable-composited-antialiasing',
                '--disable-extensions',
                '--disable-features=ScriptStreaming',
                '--disable-histogram-customizer',
                '--disable-namespace-sandbox',
                '--disable-notifications',
                '--disable-popup-blocking',
                '--disable-background-networking',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-breakpad',
                '--disable-client-side-phishing-detection',
                '--disable-component-update',
                '--disable-default-apps',
                '--disable-domain-reliability',
                '--disable-features=AudioServiceOutOfProcess',
                '--disable-hang-monitor',
                '--disable-ipc-flooding-protection',
                '--disable-logging',
                '--disable-renderer-backgrounding',
                '--disable-sync',
                '--force-color-profile=srgb',
                '--metrics-recording-only',
                '--no-first-run',
                '--password-store=basic',
                '--use-mock-keychain',
            ],
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='uz-UZ',
            timezone_id='Asia/Tashkent',
            geolocation={'latitude': 41.2995, 'longitude': 69.2401},
            permissions=['geolocation'],
            color_scheme='light',
            reduced_motion='no-preference',
            accept_downloads=True,
        )

        # Full fingerprint hardening — 7 vectors
        await self.context.add_init_script(STEALTH_INIT_SCRIPT)

        existing_pages = self.context.pages
        self.page = existing_pages[0] if existing_pages else await self.context.new_page()
        self.browser = self.context.browser

        await self.page.route("**/*", self._handle_route)

        await self._youtube_warmup()

        logger.info(f"Browser initialized with stealth mode, profile: {self.profile_dir}")

    async def _handle_route(self, route: Route):
        """Handle route interception"""
        request = route.request
        if 'api.licenses.uz' in request.url:
            logger.debug(f"API request: {request.method} {request.url}")
        await route.continue_()

    async def close(self):
        """Close browser"""
        if self.context:
            await self.context.close()
            self.context = None

        self.page = None
        self.browser = None

        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

        logger.info("Browser closed")

    async def wait_for_cloudflare(self, timeout: int = 30):
        """Wait for Cloudflare challenge to complete"""
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            title = await self.page.title()
            if title and 'license' not in title.lower() and 'loading' not in title.lower():
                content = await self.page.content()
                if 'registry' in content.lower() or 'реестр' in content.lower():
                    return True
            await asyncio.sleep(1)

        return False

    async def get_total_pages(self) -> int:
        """Get total number of pages"""
        try:
            first_page_url = (
                f"{self.BASE_URL}/registry?filter%5Bdocument_id%5D=4409&"
                "filter%5Bdocument_type%5D=LICENSE&page=1"
            )
            opened = await self._goto_with_retries(first_page_url, wait_until='domcontentloaded', timeout=60000)
            if not opened:
                return 1

            await self.wait_for_cloudflare()
            await asyncio.sleep(3)

            pagination_info = await self.page.evaluate(r"""
                () => {
                    const paginationTexts = document.querySelectorAll('*');
                    for (const el of paginationTexts) {
                        const text = el.textContent;
                        if (text && (text.includes('из') || text.includes('of'))) {
                            const match = text.match(/(\d+)\s*(из|of)\s*(\d+)/);
                            if (match) {
                                return { current: match[1], total: match[3], text: text };
                            }
                        }
                    }
                    return null;
                }
            """)

            if pagination_info:
                total_items = int(pagination_info['total'])
                total_pages = (total_items + 9) // 10
                logger.info(f"Total pages: {total_pages}")
                return total_pages

            last_page = await self.page.evaluate(r"""
                () => {
                    const buttons = document.querySelectorAll('button, a');
                    let maxPage = 1;
                    for (const btn of buttons) {
                        const text = btn.textContent.trim();
                        if (/^\d+$/.test(text)) {
                            maxPage = Math.max(maxPage, parseInt(text));
                        }
                    }
                    return maxPage;
                }
            """)

            return last_page

        except Exception as e:
            logger.error(f"Error getting total pages: {e}")
            return 1

    async def scrape_page(self, page_num: int) -> List[ParsedCertificate]:
        """Scrape a single page"""
        certificates = []

        try:
            url = f"{self.BASE_URL}/registry?filter%5Bdocument_id%5D=4409&filter%5Bdocument_type%5D=LICENSE&page={page_num}"
            await self._human_delay(0.3, 1.0)

            opened = await self._goto_with_retries(url, wait_until='domcontentloaded', timeout=60000)
            if not opened:
                return []

            await asyncio.sleep(2)

            data = await self.page.evaluate(r"""
                () => {
                    const results = [];
                    const cards = document.querySelectorAll('[class*="card"], [class*="item"], [class*="row"], tr');
                    for (const card of cards) {
                        const cert = {};
                        const text = card.textContent;

                        const docMatch = text.match(/[№N]\s*(\d+)/);
                        if (docMatch) cert.document_number = docMatch[1];

                        const stirMatch = text.match(/(\d{9})/);
                        if (stirMatch) cert.stir = stirMatch[1];

                        const links = card.querySelectorAll('a[href]');
                        for (const link of links) {
                            const href = link.getAttribute('href');
                            const uuidMatch = href.match(/certificate\/uuid\/([a-f0-9-]+)/i);
                            if (uuidMatch) {
                                cert.uuid = uuidMatch[1];
                                cert.pdf_url = `https://doc.licenses.uz/v1/certificate/uuid/${cert.uuid}/pdf?language=uz`;
                            }
                            const docIdMatch = href.match(/filter%5Bnumber%5D=(\d+)/);
                            if (docIdMatch) cert.document_id = docIdMatch[1];
                        }

                        const orgEl = card.querySelector('a, strong, b');
                        if (orgEl) cert.organization_name = orgEl.textContent.trim();

                        const dateMatches = text.match(/(\d{2}\.\d{2}\.\d{4})/g);
                        if (dateMatches) {
                            cert.issue_date = dateMatches[0];
                            if (dateMatches[1]) cert.expiry_date = dateMatches[1];
                        }

                        if (text.includes('Олий таълим') || text.includes('Высшее образование')) {
                            cert.activity_type = 'Олий таълим хизматлари';
                        }

                        if (cert.uuid || cert.document_number) {
                            results.push(cert);
                        }
                    }
                    return results;
                }
            """)

            if not data:
                logger.warning(f"No certificates visible on page {page_num}, waiting and refreshing...")
                await asyncio.sleep(random.uniform(2.2, 4.0))
                await self.page.reload(timeout=60000, wait_until='domcontentloaded')
                await asyncio.sleep(2)
                data = await self.page.evaluate(r"""
                    () => {
                        const results = [];
                        const cards = document.querySelectorAll('[class*="card"], [class*="item"], [class*="row"], tr');
                        for (const card of cards) {
                            const cert = {};
                            const text = card.textContent;

                            const docMatch = text.match(/[№N]\s*(\d+)/);
                            if (docMatch) cert.document_number = docMatch[1];

                            const stirMatch = text.match(/(\d{9})/);
                            if (stirMatch) cert.stir = stirMatch[1];

                            const links = card.querySelectorAll('a[href]');
                            for (const link of links) {
                                const href = link.getAttribute('href');
                                const uuidMatch = href.match(/certificate\/uuid\/([a-f0-9-]+)/i);
                                if (uuidMatch) {
                                    cert.uuid = uuidMatch[1];
                                    cert.pdf_url = `https://doc.licenses.uz/v1/certificate/uuid/${cert.uuid}/pdf?language=uz`;
                                }
                                const docIdMatch = href.match(/filter%5Bnumber%5D=(\d+)/);
                                if (docIdMatch) cert.document_id = docIdMatch[1];
                            }

                            const orgEl = card.querySelector('a, strong, b');
                            if (orgEl) cert.organization_name = orgEl.textContent.trim();

                            const dateMatches = text.match(/(\d{2}\.\d{2}\.\d{4})/g);
                            if (dateMatches) {
                                cert.issue_date = dateMatches[0];
                                if (dateMatches[1]) cert.expiry_date = dateMatches[1];
                            }

                            if (text.includes('Олий таълим') || text.includes('Высшее образование')) {
                                cert.activity_type = 'Олий таълим хизматлари';
                            }

                            if (cert.uuid || cert.document_number) {
                                results.push(cert);
                            }
                        }
                        return results;
                    }
                """)

            for item in data:
                cert = ParsedCertificate(
                    document_id=item.get('document_id'),
                    document_number=item.get('document_number'),
                    stir=item.get('stir'),
                    organization_name=item.get('organization_name'),
                    issue_date=item.get('issue_date'),
                    expiry_date=item.get('expiry_date'),
                    activity_type=item.get('activity_type'),
                    uuid=item.get('uuid'),
                    pdf_url=item.get('pdf_url')
                )
                certificates.append(cert)

            logger.info(f"Scraped page {page_num}: {len(certificates)} certificates")
            return certificates

        except Exception as e:
            logger.error(f"Error scraping page {page_num}: {e}")
            return []

    async def scrape_all(
            self,
            progress_callback: Optional[Callable[[int, int, int], None]] = None
    ) -> List[ParsedCertificate]:
        """Scrape all pages"""
        all_certificates = []

        try:
            total_pages = await self.get_total_pages()
            logger.info(f"Total pages to scrape: {total_pages}")

            for page_num in range(1, total_pages + 1):
                certificates = await self.scrape_page(page_num)
                all_certificates.extend(certificates)

                if progress_callback:
                    progress_result = progress_callback(page_num, total_pages, len(certificates))
                    if inspect.isawaitable(progress_result):
                        await progress_result

                await asyncio.sleep(random.uniform(0.8, 1.6))

            logger.info(f"Total certificates scraped: {len(all_certificates)}")
            return all_certificates

        except Exception as e:
            logger.error(f"Error scraping all pages: {e}")
            return all_certificates

    async def get_certificate_details(self, document_id: str) -> Optional[ParsedCertificate]:
        """Get certificate details by document ID for update flow compatibility."""
        try:
            url = f"{self.BASE_URL}/registry?filter%5Bnumber%5D={document_id}"
            opened = await self._goto_with_retries(url, wait_until='domcontentloaded', timeout=60000)
            if not opened:
                return None
            await asyncio.sleep(2)

            data = await self.page.evaluate(r"""
                () => {
                    const cert = {};
                    const text = document.body ? document.body.textContent : "";

                    const uuidMatch = text.match(/([a-f0-9]{8}-[a-f0-9-]{27})/i);
                    if (uuidMatch) cert.uuid = uuidMatch[1];

                    const docNumMatch = text.match(/[№N]\s*(\d+)/);
                    if (docNumMatch) cert.document_number = docNumMatch[1];

                    const stirMatch = text.match(/\b\d{9}\b/);
                    if (stirMatch) cert.stir = stirMatch[0];

                    const dateMatches = text.match(/(\d{2}\.\d{2}\.\d{4})/g);
                    if (dateMatches && dateMatches.length > 0) {
                        cert.issue_date = dateMatches[0];
                        if (dateMatches.length > 1) cert.expiry_date = dateMatches[1];
                    }

                    return cert;
                }
            """)

            cert = ParsedCertificate(
                document_id=document_id,
                document_number=data.get('document_number'),
                stir=data.get('stir'),
                issue_date=data.get('issue_date'),
                expiry_date=data.get('expiry_date'),
                uuid=data.get('uuid'),
            )
            if cert.uuid:
                cert.pdf_url = f"{self.DOC_URL}/certificate/uuid/{cert.uuid}/pdf?language=uz"
            return cert
        except Exception as e:
            logger.error(f"Error getting certificate details: {e}")
            return None

    async def download_pdf(self, uuid: str, output_path: str) -> bool:
        """Download PDF file"""
        try:
            pdf_url = f"{self.DOC_URL}/certificate/uuid/{uuid}/pdf?language=uz"
            response = await self.page.goto(pdf_url, timeout=60000)

            if response:
                content = await response.body()
                with open(output_path, 'wb') as f:
                    f.write(content)
                logger.info(f"PDF downloaded: {output_path}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error downloading PDF: {e}")
            return False