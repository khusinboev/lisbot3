#!/usr/bin/env python3
"""
================================================================================
LICENSE.GOV.UZ - API CAPTURE & SCREENSHOT TOOL
================================================================================
Maqsad: https://license.gov.uz/registry sahifasiga kirish va 
https://api.licenses.uz/v1/register/open_source API dan JSON ma'lumot olish

Xususiyatlar:
- Full-page screenshot
- API response interception
- Anti-bot bypass (Playwright Stealth)
- JSON auto-save
================================================================================
"""

import asyncio
import json
import random
import time
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# ============================================================================
# KERAKLI PAKETLARNI TEKSHIRISH
# ============================================================================

def check_dependencies():
    """Kerakli paketlarni tekshirish"""
    required = {
        "playwright": "pip install playwright",
        "playwright_stealth": "pip install playwright-stealth",
    }
    
    missing = []
    for module, install_cmd in required.items():
        try:
            __import__(module)
        except ImportError:
            missing.append((module, install_cmd))
    
    if missing:
        print("❌ Quyidagi paketlar o'rnatilmagan:")
        for pkg, cmd in missing:
            print(f"   - {pkg}: {cmd}")
        print("\n📦 O'rnatish uchun:")
        print("   pip install playwright playwright-stealth")
        print("   playwright install chromium")
        return False
    return True

# ============================================================================
# STEALTH SCRIPT - MAXIMUM ANTI-DETECTION
# ============================================================================

STEALTH_SCRIPT = """
// Core anti-detection
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 2 },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '', length: 2 },
        { name: 'Native Client', filename: 'internal-nacl-plugin', description: '', length: 2 }
    ]
});
Object.defineProperty(navigator, 'languages', { get: () => ['uz-UZ', 'ru', 'en-US', 'en'] });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'vendor', { get: () => 'Google Inc.' });

// Chrome object
window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {}
};

// Permissions API
const originalQuery = navigator.permissions.query;
navigator.permissions.query = (parameters) => {
    if (parameters.name === 'notifications') {
        return Promise.resolve({ state: Notification.permission });
    }
    return originalQuery(parameters);
};

// Canvas fingerprint noise
const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
CanvasRenderingContext2D.prototype.getImageData = function(...args) {
    const imageData = originalGetImageData.apply(this, args);
    const data = imageData.data;
    for (let i = 0; i < data.length; i += 4) {
        data[i] += Math.random() > 0.5 ? 1 : -1;
        data[i+1] += Math.random() > 0.5 ? 1 : -1;
        data[i+2] += Math.random() > 0.5 ? 1 : -1;
    }
    return imageData;
};

// WebGL spoof
const originalGetContext = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(type, ...args) {
    const context = originalGetContext.call(this, type, ...args);
    if (context && (type.includes('webgl'))) {
        const originalGetParameter = context.getParameter;
        context.getParameter = function(param) {
            if (param === 37445) return 'Intel Inc.';
            if (param === 37446) return 'Intel Iris OpenGL Engine';
            return originalGetParameter.call(this, param);
        };
    }
    return context;
};

console.log('[Stealth] Anti-detection loaded');
"""

# ============================================================================
# MAIN SCRAPER CLASS
# ============================================================================

