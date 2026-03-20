#!/usr/bin/env python3
"""
================================================================================
LICENSE.GOV.UZ - ULTIMATE CAPTURE TOOL
================================================================================
Eng kuchli usullarni birlashtirgan yakuniy versiya:
1. Playwright Stealth (Method 1)
2. Undetected ChromeDriver (Method 2)

Maqsad: https://license.gov.uz/registry sahifasidan
https://api.licenses.uz/v1/register/open_source API dan JSON olish

Natijalar:
- Full-page screenshot (PNG)
- API JSON data
================================================================================
"""

import asyncio
import json
import time
import random
import os
import sys
import base64
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

# ============================================================================
# RESULT DATA CLASS
# ============================================================================

@dataclass
class CaptureResult:
    method: str
    success: bool
    screenshot_path: Optional[str]
    api_data_path: Optional[str]
    api_count: int
    error: Optional[str]
    timestamp: str


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def print_header(text: str):
    print("\n" + "="*70)
    print(f" {text}")
    print("="*70)

def print_success(text: str):
    print(f"✅ {text}")

def print_error(text: str):
    print(f"❌ {text}")

def print_info(text: str):
    print(f"ℹ️  {text}")

def print_warning(text: str):
    print(f"⚠️  {text}")


# ============================================================================
# METHOD 1: PLAYWRIGHT STEALTH
# ============================================================================

