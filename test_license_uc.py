#!/usr/bin/env python3
"""
================================================================================
LICENSE.GOV.UZ - UNDETECTED CHROMEDRIVER CAPTURE
================================================================================
undetected-chromedriver bilan API capture
Bu usul ba'zi hollarda Playwright dan samaraliroq
================================================================================
"""

import json
import time
import random
import os
import sys
import base64
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# ============================================================================
# CHECK DEPENDENCIES
# ============================================================================

def check_uc():
    """undetected-chromedriver ni tekshirish"""
    try:
        import undetected_chromedriver as uc
        return True
    except ImportError:
        print("❌ undetected-chromedriver o'rnatilmagan!")
        print("   pip install undetected-chromedriver selenium")
        return False

# ============================================================================
# UC SCRAPER
# ============================================================================

class UCScraper:
    """
    undetected-chromedriver bilan scraper
    """
    
    TARGET_URL = "https://license.gov.uz/registry?filter%5Bdocument_id%5D=4409&filter%5Bdocument_type%5D=LICENSE"
    API_PATTERN = "api.licenses.uz/v1/register/open_source"
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None
        self.api_data: List[Dict] = []
        
    def init(self):
        """Driver ni ishga tushirish"""
        import undetected_chromedriver as uc
        from selenium.webdriver.chrome.options import Options
        
        options = uc.ChromeOptions()
        
        # Anti-detection options
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-features=IsolateOrigins,site-per-process")
        options.add_argument("--disable-site-isolation-trials")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")
        options.add_argument("--hide-scrollbars")
        options.add_argument("--disable-notifications")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--password-store=basic")
        options.add_argument("--use-mock-keychain")
        
        if self.headless:
            options.add_argument("--headless=new")
        
        # Enable performance logging for API interception
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        
        # Create unique profile
        profile_dir = Path.home() / ".uc_profiles" / f"profile_{random.randint(10000, 99999)}"
        profile_dir.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={profile_dir}")
        
        # Create driver
        self.driver = uc.Chrome(options=options, version_main=None)
        self.driver.set_page_load_timeout(90)
        
        print("✅ Undetected Chrome ishga tushdi")
        
    def extract_api_from_logs(self) -> List[Dict]:
        """Performance log dan API javoblarini olish"""
        import json
        
        api_data = []
        
        try:
            logs = self.driver.get_log("performance")
            
            for entry in logs:
                try:
                    message = json.loads(entry["message"])["message"]
                    
                    if message["method"] == "Network.responseReceived":
                        response = message["params"]["response"]
                        url = response["url"]
                        
                        if self.API_PATTERN in url:
                            request_id = message["params"]["requestId"]
                            status = response["status"]
                            
                            print(f"📡 API detected: {url[:80]}...")
                            print(f"   Status: {status}")
                            
                            # Get response body
                            try:
                                body = self.driver.execute_cdp_cmd(
                                    "Network.getResponseBody",
                                    {"requestId": request_id}
                                )
                                
                                body_text = body.get("body", "")
                                if body.get("base64Encoded"):
                                    body_text = base64.b64decode(body_text).decode("utf-8")
                                
                                if body_text:
                                    json_data = json.loads(body_text)
                                    api_data.append({
                                        "url": url,
                                        "status": status,
                                        "timestamp": datetime.now().isoformat(),
                                        "data": json_data
                                    })
                                    print(f"   ✅ JSON captured!")
                                    
                            except Exception as e:
                                print(f"   ⚠️ Could not get body: {e}")
                                
                except Exception:
                    continue
                    
        except Exception as e:
            print(f"⚠️ Log extraction error: {e}")
            
        return api_data
    
    def human_behavior(self):
        """Human-like behavior"""
        from selenium.webdriver.common.action_chains import ActionChains
        
        # Random scroll
        for _ in range(random.randint(2, 4)):
            scroll_y = random.randint(200, 600)
            self.driver.execute_script(f"window.scrollBy(0, {scroll_y})")
            time.sleep(random.uniform(0.5, 1.5))
        
        # Random mouse movements
        actions = ActionChains(self.driver)
        for _ in range(random.randint(3, 5)):
            x = random.randint(200, 1000)
            y = random.randint(200, 700)
            actions.move_by_offset(x, y)
            actions.perform()
            time.sleep(random.uniform(0.2, 0.5))
    
    def capture(self, output_dir: str = "/mnt/okcomputer/output") -> Dict[str, Any]:
        """Asosiy capture funksiyasi"""
        
        result = {
            "success": False,
            "screenshot_path": None,
            "api_data_path": None,
            "api_count": 0,
            "error": None
        }
        
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        try:
            print("\n" + "="*60)
            print("🚀 Sahifaga o'tish boshlandi (UC)")
            print("="*60)
            print(f"🌐 URL: {self.TARGET_URL}")
            
            # Navigate
            start_time = time.time()
            self.driver.get(self.TARGET_URL)
            
            # Wait for page load
            time.sleep(5)
            
            load_time = time.time() - start_time
            print(f"\n⏱️  Sahifa yuklanish vaqti: {load_time:.2f} soniya")
            print(f"🔗 Current URL: {self.driver.current_url}")
            print(f"📄 Title: {self.driver.title}")
            
            # Human behavior
            print("\n🎭 Human behavior simulation...")
            self.human_behavior()
            
            # Wait for API calls
            time.sleep(3)
            
            # Extract API from logs
            print("\n📡 API javoblarni log dan olish...")
            self.api_data = self.extract_api_from_logs()
            
            # Take screenshot
            print("\n📸 Full-page screenshot olinmoqda...")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{output_dir}/license_uc_{timestamp}.png"
            
            # Full page screenshot
            original_size = self.driver.get_window_size()
            total_height = self.driver.execute_script("return document.body.scrollHeight")
            self.driver.set_window_size(1920, total_height)
            self.driver.save_screenshot(screenshot_path)
            self.driver.set_window_size(original_size['width'], original_size['height'])
            
            result["screenshot_path"] = screenshot_path
            print(f"   ✅ Screenshot saqlandi: {screenshot_path}")
            
            # Save API data
            api_count = len(self.api_data)
            result["api_count"] = api_count
            
            if api_count > 0:
                api_data_path = f"{output_dir}/api_data_uc_{timestamp}.json"
                
                with open(api_data_path, 'w', encoding='utf-8') as f:
                    json.dump(self.api_data, f, ensure_ascii=False, indent=2)
                
                result["api_data_path"] = api_data_path
                result["success"] = True
                
                print(f"\n✅ API ma'lumotlari saqlandi: {api_data_path}")
                print(f"   Jami API javoblari: {api_count}")
                
                # Print summary
                first_api = self.api_data[0]
                if 'data' in first_api and isinstance(first_api['data'], dict):
                    data = first_api['data']
                    if 'data' in data and isinstance(data['data'], dict):
                        inner = data['data']
                        print(f"\n📋 Birinchi API ma'lumotlari:")
                        print(f"   Jami elementlar: {inner.get('totalItems', 'N/A')}")
                        print(f"   Jami sahifalar: {inner.get('totalPages', 'N/A')}")
                        certs = inner.get('certificates', [])
                        print(f"   Sertifikatlar soni: {len(certs)}")
                        
            else:
                result["error"] = "API ma'lumotlari olinmadi"
                print(f"\n❌ API ma'lumotlari olinmadi!")
                
        except Exception as e:
            result["error"] = str(e)
            print(f"\n❌ Xato yuz berdi: {e}")
            import traceback
            traceback.print_exc()
            
        return result
    
    def close(self):
        """Driver ni yopish"""
        if self.driver:
            self.driver.quit()
        print("\n🔒 Driver yopildi")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Asosiy funksiya"""
    
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║     LICENSE.GOV.UZ - UNDETECTED CHROMEDRIVER CAPTURE                ║
╚══════════════════════════════════════════════════════════════════════╝
    """)
    
    if not check_uc():
        return
    
    output_dir = "/mnt/okcomputer/output"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    scraper = UCScraper(headless=True)
    
    try:
        scraper.init()
        result = scraper.capture(output_dir)
    except Exception as e:
        print(f"❌ Xato: {e}")
        result = {"success": False, "error": str(e)}
    finally:
        scraper.close()
    
    # Print results
    print("\n" + "="*60)
    print("📊 RESULTS")
    print("="*60)
    print(f"Success: {'✅ YES' if result['success'] else '❌ NO'}")
    print(f"Screenshot: {result.get('screenshot_path', 'N/A')}")
    print(f"API Data: {result.get('api_data_path', 'N/A')}")
    print(f"API Count: {result.get('api_count', 0)}")
    if result.get('error'):
        print(f"Error: {result['error']}")
    print("="*60)


if __name__ == "__main__":
    main()
