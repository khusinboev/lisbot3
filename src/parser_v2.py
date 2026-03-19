"""
Improved Parser module for scraping license.gov.uz
Uses Playwright with stealth mode to bypass Cloudflare protection
"""
import asyncio
from typing import List, Dict, Optional, Callable
from playwright.async_api import async_playwright, Page, Route
from bs4 import BeautifulSoup
import json
import re
from dataclasses import dataclass
from datetime import datetime
from loguru import logger
import random


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

    BASE_URL = "https://license.gov.uz"
    API_URL = "https://api.licenses.uz/v2"
    DOC_URL = "https://doc.licenses.uz/v1"

    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        self.captured_data = []

    async def init_browser(self, headless: bool = True):
        """Initialize Playwright browser with stealth options"""
        self.playwright = await async_playwright().start()

        # Launch browser with stealth options
        self.browser = await self.playwright.chromium.launch(
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
                '--disable-features=IsolateOrigins,site-per-process',
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
            ]
        )

        # Create context with realistic settings
        self.context = await self.browser.new_context(
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

        # Add init script to hide automation
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            window.chrome = { runtime: {} };
        """)

        # Create page
        self.page = await self.context.new_page()

        # Set up route interception
        await self.page.route("**/*", self._handle_route)

        logger.info("Browser initialized with stealth mode")

    async def _handle_route(self, route: Route):
        """Handle route interception"""
        request = route.request

        # Capture API responses
        if 'api.licenses.uz' in request.url:
            logger.debug(f"API request: {request.method} {request.url}")

        await route.continue_()

    async def close(self):
        """Close browser"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser closed")

    async def wait_for_cloudflare(self, timeout: int = 30):
        """Wait for Cloudflare challenge to complete"""
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            # Check if we're past the challenge
            title = await self.page.title()
            if title and 'license' not in title.lower() and 'loading' not in title.lower():
                # Check for actual content
                content = await self.page.content()
                if 'registry' in content.lower() or 'реестр' in content.lower():
                    return True

            await asyncio.sleep(1)

        return False

    async def get_total_pages(self) -> int:
        """Get total number of pages"""
        try:
            # Navigate to the registry page
            await self.page.goto(
                f"{self.BASE_URL}/registry?filter%5Bdocument_id%5D=4409&filter%5Bdocument_type%5D=LICENSE&page=1",
                timeout=60000,
                wait_until='domcontentloaded'
            )

            # Wait for Cloudflare
            await self.wait_for_cloudflare()

            # Wait for content to load
            await asyncio.sleep(5)

            # Try to find pagination info using JavaScript
            pagination_info = await self.page.evaluate("""
                () => {
                    // Look for pagination elements
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

            # Try to find last page number
            last_page = await self.page.evaluate("""
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
            # Navigate to the page
            url = f"{self.BASE_URL}/registry?filter%5Bdocument_id%5D=4409&filter%5Bdocument_type%5D=LICENSE&page={page_num}"

            # Add random delay
            await asyncio.sleep(random.uniform(1, 3))

            await self.page.goto(url, timeout=60000, wait_until='domcontentloaded')

            # Wait for content to load
            await asyncio.sleep(5)

            # Extract data using JavaScript
            data = await self.page.evaluate("""
                () => {
                    const results = [];

                    // Look for certificate cards/rows
                    const cards = document.querySelectorAll('[class*="card"], [class*="item"], [class*="row"], tr');

                    for (const card of cards) {
                        const cert = {};

                        // Try to extract all text content
                        const text = card.textContent;

                        // Look for document number
                        const docMatch = text.match(/[№N]\s*(\d+)/);
                        if (docMatch) cert.document_number = docMatch[1];

                        // Look for STIR
                        const stirMatch = text.match(/(\d{9})/);
                        if (stirMatch) cert.stir = stirMatch[1];

                        // Look for UUID in links
                        const links = card.querySelectorAll('a[href]');
                        for (const link of links) {
                            const href = link.getAttribute('href');
                            const uuidMatch = href.match(/certificate\/uuid\/([a-f0-9-]+)/i);
                            if (uuidMatch) {
                                cert.uuid = uuidMatch[1];
                                cert.pdf_url = `https://doc.licenses.uz/v1/certificate/uuid/${cert.uuid}/pdf?language=uz`;
                            }

                            // Look for document ID
                            const docIdMatch = href.match(/filter%5Bnumber%5D=(\d+)/);
                            if (docIdMatch) cert.document_id = docIdMatch[1];
                        }

                        // Look for organization name (usually a link or bold text)
                        const orgEl = card.querySelector('a, strong, b');
                        if (orgEl) cert.organization_name = orgEl.textContent.trim();

                        // Look for dates
                        const dateMatches = text.match(/(\d{2}\.\d{2}\.\d{4})/g);
                        if (dateMatches) {
                            cert.issue_date = dateMatches[0];
                            if (dateMatches[1]) cert.expiry_date = dateMatches[1];
                        }

                        // Look for activity type
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

            # Convert to ParsedCertificate objects
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
            # Get total pages
            total_pages = await self.get_total_pages()
            logger.info(f"Total pages to scrape: {total_pages}")

            for page_num in range(1, total_pages + 1):
                certificates = await self.scrape_page(page_num)
                all_certificates.extend(certificates)

                # Call progress callback
                if progress_callback:
                    progress_callback(page_num, total_pages, len(certificates))

                # Random delay between pages
                await asyncio.sleep(random.uniform(2, 5))

            logger.info(f"Total certificates scraped: {len(all_certificates)}")
            return all_certificates

        except Exception as e:
            logger.error(f"Error scraping all pages: {e}")
            return all_certificates

    async def download_pdf(self, uuid: str, output_path: str) -> bool:
        """Download PDF file"""
        try:
            pdf_url = f"{self.DOC_URL}/certificate/uuid/{uuid}/pdf?language=uz"

            # Navigate to PDF URL
            response = await self.page.goto(pdf_url, timeout=60000)

            if response:
                # Save the PDF
                content = await response.body()
                with open(output_path, 'wb') as f:
                    f.write(content)

                logger.info(f"PDF downloaded: {output_path}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error downloading PDF: {e}")
            return False