class PlaywrightCapture:
    """Playwright Stealth bilan capture"""
    
    TARGET_URL = "https://license.gov.uz/registry?filter%5Bdocument_id%5D=4409&filter%5Bdocument_type%5D=LICENSE"
    API_PATTERN = "api.licenses.uz/v1/register/open_source"
    
    STEALTH_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            { name: 'Native Client', filename: 'internal-nacl-plugin' }
        ]
    });
    Object.defineProperty(navigator, 'languages', { get: () => ['uz-UZ', 'ru', 'en-US', 'en'] });
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
    Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
    window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {}, app: {} };
    """
    
    def __init__(self):
        self.api_data: List[Dict] = []
        
    async def capture(self, output_dir: str) -> CaptureResult:
        from playwright.async_api import async_playwright
        
        result = CaptureResult(
            method="Playwright Stealth",
            success=False,
            screenshot_path=None,
            api_data_path=None,
            api_count=0,
            error=None,
            timestamp=datetime.now().isoformat()
        )
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-web-security",
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--window-size=1920,1080",
                        "--hide-scrollbars",
                        "--disable-notifications",
                        "--no-first-run",
                    ]
                )
                
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    locale="uz-UZ",
                    timezone_id="Asia/Tashkent",
                )
                
                await context.add_init_script(self.STEALTH_SCRIPT)
                
                # API interception
                self.api_data = []
                context.on("response", lambda r: asyncio.create_task(self._handle_response(r)))
                
                page = await context.new_page()
                
                print_info("Sahifaga o'tish...")
                await page.goto(self.TARGET_URL, wait_until="networkidle", timeout=90000)
                
                print_info("Kutish (API javoblar uchun)...")
                await asyncio.sleep(5)
                
                # Screenshot
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = f"{output_dir}/license_pw_{ts}.png"
                await page.screenshot(path=screenshot_path, full_page=True)
                result.screenshot_path = screenshot_path
                print_success(f"Screenshot: {screenshot_path}")
                
                # Save API data
                if self.api_data:
                    api_path = f"{output_dir}/api_data_pw_{ts}.json"
                    with open(api_path, 'w', encoding='utf-8') as f:
                        json.dump(self.api_data, f, ensure_ascii=False, indent=2)
                    result.api_data_path = api_path
                    result.api_count = len(self.api_data)
                    result.success = True
                    print_success(f"API data: {api_path}")
                else:
                    result.error = "No API data captured"
                    print_error("No API data captured")
                
                await browser.close()
                
        except Exception as e:
            result.error = str(e)
            print_error(f"Playwright error: {e}")
            
        return result
    
    async def _handle_response(self, response):
        if self.API_PATTERN in response.url:
            try:
                body = await response.body()
                json_data = json.loads(body.decode('utf-8'))
                self.api_data.append({
                    "url": response.url,
                    "status": response.status,
                    "data": json_data
                })
                print_success(f"API captured: {response.url[:50]}...")
            except:
                pass


# ============================================================================
# METHOD 2: UNDETECTED CHROMEDRIVER
# ============================================================================

class UCCapture:
    """Undetected ChromeDriver bilan capture"""
    
    TARGET_URL = "https://license.gov.uz/registry?filter%5Bdocument_id%5D=4409&filter%5Bdocument_type%5D=LICENSE"
    API_PATTERN = "api.licenses.uz/v1/register/open_source"
    
    def capture(self, output_dir: str) -> CaptureResult:
        import undetected_chromedriver as uc
        
        result = CaptureResult(
            method="Undetected ChromeDriver",
            success=False,
            screenshot_path=None,
            api_data_path=None,
            api_count=0,
            error=None,
            timestamp=datetime.now().isoformat()
        )
        
        driver = None
        
        try:
            options = uc.ChromeOptions()
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--headless=new")
            
            options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
            
            driver = uc.Chrome(options=options)
            driver.set_page_load_timeout(90)
            
            print_info("Sahifaga o'tish...")
            driver.get(self.TARGET_URL)
            time.sleep(5)
            
            # Extract API from logs
            print_info("API javoblarni olish...")
            api_data = self._extract_api(driver)
            
            # Screenshot
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{output_dir}/license_uc_{ts}.png"
            driver.save_screenshot(screenshot_path)
            result.screenshot_path = screenshot_path
            print_success(f"Screenshot: {screenshot_path}")
            
            # Save API data
            if api_data:
                api_path = f"{output_dir}/api_data_uc_{ts}.json"
                with open(api_path, 'w', encoding='utf-8') as f:
                    json.dump(api_data, f, ensure_ascii=False, indent=2)
                result.api_data_path = api_path
                result.api_count = len(api_data)
                result.success = True
                print_success(f"API data: {api_path}")
            else:
                result.error = "No API data captured"
                print_error("No API data captured")
                
        except Exception as e:
            result.error = str(e)
            print_error(f"UC error: {e}")
            
        finally:
            if driver:
                driver.quit()
                
        return result
    
    def _extract_api(self, driver) -> List[Dict]:
        api_data = []
        try:
            logs = driver.get_log("performance")
            for entry in logs:
                msg = json.loads(entry["message"])["message"]
                if msg["method"] == "Network.responseReceived":
                    resp = msg["params"]["response"]
                    url = resp["url"]
                    if self.API_PATTERN in url:
                        try:
                            body = driver.execute_cdp_cmd(
                                "Network.getResponseBody",
                                {"requestId": msg["params"]["requestId"]}
                            )
                            body_text = body.get("body", "")
                            if body.get("base64Encoded"):
                                body_text = base64.b64decode(body_text).decode("utf-8")
                            json_data = json.loads(body_text)
                            api_data.append({"url": url, "status": resp["status"], "data": json_data})
                            print_success(f"API captured: {url[:50]}...")
                        except:
                            pass
        except Exception as e:
            print_error(f"Log extraction error: {e}")
        return api_data


# ============================================================================
# MAIN
# ============================================================================

async def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║     LICENSE.GOV.UZ - ULTIMATE CAPTURE TOOL                          ║
║     Playwright + Undetected ChromeDriver                            ║
╚══════════════════════════════════════════════════════════════════════╝
    """)
    
    output_dir = "/mnt/okcomputer/output"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    results: List[CaptureResult] = []
    
    # Method 1: Playwright
    print_header("METHOD 1: Playwright Stealth")
    try:
        pw = PlaywrightCapture()
        result1 = await pw.capture(output_dir)
        results.append(result1)
    except Exception as e:
        print_error(f"Method 1 failed: {e}")
        results.append(CaptureResult(
            method="Playwright Stealth",
            success=False,
            screenshot_path=None,
            api_data_path=None,
            api_count=0,
            error=str(e),
            timestamp=datetime.now().isoformat()
        ))
    
    # Method 2: Undetected ChromeDriver
    print_header("METHOD 2: Undetected ChromeDriver")
    try:
        uc = UCCapture()
        result2 = uc.capture(output_dir)
        results.append(result2)
    except Exception as e:
        print_error(f"Method 2 failed: {e}")
        results.append(CaptureResult(
            method="Undetected ChromeDriver",
            success=False,
            screenshot_path=None,
            api_data_path=None,
            api_count=0,
            error=str(e),
            timestamp=datetime.now().isoformat()
        ))
    
    # Summary
    print_header("FINAL SUMMARY")
    
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    
    print(f"\n📊 Results:")
    print(f"   ✅ Successful: {len(successful)}")
    print(f"   ❌ Failed: {len(failed)}")
    
    if successful:
        print(f"\n🏆 BEST RESULT:")
        best = max(successful, key=lambda r: r.api_count)
        print(f"   Method: {best.method}")
        print(f"   Screenshot: {best.screenshot_path}")
        print(f"   API Data: {best.api_data_path}")
        print(f"   API Count: {best.api_count}")
        
        # Print API summary
        if best.api_data_path and Path(best.api_data_path).exists():
            with open(best.api_data_path, 'r') as f:
                data = json.load(f)
                if data and len(data) > 0:
                    first = data[0]
                    if 'data' in first and 'data' in first['data']:
                        inner = first['data']['data']
                        print(f"\n📋 API Summary:")
                        print(f"   Total Items: {inner.get('totalItems', 'N/A')}")
                        print(f"   Total Pages: {inner.get('totalPages', 'N/A')}")
                        certs = inner.get('certificates', [])
                        print(f"   Certificates: {len(certs)}")
                        if certs:
                            print(f"\n   First Certificate:")
                            print(f"      Name: {certs[0].get('name', 'N/A')}")
                            print(f"      TIN: {certs[0].get('tin', 'N/A')}")
                            print(f"      Number: {certs[0].get('number', 'N/A')}")
    else:
        print_error("\nAll methods failed!")
        print("Possible reasons:")
        print("  - Site has strong anti-bot protection")
        print("  - Network issues")
        print("  - Chrome not installed")
        print("  - Missing dependencies")
    
    print_header("OUTPUT FILES")
    print(f"Directory: {output_dir}")
    files = list(Path(output_dir).glob("license_*.png")) + list(Path(output_dir).glob("api_data_*.json"))
    for f in sorted(files)[-6:]:  # Show last 6 files
        size = f.stat().st_size
        print(f"  📁 {f.name} ({size:,} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
