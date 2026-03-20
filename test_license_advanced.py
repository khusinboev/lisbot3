#!/usr/bin/env python3
"""
================================================================================
LICENSE.GOV.UZ - ADVANCED SCRAPER TEST
================================================================================
Eng kuchli himoya tizimlaridan o'tish uchun maxsus test
- Cloudflare Turnstile
- Rate limiting
- Bot detection
- Session management

O'rnatish:
    pip install playwright playwright-stealth fake-useragent loguru aiohttp
    playwright install chromium

Ishga tushirish:
    python test_license_advanced.py
================================================================================
"""

import asyncio
import json
import random
import time
import os
import sys
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

# ============================================================================
# LOGGING
# ============================================================================

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger("scraper")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

# ============================================================================
# CONSTANTS
# ============================================================================

BASE_URL = "https://license.gov.uz"
API_BASE = "https://api.licenses.uz"
REGISTRY_URL = f"{BASE_URL}/registry?filter%5Bdocument_id%5D=4409&filter%5Bdocument_type%5D=LICENSE"

# Test targets
TEST_TARGETS = [
    {"name": "Bot Detection", "url": "https://bot.sannysoft.com"},
    {"name": "Browser Leaks", "url": "https://browserleaks.com/webgl"},
    {"name": "PixelScan", "url": "https://pixelscan.net"},
    {"name": "License.gov.uz", "url": REGISTRY_URL},
]


# ============================================================================
# ADVANCED FINGERPRINT MANAGER
# ============================================================================

@dataclass
class FingerprintProfile:
    """To'liq browser profili"""
    # Basic
    user_agent: str
    viewport: Dict[str, int]

    # Hardware
    hardware_concurrency: int
    device_memory: int
    max_touch_points: int

    # System
    platform: str
    vendor: str
    language: str
    languages: List[str]
    timezone: str

    # Screen
    color_depth: int
    pixel_ratio: float

    # WebGL
    webgl_vendor: str
    webgl_renderer: str

    # Fonts
    fonts: List[str]


class FingerprintManager:
    """Realistik fingerprint yaratuvchi va boshqaruvchi"""

    # Zamonaviy Chrome user-agentlari
    CHROME_UAS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    VIEWPORTS = [
        {"width": 1920, "height": 1080},
        {"width": 1366, "height": 768},
        {"width": 1440, "height": 900},
        {"width": 1536, "height": 864},
        {"width": 1280, "height": 720},
    ]

    WEBGL_PROFILES = [
        {"vendor": "Intel Inc.", "renderer": "Intel Iris OpenGL Engine"},
        {"vendor": "Intel Inc.", "renderer": "Intel Iris Xe Graphics"},
        {"vendor": "NVIDIA Corporation", "renderer": "NVIDIA GeForce GTX 1050/PCIe/SSE2"},
        {"vendor": "AMD", "renderer": "AMD Radeon Pro 5300M OpenGL Engine"},
    ]

    TIMEZONES = [
        "Asia/Tashkent", "Europe/Moscow", "Europe/London",
        "America/New_York", "Europe/Berlin", "Asia/Tokyo"
    ]

    def generate(self) -> FingerprintProfile:
        """Yangi random fingerprint yaratish"""
        ua = random.choice(self.CHROME_UAS)
        webgl = random.choice(self.WEBGL_PROFILES)

        # Platformani aniqlash
        if "Windows" in ua:
            platform = "Win32"
        elif "Macintosh" in ua:
            platform = "MacIntel"
        else:
            platform = "Linux x86_64"

        return FingerprintProfile(
            user_agent=ua,
            viewport=random.choice(self.VIEWPORTS),
            hardware_concurrency=random.choice([4, 6, 8, 12, 16]),
            device_memory=random.choice([4, 8, 16, 32]),
            max_touch_points=0,
            platform=platform,
            vendor="Google Inc.",
            language="uz-UZ",
            languages=["uz-UZ", "uz", "ru-RU", "ru", "en-US", "en"],
            timezone=random.choice(self.TIMEZONES),
            color_depth=24,
            pixel_ratio=1.0,
            webgl_vendor=webgl["vendor"],
            webgl_renderer=webgl["renderer"],
            fonts=self._get_fonts()
        )

    def _get_fonts(self) -> List[str]:
        """System fontlar ro'yxati"""
        return [
            "Arial", "Helvetica", "Times New Roman", "Courier New",
            "Verdana", "Georgia", "Palatino", "Garamond", "Bookman",
            "Comic Sans MS", "Trebuchet MS", "Arial Black", "Impact",
            "Tahoma", "Geneva", "Century Gothic", "Lucida Grande"
        ]


