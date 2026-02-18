from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
import threading
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import os


_CHROMEDRIVER_PATH = None
_CHROMEDRIVER_LOCK = threading.Lock()

def _get_chromedriver_path():
    """Singleton pattern để chỉ install driver 1 lần duy nhất."""
    global _CHROMEDRIVER_PATH
    if _CHROMEDRIVER_PATH:
        return _CHROMEDRIVER_PATH
    with _CHROMEDRIVER_LOCK:
        if not _CHROMEDRIVER_PATH:
            # Use bundled chromedriver.exe
            current_dir = os.path.dirname(os.path.abspath(__file__))
            chromedriver_path = os.path.join(current_dir, 'chromedriver.exe')
            if os.path.exists(chromedriver_path):
                _CHROMEDRIVER_PATH = chromedriver_path
            else:
                raise FileNotFoundError(f"chromedriver.exe not found at {chromedriver_path}")
    return _CHROMEDRIVER_PATH

def ensure_chromedriver():
    return _get_chromedriver_path()

def get_driver(headless=True , window_rect=None, user_data_dir=None):
    options = Options()
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    if headless:
        options.add_argument("--headless=new") 
        
    if user_data_dir:
        options.add_argument(f"--user-data-dir={user_data_dir}")

    if not headless and window_rect:
        x, y, w, h = window_rect
        # Set vị trí và kích thước cửa sổ
        options.add_argument(f"--window-position={x},{y}")
        options.add_argument(f"--window-size={w},{h}")
    elif not headless:
        options.add_argument("--start-maximized")
    
    #   --- PERFORMANCE OPTIMIZATION FLAGS ---
    options.add_argument("--disable-notifications")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-web-security")
    options.add_argument("--allow-running-insecure-content")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-translate")
    options.add_argument("--hide-scrollbars")
    options.add_argument("--metrics-recording-only")
    options.add_argument("--mute-audio")
    options.add_argument("--no-crash-upload")
    options.add_argument("--disable-logging")
    options.add_argument("--disable-dev-tools")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    
    # Block images for speed
    options.add_argument("--blink-settings=imagesEnabled=false")
    
    # Disk optimizations
    options.add_argument("--disable-application-cache")
    options.add_argument("--disk-cache-size=0")
    options.add_argument("--log-level=3")
    
    # Prevent renderer timeout
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-hang-monitor")
    options.add_argument("--disable-ipc-flooding-protection")
    
    # Memory and stability options
    options.add_argument("--max_old_space_size=4096")
    options.add_argument("--memory-pressure-off")
    options.add_argument("--disable-low-end-device-mode")
    
    options.page_load_strategy = 'eager'
    
    # Updated user agent for Chrome 130+
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
    
    try:
        service = Service(_get_chromedriver_path())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        driver.set_page_load_timeout(60) 
        driver.set_script_timeout(60)
        return driver
    except Exception as e:
        error_msg = str(e)
        if "ected token" in error_msg or "stacktrace" in error_msg.lower():
            print("Chrome compatibility error detected. This might be due to Chrome version mismatch.")
            print("Try updating Chrome to a stable version or check ChromeDriver compatibility.")
            print(f"Current Chrome version: 144.0.7559.110")
        print(f"Error creating Chrome driver: {error_msg}")
        raise e

def parse_cookie_string(cookie_str):
    cookies = []
    try:
        if not cookie_str:
            return cookies
        pairs = cookie_str.split(';')
        for pair in pairs:
            if '=' in pair:
                key, value = pair.strip().split('=', 1)
                cookies.append({
                    'name': key, 
                    'value': value, 
                    'domain': '.instagram.com', 
                    'path': '/'
                })
    except Exception as e:
        print(f"Cookie parse error: {e}")
    return cookies

# --- WAITING HELPERS ---

def wait_dom_ready(driver, timeout=5, poll=0.1):
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            if driver.execute_script("return document.readyState") == "complete":
                # Also check if body element exists
                driver.find_element(By.TAG_NAME, "body")
                return True
        except Exception:
            pass
        time.sleep(poll)
    return False

def wait_element(driver, by, value, timeout=10, poll=0.1, visible=True):
    end_time = time.time() + timeout
    last_found = None
    while time.time() < end_time:
        try:
            elements = driver.find_elements(by, value)
            for el in elements:
                # Chờ element thực sự hiển thị và có thể tương tác
                for _ in range(10):
                    if not visible or (el.is_displayed() and el.is_enabled()):
                        return el
                    time.sleep(0.1)
                last_found = el
        except Exception:
            pass
        time.sleep(poll)
    # Nếu hết thời gian mà vẫn chưa clickable, trả về phần tử cuối cùng tìm thấy (nếu có)
    return last_found

def wait_and_click(driver, by, value, timeout=10, poll=0.1):
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            el = driver.find_element(by, value)
            # Scroll element into view to ensure it's not obscured
            driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", el)
            # Chờ element thực sự hiển thị và có thể tương tác
            for _ in range(10):
                if el.is_displayed() and el.is_enabled():
                    try:
                        el.click()
                        return True
                    except Exception:
                        # Try ActionChains move and click
                        try:
                            ActionChains(driver).move_to_element(el).click().perform()
                            return True
                        except Exception:
                            pass
                time.sleep(0.1)
            # Nếu click thường lỗi, thử JS Click ngay tại đây để cứu vãn
            try:
                driver.execute_script("arguments[0].click();", el)
                return True
            except:
                pass
        except Exception:
            pass
        time.sleep(poll)
    return False

def wait_and_send_keys(driver, by, value, keys, timeout=10, poll=0.1, clear_first=True):
    el = wait_element(driver, by, value, timeout=timeout, poll=poll, visible=True) 
    if not el:
        return False 
    if clear_first:
        try:
            el.clear()
        except Exception:
            pass
    try:
        el.send_keys(keys)
        return True
    except Exception:
        return False