class LicenseCaptureScraper:
    """
    license.gov.uz uchun maxsus scraper
    API interception + Full screenshot
    """
    
    TARGET_URL = "https://license.gov.uz/registry?filter%5Bdocument_id%5D=4409&filter%5Bdocument_type%5D=LICENSE"
    API_PATTERN = "api.licenses.uz/v1/register/open_source"
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None
        self.captured_api_data: List[Dict] = []
        self.playwright = None
        
    async def init(self):
        """Browser ni ishga tushirish"""
        from playwright.async_api import async_playwright
        
        self.playwright = await async_playwright().start()
        
        # Browser launch options - MAXIMUM STEALTH
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--disable-gpu",
            "--window-size=1920,1080",
            "--start-maximized",
            "--hide-scrollbars",
            "--disable-notifications",
            "--disable-extensions",
            "--no-first-run",
            "--no-default-browser-check",
            "--password-store=basic",
            "--force-color-profile=srgb",
            "--mute-audio",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-features=TranslateUI",
            "--disable-bundled-ppapi-flash",
            "--no-pings",
        ]
        
        if self.headless:
            launch_args.append("--headless=new")
        
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=launch_args
        )
        
        # Context with realistic settings
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="uz-UZ",
            timezone_id="Asia/Tashkent",
            color_scheme="light",
            extra_http_headers={
                "Accept-Language": "uz-UZ,uz;q=0.9,ru;q=0.8,en-US;q=0.7,en;q=0.6",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
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
        )
        
        # Add stealth script
        await self.context.add_init_script(STEALTH_SCRIPT)
        
        # Setup API interception
        await self._setup_api_interception()
        
        self.page = await self.context.new_page()
        
        print("✅ Browser ishga tushdi")
        print(f"   User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)...")
        print(f"   Viewport: 1920x1080")
        
    async def _setup_api_interception(self):
        """API interception sozlash"""
        
        async def handle_route(route, request):
            """Har bir request ni tekshirish"""
            url = request.url
            
            # API request ni log qilish
            if self.API_PATTERN in url:
                print(f"🌐 API Request detected: {url[:80]}...")
            
            await route.continue_()
        
        # Route handler ni qo'shish
        await self.context.route("**/*", handle_route)
        
        # Response handler
        async def handle_response(response):
            """Har bir response ni tekshirish"""
            url = response.url
            
            if self.API_PATTERN in url:
                print(f"📡 API Response: {url[:80]}...")
                print(f"   Status: {response.status}")
                
                try:
                    body = await response.body()
                    
                    # Try to parse as JSON
                    try:
                        json_data = json.loads(body.decode('utf-8'))
                        self.captured_api_data.append({
                            "url": url,
                            "status": response.status,
                            "timestamp": datetime.now().isoformat(),
                            "data": json_data
                        })
                        print(f"   ✅ JSON parsed successfully!")
                        
                        # Print summary
                        if isinstance(json_data, dict):
                            if 'data' in json_data and isinstance(json_data['data'], dict):
                                inner = json_data['data']
                                print(f"   📊 Total items: {inner.get('totalItems', 'N/A')}")
                                print(f"   📄 Total pages: {inner.get('totalPages', 'N/A')}")
                                certs = inner.get('certificates', [])
                                print(f"   📋 Certificates in page: {len(certs)}")
                                
                    except json.JSONDecodeError:
                        print(f"   ⚠️ Response is not JSON")
                        self.captured_api_data.append({
                            "url": url,
                            "status": response.status,
                            "timestamp": datetime.now().isoformat(),
                            "raw_body": body.decode('utf-8', errors='ignore')[:500]
                        })
                        
                except Exception as e:
                    print(f"   ❌ Error reading response: {e}")
        
        self.context.on("response", handle_response)
        
    async def human_behavior(self):
        """Real foydalanuvchi xatti-harakatlari"""
        # Random scroll
        for _ in range(random.randint(2, 4)):
            scroll_y = random.randint(200, 600)
            await self.page.evaluate(f"window.scrollBy(0, {scroll_y})")
            await asyncio.sleep(random.uniform(0.5, 1.5))
        
        # Random mouse movements
        for _ in range(random.randint(3, 5)):
            x = random.randint(200, 1000)
            y = random.randint(200, 700)
            await self.page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.2, 0.5))
    
    async def capture(self, output_dir: str = "/mnt/okcomputer/output") -> Dict[str, Any]:
        """
        Asosiy capture funksiyasi
        
        Returns:
            {
                "success": bool,
                "screenshot_path": str,
                "api_data_path": str or None,
                "api_count": int,
                "error": str or None
            }
        """
        result = {
            "success": False,
            "screenshot_path": None,
            "api_data_path": None,
            "api_count": 0,
            "error": None
        }
        
        # Create output directory
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        try:
            print("\n" + "="*60)
            print("🚀 Sahifaga o'tish boshlandi")
            print("="*60)
            print(f"🌐 URL: {self.TARGET_URL}")
            
            # Navigate to page
            start_time = time.time()
            
            response = await self.page.goto(
                self.TARGET_URL,
                wait_until="networkidle",
                timeout=90000
            )
            
            load_time = time.time() - start_time
            print(f"\n⏱️  Sahifa yuklanish vaqti: {load_time:.2f} soniya")
            print(f"📊 Response status: {response.status if response else 'N/A'}")
            print(f"🔗 Final URL: {self.page.url}")
            
            # Wait for API calls
            print("\n⏳ API javoblari kutilmoqda...")
            await asyncio.sleep(3)
            
            # Human behavior simulation
            print("🎭 Human behavior simulation...")
            await self.human_behavior()
            
            # Wait a bit more for any remaining API calls
            await asyncio.sleep(2)
            
            # Take full-page screenshot
            print("\n📸 Full-page screenshot olinmoqda...")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{output_dir}/license_gov_uz_{timestamp}.png"
            
            await self.page.screenshot(
                path=screenshot_path,
                full_page=True
            )
            
            result["screenshot_path"] = screenshot_path
            print(f"   ✅ Screenshot saqlandi: {screenshot_path}")
            
            # Save API data
            api_count = len(self.captured_api_data)
            result["api_count"] = api_count
            
            if api_count > 0:
                api_data_path = f"{output_dir}/api_data_{timestamp}.json"
                
                with open(api_data_path, 'w', encoding='utf-8') as f:
                    json.dump(self.captured_api_data, f, ensure_ascii=False, indent=2)
                
                result["api_data_path"] = api_data_path
                result["success"] = True
                
                print(f"\n✅ API ma'lumotlari saqlandi: {api_data_path}")
                print(f"   Jami API javoblari: {api_count}")
                
                # Print first API summary
                first_api = self.captured_api_data[0]
                if 'data' in first_api and isinstance(first_api['data'], dict):
                    data = first_api['data']
                    if 'data' in data and isinstance(data['data'], dict):
                        inner = data['data']
                        print(f"\n📋 Birinchi API ma'lumotlari:")
                        print(f"   Jami elementlar: {inner.get('totalItems', 'N/A')}")
                        print(f"   Jami sahifalar: {inner.get('totalPages', 'N/A')}")
                        print(f"   Joriy sahifa: {inner.get('currentPage', 'N/A')}")
                        certs = inner.get('certificates', [])
                        print(f"   Sertifikatlar soni: {len(certs)}")
                        
                        if certs:
                            print(f"\n   Birinchi sertifikat:")
                            first_cert = certs[0]
                            print(f"      Nomi: {first_cert.get('name', 'N/A')}")
                            print(f"      STIR: {first_cert.get('tin', 'N/A')}")
                            print(f"      Raqam: {first_cert.get('number', 'N/A')}")
                            
            else:
                result["error"] = "API ma'lumotlari olinmadi"
                print(f"\n❌ API ma'lumotlari olinmadi!")
                print(f"   Sayt anti-bot himoyeasi ishlatilayotgan bo'lishi mumkin.")
                
        except Exception as e:
            result["error"] = str(e)
            print(f"\n❌ Xato yuz berdi: {e}")
            import traceback
            traceback.print_exc()
            
        return result
    
    async def close(self):
        """Browser ni yopish"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        print("\n🔒 Browser yopildi")


# ============================================================================
# ALTERNATIVE METHOD: CDP-BASED CAPTURE
# ============================================================================

async def capture_with_cdp(output_dir: str = "/mnt/okcomputer/output") -> Dict[str, Any]:
    """
    Chrome DevTools Protocol orqali capture
    Bu usul ba'zi hollarda samaraliroq
    """
    from playwright.async_api import async_playwright
    
    result = {
        "success": False,
        "screenshot_path": None,
        "api_data_path": None,
        "api_count": 0,
        "error": None
    }
    
    TARGET_URL = "https://license.gov.uz/registry?filter%5Bdocument_id%5D=4409&filter%5Bdocument_type%5D=LICENSE"
    API_PATTERN = "api.licenses.uz/v1/register/open_source"
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    async with async_playwright() as p:
        # Launch with CDP enabled
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--remote-debugging-port=0",
            ]
        )
        
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        
        await context.add_init_script(STEALTH_SCRIPT)
        
        page = await context.new_page()
        
        # Enable request/response logging via CDP
        client = await page.context.new_cdp_session(page)
        
        api_data = []
        
        # Listen to all responses
        page.on("response", lambda response: asyncio.create_task(
            handle_cdp_response(response, api_data, API_PATTERN)
        ))
        
        try:
            print("\n" + "="*60)
            print("🚀 CDP Method: Sahifaga o'tish")
            print("="*60)
            
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=90000)
            
            print(f"🔗 Final URL: {page.url}")
            
            # Wait for API
            await asyncio.sleep(5)
            
            # Screenshot
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{output_dir}/license_cdp_{timestamp}.png"
            await page.screenshot(path=screenshot_path, full_page=True)
            result["screenshot_path"] = screenshot_path
            print(f"📸 Screenshot: {screenshot_path}")
            
            # Save API data
            if api_data:
                api_data_path = f"{output_dir}/api_data_cdp_{timestamp}.json"
                with open(api_data_path, 'w', encoding='utf-8') as f:
                    json.dump(api_data, f, ensure_ascii=False, indent=2)
                result["api_data_path"] = api_data_path
                result["api_count"] = len(api_data)
                result["success"] = True
                print(f"✅ API data: {api_data_path}")
            else:
                result["error"] = "No API data captured"
                print("❌ No API data captured")
                
        except Exception as e:
            result["error"] = str(e)
            print(f"❌ Error: {e}")
            
        finally:
            await browser.close()
            
    return result


async def handle_cdp_response(response, api_data, api_pattern):
    """CDP response handler"""
    if api_pattern in response.url:
        try:
            body = await response.body()
            json_data = json.loads(body.decode('utf-8'))
            api_data.append({
                "url": response.url,
                "status": response.status,
                "data": json_data
            })
            print(f"📡 API captured: {response.url[:60]}...")
        except:
            pass


# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Asosiy funksiya"""
    
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║        LICENSE.GOV.UZ - API CAPTURE TOOL                            ║
╚══════════════════════════════════════════════════════════════════════╝
    """)
    
    # Check dependencies
    if not check_dependencies():
        return
    
    output_dir = "/mnt/okcomputer/output"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Method 1: Standard Playwright Stealth
    print("\n" + "="*60)
    print("🔧 METHOD 1: Playwright Stealth")
    print("="*60)
    
    scraper = LicenseCaptureScraper(headless=True)
    
    try:
        await scraper.init()
        result1 = await scraper.capture(output_dir)
    except Exception as e:
        print(f"❌ Method 1 failed: {e}")
        result1 = {"success": False, "error": str(e)}
    finally:
        await scraper.close()
    
    # Print results
    print("\n" + "="*60)
    print("📊 METHOD 1 RESULTS")
    print("="*60)
    print(f"Success: {'✅ YES' if result1['success'] else '❌ NO'}")
    print(f"Screenshot: {result1.get('screenshot_path', 'N/A')}")
    print(f"API Data: {result1.get('api_data_path', 'N/A')}")
    print(f"API Count: {result1.get('api_count', 0)}")
    if result1.get('error'):
        print(f"Error: {result1['error']}")
    
    # If Method 1 failed, try Method 2
    if not result1['success']:
        print("\n" + "="*60)
        print("🔧 METHOD 2: CDP-Based Capture")
        print("="*60)
        
        try:
            result2 = await capture_with_cdp(output_dir)
            
            print("\n" + "="*60)
            print("📊 METHOD 2 RESULTS")
            print("="*60)
            print(f"Success: {'✅ YES' if result2['success'] else '❌ NO'}")
            print(f"Screenshot: {result2.get('screenshot_path', 'N/A')}")
            print(f"API Data: {result2.get('api_data_path', 'N/A')}")
            print(f"API Count: {result2.get('api_count', 0)}")
            if result2.get('error'):
                print(f"Error: {result2['error']}")
        except Exception as e:
            print(f"❌ Method 2 also failed: {e}")
    
    # Final summary
    print("\n" + "="*60)
    print("📋 FINAL SUMMARY")
    print("="*60)
    
    if result1['success']:
        print("✅ SUCCESS: API data captured using Method 1")
        print(f"   📁 Output directory: {output_dir}")
        print(f"   📸 Screenshot: {result1['screenshot_path']}")
        print(f"   💾 API JSON: {result1['api_data_path']}")
    else:
        print("❌ FAILED: Could not capture API data")
        print("   Possible reasons:")
        print("   - Site has strong anti-bot protection")
        print("   - Network issues")
        print("   - API endpoint changed")
    
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
