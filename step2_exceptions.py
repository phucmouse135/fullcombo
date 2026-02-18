# step2_exceptions.py
import time
import re
import random
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
# Import ActionChains for advanced interactions
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from step3_post_login import InstagramPostLoginStep as step3_post_login

# Import các hàm utils
from config_utils import wait_element, wait_and_send_keys, wait_dom_ready, wait_and_click
from mail_handler_v2 import get_verify_code_v2
from step1_login import InstagramLoginStep as step1_login

class InstagramExceptionStep:
    def __init__(self, driver):
        self.driver = driver
        # Callback for password change, can be set externally
        # Ensure it's always callable
        if hasattr(self, '_default_on_password_changed'):
            self.on_password_changed = self._default_on_password_changed
        else:
            # Fallback if method doesn't exist
            self.on_password_changed = lambda username, new_password: print(f"   [Step 2] Password changed for {username}: {new_password[:3]}***")
        # Instance of step1 login
        self.step1_login = step1_login(self.driver)
        # Instance of step3 post login
        self.step3_post_login = step3_post_login(self.driver)
        
    def _default_on_password_changed(self, username, new_password):
        """Default callback for password changes - does nothing."""
        print(f"   [Step 2] Password changed for {username}: {new_password[:3]}***")

    def _safe_execute_script(self, script, *args, default=None, retries=2):
        """Execute JS script with retry on timeout errors."""
        for attempt in range(retries + 1):
            try:
                return self.driver.execute_script(script, *args)
            except Exception as e:
                error_str = str(e).lower()
                if "timeout" in error_str or "renderer" in error_str or "receiving message" in error_str:
                    print(f"   [Step 2] JS renderer timeout on attempt {attempt+1}, retrying...")
                    time.sleep(2)  # Longer sleep
                    continue
                else:
                    print(f"   [Step 2] JS error: {e}")
                    return default
        print(f"   [Step 2] JS failed after {retries+1} attempts, returning default")
        return default

    def _check_status_change_with_timeout(self, initial_status, timeout=15):
        """Check if status changes within timeout, else redirect to instagram.com"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            current_status = self._check_verification_result()
            if current_status != initial_status:
                return current_status
            time.sleep(1)
        print(f"   [Step 2] Status unchanged after {timeout}s, redirecting to instagram.com")
        self.driver.get("https://www.instagram.com/")
        WebDriverWait(self.driver, 10).until(lambda d: self._safe_execute_script("return document.readyState") == "complete")
        time.sleep(2)
        return self._check_verification_result()

    def _robust_click_button(self, selectors, timeout=20, retries=3):
        """Robust button clicking with multiple selectors and retries."""
        # First, ensure page is loaded
        try:
            WebDriverWait(self.driver, 5).until(lambda d: self._safe_execute_script("return document.readyState") == "complete")
            self.driver.find_element(By.TAG_NAME, "body")  # Check if body exists
        except Exception as e:
            print(f"   [Step 2] Page not ready for clicking: {e}")
            return False
        
        print(f"   [Step 2] Attempting to click button with {len(selectors)} selectors...")
        for attempt in range(retries):
            for selector_type, sel in selectors:
                try:
                    print(f"   [Step 2] Trying selector: {selector_type} - {sel[:50]}...")
                    if selector_type == "xpath":
                        element = WebDriverWait(self.driver, timeout).until(
                            EC.element_to_be_clickable((By.XPATH, sel))
                        )
                    elif selector_type == "css":
                        element = WebDriverWait(self.driver, timeout).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                        )
                    elif selector_type == "js":
                        # For JS selector, execute the script, which may return the element or perform the action
                        result = self._safe_execute_script(sel)
                        if result:
                            if hasattr(result, 'click'):  # If it's a WebElement
                                self._safe_execute_script("arguments[0].click();", result)
                            print(f"   [Step 2] Clicked button via JS selector on attempt {attempt+1}")
                            return True
                    else:
                        continue
                    
                    if element:
                        # Try Selenium click first
                        try:
                            element.click()
                            print(f"   [Step 2] Clicked button via {selector_type}: {sel[:50]}... on attempt {attempt+1}")
                            return True
                        except Exception as click_e:
                            print(f"   [Step 2] Selenium click failed, trying JS: {click_e}")
                            # Fallback to JS click
                            try:
                                self._safe_execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", element)
                                print(f"   [Step 2] Clicked button via JS fallback on attempt {attempt+1}")
                                return True
                            except Exception as js_e:
                                print(f"   [Step 2] JS click failed: {js_e}")
                except Exception as e:
                    print(f"   [Step 2] Failed to find/click button {selector_type}: {sel[:50]}... - {str(e)[:100]}")
            time.sleep(1)  # Wait before retry
        print(f"   [Step 2] Failed to click button after {retries} attempts with all selectors")
        return False

    def _detect_page_change(self, initial_url=None, initial_title=None, timeout=5):
        """Detect if page has changed/refreshed within timeout period."""
        if initial_url is None:
            initial_url = self.driver.current_url
        if initial_title is None:
            try:
                initial_title = self.driver.title
            except:
                initial_title = None

        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                current_url = self.driver.current_url
                current_title = self.driver.title
                ready_state = self.driver.execute_script("return document.readyState")

                if current_url != initial_url:
                    print(f"   [Step 2] Page URL changed: {initial_url} -> {current_url}")
                    return True, "url_changed"
                if current_title != initial_title and initial_title is not None:
                    print(f"   [Step 2] Page title changed: {initial_title} -> {current_title}")
                    return True, "title_changed"
                if ready_state == "complete":
                    return False, "page_stable"
            except Exception as e:
                print(f"   [Step 2] Error detecting page change: {e}")
                return True, "error_checking"

            time.sleep(0.5)

        return False, "timeout"

    # ==========================================
    # 1. HELPER: VALIDATE MASKED EMAIL
    # ==========================================
    def _is_driver_alive(self):
        try:
            # Gửi lệnh nhẹ để check kết nối (lấy title hoặc url)
            _ = self.driver.current_url
            return True
        except:
            return False
    def _check_mask_match(self, real_email, masked_hint):
        if not real_email or "@" not in real_email: return False
        try:
            real_user, real_domain = real_email.lower().strip().split("@")
            mask_user, mask_domain = masked_hint.lower().strip().split("@")
            
            if mask_domain[0] != '*' and mask_domain[0] != real_domain[0]: return False
            if "." in mask_domain:
                if mask_domain.split('.')[-1] != real_domain.split('.')[-1]: return False
            if mask_user[0] != '*' and mask_user[0] != real_user[0]: return False
            
            return True
        except: return False

    def _validate_masked_email_robust(self, primary_email, secondary_email=None):
        try:
            # [RETRY] Thử lấy body text 2 lần phòng trường hợp chưa load xong hoặc stale element
            body_text = ""
            for _ in range(2):  # Reduced from 3 to 2 attempts
                try:
                    body_text = self.driver.find_element(By.TAG_NAME, "body").text
                    if "@" in body_text: break
                except Exception as e:
                    error_str = str(e).lower()
                    if "stale" in error_str or ("element" in error_str and "reference" in error_str):
                        print("   [2FA] Stale element when getting body text, retrying...")
                        time.sleep(0.5)
                        continue
                    else:
                        time.sleep(0.5)  # For other errors, still retry
            
            match = re.search(r'\b([a-zA-Z0-9][\w\*]*@[\w\*]+\.[a-zA-Z\.]+)\b', body_text)
            if not match: return True 
            masked = match.group(1).lower().strip()
            print(f"   [2FA] Detected Hint: {masked}")
            
            is_primary = self._check_mask_match(primary_email, masked)
            is_secondary = secondary_email and self._check_mask_match(secondary_email, masked)
            
            if is_primary or is_secondary: return True
            print(f"   [CRITICAL] Hint {masked} mismatch with {primary_email} / {secondary_email}")
            return False
        except: return True
        
    def _detect_stuck_on_profile_selection(self):
        """
        Thủ công kiểm tra nếu trang hiện tại có text 'use another profile' hoặc 'log into instagram',
        hoặc các dấu hiệu stuck ở trang chọn profile, trả về True để tự động reload và login lại.
        """
        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            if ("use another profile" in body_text or "log into instagram" in body_text or "switch accounts" in body_text):
                print("   [Step 2] [Manual Detect] Stuck on profile selection page!")
                return True
        except Exception as e:
            error_str = str(e).lower()
            if "stale" in error_str or ("element" in error_str and "reference" in error_str):
                print("   [Step 2] [Manual Detect] Stale element when checking profile selection, assuming not stuck")
            else:
                print(f"   [Step 2] [Manual Detect] Error checking stuck profile selection: {e}")
        return False

    # ==========================================
    # 2. MAIN ROUTING (HANDLE STATUS)
    # ==========================================
    def _handle_require_password_change(self, new_password):
        # Timeout protection for password change (max 60s)
        start_time = time.time()
        TIMEOUT = 60
        print(f"   [Step 2] Handling Require Password Change (New password: {new_password})...")
        try:
            # Tìm chính xác 2 input theo id với wait để tránh lỗi element not found
            new_pass_input = wait_element(self.driver, By.ID, "new_password1", timeout=20)
            if not new_pass_input:
                # Fallback: thử các selector khác nếu id thay đổi
                fallback_selectors = [
                    "input[name='new_password']",
                    "input[type='password']",
                    "input[placeholder*='new password']",
                    "input[placeholder*='mật khẩu mới']"
                ]
                for sel in fallback_selectors:
                    new_pass_input = wait_element(self.driver, By.CSS_SELECTOR, sel, timeout=5)
                    if new_pass_input:
                        print(f"   [Step 2] Found new password input via fallback selector: {sel}")
                        break
                if not new_pass_input:
                    raise Exception("Could not find new password input field")
            
            confirm_pass_input = wait_element(self.driver, By.ID, "new_password2", timeout=20)
            if not confirm_pass_input:
                # Fallback cho confirm password
                confirm_fallback_selectors = [
                    "input[name='confirm_password']",
                    "input[name='new_password_confirm']",
                    "input[type='password']:nth-of-type(2)",  # Giả sử ô thứ 2
                    "input[placeholder*='confirm']",
                    "input[placeholder*='xác nhận']"
                ]
                for sel in confirm_fallback_selectors:
                    confirm_pass_input = wait_element(self.driver, By.CSS_SELECTOR, sel, timeout=5)
                    if confirm_pass_input:
                        print(f"   [Step 2] Found confirm password input via fallback selector: {sel}")
                        break
                if not confirm_pass_input:
                    print("   [Step 2] Could not find confirm password input, using same input for both")
                    confirm_pass_input = new_pass_input  # Fallback: dùng cùng ô nếu không tìm thấy
            
            # Nhập password với multiple fallback strategies để tránh stale element
            input_success = False
            for input_attempt in range(3):
                try:
                    # Strategy 1: Direct Selenium input
                    if new_pass_input is None:
                        print(f"   [Step 2] New password input is None, skipping attempt {input_attempt+1}")
                        continue
                    new_pass_input.clear()
                    new_pass_input.send_keys(new_password)
                    print(f"   [Step 2] Entered new password in first field (attempt {input_attempt+1})")
                    time.sleep(1)

                    if confirm_pass_input is not None and confirm_pass_input != new_pass_input:
                        confirm_pass_input.clear()
                        confirm_pass_input.send_keys(new_password)
                        print(f"   [Step 2] Entered confirm password in second field (attempt {input_attempt+1})")
                        time.sleep(1)

                    # Verify input was successful
                    if new_pass_input.get_attribute('value') == new_password:
                        input_success = True
                        print(f"   [Step 2] Password input verified successful")
                        break
                    else:
                        print(f"   [Step 2] Password input verification failed, value: '{new_pass_input.get_attribute('value')}'")
                        continue

                except Exception as e:
                    error_str = str(e).lower()
                    if "stale" in error_str or ("element" in error_str and "reference" in error_str):
                        print(f"   [Step 2] Stale element during password input (attempt {input_attempt+1}): {e}")

                        # Strategy 2: Re-find elements and retry
                        try:
                            time.sleep(2)
                            # Re-find password inputs
                            new_pass_input = wait_element(self.driver, By.ID, "new_password1", timeout=10)
                            if not new_pass_input:
                                new_pass_input = wait_element(self.driver, By.CSS_SELECTOR, "input[type='password']", timeout=10)

                            if new_pass_input:
                                confirm_pass_input = wait_element(self.driver, By.ID, "new_password2", timeout=5)
                                if not confirm_pass_input:
                                    confirm_pass_input = new_pass_input  # Use same input if confirm not found

                                print(f"   [Step 2] Re-found password inputs, retrying input...")
                                continue  # Retry the input loop
                            else:
                                print(f"   [Step 2] Could not re-find password inputs after stale element")
                        except Exception as refind_e:
                            print(f"   [Step 2] Error re-finding elements: {refind_e}")

                        # Strategy 3: JavaScript input as last resort
                        try:
                            print(f"   [Step 2] Trying JavaScript input fallback...")
                            # Find inputs via JavaScript
                            js_script = """
                                var inputs = document.querySelectorAll('input[type="password"]');
                                if (inputs.length >= 1) {
                                    inputs[0].value = arguments[0];
                                    inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
                                    inputs[0].dispatchEvent(new Event('change', { bubbles: true }));
                                    if (inputs.length >= 2) {
                                        inputs[1].value = arguments[0];
                                        inputs[1].dispatchEvent(new Event('input', { bubbles: true }));
                                        inputs[1].dispatchEvent(new Event('change', { bubbles: true }));
                                    }
                                    return true;
                                }
                                return false;
                            """
                            js_result = self.driver.execute_script(js_script, new_password)
                            if js_result:
                                print(f"   [Step 2] JavaScript password input successful")
                                input_success = True
                                break
                            else:
                                print(f"   [Step 2] JavaScript input failed - no password inputs found")
                        except Exception as js_e:
                            print(f"   [Step 2] JavaScript input error: {js_e}")

                        continue  # Try next input attempt
                    else:
                        # Non-stale error, re-raise
                        raise e

            if not input_success:
                raise Exception("Failed to input password after all attempts and strategies")

            # Wait for page to stabilize after password input
            print(f"   [Step 2] Waiting for page stabilization after password input...")
            time.sleep(2)

            # Check if page has changed/refreshed by monitoring URL and readyState
            initial_url = self.driver.current_url
            initial_ready_state = self.driver.execute_script("return document.readyState")

            # Wait up to 10 seconds for any page changes to complete
            for wait_attempt in range(10):
                time.sleep(1)
                try:
                    current_url = self.driver.current_url
                    current_ready_state = self.driver.execute_script("return document.readyState")

                    if current_ready_state == "complete" and current_url != initial_url:
                        print(f"   [Step 2] Page changed/refreshed to: {current_url}")
                        # Wait a bit more for dynamic content to load
                        time.sleep(2)
                        break
                    elif current_ready_state == "complete":
                        print(f"   [Step 2] Page stabilized, ready to proceed")
                        break
                except Exception as e:
                    print(f"   [Step 2] Error checking page state: {e}")
                    break

            # Additional wait for any client-side validation
            time.sleep(2)

            # Nhấn nút Next với comprehensive stale element handling
            next_clicked = False
            next_selectors = [
                (By.XPATH, "//button[contains(text(), 'Next')]"),
                (By.XPATH, "//button[contains(text(), 'Tiếp')]"),
                (By.CSS_SELECTOR, "div[role='button'][tabindex='0']"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//button[contains(@class, 'x1i10hfl')]"),
                (By.CSS_SELECTOR, "div.x1i10hfl.xjqpnuy.xc5r6h4.xqeqjp1.x1phubyo.x972fbf.x10w94by.x1qhh985.x14e42zd.xdl72j9.x2lah0s.x3ct3a4.xdj266r.x14z9mp.xat24cr.x1lziwak.x2lwn1j.xeuugli.xexx8yu.x18d9i69.x1hl2dhg.xggy1nq.x1ja2u2z.x1t137rt.x1q0g3np.x1lku1pv.x1a2a7pz.x6s0dn4.xjyslct.x1obq294.x5a5i1n.xde0f50.x15x8krk.x1ejq31n.x18oe1m7.x1sy0etr.xstzfhl.x9f619.x9bdzbf.x1ypdohk.x1f6kntn.xwhw2v2.x10w6t97.xl56j7k.x17ydfre.xf7dkkf.xv54qhq.x1n2onr6.x2b8uid.xlyipyv.x87ps6o.x5c86q.x18br7mf.x1i0vuye.xh8yej3.x18cabeq.x158me93.xk4oym4.x1uugd1q.x3nfvp2")
            ]

            # JavaScript click as ultimate fallback
            js_click_script = """
                var buttons = document.querySelectorAll('button, div[role="button"], input[type="submit"]');
                for (var i = 0; i < buttons.length; i++) {
                    var btn = buttons[i];
                    if (btn.offsetParent !== null && (btn.textContent.toLowerCase().includes('next') ||
                        btn.textContent.toLowerCase().includes('tiếp') ||
                        btn.value.toLowerCase().includes('next'))) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            """

            for attempt in range(5):  # Increased retries for stale elements
                print(f"   [Step 2] Next button attempt {attempt+1}/5")

                # Try Selenium selectors first
                for by, sel in next_selectors:
                    try:
                        next_btns = self.driver.find_elements(by, sel)
                        for btn in next_btns:
                            if btn.is_displayed() and btn.is_enabled():
                                try:
                                    btn.click()
                                    print(f"   [Step 2] Clicked Next via Selenium: {sel}")
                                    next_clicked = True
                                    break
                                except Exception as click_e:
                                    error_str = str(click_e).lower()
                                    if "stale" in error_str:
                                        print(f"   [Step 2] Stale element during click, continuing to next selector...")
                                        continue
                                    try:
                                        # Try JS click on this specific element
                                        self.driver.execute_script("arguments[0].click();", btn)
                                        print(f"   [Step 2] Clicked Next via JS fallback on element: {sel}")
                                        next_clicked = True
                                        break
                                    except Exception as js_e:
                                        print(f"   [Step 2] JS click failed: {js_e}")
                                        continue
                        if next_clicked:
                            break
                    except Exception as e:
                        error_str = str(e).lower()
                        if "stale" in error_str:
                            print(f"   [Step 2] Stale element when finding button {sel}, continuing...")
                            continue
                        else:
                            print(f"   [Step 2] Error with selector {sel}: {e}")
                            continue
                    if next_clicked:
                        break

                if next_clicked:
                    break

                # If Selenium failed, try JavaScript approach
                if not next_clicked:
                    try:
                        js_result = self.driver.execute_script(js_click_script)
                        if js_result:
                            print(f"   [Step 2] Clicked Next via JavaScript fallback (attempt {attempt+1})")
                            next_clicked = True
                            break
                        else:
                            print(f"   [Step 2] JavaScript click found no suitable buttons (attempt {attempt+1})")
                    except Exception as js_e:
                        print(f"   [Step 2] JavaScript click error: {js_e}")

                # Wait between attempts, but not after the last one
                if attempt < 4 and not next_clicked:
                    print(f"   [Step 2] Next button not found, waiting 2s before retry...")
                    time.sleep(2)

                if time.time() - start_time > TIMEOUT:
                    raise Exception("TIMEOUT_REQUIRE_PASSWORD_CHANGE: Next button find")

            if not next_clicked:
                print("   [Step 2] Could not find Next button after password change (all methods tried).")
                raise Exception("Could not find Next button after password change")
                
            if time.time() - start_time > TIMEOUT:
                raise Exception("TIMEOUT_REQUIRE_PASSWORD_CHANGE: End")
            
            # Sau khi nhấn Next, chờ page load hoàn toàn
            WebDriverWait(self.driver, 15).until(lambda d: d.execute_script("return document.readyState") == "complete")
            time.sleep(3)  # Extra wait for any redirects
            
            try:
                # Kiểm tra driver còn sống và page đã load
                current_url = self.driver.current_url
                print(f"   [Step 2] Post-Next URL: {current_url}")
                WebDriverWait(self.driver, 10).until(lambda d: d.execute_script("return document.readyState") == "complete")
            except Exception as crash_e:
                print(f"   [Step 2] Crash detected after Next click: {crash_e}. Reloading to instagram.com...")
                self.driver.get("https://www.instagram.com/")
                WebDriverWait(self.driver, 10).until(lambda d: d.execute_script("return document.readyState") == "complete")
                time.sleep(2)
                return  # Hoặc raise tùy logic
        except Exception as e:
            print(f"   [Step 2] Error handling require password change: {e}")
            raise e
    def handle_status(self, status, ig_username, gmx_user, gmx_pass, linked_mail=None, ig_password=None, depth=0):
        # Chống đệ quy vô tận (giới hạn 20 bước nhảy trạng thái)
        if depth > 20:
             raise Exception("STOP_FLOW_LOOP: Max recursion depth reached")
        print(f"   [{ig_username}] [Step 2] Processing status: {status}")
        if not self._is_driver_alive():
            raise Exception("STOP_FLOW_CRASH: Browser Closed")

        # GET_HELP_LOG_IN
        if status == "GET_HELP_LOG_IN":
            # fail 
            print(f"   [{ig_username}] [Step 2] Detected 'Get Help Logging In' - Failing out of flow.")
            raise Exception("GET_HELP_LOG_IN")

        success_statuses = [
            "LOGGED_IN_SUCCESS", "COOKIE_CONSENT", "TERMS_AGREEMENT", 
            "NEW_MESSAGING_TAB", "SUCCESS"
        ]
        if status in success_statuses:
            print(f"   [{ig_username}] [Step 2] Success status reached: {status}")
            return status
        
        
        # DATA_PROCESSING_FOR_ADS
        if status == "DATA_PROCESSING_FOR_ADS":
            print(f"   [{ig_username}] [Step 2] Handling Data Processing For Ads...")
            # click not now 
            self._robust_click_button([
                ("js", """
                    var buttons = document.querySelectorAll('button, [role=\"button\"], div[role=\"button\"]');
                    for (var i=0; i<buttons.length; i++) {
                        var text = buttons[i].textContent.trim().toLowerCase();
                        if (text.includes('no') || text.includes('decline') || text.includes('don\\'t allow') ||
                            text.includes('not now') || text.includes('skip') || text.includes('dismiss') ||
                            text.includes('không') || text.includes('từ chối') || text.includes('bỏ qua')) {
                            return buttons[i];
                        }
                    }
                    return null;
                """),
                ("css", "button[data-testid*='not-now'], button[aria-label*='not now']"),
                ("css", "div[role='button'][tabindex='0']"),
                ("css", "div[role='button']"),
                ("css", "button")  # Last resort - any button
            ])
            time.sleep(2)
            wait_dom_ready(self.driver, timeout=20)

            # redirect to instagram home to bypass
            self.driver.get("https://www.instagram.com/")
            WebDriverWait(self.driver, 10).until(lambda d: d.execute_script("return document.readyState") == "complete")
            time.sleep(2)
            new_status = self._check_verification_result()
            if new_status == status:
                print(f"   [{ig_username}] [Step 2] Status unchanged after handling Data Processing For Ads, trying to navigate away")
                new_status = self._check_status_change_with_timeout(status, 15)
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
        
            
        
        # "REAL_BIRTHDAY_REQUIRED"
        if status == "REAL_BIRTHDAY_REQUIRED":
            # reload instagram to trigger birthday screen
            print(f"   [{ig_username}] [Step 2] Handling Real Birthday Required - Reloading Instagram...")
            self.driver.get("https://www.instagram.com/")
            WebDriverWait(self.driver, 10).until(lambda d: d.execute_script("return document.readyState") == "complete")
            new_status = self._check_verification_result()
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
        
        # COOKIE_CONSENT_POPUP
        if status == "COOKIE_CONSENT_POPUP":
            print(f"   [{ig_username}] [Step 2] Handling Cookie Consent Popup...")
            self.step3_post_login._handle_cookie_consent()
            time.sleep(2)
            
            wait_dom_ready(self.driver, timeout=10)
            new_status = self._check_verification_result()
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
        
        # CONFIRM_TRUSTED_DEVICE
        if status == "CONFIRM_TRUSTED_DEVICE":
            print(f"   [{ig_username}] [Step 2] Handling Confirm Trusted Device...")
            # Click "Close" button using robust method with more selectors
            success = self._robust_click_button([
                ("js", """
                    var buttons = document.querySelectorAll('button, [role=\"button\"], div[role=\"button\"]');
                    for (var i = 0; i < buttons.length; i++) {
                        var text = buttons[i].textContent.trim().toLowerCase();
                        if (text.includes('close') || text.includes('x') || text.includes('cancel') ||
                            text.includes('not now') || text.includes('skip') || text.includes('dismiss')) {
                            return buttons[i];
                        }
                    }
                    // Also check for close icons (SVG/X)
                    var closeIcons = document.querySelectorAll('svg[aria-label*=\"close\"], svg[aria-label*=\"x\"], button svg');
                    if (closeIcons.length > 0) {
                        return closeIcons[0].closest('button') || closeIcons[0];
                    }
                    return null;
                """),
                ("css", "div.x1i10hfl.xjqpnuy.xc5r6h4.xqeqjp1.x1phubyo.x972fbf.x10w94by.x1qhh985.x14e42zd.xdl72j9.x2lah0s.x3ct3a4.xdj266r.x14z9mp.xat24cr.x1lziwak.x2lwn1j.xeuugli.xexx8yu.x18d9i69.x1hl2dhg.xggy1nq.x1ja2u2z.x1t137rt.x1q0g3np.x1lku1pv.x1a2a7pz.x6s0dn4.xjyslct.x1obq294.x5a5i1n.xde0f50.x15x8krk.x1ejq31n.x18oe1m7.x1sy0etr.xstzfhl.x9f619.x1ypdohk.x1f6kntn.xwhw2v2.x10w6t97.xl56j7k.x17ydfre.xf7dkkf.xv54qhq.x1n2onr6.x2b8uid.xlyipyv.x87ps6o.x5c86q.x18br7mf.x1i0vuye.xh8yej3.x1aavi5t.x1h6iz8e.xixcex4.xk4oym4.xl3ioum.x3nfvp2"),
                ("css", "div[role='button'][tabindex='0']"),
                ("css", "div[role='button']"),
                ("css", "div[tabindex='0']"),
                ("xpath", "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'close')]"),
                ("xpath", "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'cancel')]"),
                ("xpath", "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'not now')]"),
                ("xpath", "//*[contains(@aria-label, 'close') or contains(@aria-label, 'Close')]"),
                ("css", "button[data-testid*='close'], button[aria-label*='close']"),
                ("css", "button")  # Last resort - any button
            ])
            if success:
                print(f"   [{ig_username}] [Step 2] Successfully clicked close/dismiss button")
            else:
                print(f"   [{ig_username}] [Step 2] Could not find close button, waiting for auto-dismiss or page change")
                # Wait a bit for potential auto-dismiss
                time.sleep(5)
            
            WebDriverWait(self.driver, 10).until(lambda d: self._safe_execute_script("return document.readyState") == "complete")
            time.sleep(2)
            new_status = self._check_verification_result()
            if new_status == status:
                print(f"   [{ig_username}] [Step 2] Status unchanged, trying to navigate away from trusted device dialog")
                # Try to click outside the dialog or refresh the page
                try:
                    body = self.driver.find_element(By.TAG_NAME, "body")
                    body.click()
                    time.sleep(2)
                    new_status = self._check_verification_result()
                except:
                    pass
                
                if new_status == status:
                    new_status = self._check_status_change_with_timeout(status, 15)
            
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
        # RETRY_LOGIN_2
        if status == "RETRY_LOGIN_2":
            print(f"   [{ig_username}] [Step 2] Handling Retry Login 2...")
            # dien lai username
            username_input = wait_element(self.driver, By.NAME, "username", timeout=10)
            if username_input:
                username_input.clear()
                username_input.send_keys(ig_username)
                time.sleep(1)
                username_input.send_keys(Keys.ENTER)
                WebDriverWait(self.driver, 10).until(lambda d: self._safe_execute_script("return document.readyState") == "complete")
            else:
                print(f"   [{ig_username}] [Step 2] Could not find username input to retry login.")
                
            wait_dom_ready(self.driver, timeout=10)
            time.sleep(2)
            # DIEN LAI PASSWORD
            password_input = None
            try:
                pass_selectors = [
                    (By.NAME, "pass"),
                    (By.NAME, "password"),
                    (By.CSS_SELECTOR, "input[type='password']"),
                    (By.XPATH, "//input[@type='password']")
                ]
                for by, sel in pass_selectors:
                    password_input = wait_element(self.driver, by, sel, timeout=5)
                    if password_input:
                        print(f"   [Step 2] Found password input with selector: {sel}")
                        break
            except Exception as e:
                print(f"   [Step 2] Error searching for password input: {e}")

            if password_input:
                password_input.clear()
                password_input.send_keys(ig_password)
                time.sleep(1)
                password_input.send_keys(Keys.ENTER)
                WebDriverWait(self.driver, 10).until(lambda d: self._safe_execute_script("return document.readyState") == "complete")
            else:
                print(f"   [{ig_username}] [Step 2] Could not find password input to retry login.")
            wait_dom_ready(self.driver, timeout=10)
            time.sleep(2)
            
            new_status = self._check_verification_result()
            if new_status == status:
                new_status = self._check_status_change_with_timeout(status, 15)
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
        
        # POST_VIOLATES_COMMUNITY_STANDARDS 
        if status == "POST_VIOLATES_COMMUNITY_STANDARDS":
            # click OK 
            print(f"   [{ig_username}] [Step 2] Handling Post Violates Community Standards...")
            self._robust_click_button([
                ("xpath", "//button[contains(text(), 'OK')]"),
                ("css", "button[type='button']"),
                ("js", """
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        if (buttons[i].textContent.trim().toLowerCase().includes('ok')) {
                            return buttons[i];
                        }
                    return null;
                """)
            ])
            WebDriverWait(self.driver, 10).until(lambda d: self._safe_execute_script("return document.readyState") == "complete")
            time.sleep(2)
            new_status = self._check_verification_result()
            if new_status == status:
                new_status = self._check_status_change_with_timeout(status, 15)
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)

        # ACCOUNTS_CENTER_DATA_SHARING
        if status == "ACCOUNTS_CENTER_DATA_SHARING":
            print(f"   [{ig_username}] [Step 2] Handling Accounts Center Data Sharing...")
            # click radio button use data across accounts
            self._robust_click_button([("xpath", "//input[@type='radio' and (contains(@value, 'yes') or contains(@aria-label, 'Yes'))]"),
                ("css", "input[type='radio'][value='yes'], input[type='radio'][aria-label*='Yes']")
            ])
            time.sleep(1)
            wait_dom_ready(self.driver, timeout=10)
            
            # click next 
            self._robust_click_button([
                ("xpath", "//button[contains(text(), 'Next')]"),
                ("css", "button[type='submit']"),
                ("js", """
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        if (buttons[i].textContent.trim().toLowerCase().includes('next')) {
                            return buttons[i];
                        }
                    }
                    return null;
                """)
            ])
            WebDriverWait(self.driver, 10).until(lambda d: self._safe_execute_script("return document.readyState") == "complete")
            time.sleep(2)
            
            new_status = self._check_verification_result()
            if new_status == status:
                
                new_status = self._check_status_change_with_timeout(status, 15)
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
        
        # RETRY LOGIN
        if status == "RETRY_LOGIN":
            print(f"   [{ig_username}] [Step 2] Handling Retry Login...")
            # click continue button
            self._robust_click_button([
                ("css", "button[type='submit']"),
                ("xpath", "//div[@role='button' or contains(@class, 'x1ja2u2z')][.//text()[contains(., 'Continue')]]"),
                ("xpath", "//button[contains(text(), 'Continue') or contains(text(), 'Tiếp tục') or contains(text(), 'Next') or contains(text(), 'Continue as') or contains(text(), 'Proceed')]"),
                ("xpath", "//div[contains(text(), 'Continue') or contains(text(), 'Tiếp tục')]"),
                ("xpath", "//span[contains(text(), 'Continue') or contains(text(), 'Tiếp tục')]"),
                ("js", """
                    var elements = document.querySelectorAll('button, div[role="button"], span, div');
                    for (var i = 0; i < elements.length; i++) {
                        var el = elements[i];
                        if (el.textContent && (el.textContent.trim().toLowerCase() === 'continue' || el.textContent.trim().toLowerCase() === 'tiếp tục')) {
                            // Prefer button or div[role=button] if multiple match, or just click the first one that looks like a leaf node or specific container
                             if (el.tagName === 'BUTTON' || el.getAttribute('role') === 'button') {
                                return el;
                            }
                            // If it's a span/div with exact text match, return it
                            if (el.childElementCount === 0 || el.innerText.trim() === 'Continue') {
                                return el;
                            }
                        }
                    }
                    // Fallback broad search
                    var allDivs = document.querySelectorAll('div');
                    for (var i = 0; i < allDivs.length; i++) {
                        if (allDivs[i].innerText === 'Continue' || allDivs[i].innerText === 'Tiếp tục') {
                            return allDivs[i];
                        }
                    }
                    return null;
                """)
            ])
            WebDriverWait(self.driver, 10).until(lambda d: self._safe_execute_script("return document.readyState") == "complete")
            time.sleep(2)
            # Nhap lai password
            password_input = None
            try:
                pass_selectors = [
                    (By.NAME, "pass"),
                    (By.NAME, "password"),
                    (By.CSS_SELECTOR, "input[type='password']"),
                    (By.XPATH, "//input[@type='password']")
                ]
                for by, sel in pass_selectors:
                    password_input = wait_element(self.driver, by, sel, timeout=5)
                    if password_input:
                        print(f"   [Step 2] Found password input with selector: {sel}")
                        break
            except Exception as e:
                print(f"   [Step 2] Error searching for password input: {e}")
            
            if password_input:
                try:
                    password_input.click()
                    time.sleep(0.5)
                    password_input.clear()
                    password_input.send_keys(ig_password)
                    time.sleep(1)
                    password_input.send_keys(Keys.ENTER)
                    WebDriverWait(self.driver, 10).until(lambda d: self._safe_execute_script("return document.readyState") == "complete")
                except Exception as e:
                    print(f"   [Step 2] Error entering password: {e}")
            else:
                print(f"   [{ig_username}] [Step 2] Could not find password input to retry login.")
                
            wait_dom_ready(self.driver, timeout=10)
            time.sleep(2)
            new_status = self._check_verification_result()
            if new_status == status:
                new_status = self._check_status_change_with_timeout(status, 15)
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
        
        # UNUSUAL_ACTIVITY_DETECTED
        if status == "UNUSUAL_ACTIVITY_DETECTED":
            print(f"   [{ig_username}] [Step 2] Handling Unusual Activity Detected...")
            # click Dismiss button
            self._robust_click_button([
                ("xpath", "//button[contains(text(), 'Dismiss') or contains(text(), 'Bỏ qua')]"),
                ("css", "button[type='button']"),
                ("js", """
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        if (buttons[i].textContent.trim().toLowerCase().includes('dismiss') || buttons[i].textContent.trim().toLowerCase().includes('bỏ qua')) {
                            return buttons[i];
                        }
                    return null;
                """)
            ])
            WebDriverWait(self.driver, 10).until(lambda d: self._safe_execute_script("return document.readyState") == "complete")
            time.sleep(2)
            new_status = self._check_verification_result()
            if new_status == status:
                new_status = self._check_status_change_with_timeout(status, 15)
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
        

        # [CONSOLIDATED] AUTOMATED_BEHAVIOR_DETECTED
        if status == "AUTOMATED_BEHAVIOR_DETECTED":
            print(f"   [{ig_username}] [Step 2] Automated Behavior Detected. Attempting to dismiss...")
            # Try specific "Dismiss" button first (Updated for Flexbox/aria-label)
            self._robust_click_button([
                 ("js", """
                    var btns = document.querySelectorAll('button, div[role="button"]');
                    for (var b of btns) {
                        var t = b.innerText ? b.innerText.toLowerCase().trim() : "";
                        var a = b.getAttribute('aria-label') ? b.getAttribute('aria-label').toLowerCase().trim() : "";
                        if (t === 'dismiss' || t === 'bỏ qua' || a === 'dismiss' || a === 'bỏ qua') return b;
                    }
                    return null;
                 """),
                 ("css", "div[role='button'][aria-label='Dismiss']"),
                 ("xpath", "//div[@role='button' and @aria-label='Dismiss']"),
                 ("xpath", "//button[text()='Dismiss']"),
                 ("xpath", "//div[@role='button' and text()='Dismiss']"),
                 # Then contains
                 ("xpath", "//button[contains(text(), 'Dismiss')]"),
                 ("xpath", "//div[@role='button' and contains(text(), 'Dismiss')]")
            ])
            
            WebDriverWait(self.driver, 10).until(lambda d: self._safe_execute_script("return document.readyState") == "complete")
            time.sleep(3)
            new_status = self._check_verification_result()
             # If still same status, retry with broader selector
            if new_status == status:
                 print(f"   [{ig_username}] [Step 2] 'Dismiss' click didn't change status. Retrying with loose match...")
                 self._robust_click_button([
                      ("js", """
                        var buttons = document.querySelectorAll('button, div[role="button"]');
                        for (var i = 0; i < buttons.length; i++) {
                            if (buttons[i].textContent.toLowerCase().includes('dismiss') || buttons[i].textContent.toLowerCase().includes('bỏ qua')) {
                                return buttons[i];
                            }
                        }
                        return null;
                      """)
                 ])
                 time.sleep(3)
                 new_status = self._check_verification_result()
                 
            if new_status == status:
                new_status = self._check_status_change_with_timeout(status, 15)
            
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)

        
        # SUBSCRIBE_OR_CONTINUE
        if status == "SUBSCRIBE_OR_CONTINUE":
            print("   [Step 2] Handling Subscribe Or Continue...")
            # se co 2 radio button: => chon cai thu 2 (use for free with ads)
            self._robust_click_button([("xpath", "(//input[@type='radio'])[2]"), ("css", "input[type='radio']:nth-of-type(2)")])
            time.sleep(1)
            self._robust_click_button([
                ("xpath", "//button[contains(text(), 'Continue') or contains(text(), 'Tiếp tục') or contains(text(), 'Next') or contains(text(), 'Continue as') or contains(text(), 'Proceed')]"),
                ("css", "button[type='submit']"),
                ("js", """
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        var text = buttons[i].textContent.trim().toLowerCase();
                        if (text.includes('continue') || text.includes('tiếp tục') || text.includes('next') || text.includes('proceed')) {
                            return buttons[i];
                        }
                    }
                    return null;
                """)
            ])
            WebDriverWait(self.driver, 10).until(lambda d: self._safe_execute_script("return document.readyState") == "complete")
            new_status = self._check_verification_result()
            if new_status == status:
                new_status = self._check_status_change_with_timeout(status, 15)
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
                
        # CHECKPOINT_PHONE
        if status == "CHECKPOINT_PHONE":
            print("   [Step 2] Handling Checkpoint Phone...")
            # click button back to return CONTINUE_UNUSUAL_LOGIN
            back_clicked = self._robust_click_button([
                ("xpath", "//button[contains(text(), 'Back') or contains(text(), 'Quay lại')]"),
                ("css", "button[type='button']"),
                ("js", """
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        if (buttons[i].textContent.trim().toLowerCase().includes('back') || buttons[i].textContent.trim().toLowerCase().includes('quay lại')) {
                            return buttons[i];
                        }
                    }
                    return null;
                """)
            ])
            wait_dom_ready(self.driver, timeout=10)
            if back_clicked:
                return self.handle_status("CONTINUE_UNUSUAL_LOGIN", ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
            
        # RECOVERY_CHALLENGE
        if status == "RECOVERY_CHALLENGE":
            print("   [Step 2] Handling Recovery Challenge...")
            # Select email radio button
            try:
                email_radio = self.driver.find_element(By.CSS_SELECTOR, "input[type='radio'][value='EMAIL']")
                email_radio.click()
                print("   [Step 2] Selected email radio button.")
            except Exception as e:
                print(f"   [Step 2] Error selecting email radio: {e}")
            
            # Click continue
            self._robust_click_button([
                ("xpath", "//span[contains(text(), 'Continue')]"),
                ("css", "button[type='submit']"),
                ("js", """
                    var spans = document.querySelectorAll('span');
                    for (var i = 0; i < spans.length; i++) {
                        if (spans[i].textContent.trim().toLowerCase().includes('continue')) {
                            return spans[i].closest('button') || spans[i];
                        }
                    }
                    return null;
                """)
            ])
            
            WebDriverWait(self.driver, 10).until(lambda d: self._safe_execute_script("return document.readyState") == "complete")
            new_status = self._check_verification_result()
            if new_status == status:
                new_status = self._check_status_change_with_timeout(status, 15)
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
            
        # SELECT_EMAIL_TO_SEND_CODE
        if status == "SELECT_EMAIL_TO_SEND_CODE":
            print(f"   [{ig_username}] [Step 2] Handling Select Email To Send Code...")
            # Click first radio button (default selection often works, but explicit click is safer)
            self._robust_click_button([
                ("css", "input[type='radio']"),
                ("xpath", "//input[@type='radio']"),
                ("xpath", "(//input[@type='radio'])[1]")
            ])
            time.sleep(1)
            
            # Click Continue
            self._robust_click_button([
                ("xpath", "//button[contains(text(), 'Continue') or contains(text(), 'Tiếp tục') or contains(text(), 'Next') or contains(text(), 'Proceed')]"),
                ("css", "button[type='submit']"),
                ("js", """
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        var text = buttons[i].textContent.trim().toLowerCase();
                        if (text.includes('continue') || text.includes('tiếp tục') || text.includes('next')) {
                            return buttons[i];
                        }
                    }
                    return null;
                """)
            ])
            
            WebDriverWait(self.driver, 10).until(lambda d: self._safe_execute_script("return document.readyState") == "complete")
            time.sleep(2)
            
            new_status = self._check_verification_result()
            if new_status == status:
                new_status = self._check_status_change_with_timeout(status, 15)
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
            
        # RETRY_UNSUAL_LOGIN
        if status == "RETRY_UNUSUAL_LOGIN":
            # call step 1 to login again with new data 
            print("   [Step 2] Handling Retry Unusual Login...")
            # Nhấn button Continue 
            self._robust_click_button([
                ("xpath", "//button[contains(text(), 'Continue') or contains(text(), 'Tiếp tục') or contains(text(), 'Next') or contains(text(), 'Continue as') or contains(text(), 'Proceed')]"),
                ("css", "button[type='submit']"),
                ("js", """
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        var text = buttons[i].textContent.trim().toLowerCase();
                        if (text.includes('continue') || text.includes('tiếp tục') || text.includes('next') || text.includes('proceed')) {
                            return buttons[i];
                        }
                    }
                    return null;
                """)
            ])
            WebDriverWait(self.driver, 10).until(lambda d: self._safe_execute_script("return document.readyState") == "complete")
            time.sleep(2)
            
            # Nhap password lai
            password_input = None
            try:
                pass_selectors = [
                    (By.NAME, "pass"),
                    (By.NAME, "password"),
                    (By.CSS_SELECTOR, "input[type='password']"),
                    (By.XPATH, "//input[@type='password']")
                ]
                for by, sel in pass_selectors:
                    password_input = wait_element(self.driver, by, sel, timeout=5)
                    if password_input:
                        print(f"   [Step 2] Found password input with selector: {sel}")
                        break
            except Exception as e:
                print(f"   [Step 2] Error searching for password input: {e}")

            if password_input: 
                password_input.clear()
                password_input.send_keys(ig_password)
                time.sleep(1)
                password_input.send_keys(Keys.ENTER)
                WebDriverWait(self.driver, 10).until(lambda d: self._safe_execute_script("return document.readyState") == "complete")
            else:
                print("   [Step 2] Could not find password input to retry unusual login.")
            wait_dom_ready(self.driver, timeout=10)
            time.sleep(2)
            new_status = self._check_verification_result()
            if new_status == status:
                new_status = self._check_status_change_with_timeout(status, 15)
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
            
        
        if status == "CONTINUE_UNUSUAL_LOGIN":
            # Timeout protection for unusual login (max 60s)
            start_time = time.time()
            TIMEOUT = 60
            print("   [Step 2] Handling Unusual Login (Clicking Continue/This Was Me)...")
            time.sleep(2) # Chờ load UI
            try:
                # Tìm tất cả các thẻ label (vì cấu trúc bạn gửi là <label ...> Text <input> ... </label>)
                labels = self.driver.execute_script("return Array.from(document.querySelectorAll('label'));")
                email_selected = False
                
                if len(labels) > 0:
                    # Ưu tiên chọn radio button Email
                    email_radio = None
                    for label in labels:
                        if "email" in label.text.lower() or "e-mail" in label.text.lower():
                            try:
                                inp = label.find_element(By.TAG_NAME, "input")
                                if inp.get_attribute("type") == "radio":
                                    email_radio = inp
                                    print(f"   [Step 2] Found Email radio: {label.text.strip()}")
                                    break
                            except:
                                continue
                    
                    if email_radio:
                        # Click radio Email
                        radio_id = email_radio.get_attribute("id")
                        if radio_id:
                            wait_and_click(self.driver, By.CSS_SELECTOR, f"input[id='{radio_id}']", timeout=20)
                        else:
                            email_radio.click()
                        print("   [Step 2] Selected Email radio button.")
                        email_selected = True
                    else:
                        # Fallback: Chọn radio đầu tiên nếu không tìm thấy Email
                        radios = self.driver.execute_script("return Array.from(document.querySelectorAll('input[type=\"radio\"]'));")
                        if len(radios) > 0:
                            print("   [Step 2] Email radio not found. Selecting 1st radio...")
                            wait_and_click(self.driver, By.CSS_SELECTOR, "input[type='radio']", timeout=20)
                            email_selected = True  # Assume selected
                        else:
                            print("   [Step 2] No radio buttons found.")
                else:
                    print("   [Step 2] No labels found. Proceeding to click Continue.")

            except Exception as e:
                print(f"   [Step 2] Radio selection warning: {e}")

            time.sleep(1) # Chờ UI update nhẹ
            
            # Tìm nút Continue hoặc This Was Me
            keywords = ["continue", "tiếp tục", "this was me", "đây là tôi"]
            
            # Quét buttons
            btns = self.driver.execute_script("return Array.from(document.querySelectorAll('button'));")
            clicked = False
            for b in btns:
                if any(k in b.text.lower() for k in keywords) and b.is_displayed():
                    if wait_and_click(self.driver, By.TAG_NAME, "button", timeout=20):
                        clicked = True
                        print(f"   [Step 2] Clicked button: {b.text}")
                        break
                if time.time() - start_time > TIMEOUT:
                    raise Exception("TIMEOUT_CONTINUE_UNUSUAL_LOGIN: Button click")
            
            # Fallback div role button
            if not clicked:
                divs = self.driver.execute_script("return Array.from(document.querySelectorAll('div[role=\"button\"]'));")
                for d in divs:
                    if any(k in d.text.lower() for k in keywords) and d.is_displayed():
                        wait_and_click(self.driver, By.XPATH, "//div[@role='button']", timeout=20)
                        clicked = True
                        print(f"   [Step 2] Clicked div button: {d.text}")
                        break
                    if time.time() - start_time > TIMEOUT:
                        raise Exception("TIMEOUT_CONTINUE_UNUSUAL_LOGIN: Fallback button click")

            if not clicked:
                print("   [Step 2] No Continue/This Was Me button found. Trying alternative approaches...")
                # Try clicking any visible button as last resort
                try:
                    all_buttons = self.driver.execute_script("""
                        return Array.from(document.querySelectorAll('button, div[role="button"], input[type="submit"]'))
                        .filter(el => el.offsetParent !== null && el.textContent.trim());
                    """)
                    if all_buttons:
                        # Click the first visible button
                        self.driver.execute_script("arguments[0].click();", all_buttons[0])
                        clicked = True
                        print(f"   [Step 2] Clicked fallback button: {all_buttons[0].textContent}")
                except Exception as e:
                    print(f"   [Step 2] Fallback button click failed: {e}")

            time.sleep(5) # Chờ load sau khi click
            if time.time() - start_time > TIMEOUT:
                raise Exception("TIMEOUT_CONTINUE_UNUSUAL_LOGIN: End")
            
            # Sau khi click continue, thường sẽ nhảy sang Checkpoint Mail
            # Gọi đệ quy lại handle_status với trạng thái mới (quét lại body)
            wait_dom_ready(self.driver, timeout=10)
            time.sleep(2)
            new_status = self._check_verification_result()
            print(f"   [Step 2] Status after Continue: {new_status}")
            
            # Anti-hang: If status unchanged or still unusual login, check with timeout and more verification
            if new_status == status or "UNUSUAL" in new_status:
                print("   [Step 2] Status indicates popup may still be present. Waiting longer...")
                time.sleep(5)
                new_status = self._check_verification_result()
                print(f"   [Step 2] Status after additional wait: {new_status}")
                
                # If still not resolved, try to force close any modal/popups
                if new_status == status or "UNUSUAL" in new_status:
                    print("   [Step 2] Attempting to force close popups...")
                    try:
                        self.driver.execute_script("""
                            // Try to close any modals/dialogs
                            var dialogs = document.querySelectorAll('div[role="dialog"]');
                            for (var dialog of dialogs) {
                                var closeBtn = dialog.querySelector('button, [role="button"]');
                                if (closeBtn) closeBtn.click();
                            }
                            
                            // Try ESC key
                            var event = new KeyboardEvent('keydown', {key: 'Escape'});
                            document.dispatchEvent(event);
                        """)
                        time.sleep(3)
                        new_status = self._check_verification_result()
                        print(f"   [Step 2] Status after force close: {new_status}")
                    except Exception as e:
                        print(f"   [Step 2] Force close failed: {e}")
                    
                return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
            
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
        
        if status == "CONFIRM_YOUR_ACCOUNTS":
            print("   [Step 2] Handling 'Confirm Your Accounts' (Meta Accounts Center)...")
            
            # 1. Click nút "Get started" / "Bắt đầu"
            clicked_start = self._robust_click_button([
                ("xpath", "//button[contains(text(), 'Get started')]"),
                ("xpath", "//div[@role='button'][contains(text(), 'Get started')]"),
                ("xpath", "//button[contains(text(), 'Bắt đầu')]"),
                ("xpath", "//div[@role='button'][contains(text(), 'Bắt đầu')]"),
                ("css", "button._acan._acap._acas") # Class thường dùng cho nút xanh primary
            ], timeout=10)
            
            # neu khong nhan duoc thi thu click div role button
            if not clicked_start:
                print("   [Step 2] 'Get started' button not found, trying alternative selector...")
                clicked_start = self._robust_click_button([
                    ("css", "div[role='button']"),
                ], timeout=20)
                
            # 2. Chờ load xong
            wait_dom_ready(self.driver, timeout=20)
            time.sleep(3)
            
            # giao dien hien thi 2 radio button: use data across accounts va manage accounts -> chon use data across accounts
            clicked_use_data = self._robust_click_button([
                ("xpath", "//label[contains(., 'Use data across accounts')]"),
                ("xpath", "//label[contains(., 'Sử dụng dữ liệu trên các tài khoản')]"),
                ("css", "label._acan._acap") # Class thường dùng cho label radio
            ], timeout=20)
            time.sleep(2)
            
            # retry neu chua chon duoc
            if not clicked_use_data:
                print("   [Step 2] 'Use data across accounts' radio not found, trying alternative selector...")
                clicked_use_data = self._robust_click_button([
                    ("css", "label"), # Fallback to any label
                ], timeout=20)
                time.sleep(2)
            
            # Click nút "Next"
            clicked_next = self._robust_click_button([
                ("xpath", "//button[contains(text(), 'Next')]"),
                ("xpath", "//div[@role='button'][contains(text(), 'Next')]"),
                ("xpath", "//button[contains(text(), 'Tiếp theo')]"),
                ("xpath", "//div[@role='button'][contains(text(), 'Tiếp theo')]"),
                ("css", "button._acan._acap._acas") # Class thường dùng cho nút xanh primary
            ], timeout=10)
            
            if not clicked_next:
                print("   [Step 2] 'Next' button not found, trying alternative selector...")
                clicked_next = self._robust_click_button([
                    ("css", "div[role='button']"),
                ], timeout=20)
        
            wait_dom_ready(self.driver, timeout=20)
            time.sleep(2)

            # Kiểm tra trạng thái mới
            new_status = self._check_verification_result()
            
            print(f"   [Step 2] Status after Confirm Your Accounts: {new_status}")
            if new_status == status:
                new_status = self._check_status_change_with_timeout(status, 15)
            # Đệ quy để kiểm tra lại trạng thái mới
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)

        if status == "REQUIRE_PASSWORD_CHANGE":
            # Timeout protection for password change (max 60s)
            start_time = time.time()
            TIMEOUT = 60
            print("   [Step 2] Handling Require Password Change...")
            if ig_password:
                new_pass = ig_password + "@"
                try:
                    self._handle_require_password_change(new_pass)
                except Exception as e:
                    error_msg = str(e)
                    print(f"   [Step 2] Error in _handle_require_password_change: {error_msg}")

                    # Check if it's a stale element issue that might be recoverable
                    if "stale" in error_msg.lower() or "element" in error_msg.lower():
                        print(f"   [Step 2] Stale element detected, attempting page refresh recovery...")
                        try:
                            self.driver.refresh()
                            WebDriverWait(self.driver, 10).until(lambda d: d.execute_script("return document.readyState") == "complete")
                            time.sleep(3)

                            # Check current status after refresh
                            current_status = self._check_verification_result()
                            if current_status != "REQUIRE_PASSWORD_CHANGE":
                                print(f"   [Step 2] Status changed after refresh: {current_status}")
                                return self.handle_status(current_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
                            else:
                                print(f"   [Step 2] Status still REQUIRE_PASSWORD_CHANGE after refresh, re-attempting...")
                                # Try one more time
                                self._handle_require_password_change(new_pass)
                        except Exception as recovery_e:
                            print(f"   [Step 2] Recovery attempt failed: {recovery_e}")
                            raise e  # Raise original error
                    else:
                        # Non-stale error, raise immediately
                        raise e

                if time.time() - start_time > TIMEOUT:
                    raise Exception("TIMEOUT_REQUIRE_PASSWORD_CHANGE: End")

                # Cập nhật lại password mới lên GUI NGAY LẬP TỨC trước khi gọi các bước tiếp theo
                if hasattr(self, "on_password_changed") and callable(getattr(self, "on_password_changed", None)):
                    try:
                        self.on_password_changed(ig_username, new_pass)
                    except Exception as callback_e:
                        print(f"   [Step 2] Error in password change callback: {callback_e}")
                time.sleep(4)
                wait_dom_ready(self.driver, timeout=20)

                # Check if we're actually logged in after password change
                current_status = self._check_verification_result()
                if current_status in ["LOGGED_IN_SUCCESS", "COOKIE_CONSENT", "TERMS_AGREEMENT"]:
                    print(f"   [Step 2] Password changed and login successful. Status: {current_status}")
                    return current_status
                else:
                    # If not logged in, restart the login process
                    print(f"   [Step 2] Password changed but not logged in. Status: {current_status}. Returning RESTART_LOGIN to restart process with new password.")
                    return "RESTART_LOGIN"
            else:
                raise Exception("STOP_FLOW_REQUIRE_PASSWORD_CHANGE: No password provided")

        if status == "PASSWORD_CHANGE_CONFIRMATION":
            print("   [Step 2] Handling Password Change Confirmation...")
            if ig_password:
                new_pass = ig_password + "@"
                # Find input and send keys
                input_el = wait_element(self.driver, By.CSS_SELECTOR, "input[type='password']", timeout=10)
                if input_el:
                    input_el.clear()
                    input_el.send_keys(new_pass)
                    time.sleep(1)
                # Click confirm
                self._robust_click_button([
                    ("xpath", "//button[contains(text(), 'Confirm')]"),
                    ("xpath", "//button[contains(text(), 'Xác nhận')]"),
                    ("css", "button[type='submit']"),
                    ("js", """
                        var buttons = document.querySelectorAll('button');
                        for (var b of buttons) {
                            if (b.textContent.toLowerCase().includes('confirm') || b.textContent.toLowerCase().includes('xác nhận')) {
                                return b;
                            }
                        }
                        return null;
                    """)
                ])
                wait_dom_ready(self.driver, timeout=10)
                time.sleep(2)
                new_status = self._check_verification_result()
                return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
            else:
                raise Exception("STOP_FLOW_PASSWORD_CHANGE_CONFIRMATION: No password provided")

        if status == "CHANGE_PASSWORD":
            # handle one input for new password
            print("   [Step 2] Handling Change Password...")
            if ig_password :
                new_pass = ig_password + "@"
                try:
                    self._handle_change_password(new_pass)  # Use the same method as REQUIRE_PASSWORD_CHANGE
                except Exception as e:
                    print(f"   [Step 2] Error in _handle_change_password: {e}")
                    # If error, try to recover by refreshing
                    self.driver.get("https://www.instagram.com/")
                    wait_dom_ready(self.driver, timeout=20)
                    time.sleep(2)
                    raise e
                # Cập nhật lại password mới lên GUI NGAY LẬP TỨC trước khi gọi các bước tiếp theo
                if hasattr(self, "on_password_changed") and callable(getattr(self, "on_password_changed", None)):
                    try:
                        self.on_password_changed(ig_username, new_pass)
                    except Exception as callback_e:
                        print(f"   [Step 2] Error in password change callback: {callback_e}")
                
                wait_dom_ready(self.driver, timeout=20)
                time.sleep(4)
                
                new_status = self._check_verification_result()
                if new_status == status:
                    new_status = self._check_status_change_with_timeout(status, 15)
                return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, new_pass, depth + 1)
            else:
                raise Exception("STOP_FLOW_CHANGE_PASSWORD: No password provided")
            

        # XỬ LÝ BIRTHDAY
        if status == "BIRTHDAY_SCREEN":
            wait_dom_ready(self.driver, timeout=20)
            if self._handle_birthday_screen():
                # get new status after handling birthday
                wait_dom_ready(self.driver, timeout=20)
                time.sleep(3)
                new_status = self._check_verification_result()
                print(f"   [Step 2] Status after Birthday: {new_status}")
                # Anti-hang: If status unchanged, refresh to avoid loop
                if new_status == status:
                    print(f"   [Step 2] Status unchanged after handling {status}, refreshing to avoid hang...")
                    self.driver.refresh()
                    wait_dom_ready(self.driver, timeout=20)
                    new_status = self._check_verification_result()
                # de quy kiem tra lai trang thai
                return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
            else:   
                return self._handle_birthday_screen()
            
        # [DUPLICATE REMOVED]

        # XỬ LÝ CHECKPOINT MAIL

        # XỬ LÝ CHECKPOINT MAIL
        if status == "CHECKPOINT_MAIL":
            print("   [Step 2] Handling Email Checkpoint...")
            result = self._solve_email_checkpoint(ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth)
            
            wait_dom_ready(self.driver, timeout=20)
            time.sleep(3)
            new_status = self._check_verification_result()
            print(f"   [Step 2] Status after Email Checkpoint: {new_status}")
            # Anti-hang: If status unchanged, refresh to avoid loop
            if new_status == status:
                print(f"   [Step 2] Status unchanged after handling {status}, refreshing to avoid hang...")
                self.driver.refresh()
                wait_dom_ready(self.driver, timeout=20)
                new_status = self._check_verification_result()
                
            # de quy kiem tra lai trang thai
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
        
        # LOGIN_FAILED_SOMETHING_WENT_WRONG 
        if status == "LOGIN_FAILED_SOMETHING_WENT_WRONG":
            # refresh page to try again
            print("   [Step 2] Login Failed Something Went Wrong detected. Refreshing page to retry...")
            self.driver.get("https://www.instagram.com/")
            WebDriverWait(self.driver, 10).until(lambda d: d.execute_script("return document.readyState") == "complete")
            time.sleep(3)
            new_status = self._check_verification_result()
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
        
        if status == "SOMETHING_WRONG":
            # refresh page to try again
            print("   [Step 2] Something went wrong detected. Refreshing page to retry...")
            # truy cap instagram.com
            self.driver.get("https://www.instagram.com/")
            WebDriverWait(self.driver, 10).until(lambda d: d.execute_script("return document.readyState") == "complete")
            time.sleep(3)
            new_status = self._check_verification_result()
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
        
        
        

        # NHÓM FAIL
        if status == "WRONG_CODE":
            print("   [Step 2] Wrong code detected. Retrying checkpoint...")
            return self.handle_status("CHECKPOINT_MAIL", ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)

        if status == "CAN_GET_NEW_CODE":
            print("   [Step 2] Can get new code detected. Retrying checkpoint...")
            return self.handle_status("CHECKPOINT_MAIL", ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
        


        # Handle reload and login again if redirected to profile selection or use another profile
        if status == "RETRY_UNUSUAL_LOGIN" or self._detect_stuck_on_profile_selection():
            print("   [Step 2] Detected need to reload and login again (profile selection or use another profile, or stuck)...")
            self.driver.get("https://www.instagram.com/")
            wait_dom_ready(self.driver, timeout=20)
            time.sleep(2)
            if ig_username and ig_password:
                print("   [Step 2] Calling step1 to login again with new password...")
                isLogin = self.step1_login.perform_login(ig_username, ig_password)
                wait_dom_ready(self.driver, timeout=20)
                if isLogin == "LOGGED_IN_SUCCESS":
                    return self.handle_status("LOGGED_IN_SUCCESS", ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
                else:
                    return self.handle_status(isLogin, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
            else:
                raise Exception("STOP_FLOW_RETRY_UNUSUAL_LOGIN: Missing username or password")

        fail_statuses = [
            "UNUSUAL_LOGIN", "TRY_ANOTHER_DEVICE", "2FA_REQUIRED", "SUSPENDED",
            "LOGIN_FAILED_INCORRECT", "2FA_SMS", "2FA_WHATSAPP", "GET_HELP_LOG_IN",
            "2FA_APP", "2FA_APP_CONFIRM", "FAIL_LOGIN_REDIRECTED_TO_PROFILE_SELECTION",
            "LOGIN_FAILED_RETRY", "2FA_NOTIFICATIONS", "LOGGED_IN_UNKNOWN_STATE",
            "TIMEOUT_LOGIN_CHECK", "PAGE_BROKEN", "SUSPENDED_PHONE","LOG_IN_ANOTHER_DEVICE", 
            "CONFIRM_YOUR_IDENTITY", "2FA_TEXT_MESSAGE", 
            "ACCOUNT_DISABLED", "CONTINUE_UNUSUAL_LOGIN_PHONE", "DISABLE_ACCOUNT", "LOGIN_FAILED", "NOT_CONNECT_INSTAGRAM"
        ]

        if status in fail_statuses:
            raise Exception(f"STOP_FLOW_EXCEPTION: {status}")
        
        if status == "BIRTHDAY_SCREEN":
            wait_dom_ready(self.driver, timeout=20)
            time.sleep(2)
            if self._handle_birthday_screen():
                # get new status after handling birthday
                wait_dom_ready(self.driver, timeout=20)
                new_status = self._check_verification_result()
                print(f"   [Step 2] Status after Birthday: {new_status}")
                # Anti-hang: If status unchanged, refresh to avoid loop
                if new_status == status:
                    print(f"   [Step 2] Status unchanged after handling {status}, refreshing to avoid hang...")
                    self.driver.refresh()
                    wait_dom_ready(self.driver, timeout=20)
                    new_status = self._check_verification_result()
                # de quy kiem tra lai trang thai
                return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
            else:
                return self._handle_birthday_screen()
        
        if status == "TIMEOUT" and depth < 10:
            print("   [Step 2] Status is TIMEOUT. Reloading page to retry...")
            self.driver.get("https://www.instagram.com/")
            wait_dom_ready(self.driver, timeout=20)
            new_status = self._check_verification_result()
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
            
        
        # UNBLOCK_ACCOUNT
        if status == "UNBLOCK_ACCOUNT":
            print("   [Step 2] Handling Unblock Account...")
            self.step3_post_login._handle_interruptions()
            wait_dom_ready(self.driver, timeout=20)
            time.sleep(2)
            new_status = self._check_verification_result()
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)
        
        # Handle TIMEOUT after max retries - redirect to instagram.com as fallback
        if status == "TIMEOUT" and depth >=10:
            print("   [Step 2] TIMEOUT persisted after retries. Redirecting to instagram.com as fallback...")
            # profile 
            self.driver.get("https://www.instagram.com/{}/".format(ig_username))
            self.step3_post_login._handle_interruptions()
            WebDriverWait(self.driver, 10).until(lambda d: self._safe_execute_script("return document.readyState") == "complete")
            time.sleep(2)
            new_status = self._check_verification_result()
            return self.handle_status(new_status, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)

    # ==========================================
    # 3. LOGIC XỬ LÝ BIRTHDAY (STRICT VERIFY YEAR)
    # ==========================================
    def _handle_birthday_screen(self):
        # Timeout protection for birthday screen (max 60s)
        start_time = time.time()
        TIMEOUT = 60
        print("   [Step 2] Handling Birthday Screen...")
        # Check for "Enter your real birthday" text and reload if found
        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            if "enter your real birthday" in body_text or "nhập ngày sinh thật của bạn" in body_text:
                print("   [Step 2] Detected 'Enter your real birthday' - Reloading Instagram...")
                self.driver.get("https://www.instagram.com/")
                WebDriverWait(self.driver, 10).until(lambda d: d.execute_script("return document.readyState") == "complete")
                return "LOGGED_IN_SUCCESS"
        except Exception as e:
            print(f"   [Step 2] Warning checking for real birthday text: {e}")
        
        try:
            # VÒNG LẶP CHÍNH (3 Lần)
            for attempt in range(3):
                try:
                    body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                    if "enter your real birthday" in body_text or "nhập ngày sinh thật của bạn" in body_text:
                        print("   [Step 2] Detected 'Enter your real birthday' - Reloading Instagram...")
                        self.driver.get("https://www.instagram.com/")
                        time.sleep(2)
                        wait_dom_ready(self.driver, timeout=20)
                        return "LOGGED_IN_SUCCESS"
                except Exception as e:
                    print(f"   [Step 2] Warning checking for real birthday text: {e}")
                if time.time() - start_time > TIMEOUT:
                    raise Exception("TIMEOUT_BIRTHDAY_SCREEN: Main loop")
                print(f"   [Step 2] Birthday Attempt {attempt+1}/3...")
                
                # BƯỚC 2: CHỌN NĂM (STRICT VERIFICATION)
                year_confirmed = False 
                
                try:
                    year_select_el = None
                    selectors = [
                        "select[title='Year:']", "select[title='Năm:']", 
                        "select[name='birthday_year']", "select[aria-label='Year']"
                    ]
                    
                    for sel in selectors:
                        els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                        if els and els[0].is_displayed():
                            year_select_el = els[0]; break
                        if time.time() - start_time > TIMEOUT:
                            raise Exception("TIMEOUT_BIRTHDAY_SCREEN: Year select find")
                    
                    if year_select_el:
                        select = Select(year_select_el)
                        
                        # Random năm an toàn (1985-2000)
                        target_year = str(random.randint(1985, 2000))
                        
                        # --- LOOP CHỌN VÀ KIỂM TRA LẠI ---
                        for _ in range(3):
                            # Thử chọn
                            try: select.select_by_value(target_year)
                            except: pass
                            
                            # Thử JS ép giá trị
                            try:
                                self.driver.execute_script(f"arguments[0].value = '{target_year}';", year_select_el)
                                self.driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", year_select_el)
                            except: pass
                            
                            time.sleep(0.5)
                            
                            # Kiểm tra giá trị thực tế
                            current_val = year_select_el.get_attribute("value")
                            if current_val == target_year:
                                year_confirmed = True
                                print(f"   [Step 2] Year VERIFIED: {target_year}")
                                break 
                            else:
                                print(f"   [Step 2] Year mismatch ({current_val} vs {target_year}). Retrying...")
                            if time.time() - start_time > TIMEOUT:
                                raise Exception("TIMEOUT_BIRTHDAY_SCREEN: Year select loop")
                        
                        if year_confirmed:
                            # Chọn Tháng/Ngày
                            try:
                                Select(self.driver.find_element(By.CSS_SELECTOR, "select[name='birthday_month']")).select_by_index(random.randint(1, 11))
                                Select(self.driver.find_element(By.CSS_SELECTOR, "select[name='birthday_day']")).select_by_index(random.randint(1, 27))
                            except: pass
                            time.sleep(1.5)
                        else:
                            print("   [Step 2] Failed to verify Year change. Popup might be blocking.")
                    
                    else:
                        print(f"   [Step 2] Year dropdown missing. Retrying popup logic...")
                        # if nuke_real_birthday_popup(): continue 
                        time.sleep(1); continue
                        
                except Exception as e:
                    print(f"   [Step 2] Select error: {e}")
                    time.sleep(1); continue

                # BƯỚC 3: CLICK NEXT (CHỈ KHI ĐÃ VERIFY NĂM)
                if year_confirmed:
                    print("   [Step 2] Year is Confirmed. Clicking Next...")
                    next_clicked = False
                    
                    # Robust Next button finding and clicking
                    next_selectors = [
                        # Specific class from HTML
                        (By.CSS_SELECTOR, "div.x1i10hfl.xjqpnuy.xc5r6h4.xqeqjp1.x1phubyo.x972fbf.x10w94by.x1qhh985.x14e42zd.xdl72j9.x2lah0s.x3ct3a4.xdj266r.x14z9mp.xat24cr.x1lziwak.x2lwn1j.xeuugli.xexx8yu.x18d9i69.x1hl2dhg.xggy1nq.x1ja2u2z.x1t137rt.x1q0g3np.x1lku1pv.x1a2a7pz.x6s0dn4.xjyslct.x1ejq31n.x18oe1m7.x1sy0etr.xstzfhl.x9f619.x9bdzbf.x1ypdohk.x78zum5.x1f6kntn.xwhw2v2.xl56j7k.x17ydfre.x1n2onr6.x2b8uid.xlyipyv.x87ps6o.x14atkfc.x5c86q.x18br7mf.x1i0vuye.x6nl9eh.x1a5l9x9.x7vuprf.x1mg3h75.xn3w4p2.x106a9eq.x1xnnf8n.x18cabeq.x158me93.xk4oym4.x1uugd1q"),
                        # Generic role button with Next text
                        (By.XPATH, "//div[@role='button' and contains(text(), 'Next')]"),
                        # Button with Next text
                        (By.XPATH, "//button[contains(text(), 'Next')]"),
                        # Vietnamese Next
                        (By.XPATH, "//button[contains(text(), 'Tiếp')]"),
                        # Generic div role button
                        (By.CSS_SELECTOR, "div[role='button'][tabindex='0']")
                    ]
                    
                    for by, sel in next_selectors:
                        try:
                            next_btn = wait_element(self.driver, by, sel, timeout=20)
                            if next_btn and next_btn.is_displayed() and next_btn.is_enabled():
                                print(f"   [Step 2] Found Next button with selector: {sel}")
                                
                                # Try multiple click methods
                                click_success = False
                                
                                # Method 1: Direct click
                                try:
                                    next_btn.click()
                                    click_success = True
                                    print("   [Step 2] Next button clicked via direct click.")
                                except Exception as e:
                                    print(f"   [Step 2] Direct click failed: {e}")
                                
                                # Method 2: JS click if direct failed
                                if not click_success:
                                    try:
                                        self.driver.execute_script("arguments[0].click();", next_btn)
                                        click_success = True
                                        print("   [Step 2] Next button clicked via JS click.")
                                    except Exception as e:
                                        print(f"   [Step 2] JS click failed: {e}")
                                
                                # Method 3: ActionChains if JS failed
                                if not click_success:
                                    try:
                                        ActionChains(self.driver).move_to_element(next_btn).click().perform()
                                        click_success = True
                                        print("   [Step 2] Next button clicked via ActionChains.")
                                    except Exception as e:
                                        print(f"   [Step 2] ActionChains click failed: {e}")
                                
                                if click_success:
                                    next_clicked = True
                                    break
                        except Exception as e:
                            print(f"   [Step 2] Error with selector {sel}: {e}")
                            continue
                    
                    if not next_clicked:
                        print("   [Step 2] Failed to click Next button with all methods.")
                    else:
                        print("   [Step 2] Next button clicked successfully.")
                    
                    time.sleep(2)

                    # CHECK CONFIRM YES
                    yes_xpaths = ["//button[contains(text(), 'Yes')]", "//button[contains(text(), 'Có')]"]
                    clicked_yes = False
                    for xpath in yes_xpaths:
                        if wait_and_click(self.driver, By.XPATH, xpath, timeout=20): 
                            clicked_yes = True; break
                        if time.time() - start_time > TIMEOUT:
                            raise Exception("TIMEOUT_BIRTHDAY_SCREEN: Yes button click")
                    
                    if clicked_yes: break 
                    
                    # Nếu vào được bên trong -> Thoát
                    body = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                    if "allow the use of cookies" in body or "posts" in body or "search" in body: break
                else:
                    print("   [Step 2] Skipping Next because Year was not confirmed.")

            WebDriverWait(self.driver, 10).until(lambda d: d.execute_script("return document.readyState") == "complete")
            if time.time() - start_time > TIMEOUT:
                raise Exception("TIMEOUT_BIRTHDAY_SCREEN: End")
            return "LOGGED_IN_SUCCESS"

        except Exception as e:
            print(f"   [Step 2] Warning Birthday Handle: {str(e)}")
            return "LOGGED_IN_SUCCESS"

    # ==========================================
    # 4. LOGIC GIẢI CHECKPOINT (RADIO + POLLING FIX)
    # ==========================================
    def _check_is_birthday_screen(self):
        timeout = 30
        poll = 0.5
        end_time = time.time() + timeout
        keywords = ["add your birthday", "thêm ngày sinh", "date of birth", "birth", "sinh nhật"]
        while time.time() < end_time:
            try:
                body = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                has_select = len(self.driver.find_elements(By.TAG_NAME, "select")) > 0
                has_text = any(k in body for k in keywords)
                if has_text and has_select:
                    return True
            except:
                pass
            time.sleep(poll)
        return False

    def _solve_email_checkpoint(self, ig_username, gmx_user, gmx_pass, linked_mail=None, ig_password=None, depth=0):
        # Timeout protection for email checkpoint (max 60s)
        start_time = time.time()
        TIMEOUT = 70
        print(f"   [Step 2] Detected Email Checkpoint...")
        
        # --- GIAI ĐOẠN 0: RADIO BUTTON ---
        try:
            radios = self.driver.execute_script("return Array.from(document.querySelectorAll('input[type=\"radio\"]'));")
            if len(radios) > 0:
                print(f"   [Step 2] Found {len(radios)} options. Selecting 1st radio...")
                
                # Click radio đầu tiên
                wait_and_click(self.driver, By.CSS_SELECTOR, "input[type='radio']", timeout=20)
                time.sleep(0.5)  # Reduced from 1s
                
                # Click Send/Next
                send_btns = self.driver.execute_script("return Array.from(document.querySelectorAll('button[type=\"submit\"], button._acan, div[role=\"button\"][tabindex=\"0\"]'));")
                for btn in send_btns:
                    txt = btn.text.lower()
                    if btn.is_displayed() and any(k in txt for k in ["send", "gửi", "next", "tiếp", "continue"]):
                        print(f"   [Step 2] Clicked confirmation: {txt}")
                        wait_and_click(self.driver, By.CSS_SELECTOR, "button[type='submit'], button._acan, div[role='button'][tabindex='0']", timeout=20)
                        time.sleep(2)  # Reduced from 2s
                        break
                        if time.time() - start_time > TIMEOUT:
                            raise Exception("TIMEOUT_EMAIL_CHECKPOINT: Radio/Send button")
        except Exception as e:
            print(f"   [Step 2] Warning handling radio buttons: {e}")
        
        # --- GIAI ĐOẠN 1: VERIFY HINT ---
        if not self._validate_masked_email_robust(gmx_user, linked_mail):
            raise Exception("STOP_FLOW_CHECKPOINT: Email hint mismatch")

        # Sử dụng _check_mail_flow để đồng bộ logic chống lặp vô hạn
        def get_code():
            try:
                # Truyền thêm tham số linked_mail vào đây
                return get_verify_code_v2(gmx_user, gmx_pass, ig_username, target_email=linked_mail)
            except Exception as e:
                if "GMX_DIE" in str(e): raise e
                return None
        def input_code(code):
            code = str(code).strip()
            if len(code) != 6:
                print(f"   [Step 2] Warning: Code length is {len(code)}, expected 6.")
            
            # Check for multiple code inputs (6 separate fields)
            multiple_inputs = self.driver.execute_script("""
                var inputs = document.querySelectorAll('input[type="text"], input[maxlength="1"]');
                var codeInputs = [];
                for (var i = 0; i < inputs.length; i++) {
                    var inp = inputs[i];
                    if (inp.offsetParent !== null && (inp.name && inp.name.toLowerCase().includes('code') || inp.placeholder && inp.placeholder.toLowerCase().includes('code') || inp.className && inp.className.toLowerCase().includes('code'))) {
                        codeInputs.push(inp);
                    }
                }
                if (codeInputs.length < 2) {
                    // Fallback: all text inputs if no specific code inputs found
                    codeInputs = Array.from(document.querySelectorAll('input[type="text"]')).filter(function(inp) {
                        return inp.offsetParent !== null;
                    });
                }
                return codeInputs.slice(0, 6);  // Limit to 6
            """)
            
            if len(multiple_inputs) > 1 and len(multiple_inputs) <= 6:
                print(f"   [Step 2] Detected {len(multiple_inputs)} separate code input fields. Inputting code digit by digit.")
                try:
                    for i, inp in enumerate(multiple_inputs):
                        if i < len(code):
                            self.driver.execute_script("arguments[0].click();", inp)
                            time.sleep(0.1)
                            self.driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", inp, code[i])
                            time.sleep(0.1)
                    # After inputting all digits, try to submit
                    self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", multiple_inputs[-1])
                    time.sleep(0.5)
                    # Try to find and click submit button
                    submit_btn = self.driver.execute_script("""
                        var buttons = document.querySelectorAll('button[type="submit"], button');
                        for (var i = 0; i < buttons.length; i++) {
                            if (buttons[i].textContent.trim().toLowerCase().includes('confirm') || buttons[i].textContent.trim().toLowerCase().includes('submit') || buttons[i].textContent.trim().toLowerCase().includes('next')) {
                                return buttons[i];
                            }
                        }
                        return null;
                    """)
                    if submit_btn:
                        self.driver.execute_script("arguments[0].click();", submit_btn)
                        print("   [Step 2] Clicked submit button after digit input.")
                    else:
                        print("   [Step 2] No submit button found after digit input.")
                except Exception as e:
                    print(f"   [Step 2] Error inputting code into separate fields: {e}")
                    raise Exception("STOP_FLOW_CHECKPOINT: Failed to input code into separate fields")
                return
            
            # Fallback to single input field
            code_input = None
            # Fast JS check for common code inputs
            code_input = self.driver.execute_script("""
                var inputs = document.querySelectorAll('input');
                for (var i = 0; i < inputs.length; i++) {
                    var inp = inputs[i];
                    if (inp.id === 'security_code' || inp.name === 'security_code' || inp.name === 'verificationCode' || (inp.type === 'text' && inp.offsetParent !== null)) {
                        return inp;
                    }
                }
                return null;
            """)
            if code_input and code_input.is_displayed() and code_input.is_enabled():
                print("   [Step 2] Found single code input via fast JS check")
            else:
                code_input = None
                # Ưu tiên tìm label "Code" rồi lấy input liên kết
                try:
                    labels = self.driver.execute_script("return Array.from(document.querySelectorAll('label'));")
                    for label in labels:
                        if label.text.strip().lower() == "code":
                            input_id = label.get_attribute("for")
                            if input_id:
                                try:
                                    code_input = self.driver.find_element(By.ID, input_id)
                                    if code_input.is_displayed() and code_input.is_enabled():
                                        print(f"   [Step 2] Found code input via label 'Code': {input_id}")
                                        break
                                except:
                                    continue
                except:
                    pass
                
                # Fallback: Thử các selector khác
                if not code_input:
                    input_css_list = ["input[id='security_code']", "input[name='email']", "input[name='security_code']", "input[type='text']", "input[name='verificationCode']"]
                    for sel in input_css_list:
                        try:
                            el = wait_element(self.driver, By.CSS_SELECTOR, sel, timeout=15)  # Giảm timeout
                            if el and el.is_displayed() and el.is_enabled():
                                code_input = el
                                print(f"   [Step 2] Found code input with selector: {sel}")
                                break
                        except Exception as e:
                            print(f"   [Step 2] Error finding input with {sel}: {e}")
            
            if code_input:
                try:
                    print(f"   [Step 2] Attempting to input code {code} into single field...")
                    # First try to click and focus
                    code_input.click()
                    time.sleep(0.2)
                    # Clear existing value
                    code_input.send_keys(Keys.CONTROL + "a")
                    code_input.send_keys(Keys.DELETE)
                    time.sleep(0.1)
                    # Input the code
                    code_input.send_keys(code)
                    time.sleep(0.5)
                    # Check if value was set
                    current_value = code_input.get_attribute('value')
                    print(f"   [Step 2] Input field value after send_keys: '{current_value}'")
                    if current_value != code:
                        print("   [Step 2] send_keys failed, trying JS...")
                        # Fallback to JS
                        self.driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', {{ bubbles: true }}));", code_input, code)
                        time.sleep(0.2)
                        current_value = code_input.get_attribute('value')
                        print(f"   [Step 2] Input field value after JS: '{current_value}'")
                    # Send Enter
                    code_input.send_keys(Keys.ENTER)
                    time.sleep(1)
                    if "security_code" in self.driver.current_url:
                        wait_and_click(self.driver, By.XPATH, "//button[@type='submit'] | //button[contains(text(), 'Confirm')] | //button[contains(text(), 'Xác nhận')]",
                        timeout=20)
                    print("   [Step 2] Code input completed.")
                except Exception as e:
                    print(f"   [Step 2] Error inputting code: {e}")
                    # Last resort: JS input
                    try:
                        self.driver.execute_script(f"document.querySelector('input[id=\"{code_input.get_attribute('id')}\"]').value = '{code}'; document.querySelector('input[id=\"{code_input.get_attribute('id')}\"]').dispatchEvent(new Event('input', {{ bubbles: true }}));")
                        print("   [Step 2] JS fallback input attempted.")
                    except Exception as e2:
                        print(f"   [Step 2] JS fallback failed: {e2}")
            else:
                raise Exception("STOP_FLOW_CHECKPOINT: Cannot find code input")
        check_result = self._check_mail_flow(get_code, input_code, max_retries=3, timeout=TIMEOUT)
        print(f"   [Step 2] Email Checkpoint code verification result: {check_result}")
        return self.handle_status(check_result, ig_username, gmx_user, gmx_pass, linked_mail, ig_password, depth + 1)

    # ==========================================
    # 5. LOGIC CHECK MAIL (REUSE, ANTI-INFINITE LOOP)
    # ==========================================
    def _check_mail_flow(self, get_code_func, input_code_func, max_retries=3, timeout=60):
        """
        Chuẩn hóa logic check mail: lấy code, nhập code, kiểm tra kết quả, chống lặp vô hạn.
        get_code_func: hàm lấy code (lambda)
        input_code_func: hàm nhập code (lambda code)
        """
        start_time = time.time()
        for attempt in range(1, max_retries + 1):
            if time.time() - start_time > timeout:
                raise Exception("CHECK_MAIL: No code ")
            print(f"   [Step 2] >>> Code Attempt {attempt}/{max_retries} <<<")
            if attempt > 1:
                # Có thể bổ sung logic gửi lại mã nếu cần
                pass
            try:
                code = get_code_func()
            except Exception as e:
                print(f"   [Step 2] Error getting code: {e}")
                code = None
            if not code:
                if attempt < max_retries:
                    print("   [Step 2] No code found via mail. Retrying...")
                    time.sleep(2)  # Reduced from 3s to 2s for faster retry
                    continue
                else:
                    raise Exception("STOP_FLOW_CHECK_MAIL: No code found in mail")
            print(f"   [Step 2] Inputting code {code}...")
            try:
                if not self._is_driver_alive():
                    raise Exception("Browser closed before input")
                input_code_func(code)
                if not self._is_driver_alive():
                    raise Exception("Browser closed during input")
                print("   [Step 2] Waiting for UI to update after code input...")
                wait_and_click(self.driver, By.CSS_SELECTOR, "button[type='submit']", timeout=20)
                # Tăng thời gian chờ sau khi nhấn submit để tránh check mail quá sớm khi UI còn đang xử lý
                WebDriverWait(self.driver, 10).until(lambda d: d.execute_script("return document.readyState") == "complete")
                time.sleep(1)  # Reduced sleep to 1s
                print("   [Step 2] Verifying code...")
                check_result = self._check_verification_result()
                print(f"   [Step 2] Result: {check_result}")
            except Exception as e:
                if "closed" in str(e).lower() or "crash" in str(e).lower() or "stale" in str(e).lower() or "not reachable" in str(e).lower():
                    raise Exception("STOP_FLOW_CRASH: Browser closed during code verification")
                else:
                    print(f"   [Step 2] Error during code input/verification: {e}")
                    if attempt < max_retries:
                        print("   [Step 2] Retrying due to error...")
                        time.sleep(1)
                        continue
                    else:
                        raise
            if check_result in ["CHECKPOINT_MAIL", "WRONG_CODE", "CAN_GET_NEW_CODE", "TIMEOUT"]:
                if attempt < max_retries:
                    if check_result in ["WRONG_CODE", "CAN_GET_NEW_CODE"]:
                        # Click "Get new code" link or button using JS for precision
                        try:
                            get_new_element = self.driver.execute_script("""
                                // Check links first
                                var links = document.querySelectorAll('a');
                                for (var i = 0; i < links.length; i++) {
                                    var text = links[i].textContent.trim().toLowerCase();
                                    if (text.includes('get a new one') || text.includes('get new code') || text.includes('get a new code') || 
                                        text.includes('didn\'t get a code') || text.includes('didn\'t receive') || text.includes('resend') || 
                                        text.includes('send new code') || text.includes('request new code') || text.includes('try again')) {
                                        return links[i];
                                    }
                                }
                                // Check buttons
                                var buttons = document.querySelectorAll('button');
                                for (var i = 0; i < buttons.length; i++) {
                                    var text = buttons[i].textContent.trim().toLowerCase();
                                    if (text.includes('get a new one') || text.includes('get new code') || text.includes('get a new code') || 
                                        text.includes('didn\'t get a code') || text.includes('didn\'t receive') || text.includes('resend') || 
                                        text.includes('send new code') || text.includes('request new code') || text.includes('try again')) {
                                        return buttons[i];
                                    }
                                }
                                return null;
                            """)
                            if get_new_element:
                                self.driver.execute_script("arguments[0].click();", get_new_element)
                                print("   [Step 2] Clicked 'Get new code' via JS.")
                                time.sleep(2)  # Wait for new code to be sent
                            else:
                                print("   [Step 2] 'Get new code' element not found via JS.")
                        except Exception as e:
                            print(f"   [Step 2] Error clicking 'Get new code' via JS: {e}")
                    print("   [Step 2] Code verification failed (wrong/rejected/timeout), retrying mail...")
                    continue
                else:
                    raise Exception("STOP_FLOW_CHECKPOINT_MAIL_EXHAUSTED: Max mail attempts reached")
            return check_result



    def _handle_change_password(self, old_password):
        """Xử lý đổi mật khẩu: Chỉ điền 1 input duy nhất và nhấn Confirm."""
        start_time = time.time()
        TIMEOUT = 120
        print(f"   [Step 2] Handling Password Change (Single Input Mode)...")
        
        try:
            # 1. Tìm ô input (Sử dụng danh sách ưu tiên để tìm đúng ô New Password)
            # Chúng ta tìm tất cả nhưng sẽ chỉ thao tác với thằng đầu tiên hiển thị
            password_input = None
            selectors = [
                "input[name='password']", 
                "input[name='new_password']", 
                "input[type='password']",
                "input[aria-label*='Password']"
            ]
            
            # Chờ đợi thông minh cho đến khi thấy ít nhất 1 ô input
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for el in elements:
                        if el.is_displayed() and el.is_enabled():
                            password_input = el
                            break
                    if password_input: break
                except: continue

            if not password_input:
                raise Exception("STOP_FLOW: No visible password input field found")

            # 2. Thao tác điền mật khẩu vào DUY NHẤT 1 ô
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", password_input)
                time.sleep(0.5)
                password_input.click()
                password_input.clear()
                password_input.send_keys(old_password)
                print(f"   [Step 2] Filled password into the primary input field.")
            except Exception as e:
                raise Exception(f"STOP_FLOW: Failed to fill password input: {str(e)}")

            time.sleep(0.8) # Ổn định UI ngắn

            # 3. Xử lý Submit (Confirm)
            submit_clicked = False
            
            # Ưu tiên 1: Click bằng Selector chuẩn
            submit_selectors = [
                "button[type='submit']",
                "div[role='button'][type='submit']",
                "button:not([disabled])" # Nút bất kỳ không bị disable
            ]
            
            for sel in submit_selectors:
                if wait_and_click(self.driver, By.CSS_SELECTOR, sel, timeout=5):
                    submit_clicked = True
                    break
            
            # Ưu tiên 2: Fallback quét text nếu Selector chuẩn thất bại
            if not submit_clicked:
                btns = self.driver.find_elements(By.TAG_NAME, 'button')
                for b in btns:
                    try:
                        text = b.text.lower()
                        if b.is_displayed() and any(k in text for k in ["change", "submit", "continue", "save", "update", "confirm", "xác nhận", "tiếp tục"]):
                            self.driver.execute_script("arguments[0].click();", b)
                            submit_clicked = True
                            break
                    except: continue

            # Ưu tiên 3: Nhấn Enter nếu không tìm thấy nút
            if not submit_clicked:
                print("   [Step 2] No button found. Pressing Enter...")
                password_input.send_keys(Keys.ENTER)
                submit_clicked = True

            # 4. Đợi hoàn tất chuyển trang
            print("   [Step 2] Submitted. Waiting for page transition...")
            time.sleep(5) 
            WebDriverWait(self.driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            
            if time.time() - start_time > TIMEOUT:
                raise Exception("TIMEOUT_CHANGE_PASSWORD: Total time exceeded")

        except Exception as e:
            print(f"   [Step 2] Error in password change flow: {e}")
            if "STOP_FLOW" in str(e):
                raise e # Ném lỗi nghiêm trọng lên tầng trên xử lý

        return True
    def _check_verification_result(self):
        # Timeout protection for verification result (max 60s)
        # Optimized with JS checks to avoid hangs and speed up detection
        TIMEOUT = 20
        end_time = time.time() + TIMEOUT
        consecutive_failures = 0
        max_consecutive_failures = 20  # If JS fails 20 times in a row, consider timeout
        try:
            WebDriverWait(self.driver, 10).until(lambda d: self._safe_execute_script("return document.readyState") == "complete")
        except Exception as e:
            print(f"   [Step 2] Page not ready after 10s: {e}")
        while time.time() < end_time:
            try:
                # Get body text safely
                body_text = ""
                try:
                    body_element = self.driver.find_element(By.TAG_NAME, "body")
                    body_text = body_element.text.lower()
                except:
                    body_text = ""
                
                # Check URL for unblock terms
                current_url = self.driver.current_url.lower()
                if "unblock" in current_url: 
                    return "UNBLOCK_ACCOUNT"
                
                # Check URL for cookie choice
                if "user_cookie_choice" in current_url:
                    return "COOKIE_CONSENT_POPUP"
                
                if "api/v1/discover/ayml/" in current_url:
                    return "SOMETHING_WRONG"
                
                # you need to request help logging in To secure your account, you need to request help logging in
                if "you need to request help logging in" in body_text or "to secure your account, you need to request help logging in" in body_text:
                    return "GET_HELP_LOG_IN"
                
                if "use another profile" in body_text and "continue" in body_text:
                    return "RETRY_LOGIN"
                
                # We suspect automated behavior on your account
                if 'we suspect automated behavior on your account' in body_text:
                    return "AUTOMATED_BEHAVIOR_DETECTED"
                
                if 'prevent your account from being temporarily ' in body_text or 'verify you are a real person' in body_text or 'suspicious activity' in body_text:
                    return "AUTOMATED_BEHAVIOR_DETECTED"
                
                if "the login information you entered is incorrect" in body_text or \
                       "incorrect username or password" in body_text or \
                        "thông tin đăng nhập bạn đã nhập không chính xác" in body_text or "find your account and log in" in body_text:
                    return "LOGIN_FAILED_INCORRECT"
                
                if "enter the 6-digit code we sent to the number ending in" in body_text:
                    return "CHECKPOINT_PHONE"
                
                # keep using your personal data across these accounts / use data across accounts / manage accounts
                if "keep using your personal data across these accounts" in body_text or "use data across accounts" in body_text or "manage accounts" in body_text:
                    return "ACCOUNTS_CENTER_DATA_SHARING"
            
                # enter your email
                if "enter your email" in body_text or "please enter your email address to continue" in body_text:
                    return "DISABLE_ACCOUNT"
                
                # Log in on another device to continue
                if "log in on another device to continue" in body_text or "đăng nhập trên thiết bị khác để tiếp tục" in body_text:
                    return "LOG_IN_ANOTHER_DEVICE"
                
                if "add phone number to get back into instagram" in body_text or "send confirmation" in body_text or "log into another account" in body_text or "we will send a confirmation code via sms to your phone." in body_text: 
                    return "SUSPENDED_PHONE"
                # this was me / let us know if it was you
                if "this was me" in body_text or "let us know if it was you" in body_text:
                    return "CONFIRM_TRUSTED_DEVICE"
                
                # Which email should we send the code to?
                if "which email should we send the code to" in body_text:
                    return "SELECT_EMAIL_TO_SEND_CODE"

                # check your text messages
                    return "2FA_TEXT_MESSAGE"
                
                # Help us confirm it's you
                if "help us confirm it's you" in body_text or "xác nhận đó là bạn" in body_text:
                    return "CONFIRM_YOUR_IDENTITY"
                
                # SMS 2FA screen "Enter a 6-digit login code generated by an authentication app." or vietnamese
                if "mã đăng nhập 6 chữ số được tạo bởi ứng dụng xác thực" in body_text or "enter a 6-digit login code generated by an authentication app." in body_text:
                    return "2FA_SMS"

                    # Check your WhatsApp messages 
                if "check your whatsapp messages" in body_text or "kiểm tra tin nhắn whatsapp của bạn" in body_text or "we sent via whatsapp to" in body_text:
                    return "2FA_WHATSAPP"
                
                # your post goes against our community standards / How we make decisions
                if "your post goes against our community standards" in body_text or "bài đăng của bạn vi phạm các tiêu chuẩn cộng đồng của chúng tôi" in body_text or "how we make decisions" in body_text:
                    return "POST_VIOLATES_COMMUNITY_STANDARDS"


                    # Confirm your info on the app 
                if "confirm your info on the app" in body_text:
                    return "2FA_APP"
                
                #  Check your email or This email will replace all existing contact and login info on your account
                if 'check your email' in body_text or 'this email will replace all existing contact and login info on your account' in body_text:
                    return "CHECKPOINT_MAIL"
                
                #  We couldn't connect to Instagram. Make sure you're connected to the internet and try again. 
                if "we couldn't connect to instagram" in body_text and "make sure you're connected to the internet" in body_text:
                    return "NOT_CONNECT_INSTAGRAM"
                
                if "choose a way to recover" in body_text:
                    return "RECOVERY_CHALLENGE"
                
                # Choose if we process your data for ads
                if "choose if we process your data for ads" in body_text or "choose whether we process your data for ads" in body_text or "choose if we can process your data for ads" in body_text or "chọn nếu chúng tôi xử lý dữ liệu của bạn cho quảng cáo" in body_text:
                    return "DATA_PROCESSING_FOR_ADS"
                
                if 'change password' in body_text or 'new password' in body_text or 'create a strong password' in body_text or 'change your password to secure your account' in body_text:
                    # nếu có new confirm new password thì require change password
                    if len(self._safe_execute_script("return Array.from(document.querySelectorAll('input[type=\"password\"]'));", [])) >= 2:
                        return "REQUIRE_PASSWORD_CHANGE"
                    else:
                        return "CHANGE_PASSWORD"
                
                if 'add phone number' in body_text or 'send confirmation' in body_text or 'log into another account' in body_text:
                    return "SUSPENDED_PHONE"
                
                if "password" in body_text and "mobile number,username or email" in body_text:
                    return "RETRY_LOGIN_2"
                
                if "you will be logged out anywhere else when your new password is set" in body_text:
                    return "PASSWORD_CHANGE_CONFIRMATION"
                
                if 'select your birthday' in body_text or 'add your birthday' in body_text:
                    return "BIRTHDAY_SCREEN"
                
                if 'suspended' in body_text or 'đình chỉ' in body_text:
                    return "SUSPENDED"
                # some thing wrong 
                if 'something went wrong' in body_text or 'đã xảy ra sự cố' in body_text or "this page isn’t working" in body_text or 'the site is temporarily unavailable' in body_text or "reload" in body_text or "HTTP ERROR" in body_text or "HTTP 500" in body_text or "HTTP 502" in body_text or "HTTP 504" in body_text or "useragent mismatch" in body_text:
                    return "SOMETHING_WRONG"
                
                if 'sorry, there was a problem' in body_text or 'please try again' in body_text:
                    return "RETRY_UNUSUAL_LOGIN"
                
                # Check for wrong code
                if 'code isn\'t right' in body_text or 'mã không đúng' in body_text or 'incorrect' in body_text or 'wrong code' in body_text or 'invalid' in body_text or 'the code you entered' in body_text:
                    return "WRONG_CODE"
                
                if 'create a password at least 6 characters long' in body_text or 'password must be at least 6 characters' in body_text:
                    return "REQUIRE_PASSWORD_CHANGE"
                
                # enter your real birthday
                if 'enter your real birthday' in body_text or 'nhập ngày sinh thật của bạn' in body_text:
                    return "REAL_BIRTHDAY_REQUIRED"
                
                # for you , following , also from meta, Suggested for you , Get fresh updates here when you follow accounts
                if 'for you' in body_text or 'following' in body_text or 'suggested for you' in body_text or 'get fresh updates here when you follow accounts' in body_text: 
                    return "LOGGED_IN_SUCCESS"
                
                # use another profile va log into instagram => dang nhap lai voi data moi 
                if 'log into instagram' in body_text or 'use another profile' in body_text or "create new account" in body_text :
                    if "continue" in body_text or "tiếp tục" in body_text:
                        return "RETRY_LOGIN"
                    return "FAIL_LOGIN_REDIRECTED_TO_PROFILE_SELECTION"  
                
                if 'save your login info' in body_text or 'we can save your login info' in body_text or 'lưu thông tin đăng nhập' in body_text:
                    return "LOGGED_IN_SUCCESS"
                
                # save info or not now
                if self._safe_execute_script("return (document.querySelector('button[type=\"submit\"]') !== null && (document.body.innerText.toLowerCase().includes('save info') || document.body.innerText.toLowerCase().includes('not now') || document.body.innerText.toLowerCase().includes('để sau')))", False):
                    return "LOGGED_IN_SUCCESS"
                if 'save your login info' in body_text or 'we can save your login info' in body_text or 'lưu thông tin đăng nhập' in body_text:
                    return "LOGGED_IN_SUCCESS"
                
                # save info or not now
                if self._safe_execute_script("return (document.querySelector('button[type=\"submit\"]') !== null && (document.body.innerText.toLowerCase().includes('save info') || document.body.innerText.toLowerCase().includes('not now') || document.body.innerText.toLowerCase().includes('để sau')))", False):
                    return "LOGGED_IN_SUCCESS"
                
                # post , follower, following edit profile
                if 'posts' in body_text or 'followers' in body_text or 'following' in body_text or 'edit profile' in body_text:
                    return "LOGGED_IN_SUCCESS"
                
                
                
                # Want to subscribe or continue
                if 'subscribe' in body_text:
                    return "SUBSCRIBE_OR_CONTINUE"
                    return "LOGGED_IN_SUCCESS"
                if 'save your login info' in body_text or 'we can save your login info' in body_text or 'lưu thông tin đăng nhập' in body_text:
                    return "LOGGED_IN_SUCCESS"
                
                # save info or not now
                if self._safe_execute_script("return (document.querySelector('button[type=\"submit\"]') !== null && (document.body.innerText.toLowerCase().includes('save info') || document.body.innerText.toLowerCase().includes('not now') || document.body.innerText.toLowerCase().includes('để sau')))", False):
                    return "LOGGED_IN_SUCCESS"
                
                
                
                # Want to subscribe or continue
                if 'subscribe' in body_text:
                    return "SUBSCRIBE_OR_CONTINUE"
                
                # Check if "get new code" option is available
                if 'get a new one' in body_text or 'get new code' in body_text or 'get a new code' in body_text or 'didn\'t get a code' in body_text or 'didn\'t receive' in body_text or 'resend' in body_text or 'send new code' in body_text or 'request new code' in body_text:
                    return "CAN_GET_NEW_CODE"
                
                if "log into instagram" in body_text or "password" in body_text or "mobile number, username, or email" in body_text or "log in with facebook" in body_text or "create new account" in body_text:
                    self.count += 1
                    if self.count >=20:
                        return "LOGIN_FAILED"
                    
                    # Nếu vẫn còn ô password -> Login chưa qua (có thể đang loading)
                if len(self.driver.find_elements(By.CSS_SELECTOR, "input[type='password']")) > 0:
                    self.count += 1
                    if self.count >=20:
                        return "LOGIN_FAILED_RETRY"
                
                consecutive_failures = 0  # Reset on successful check
            except Exception as e:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    print(f"   [Step 2] Too many JS failures in verification check: {e}")
                    break
            time.sleep(1.0)
        # Log current state for debugging timeout
        try:
            current_url = self.driver.current_url
            body_text = self.driver.find_element(By.TAG_NAME, "body").text[:500]  # First 500 chars
            print(f"   [Step 2] TIMEOUT reached. Current URL: {current_url}")
            print(f"   [Step 2] Page body preview: {body_text}...")
            
            # Capture screenshot for timeout (unknown status)
            timestamp = int(time.time())
            screenshot_dir = "screenshots"
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_path = os.path.join(screenshot_dir, f"timeout_unknown_status_{timestamp}.png")
            self.driver.save_screenshot(screenshot_path)
            print(f"   [Step 2] Screenshot saved for timeout unknown status: {screenshot_path}")
            
            # Additional check: If we're on checkpoint mail screen but regex didn't catch it
            # Check for radio buttons (typical in checkpoint mail)
            try:
                radios = self._safe_execute_script("return Array.from(document.querySelectorAll('input[type=\"radio\"]')).length;", 0)
                if radios > 0:
                    print(f"   [Step 2] Found {radios} radio buttons, likely checkpoint mail screen")
                    return "CHECKPOINT_MAIL"
            except:
                pass
            
            # Check for code input fields
            try:
                code_inputs = self._safe_execute_script("return Array.from(document.querySelectorAll('input[type=\"text\"], input[name=\"security_code\"], input[id=\"security_code\"])).length;", 0)
                if code_inputs > 0:
                    print(f"   [Step 2] Found {code_inputs} text inputs, likely checkpoint mail screen")
                    return "CHECKPOINT_MAIL"
            except:
                pass
            
            # Check for common checkpoint mail keywords that might have been missed
            try:
                checkpoint_keywords = ["checkpoint", "verify", "verification", "security code", "confirmation code", "email verification", "mã xác nhận", "xác nhận email"]
                if any(keyword in body_text for keyword in checkpoint_keywords):
                    print("   [Step 2] Found checkpoint-related keywords, likely checkpoint mail screen")
                    return "CHECKPOINT_MAIL"
            except:
                pass
                
        except Exception as e:
            print(f"   [Step 2] Error logging timeout state: {e}")
        return "TIMEOUT"

    def _fill_input_with_delay(self, input_el, text_value):
        """Nhập text vào input với delay giữa mỗi ký tự để mô phỏng nhập thật."""
        val = str(text_value).strip()
        try:
            ActionChains(self.driver).move_to_element(input_el).click().perform()
            input_el.clear()
            for char in val:
                input_el.send_keys(char)
                time.sleep(0.1)  # Delay 0.1s giữa mỗi ký tự
            time.sleep(0.5)  # Chờ sau khi nhập xong
            return input_el.get_attribute("value") == val
        except Exception as e:
            print(f"   [Step 2] Input fill failed: {e}")
            return False