# ============================================================================
# STEALTH INJECT SCRIPTS
# ============================================================================

class StealthScripts:
    """Browser stealth inject scriptlari"""

    @staticmethod
    def get_full_stealth_script(fingerprint: FingerprintProfile) -> str:
        """To'liq stealth script"""
        return f"""
        // ============================================
        // CORE ANTI-DETECTION
        // ============================================

        // 1. Navigator properties
        Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
        Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {fingerprint.hardware_concurrency} }});
        Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {fingerprint.device_memory} }});
        Object.defineProperty(navigator, 'maxTouchPoints', {{ get: () => {fingerprint.max_touch_points} }});
        Object.defineProperty(navigator, 'platform', {{ get: () => '{fingerprint.platform}' }});
        Object.defineProperty(navigator, 'vendor', {{ get: () => '{fingerprint.vendor}' }});
        Object.defineProperty(navigator, 'language', {{ get: () => '{fingerprint.language}' }});
        Object.defineProperty(navigator, 'languages', {{ get: () => {json.dumps(fingerprint.languages)} }});

        // 2. Chrome object
        window.chrome = {{
            runtime: {{}},
            loadTimes: function() {{}},
            csi: function() {{}},
            app: {{}},
            webstore: {{ onInstallStageChanged: {{}}, onDownloadProgress: {{}} }}
        }};

        // 3. Plugins
        Object.defineProperty(navigator, 'plugins', {{
            get: () => {{
                const plugins = [
                    {{
                        name: 'Chrome PDF Plugin',
                        filename: 'internal-pdf-viewer',
                        description: 'Portable Document Format',
                        length: 2,
                        item: idx => ({{type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: plugins[0]}})
                    }},
                    {{
                        name: 'Chrome PDF Viewer', 
                        filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                        description: '',
                        length: 2,
                        item: idx => ({{type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: plugins[1]}})
                    }},
                    {{
                        name: 'Native Client',
                        filename: 'internal-nacl-plugin',
                        description: '',
                        length: 2,
                        item: idx => null
                    }}
                ];
                plugins.length = 3;
                plugins.refresh = () => {{}};
                plugins.item = idx => plugins[idx];
                plugins.namedItem = name => plugins.find(p => p.name === name);
                return plugins;
            }}
        }});

        // 4. MimeTypes
        Object.defineProperty(navigator, 'mimeTypes', {{
            get: () => {{
                const types = [
                    {{type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: {{name: 'Chrome PDF Plugin'}}}},
                    {{type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: {{name: 'Chrome PDF Viewer'}}}},
                    {{type: 'application/x-nacl', suffixes: '', description: 'Native Client module', enabledPlugin: {{name: 'Native Client'}}}}
                ];
                types.length = 3;
                types.item = idx => types[idx];
                types.namedItem = name => types.find(t => t.type === name);
                return types;
            }}
        }});

        // 5. Permissions API
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => {{
            if (parameters.name === 'notifications') {{
                return Promise.resolve({{ state: Notification.permission }});
            }}
            if (parameters.name === 'clipboard-read' || parameters.name === 'clipboard-write') {{
                return Promise.resolve({{ state: 'prompt' }});
            }}
            return originalQuery(parameters);
        }};

        // 6. Canvas fingerprint noise
        const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
        const noise = () => Math.random() > 0.5 ? 1 : -1;

        CanvasRenderingContext2D.prototype.getImageData = function(...args) {{
            const imageData = originalGetImageData.apply(this, args);
            const data = imageData.data;
            for (let i = 0; i < data.length; i += 4) {{
                data[i] = Math.min(255, Math.max(0, data[i] + noise()));
                data[i+1] = Math.min(255, Math.max(0, data[i+1] + noise()));
                data[i+2] = Math.min(255, Math.max(0, data[i+2] + noise()));
            }}
            return imageData;
        }};

        // 7. WebGL spoof
        const getParameterProxy = {{
            apply: function(target, thisArg, args) {{
                const param = args[0];
                if (param === 37445) return '{fingerprint.webgl_vendor}';
                if (param === 37446) return '{fingerprint.webgl_renderer}';
                return target.apply(thisArg, args);
            }}
        }};

        const originalGetContext = HTMLCanvasElement.prototype.getContext;
        HTMLCanvasElement.prototype.getContext = function(type, ...args) {{
            const context = originalGetContext.call(this, type, ...args);
            if (context && (type === 'webgl' || type === 'experimental-webgl' || type === 'webgl2')) {{
                const originalGetParameter = context.getParameter;
                context.getParameter = new Proxy(originalGetParameter, getParameterProxy);

                // Spoof getSupportedExtensions
                const originalGetSupportedExtensions = context.getSupportedExtensions;
                context.getSupportedExtensions = function() {{
                    return [
                        'WEBGL_debug_renderer_info',
                        'WEBGL_lose_context',
                        'EXT_texture_filter_anisotropic',
                        'EXT_disjoint_timer_query',
                        'OES_texture_float_linear',
                        'OES_element_index_uint',
                        'OES_standard_derivatives',
                        'WEBGL_compressed_texture_s3tc',
                        'WEBGL_depth_texture',
                        'OES_texture_float',
                        'WEBGL_draw_buffers'
                    ];
                }};
            }}
            return context;
        }};

        // 8. AudioContext spoof
        const originalCreateAnalyser = AudioContext.prototype.createAnalyser;
        AudioContext.prototype.createAnalyser = function(...args) {{
            const analyser = originalCreateAnalyser.apply(this, args);
            const originalGetFloatFrequencyData = analyser.getFloatFrequencyData;
            const originalGetByteFrequencyData = analyser.getByteFrequencyData;

            analyser.getFloatFrequencyData = function(array) {{
                originalGetFloatFrequencyData.call(this, array);
                for (let i = 0; i < array.length; i++) {{
                    array[i] += (Math.random() - 0.5) * 0.001;
                }}
            }};

            analyser.getByteFrequencyData = function(array) {{
                originalGetByteFrequencyData.call(this, array);
                for (let i = 0; i < array.length; i++) {{
                    array[i] = Math.min(255, array[i] + (Math.random() > 0.5 ? 1 : 0));
                }}
            }};

            return analyser;
        }};

        // 9. Font detection bypass
        const originalMeasureText = CanvasRenderingContext2D.prototype.measureText;
        CanvasRenderingContext2D.prototype.measureText = function(text) {{
            const result = originalMeasureText.call(this, text);
            const widthNoise = (Math.random() - 0.5) * 0.02;
            Object.defineProperty(result, 'width', {{
                get: () => result._width + widthNoise,
                configurable: true
            }});
            result._width = result.width;
            return result;
        }};

        // 10. Notification permission
        const originalNotification = window.Notification;
        Object.defineProperty(window, 'Notification', {{
            get: function() {{
                return originalNotification;
            }},
            set: function(value) {{
                originalNotification = value;
            }}
        }});

        // 11. Iframe contentWindow spoof
        const originalCreateElement = Document.prototype.createElement;
        Document.prototype.createElement = function(tagName, ...args) {{
            const element = originalCreateElement.call(this, tagName, ...args);
            if (tagName.toLowerCase() === 'iframe') {{
                try {{
                    Object.defineProperty(element, 'contentWindow', {{
                        get: function() {{
                            return window;
                        }}
                    }});
                    Object.defineProperty(element, 'contentDocument', {{
                        get: function() {{
                            return document;
                        }}
                    }});
                }} catch (e) {{}}
            }}
            return element;
        }};

        // 12. toString patch
        const originalToString = Function.prototype.toString;
        Function.prototype.toString = function() {{
            if (this === Function.prototype.toString) return 'function toString() {{ [native code] }}';
            if (this === navigator.permissions.query) return 'function query() {{ [native code] }}';
            return originalToString.call(this);
        }};

        // 13. Document attributes
        Object.defineProperty(document, 'documentElement', {{
            get: () => document.querySelector('html')
        }});

        // 14. Webdriver property check bypass
        delete navigator.__proto__.webdriver;

        console.log('[Stealth] Anti-detection scripts loaded successfully');
        """


