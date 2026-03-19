"""
Parser module for scraping license.gov.uz
Uses Playwright to bypass Cloudflare protection
"""
import asyncio
from typing import List, Dict, Optional, Callable
from playwright.async_api import async_playwright, Page
from bs4 import BeautifulSoup
import json
import re
from dataclasses import dataclass
from datetime import datetime
from loguru import logger


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


class LicenseParser:
    """Parser for license.gov.uz"""
    
    BASE_URL = "https://license.gov.uz"
    API_URL = "https://api.licenses.uz/v2"
    DOC_URL = "https://doc.licenses.uz/v1"
    
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self.api_data = []
    
    async def init_browser(self, headless: bool = True):
        """Initialize Playwright browser"""
        playwright = await async_playwright().start()
        
        self.browser = await playwright.chromium.launch(
            headless=headless,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
        )
        
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='uz-UZ',
            timezone_id='Asia/Tashkent',
        )
        
        # Set up request interception to capture API calls
        self.page = await self.context.new_page()
        self.page.on("response", self._handle_response)
        
        logger.info("Browser initialized")
    
    async def _handle_response(self, response):
        """Handle API responses"""
        try:
            if 'api.licenses.uz' in response.url:
                if response.status == 200:
                    try:
                        data = await response.json()
                        if isinstance(data, dict) and 'items' in data:
                            self.api_data.extend(data['items'])
                            logger.debug(f"Captured {len(data['items'])} items from API")
                    except:
                        pass
        except Exception as e:
            logger.error(f"Error handling response: {e}")
    
    async def close(self):
        """Close browser"""
        if self.browser:
            await self.browser.close()
            logger.info("Browser closed")
    
    async def get_total_pages(self) -> int:
        """Get total number of pages"""
        try:
            # Navigate to the registry page
            await self.page.goto(
                f"{self.BASE_URL}/registry?filter%5Bdocument_id%5D=4409&filter%5Bdocument_type%5D=LICENSE&page=1",
                timeout=60000,
                wait_until='networkidle'
            )
            
            # Wait for the page to load
            await asyncio.sleep(3)
            
            # Get page content
            content = await self.page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for pagination info
            pagination_text = soup.find(text=re.compile(r'\d+\s*-\s*\d+\s*из\s*\d+'))
            if pagination_text:
                match = re.search(r'из\s*(\d+)', pagination_text)
                if match:
                    total_items = int(match.group(1))
                    # Each page has 10 items
                    total_pages = (total_items + 9) // 10
                    return total_pages
            
            # Try to find pagination buttons
            pagination = soup.find('div', class_=re.compile(r'pagination|paginator', re.I))
            if pagination:
                page_buttons = pagination.find_all('button')
                if page_buttons:
                    last_page = 1
                    for btn in page_buttons:
                        text = btn.get_text(strip=True)
                        if text.isdigit():
                            last_page = max(last_page, int(text))
                    return last_page
            
            return 1
        except Exception as e:
            logger.error(f"Error getting total pages: {e}")
            return 1
    
    async def scrape_page(self, page_num: int) -> List[ParsedCertificate]:
        """Scrape a single page"""
        certificates = []
        
        try:
            # Navigate to the page
            url = f"{self.BASE_URL}/registry?filter%5Bdocument_id%5D=4409&filter%5Bdocument_type%5D=LICENSE&page={page_num}"
            await self.page.goto(url, timeout=60000, wait_until='networkidle')
            
            # Wait for the page to load
            await asyncio.sleep(3)
            
            # Get page content
            content = await self.page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            # Find certificate rows
            # The data is loaded dynamically, so we need to extract from the page
            # Look for table rows or card elements
            
            # Try to find certificate cards
            cards = soup.find_all('div', class_=re.compile(r'card|item|row', re.I))
            
            for card in cards:
                cert = self._parse_card(card)
                if cert and cert.uuid:
                    certificates.append(cert)
            
            # If no cards found, try to extract from script tags
            if not certificates:
                scripts = soup.find_all('script')
                for script in scripts:
                    if script.string:
                        # Look for JSON data in scripts
                        json_data = self._extract_json_from_script(script.string)
                        if json_data:
                            for item in json_data:
                                cert = self._parse_json_item(item)
                                if cert and cert.uuid:
                                    certificates.append(cert)
            
            logger.info(f"Scraped page {page_num}: {len(certificates)} certificates")
            return certificates
            
        except Exception as e:
            logger.error(f"Error scraping page {page_num}: {e}")
            return []
    
    def _parse_card(self, card) -> Optional[ParsedCertificate]:
        """Parse a certificate card"""
        try:
            cert = ParsedCertificate()
            
            # Extract document number
            doc_num_elem = card.find(text=re.compile(r'Ҳужжат\s*рақами|Документ'))
            if doc_num_elem:
                parent = doc_num_elem.parent
                if parent:
                    value = parent.find_next_sibling()
                    if value:
                        cert.document_number = value.get_text(strip=True)
            
            # Extract organization name
            org_elem = card.find(text=re.compile(r'Ташкилот|Организация'))
            if org_elem:
                parent = org_elem.parent
                if parent:
                    value = parent.find_next_sibling()
                    if value:
                        cert.organization_name = value.get_text(strip=True)
            
            # Extract STIR
            stir_elem = card.find(text=re.compile(r'СТИР|ИНН'))
            if stir_elem:
                parent = stir_elem.parent
                if parent:
                    value = parent.find_next_sibling()
                    if value:
                        cert.stir = value.get_text(strip=True)
            
            # Extract activity type
            activity_elem = card.find(text=re.compile(r'Фаолият\s*тури|Вид\s*деятельности'))
            if activity_elem:
                parent = activity_elem.parent
                if parent:
                    value = parent.find_next_sibling()
                    if value:
                        cert.activity_type = value.get_text(strip=True)
            
            # Extract UUID from links
            links = card.find_all('a', href=True)
            for link in links:
                href = link['href']
                uuid_match = re.search(r'/certificate/uuid/([a-f0-9-]+)', href)
                if uuid_match:
                    cert.uuid = uuid_match.group(1)
                    cert.pdf_url = f"{self.DOC_URL}/certificate/uuid/{cert.uuid}/pdf?language=uz"
                    break
            
            # Extract document ID from links
            doc_id_match = re.search(r'filter%5Bnumber%5D=(\d+)', str(card))
            if doc_id_match:
                cert.document_id = doc_id_match.group(1)
            
            return cert
            
        except Exception as e:
            logger.error(f"Error parsing card: {e}")
            return None
    
    def _extract_json_from_script(self, script_text: str) -> List[Dict]:
        """Extract JSON data from script"""
        try:
            # Look for JSON arrays
            matches = re.findall(r'\[\s*{\s*"[^"]+"\s*:', script_text)
            if matches:
                # Try to extract the full JSON
                start = script_text.find('[')
                end = script_text.rfind(']') + 1
                if start >= 0 and end > start:
                    json_str = script_text[start:end]
                    return json.loads(json_str)
        except:
            pass
        return []
    
    def _parse_json_item(self, item: Dict) -> Optional[ParsedCertificate]:
        """Parse JSON item to certificate"""
        try:
            cert = ParsedCertificate()
            
            cert.document_id = str(item.get('id', ''))
            cert.document_number = item.get('number', '')
            cert.status = item.get('status', '')
            cert.issue_date = item.get('issueDate', '')
            cert.inserted_date = item.get('insertedDate', '')
            cert.organization_name = item.get('organization', '')
            cert.address = item.get('address', '')
            cert.stir = item.get('tin', '')
            cert.expiry_date = item.get('expireDate', '')
            cert.activity_type = item.get('activityType', '')
            cert.uuid = item.get('uuid', '')
            
            if cert.uuid:
                cert.pdf_url = f"{self.DOC_URL}/certificate/uuid/{cert.uuid}/pdf?language=uz"
            
            return cert
        except Exception as e:
            logger.error(f"Error parsing JSON item: {e}")
            return None
    
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
                
                # Small delay to avoid being blocked
                await asyncio.sleep(2)
            
            logger.info(f"Total certificates scraped: {len(all_certificates)}")
            return all_certificates
            
        except Exception as e:
            logger.error(f"Error scraping all pages: {e}")
            return all_certificates
    
    async def get_certificate_details(self, document_id: str) -> Optional[ParsedCertificate]:
        """Get certificate details by document ID"""
        try:
            url = f"{self.BASE_URL}/registry?filter%5Bnumber%5D={document_id}"
            await self.page.goto(url, timeout=60000, wait_until='networkidle')
            
            await asyncio.sleep(3)
            
            content = await self.page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            # Parse the details page
            cert = ParsedCertificate()
            cert.document_id = document_id
            
            # Extract all available information
            # This depends on the page structure
            
            return cert
            
        except Exception as e:
            logger.error(f"Error getting certificate details: {e}")
            return None
    
    async def download_pdf(self, uuid: str, output_path: str) -> bool:
        """Download PDF file"""
        try:
            pdf_url = f"{self.DOC_URL}/certificate/uuid/{uuid}/pdf?language=uz"
            
            # Use page to download the PDF
            async with self.page.expect_download() as download_info:
                await self.page.goto(pdf_url)
            
            download = await download_info.value
            await download.save_as(output_path)
            
            logger.info(f"PDF downloaded: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error downloading PDF: {e}")
            return False