# ============================================================================
# ADVANCED PLAYWRIGHT SCRAPER
# ============================================================================

class AdvancedLicenseScraper:
    """
    license.gov.uz uchun maxsus advanced scraper
    """

    def __init__(self, headless: bool = True, use_proxy: bool = False):
        self.headless = headless
        self.use_proxy = use_proxy
        self.browser = None
        self.context = None
        self.page = None
        self.fingerprint = FingerprintManager().generate()
        self.captured_api_data = []

    async def init(self):
        """Browser ni ishga tushirish"""
        from playwright.async_api import async_playwright

        self.playwright = await async_playwright().start()

        # Launch options
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--disable-gpu",
            f"--window-size={self.fingerprint.viewport['width']},{self.fingerprint.viewport['height']}",
            "--start-maximized",
            "--hide-scrollbars",
            "--disable-notifications",
            "--disable-extensions",
            "--disable-default-apps",
            "--no-first-run",
            "--no-default-browser-check",
            "--password-store=basic",
            "--use-mock-keychain",
            "--force-color-profile=srgb",
            "--mute-audio",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-features=TranslateUI",
            "--disable-component-extensions-with-background-pages",
            "--disable-bundled-ppapi-flash",
            "--disable-plugins-discovery",
            "--disable-logging",
            "--disable-breakpad",
            "--disable-sync",
            "--disable-translate",
            "--metrics-recording-only",
            "--safebrowsing-disable-auto-update",
            "--no-pings",
            "--font-render-hinting=none",
        ]

        launch_options = {
            "headless": self.headless,
            "args": launch_args,
        }

        if self.use_proxy:
            launch_options["proxy"] = {"server": "http://proxy.example.com:8080"}

        self.browser = await self.playwright.chromium.launch(**launch_options)

        # Context options
        context_options = {
            "viewport": self.fingerprint.viewport,
            "user_agent": self.fingerprint.user_agent,
            "locale": "uz-UZ",
            "timezone_id": self.fingerprint.timezone,
            "color_scheme": "light",
            "geolocation": {"latitude": 41.2995, "longitude": 69.2401},  # Tashkent
            "permissions": ["geolocation"],
            "extra_http_headers": {
                "Accept-Language": "uz-UZ,uz;q=0.9,ru;q=0.8,en-US;q=0.7,en;q=0.6",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
                "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            }
        }

        self.context = await self.browser.new_context(**context_options)

        # Add stealth script
        await self.context.add_init_script(
            StealthScripts.get_full_stealth_script(self.fingerprint)
        )

        # Setup request/response interception
        await self._setup_interception()

        self.page = await self.context.new_page()

        logger.info(f"✅ Advanced Scraper ishga tushdi")
        logger.info(f"   User-Agent: {self.fingerprint.user_agent[:50]}...")
        logger.info(f"   Viewport: {self.fingerprint.viewport}")

    async def _setup_interception(self):
        """API interception sozlash"""

        async def handle_route(route, request):
            url = request.url

            # Log API requests
            if "api.licenses.uz" in url:
                logger.debug(f"🌐 API Request: {url[:100]}...")

            await route.continue_()

        async def handle_response(response):
            url = response.url

            # Capture API responses
            if "api.licenses.uz" in url and "/register/open_source" in url:
                try:
                    body = await response.body()
                    data = json.loads(body.decode('utf-8'))
                    self.captured_api_data.append({
                        "url": url,
                        "status": response.status,
                        "data": data,
                        "timestamp": datetime.now().isoformat()
                    })
                    logger.info(f"📡 API Response captured: {url[:80]}...")
                except Exception as e:
                    logger.warning(f"API parse error: {e}")

        self.context.on("response", handle_response)

    async def human_like_behavior(self):
        """Real foydalanuvchi xatti-harakatlari"""
        # Random scroll
        for _ in range(random.randint(2, 5)):
            scroll_y = random.randint(100, 500)
            await self.page.evaluate(f"window.scrollBy(0, {scroll_y})")
            await asyncio.sleep(random.uniform(0.5, 1.5))

        # Random mouse movements
        for _ in range(random.randint(3, 7)):
            x = random.randint(100, 800)
            y = random.randint(100, 600)
            await self.page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.1, 0.3))

    async def goto(self, url: str, wait_for: str = None, timeout: int = 60000):
        """Sahifaga o'tish"""
        try:
            response = await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)

            # Wait for specific selector
            if wait_for:
                await self.page.wait_for_selector(wait_for, timeout=timeout)
            else:
                await self.page.wait_for_load_state("networkidle")

            # Human-like behavior
            await self.human_like_behavior()

            return {
                "success": True,
                "status": response.status if response else None,
                "url": self.page.url,
                "title": await self.page.title()
            }

        except Exception as e:
            logger.error(f"Navigation error: {e}")
            return {
                "success": False,
                "error": str(e),
                "url": url
            }

    async def extract_data(self) -> Dict[str, Any]:
        """Sahifadan ma'lumot olish"""
        try:
            # Get page info
            title = await self.page.title()
            url = self.page.url

            # Get all text content
            text_content = await self.page.evaluate("() => document.body.innerText")

            # Get links
            links = await self.page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a')).map(a => ({
                    text: a.innerText,
                    href: a.href
                }));
            }""")

            # Get API data if captured
            api_data = self.captured_api_data.copy()

            return {
                "success": True,
                "title": title,
                "url": url,
                "text_length": len(text_content),
                "links_count": len(links),
                "api_responses": len(api_data),
                "api_data": api_data[:3]  # First 3 API responses
            }

        except Exception as e:
            logger.error(f"Extract error: {e}")
            return {"success": False, "error": str(e)}

    async def screenshot(self, path: str):
        """Screenshot olish"""
        await self.page.screenshot(path=path, full_page=True)
        logger.info(f"📸 Screenshot saqlandi: {path}")

    async def save_api_data(self, path: str):
        """API ma'lumotlarini saqlash"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.captured_api_data, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 API data saqlandi: {path}")

    async def close(self):
        """Browser ni yopish"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("🔒 Browser yopildi")


# ============================================================================
# TEST FUNCTIONS
# ============================================================================

async def run_comprehensive_test():
    """To'liq test"""
    print("""
    ╔══════════════════════════════════════════════════════════════════════╗
    ║        LICENSE.GOV.UZ - ADVANCED SCRAPER TEST                       ║
    ║        Comprehensive Anti-Bot Bypass Testing                        ║
    ╚══════════════════════════════════════════════════════════════════════╝
    """)

    scraper = AdvancedLicenseScraper(headless=True)

    try:
        await scraper.init()

        # Test 1: Bot Detection
        print("\n" + "=" * 60)
        print("🧪 TEST 1: Bot Detection (bot.sannysoft.com)")
        print("=" * 60)
        result = await scraper.goto("https://bot.sannysoft.com", timeout=60000)
        print(f"   Status: {'✅ SUCCESS' if result['success'] else '❌ FAILED'}")
        print(f"   URL: {result.get('url', 'N/A')}")
        print(f"   Title: {result.get('title', 'N/A')}")

        if result['success']:
            await scraper.screenshot("/mnt/okcomputer/output/test1_bot_detection.png")
            data = await scraper.extract_data()
            print(f"   Content length: {data.get('text_length', 0)} chars")

        # Test 2: PixelScan
        print("\n" + "=" * 60)
        print("🧪 TEST 2: PixelScan (pixelscan.net)")
        print("=" * 60)
        result = await scraper.goto("https://pixelscan.net", timeout=60000)
        print(f"   Status: {'✅ SUCCESS' if result['success'] else '❌ FAILED'}")

        if result['success']:
            await scraper.screenshot("/mnt/okcomputer/output/test2_pixelscan.png")

        # Test 3: BrowserLeaks WebGL
        print("\n" + "=" * 60)
        print("🧪 TEST 3: BrowserLeaks WebGL (browserleaks.com/webgl)")
        print("=" * 60)
        result = await scraper.goto("https://browserleaks.com/webgl", timeout=60000)
        print(f"   Status: {'✅ SUCCESS' if result['success'] else '❌ FAILED'}")

        if result['success']:
            await scraper.screenshot("/mnt/okcomputer/output/test3_webgl.png")

        # Test 4: Real Target - license.gov.uz
        print("\n" + "=" * 60)
        print("🧪 TEST 4: Real Target (license.gov.uz)")
        print("=" * 60)

        # First warmup with a neutral site
        print("   🔄 Warming up...")
        await scraper.goto("https://www.google.com", timeout=30000)
        await asyncio.sleep(2)

        # Now go to target
        result = await scraper.goto(REGISTRY_URL, wait_for="body", timeout=90000)
        print(f"   Status: {'✅ SUCCESS' if result['success'] else '❌ FAILED'}")
        print(f"   URL: {result.get('url', 'N/A')}")
        print(f"   Title: {result.get('title', 'N/A')}")

        if result['success']:
            await scraper.screenshot("/mnt/okcomputer/output/test4_license_gov_uz.png")

            # Extract data
            data = await scraper.extract_data()
            print(f"\n   📊 Extracted Data:")
            print(f"      Text length: {data.get('text_length', 0)} chars")
            print(f"      Links found: {data.get('links_count', 0)}")
            print(f"      API responses captured: {data.get('api_responses', 0)}")

            # Save API data
            if data.get('api_data'):
                await scraper.save_api_data("/mnt/okcomputer/output/api_data.json")

                for i, api in enumerate(data['api_data'][:2]):
                    print(f"\n      API #{i + 1}:")
                    print(f"         URL: {api['url'][:60]}...")
                    print(f"         Status: {api['status']}")
                    if isinstance(api['data'], dict):
                        print(f"         Data keys: {list(api['data'].keys())}")

        # Test 5: Check for Cloudflare/Protection
        print("\n" + "=" * 60)
        print("🧪 TEST 5: Protection Detection")
        print("=" * 60)

        content = await scraper.page.content()

        protection_signals = {
            "Cloudflare": "cf-browser-verification" in content or "__cf_bm" in content,
            "DataDome": "datadome" in content.lower(),
            "PerimeterX": "perimeterx" in content.lower() or "px-captcha" in content,
            "reCAPTCHA": "g-recaptcha" in content or "google.com/recaptcha" in content,
            "hCaptcha": "hcaptcha" in content.lower(),
        }

        for protection, detected in protection_signals.items():
            status = "⚠️ DETECTED" if detected else "✅ NOT DETECTED"
            print(f"   {protection}: {status}")

    except Exception as e:
        logger.error(f"Test error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await scraper.close()

    print("\n" + "=" * 60)
    print("✅ Barcha testlar yakunlandi!")
    print("=" * 60)


async def test_multiple_fingerprints():
    """Bir nechta fingerprint bilan test"""
    print("\n" + "=" * 60)
    print("🧪 MULTI-FINGERPRINT TEST")
    print("=" * 60)

    for i in range(3):
        print(f"\n--- Fingerprint #{i + 1} ---")

        scraper = AdvancedLicenseScraper(headless=True)

        try:
            await scraper.init()
            result = await scraper.goto("https://bot.sannysoft.com", timeout=60000)

            print(f"   Status: {'✅' if result['success'] else '❌'}")
            print(f"   UA: {scraper.fingerprint.user_agent[:50]}...")
            print(f"   Viewport: {scraper.fingerprint.viewport}")

            if result['success']:
                await scraper.screenshot(f"/mnt/okcomputer/output/multi_fp_{i + 1}.png")

        except Exception as e:
            print(f"   Error: {e}")
        finally:
            await scraper.close()

        await asyncio.sleep(2)


# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Asosiy funksiya"""

    # Create output directory
    Path("/mnt/okcomputer/output").mkdir(parents=True, exist_ok=True)

    # Run comprehensive test
    await run_comprehensive_test()

    # Run multi-fingerprint test
    # await test_multiple_fingerprints()


if __name__ == "__main__":
    asyncio.run(main())