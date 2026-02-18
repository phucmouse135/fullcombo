# step4_2fa.py
import time
import re
import pyotp
import pyperclip
import hashlib
import subprocess
from urllib.parse import urlparse, parse_qs
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from config_utils import wait_dom_ready, wait_element, wait_and_click

# Import Mail Handler
from mail_handler_v2 import get_2fa_code_v2

class Instagram2FAStep:
    def __init__(self, driver):
        self.driver = driver
        self.target_url = "https://accountscenter.instagram.com/password_and_security/two_factor/"

    def _safe_element_action(self, action_func, max_retries=3, delay=0.5):
        """
        Helper to perform element actions with retry on StaleElementReferenceException.
        Ensures stability by re-locating elements if they become stale.
        """
        from selenium.common.exceptions import StaleElementReferenceException
        for attempt in range(max_retries):
            try:
                return action_func()
            except StaleElementReferenceException:
                if attempt < max_retries - 1:
                    print(f"   [Step 4] Element stale, retrying ({attempt+1}/{max_retries})...")
                    time.sleep(delay)
                else:
                    raise
        return False

    def _find_code_input(self):
        """
        Helper to find the code input element using JS.
        """
        return self.driver.execute_script("""
            var inputs = document.querySelectorAll('input');
            for (var inp of inputs) {
                if (inp.offsetParent !== null) {
                    var name = inp.name.toLowerCase();
                    var placeholder = inp.placeholder ? inp.placeholder.toLowerCase() : '';
                    var id = inp.id ? inp.id.toLowerCase() : '';
                    if (name === 'code' || placeholder.includes('code') || inp.type === 'tel' || inp.maxLength == 6 || id.startsWith('_r_') || (inp.type === 'text' && inp.autocomplete === 'off')) {
                        return inp;
                    }
                }
            }
            return null;
        """)
        
    def _validate_key(self, secret_key):
        """Hàm kiểm tra xem Secret Key có tạo được OTP hợp lệ không."""
        try:
            key_for_otp = secret_key.replace(" ", "").strip()
            # Thử khởi tạo TOTP, nếu key sai định dạng Base32 pyotp sẽ raise Error
            totp = pyotp.TOTP(key_for_otp)
            otp_code = totp.now()
            # Kiểm tra OTP phải là 6 chữ số
            if otp_code and len(otp_code) == 6 and otp_code.isdigit():
                return True
            return False
        except Exception:
            return False

    def setup_2fa(self, gmx_user, gmx_pass, target_username, linked_mail=None):
        """
        Setup 2FA Flow - Logic gốc bảo toàn, thêm tối ưu chống treo.
        """
        try: 
            print(f"   [{target_username}] [Step 4] Accessing settings...")
            print(f"   [{target_username}] [Step 4] Starting 2FA Setup for {target_username}...")
            
            # Đồng bộ thời gian hệ thống với NTP
            try:
                subprocess.run(['w32tm', '/resync', '/force'], capture_output=True, timeout=10)
                print(f"   [{target_username}] [Step 4] System time synced with NTP.")
            except Exception as e:
                print(f"   [{target_username}] [Step 4] NTP sync failed: {e}, proceeding.")
            
            self.driver.get(self.target_url)
            wait_dom_ready(self.driver, timeout=5)

            # --- 0. BYPASS 'DOWNLOAD APP' PAGE ---
            self._bypass_lite_page()

            # -------------------------------------------------
            # STEP 1: SELECT ACCOUNT
            # -------------------------------------------------
            print(f"   [{target_username}] [2FA] Step 1: Selecting Account...")
            acc_selected = False
            for attempt in range(3):
                try:
                    wait_element(self.driver, By.XPATH, "//div[@role='button'] | //a[@role='link']", timeout=5)
                    clicked = self.driver.execute_script("""
                        var els = document.querySelectorAll('div[role="button"], a[role="link"]');
                        for (var i=0; i<els.length; i++) {
                            if (els[i].innerText.toLowerCase().includes('instagram')) { els[i].click(); return true; }
                        }
                        return false;
                    """)
                    if clicked: 
                        acc_selected = True
                        wait_dom_ready(self.driver, timeout=5)
                        break
                    else:
                        if "lite" in self.driver.current_url: 
                            self.driver.get(self.target_url)
                            wait_dom_ready(self.driver, timeout=5)
                        else: time.sleep(1)
                except: time.sleep(1)
            
            if not acc_selected: print(f"   [{target_username}] [2FA] Warning: Select Account failed (May already be inside).")

            
            wait_dom_ready(self.driver, timeout=5)
            time.sleep(3)  # Chờ thêm 3s để trang ổn định

            # -------------------------------------------------
            # STEP 2: SCAN STATE & HANDLE EXCEPTIONS
            # -------------------------------------------------
            print(f"   [{target_username}] [Step 4] Scanning UI State...")
            state = "UNKNOWN"
            broken_retries = 0  # Biến đếm số lần cứu hộ
            
            # Quét 15 lần (Logic gốc)
            for _ in range(15):
                state = self._get_page_state()
                
                # UNUSUAL LOGIN FIX
                if state == 'UNUSUAL_LOGIN':
                    print(f"   [{target_username}] [Step 4] Detected 'Unusual Login'. Clicking 'This Was Me'...")
                    if self._click_continue_robust():
                        print(f"   [{target_username}] [Step 4] Clicked 'This Was Me'. Waiting...")
                        wait_dom_ready(self.driver, timeout=5)
                        if "two_factor" not in self.driver.current_url:
                            self.driver.get(self.target_url)
                            wait_dom_ready(self.driver, timeout=5)
                    continue 

                if state == 'LITE_PAGE': 
                    self.driver.get(self.target_url)
                    wait_dom_ready(self.driver, timeout=5)
                    continue
                
                # BLOCK UNSUPPORTED METHODS
                if state == 'WHATSAPP_REQUIRED': 
                    raise Exception("STOP_FLOW_2FA: WhatsApp Verification Required")
                if state == 'SMS_REQUIRED': 
                    raise Exception("STOP_FLOW_2FA: SMS Verification Required")

                # [MODIFIED] Xử lý BROKEN: Thử Refresh thay vì chết ngay
                if state == 'BROKEN': 
                    broken_retries += 1
                    if broken_retries <= 2:
                        print(f"   [{target_username}] [Step 4] ⚠️ State detected: BROKEN/UNAVAILABLE. Attempting Refresh Recovery ({broken_retries}/2)...")
                        self.driver.refresh()
                        wait_dom_ready(self.driver, timeout=10)
                        time.sleep(3)
                        continue # Quay lại đầu vòng lặp để check lại state
                    else:
                        raise Exception("STOP_FLOW_2FA: Page Broken/Content Unavailable (After Refreshes)")
                
                # Thoát vòng lặp nếu trạng thái đã rõ ràng
                if state in ['SELECT_APP', 'CHECKPOINT', 'ALREADY_ON', 'RESTRICTED', 'OTP_INPUT_SCREEN']: 
                    break
                
                time.sleep(1)

            print(f"   [{target_username}] [Step 4] Detected State: {state}")

            if state == 'RESTRICTED': 
                raise Exception("STOP_FLOW_2FA: RESTRICTED_DEVICE")
            if state == 'SUSPENDED': 
                raise Exception("STOP_FLOW_2FA: ACCOUNT_SUSPENDED")
            if state == 'ALREADY_ON': 
                print(f"   [{target_username}] [Step 4] 2FA is already ON.")
                return "ALREADY_2FA_ON"

            # -------------------------------------------------
            # STEP 2.5: HANDLE CHECKPOINT (INTERNAL)
            # -------------------------------------------------
            if state == 'CHECKPOINT':
                print(f"   [{target_username}] [Step 4] Step 2.5: Handling Internal Checkpoint...")
                if not self._validate_masked_email_robust(gmx_user, linked_mail):
                    print(f"   [{target_username}] [STOP] Script halted: Targeted email is not yours.")
                    raise Exception("STOP_FLOW_2FA: EMAIL_MISMATCH") 
                time.sleep(1.5)
                result = self._solve_internal_checkpoint(gmx_user, gmx_pass, target_username)
                state = self._get_page_state()

            # -------------------------------------------------
            # STEP 3: SELECT AUTH APP
            # -------------------------------------------------
            print(f"   [{target_username}] [Step 4] Step 3: Selecting Auth App...")
            self._select_auth_app_method(state)

            # -------------------------------------------------
            # STEP 4: GET SECRET KEY (CHỐT CHẶN CỨNG - KHÔNG SKIP)
            # -------------------------------------------------
            wait_dom_ready(self.driver, timeout=20)
            print(f"   [{target_username}] [Step 4] Step 4: Getting Secret Key (Blocking until captured)...")
            time.sleep(5) 
            
            # [UPDATED] Hàm này đã được tối ưu để check Anti-Freeze
            secret_key = self._extract_secret_key(ig_username = target_username)
            
            def format_key_groups(key):
                key_nospaces = key.replace(" ", "")
                return " ".join([key_nospaces[i:i+4] for i in range(0, len(key_nospaces), 4)])

            secret_key_grouped = format_key_groups(secret_key)
            self.last_secret_key_raw = secret_key_grouped # Lưu lại cho GUI
            
            print(f"\n========================================\n[{target_username}] [Step 4] !!! SECRET KEY FOUND: {secret_key_grouped}\n========================================\n")

            # Prepare TOTP for later use (SHA1, 6 digits, 30s interval)
            key_for_otp = secret_key.replace(" ","")
            totp = pyotp.TOTP(key_for_otp, interval=30, digits=6, digest=hashlib.sha1)

            # Callback GUI
            if hasattr(self, 'on_secret_key_found') and callable(self.on_secret_key_found):
                try: self.on_secret_key_found(secret_key_grouped)
                except Exception as e: print(f"[{target_username}] [Step 4] GUI callback error: {e}")

            # -------------------------------------------------
            # STEP 5: CONFIRM OTP (FIXED INPUT)
            # -------------------------------------------------
            print(f"   [{target_username}] [Step 4] Clicking Next to Input OTP...")
            self._click_continue_robust()
            
            # Đảm bảo chắc chắn sang màn hình nhập OTP (giảm timeout xuống 5s, poll 0.5s)
            wait_end = time.time() + 5
            while time.time() < wait_end:
                if self._get_page_state() == 'OTP_INPUT_SCREEN':
                    print(f"   [{target_username}] [Step 4] Confirmed: On OTP Input Screen.")
                    break
                time.sleep(0.5)
            else:
                print(f"   [{target_username}] [Step 4] Warning: Not on OTP input screen yet, proceeding anyway.")
            
            # Generate OTP just before using to avoid expiration (at start of time window)
            current_time = int(time.time())
            window_start = current_time - (current_time % 30)
            otp_code = totp.at(window_start)
            print(f"   [{target_username}] [Step 4] Generated OTP Code: {otp_code}")
            
            # Time Drift Prevention: If less than 6s left in window, wait for next cycle
            remaining = 30 - (int(time.time()) % 30)
            if remaining < 6:
                print(f"   [{target_username}] [Step 4] Less than 6s left in window ({remaining}s), waiting for next cycle...")
                time.sleep(remaining + 1)
                current_time = int(time.time())
                window_start = current_time - (current_time % 30)
                otp_code = totp.at(window_start)
                print(f"   [{target_username}] [Step 4] Regenerated OTP after wait: {otp_code}")
            
            is_filled = False
            fill_end = time.time() + 5  # Giảm timeout xuống 5s
            while time.time() < fill_end:
                if self._robust_fill_input(otp_code):
                    is_filled = True; break
                print(f"   [{target_username}] [Step 4] Retrying input fill...")
                time.sleep(0.5)  # Poll nhanh hơn
                
            if not is_filled: 
                raise Exception("STOP_FLOW_2FA: OTP_INPUT_FAIL")
            
            print(f"   [{target_username}] [Step 4] OTP Input Filled. Confirming...")
            time.sleep(0.3)  # Giảm wait xuống 0.3s
            self._click_continue_robust()
            
            # -------------------------------------------------
            # LOGIC RECOVERY (CONTENT NO LONGER AVAILABLE)
            # -------------------------------------------------
            time.sleep(2) # Chờ popup
            
            is_error_popup = self.driver.execute_script("""
                var body = document.body.innerText.toLowerCase();
                var keywords = ["content is no longer available", "không khả dụng", "không hiển thị được lúc này"];
                return keywords.some(k => body.includes(k));
            """)

            if is_error_popup:
                print(f"   [{target_username}] [Step 4] ⚠️ CRITICAL: Error Pop-up detected! Initiating Recovery Flow...")
                
                # 1. RELOAD
                print(f"   [{target_username}] [Recovery] Reloading page...")
                self.driver.refresh(); wait_dom_ready(self.driver, timeout=10); time.sleep(2)
                # 2. CLICK NEXT
                print(f"   [{target_username}] [Recovery] Clicking Next/Continue...")
                self._click_continue_robust(); time.sleep(5)

                # 3. HANDOVER STEP 2
                print(f"   [{target_username}] [Recovery] Handover to Step 2 Handler...")
                from step2_exceptions import InstagramExceptionStep
                step2_handler = InstagramExceptionStep(self.driver)
                current_status = step2_handler._check_verification_result()
                print(f"   [{target_username}] [Recovery] Status detected: {current_status}")
                step2_handler.handle_status(current_status, target_username, gmx_user, gmx_pass, linked_mail, None)

                # 4. CLICK TO HOME
                print(f"   [{target_username}] [Recovery] Finalizing: Clearing post-login screens...")
                max_final_clicks = 8
                for i in range(max_final_clicks):
                    curr_url = self.driver.current_url.lower()
                    try: body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                    except: body_text = ""

                    is_home = "instagram.com/" in curr_url and \
                            "/challenge/" not in curr_url and \
                            "/two_factor/" not in curr_url and \
                            any(k in body_text for k in ["search", "home", "reels", "direct", "posts"])
                    
                    if is_home:
                        print(f"   [{target_username}] [Recovery] SUCCESS: Reached Instagram Home.")
                        break 
                    
                    clicked = self.driver.execute_script("""
                        var selectors = ["button", "div[role='button']", "span"];
                        var keywords = ["next", "tiếp", "continue", "submit", "xác nhận", "confirm", "done", "xong", "save", "lưu", "not now", "lúc khác"];
                        for (var sel of selectors) {
                            var btns = document.querySelectorAll(sel);
                            for (var b of btns) {
                                var txt = b.innerText.toLowerCase();
                                if (b.offsetParent !== null && keywords.some(k => txt.includes(k))) {
                                    b.click(); return true;
                                }
                            }
                        }
                        return false;
                    """)
                    if not clicked: time.sleep(1)
                    else: time.sleep(2)

                print(f"   [{target_username}] [Recovery] Flow Completed. Returning Success immediately.")
                return secret_key 

            else:
                print(f"   [{target_username}] [Step 4] No error pop-up detected. Continuing standard check...")
            
            # -------------------------------------------------
            # STANDARD CHECK (DONE BUTTON)
            # -------------------------------------------------
            print(f"   [{target_username}] [Step 4] Waiting for completion...")
            end_confirm = time.time() + 60
            success = False
            wrong_otp_count = 0
            max_wrong_retries = 3
            
            # [ADDED] Pre-check: If URL redirected to settings home, it's a success
            if "two_factor" not in self.driver.current_url and "challenge" not in self.driver.current_url:
                 print(f"   [{target_username}] [Step 4] URL redirected away from 2FA flow. Assessing success...")
                 # Verify 2FA status via page state might be hard here without navigation, 
                 # but assume success if no error and URL changed significantly (e.g. to accounts center home)
            
            while time.time() < end_confirm:
                res = self.driver.execute_script("""
                    var body = document.body.innerText.toLowerCase();
                    if (body.includes("code isn't right") || body.includes("mã không đúng")) return 'WRONG_OTP';
                    
                    // Success Signals
                    if (body.includes("authentication is on") || body.includes("đang bật")) return 'SUCCESS';
                    if (body.includes("this content is no longer available") || body.includes("không khả dụng")) return 'SUCCESS';
                    
                    // Button Click Attempt
                    var doneBtns = document.querySelectorAll("span, div[role='button'], button");
                    for(var b of doneBtns) {
                        var txt = b.innerText.trim().toLowerCase();
                        if((txt === 'done' || txt === 'xong') && b.offsetParent !== null) {
                            try { b.click(); } catch(e){} 
                            return 'SUCCESS';
                        }
                    }
                    
                    return 'WAIT';
                """)
                
                # [ADDED] Check URL change as implicit success signal
                current_url = self.driver.current_url
                if "password_and_security" in current_url and "two_factor" not in current_url:
                     # Returned to P&S menu usually means done
                     print(f"   [{target_username}] [Step 4] Implicit Success: Returned to Password & Security menu.")
                     success = True; break

                if res == 'WRONG_OTP': 
                    wrong_otp_count += 1
                    if wrong_otp_count < max_wrong_retries:
                        print(f"   [{target_username}] [Step 4] Wrong OTP detected, retrying ({wrong_otp_count}/{max_wrong_retries})...")
                        # Regenerate and re-input with drift prevention
                        current_time = int(time.time())
                        window_start = current_time - (current_time % 30)
                        otp_code = totp.at(window_start)
                        remaining = 30 - (int(time.time()) % 30)
                        if remaining < 6:
                            time.sleep(remaining + 1)
                            current_time = int(time.time())
                            window_start = current_time - (current_time % 30)
                            otp_code = totp.at(window_start)
                        print(f"   [{target_username}] [Step 4] Regenerated OTP: {otp_code}")
                        # Re-input
                        is_filled = False
                        fill_end = time.time() + 5
                        while time.time() < fill_end:
                            if self._robust_fill_input(otp_code):
                                is_filled = True
                                break
                            time.sleep(0.5)
                        if is_filled:
                            print(f"   [{target_username}] [Step 4] Re-input OTP. Confirming...")
                            time.sleep(0.3)
                            self._click_continue_robust()
                            # Reset the confirm timer
                            end_confirm = time.time() + 60
                            continue
                        else:
                            raise Exception("STOP_FLOW_2FA: OTP_INPUT_FAIL")
                    else:
                        raise Exception("STOP_FLOW_2FA: OTP_REJECTED")
                if res == 'SUCCESS' or self._get_page_state() == 'ALREADY_ON': 
                    success = True
                    print(f"   [{target_username}] [Step 4] => SUCCESS: 2FA Enabled.")
                    break
                time.sleep(1)

            if not success: 
                raise Exception("STOP_FLOW_2FA: TIMEOUT (Done button not found)")
            time.sleep(1)
            return secret_key
        except Exception as e: # <--- THÊM EXCEPT ĐỂ BẮT MỌI LỖI
            err_msg = str(e)
            print(f"   [{target_username}] [Step 4] Error handled gracefully: {err_msg}")
            
            # Trả về nội dung lỗi để điền vào cột 2FA
            # Loại bỏ prefix "STOP_FLOW_2FA: " và "ERROR_2FA: " cho ngắn gọn
            clean_err = err_msg.replace("STOP_FLOW_2FA: ", "").replace("ERROR_2FA: ", "").strip()
            return f"ERROR_2FA: {clean_err}"

    # ==========================================
    # CORE HELPERS
    # ==========================================

    def _bypass_lite_page(self):
        if "lite" in self.driver.current_url or len(self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Download Instagram Lite')]")) > 0:
            print(f"   [{self.target_username if hasattr(self, 'target_username') else 'Unknown'}] [Step 4] Detected 'Download Lite' page. Attempting bypass...")
            try:
                btns = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Not now') or contains(text(), 'Lúc khác')]")
                if btns: 
                    btns[0].click(); wait_dom_ready(self.driver, timeout=5)
                else: 
                    self.driver.get(self.target_url); wait_dom_ready(self.driver, timeout=5)
            except: pass

    def _select_account_center_profile(self, target_username):
        acc_selected = False
        target_lower = target_username.lower()
        for attempt in range(5):  # Tăng số lần thử lên 5
            try:
                wait_element(self.driver, By.XPATH, "//div[@role='button'] | //a[@role='link']", timeout=5)
                
                # Use JS to find and click the account
                clicked = self.driver.execute_script(f"""
                    var target = '{target_lower}';
                    var elements = document.querySelectorAll('div[role="button"], a[role="link"]');
                    
                    // First: exact match with instagram
                    for (var el of elements) {{
                        var txt = el.textContent.toLowerCase();
                        if (txt.includes(target) && txt.includes('instagram')) {{
                            el.scrollIntoView({{behavior: 'instant', block: 'center'}});
                            el.click();
                            return true;
                        }}
                    }}
                    
                    // Second: any with username
                    for (var el of elements) {{
                        var txt = el.textContent.toLowerCase();
                        if (txt.includes(target)) {{
                            el.scrollIntoView({{behavior: 'instant', block: 'center'}});
                            el.click();
                            return true;
                        }}
                    }}
                    
                    // Third: any instagram
                    for (var el of elements) {{
                        var txt = el.textContent.toLowerCase();
                        if (txt.includes('instagram')) {{
                            el.scrollIntoView({{behavior: 'instant', block: 'center'}});
                            el.click();
                            return true;
                        }}
                    }}
                    
                    return false;
                """)
                
                if clicked:
                    wait_dom_ready(self.driver, timeout=5)
                    # Verify selection
                    try:
                        body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                        if target_lower in body_text or target_username in body_text:
                            print(f"   [Step 4] Verified: Account {target_username} selected")
                            acc_selected = True
                        else:
                            print(f"   [Step 4] Verification failed: Username not found in page, retrying...")
                            continue  # Try again
                    except:
                        print(f"   [Step 4] Verification error, assuming selected")
                        acc_selected = True
                    break
                else:
                    print(f"   [Step 4] No suitable account element found in attempt {attempt+1}")
                    time.sleep(1)
            except Exception as e:
                print(f"   [Step 4] Attempt {attempt+1} failed: {e}")
                time.sleep(1)
        if not acc_selected: 
            print("   [Step 4] Warning: Select Account failed (May already be inside).")
            return False
        return acc_selected

    def _get_page_state(self):
        # [UPDATED] JS Sensor nhanh + check Content Unavailable
        js_sensor = """
        function checkState() {
            var body = document.body.innerText.toLowerCase();
            var url = window.location.href;

            if (body.includes("content is no longer available")) return 'BROKEN';
            if (body.includes("sorry, this page isn't available")) return 'BROKEN';

            if (body.includes("download instagram lite") || url.includes("lite") || body.includes("download apk")) return 'LITE_PAGE';

            if (body.includes("unusual login") || body.includes("suspicious login")) return 'UNUSUAL_LOGIN';
            
            if (body.includes("you can't make this change")) return 'RESTRICTED';
            if (body.includes("suspended") || body.includes("đình chỉ")) return 'SUSPENDED';

            if (body.includes("authentication is on") || body.includes("xác thực 2 yếu tố đang bật")) return 'ALREADY_ON';
            
            // Move OTP_INPUT_SCREEN check UP to prevent false positive SELECT_APP
            var hasInput = document.querySelector("input[name='code']") || document.querySelector("input[placeholder*='Code']");
            var hasNext = false;
            var btns = document.querySelectorAll("button, div[role='button']");
            for (var b of btns) { if (b.innerText.toLowerCase().includes("next") || b.innerText.toLowerCase().includes("tiếp") || b.innerText.toLowerCase().includes("confirm") || b.innerText.toLowerCase().includes("xác nhận")) hasNext = true; }

            if (hasInput && (body.includes("authentication app") || body.includes("ứng dụng xác thực")) && hasNext) return 'OTP_INPUT_SCREEN';

            if (body.includes("help protect your account") || body.includes("authentication app")) return 'SELECT_APP';

            if (body.includes("check your whatsapp")) return 'WHATSAPP_REQUIRED';
            if (body.includes("check your sms")) return 'SMS_REQUIRED';

            // Check input fields for Checkpoint
            var inputs = document.querySelectorAll("input");
            for (var i=0; i<inputs.length; i++) {
                if (inputs[i].offsetParent !== null) {
                    var attr = (inputs[i].name + " " + inputs[i].placeholder + " " + inputs[i].getAttribute("aria-label")).toLowerCase();
                    if (attr.includes("code") || attr.includes("security") || inputs[i].type === "tel" || inputs[i].type === "number") {
                        return 'CHECKPOINT';
                    }
                }
            }
            if (body.includes("check your email")) return 'CHECKPOINT';

            var hasInput = document.querySelector("input[name='code']") || document.querySelector("input[placeholder*='Code']");
            var hasNext = false;
            var btns = document.querySelectorAll("button, div[role='button']");
            for (var b of btns) { if (b.innerText.toLowerCase().includes("next") || b.innerText.toLowerCase().includes("tiếp")) hasNext = true; }

            if (hasInput && body.includes("authentication app") && hasNext) return 'OTP_INPUT_SCREEN';
            return 'UNKNOWN';
        }
        return checkState();
        """
        try: return self.driver.execute_script(js_sensor)
        except: return 'UNKNOWN'

    def _solve_internal_checkpoint(self, gmx_user, gmx_pass, target_ig_username):
        print(f"   [Step 4] Solving Internal Checkpoint for {target_ig_username}...")
        checkpoint_passed = False
        start_time = time.time()
        max_duration = 120  # Timeout tổng 120s để tránh treo
        
        for mail_attempt in range(1, 4):
            if time.time() - start_time > max_duration:
                raise Exception("STOP_FLOW_2FA: Checkpoint timeout after 120s")
            
            print(f"   [Step 4] Mail Retrieval Attempt {mail_attempt}/3...")
            code = get_2fa_code_v2(gmx_user, gmx_pass, target_ig_username)
            
            if not code:
                if self._get_page_state() in ['SELECT_APP', 'ALREADY_ON']: 
                    checkpoint_passed = True; break
                print("   [Step 4] Code not found. Clicking 'Get new code'...")
                self.driver.execute_script("var a=document.querySelectorAll('span, div[role=\"button\"]'); for(var e of a){if(e.innerText.toLowerCase().includes('get a new code')){e.click();break;}}")
                # Poll for new code (giảm xuống 2 lần)
                for poll in range(2):
                    time.sleep(1.5)  # Giảm xuống 1.5s
                    code = get_2fa_code_v2(gmx_user, gmx_pass, target_ig_username)
                    if code: break
                if not code:
                    print("   [Step 4] Still no code after polling. Continuing to next attempt...")
                    continue 

            print(f"   [Step 4] Inputting Code: {code}")
            if self._robust_fill_input(code):
                self._click_continue_robust()
                time.sleep(1)  # Chờ UI update sau click
                is_wrong_code = False
                print("   [Step 4] Verifying...")
                time.sleep(1.5)  # Giảm xuống 1.5s

                verify_attempts = 0
                while verify_attempts < 6:  # Giảm xuống 6
                    if time.time() - start_time > max_duration:
                        raise Exception("STOP_FLOW_2FA: Checkpoint timeout during verification")
                    
                    time.sleep(0.8)  # Giảm xuống 0.8s
                    curr = self._get_page_state()
                    if curr in ['SELECT_APP', 'ALREADY_ON']:
                        checkpoint_passed = True; print("   [Step 4] Checkpoint Passed!"); break
                    
                    err_msg = self.driver.execute_script("return document.body.innerText.toLowerCase()")
                    if ("isn't right" in err_msg or "không đúng" in err_msg or "incorrect" in err_msg or 
                        "the code you entered" in err_msg or "mã bạn đã nhập" in err_msg or "wrong code" in err_msg or 
                        "code is invalid" in err_msg or "mã không hợp lệ" in err_msg):
                        print(f"   [WARNING] Code {code} REJECTED."); is_wrong_code = True; break
                    
                    print("   [Step 4] Not verified yet, retrying confirm...")
                    self._click_continue_robust()
                    verify_attempts += 1

                if checkpoint_passed: break
                if is_wrong_code:
                    print("   [Step 4] Code rejected. Clearing input and requesting new code...")
                    # Clear input trước khi get new code
                    try:
                        input_el = self.driver.find_element(By.CSS_SELECTOR, "input[name='code'], input[placeholder*='Code']")
                        input_el.send_keys(Keys.CONTROL + "a"); input_el.send_keys(Keys.DELETE)
                    except: pass
                    # Click Get new code
                    self.driver.execute_script("var a=document.querySelectorAll('span, div[role=\"button\"]'); for(var e of a){if(e.innerText.toLowerCase().includes('get a new code')){e.click();break;}}")
                    # Chờ mail mới với poll (giảm xuống 2 lần)
                    print("   [Step 4] Waiting for new code in mail...")
                    for poll in range(2):
                        time.sleep(1.5)
                        new_code = get_2fa_code_v2(gmx_user, gmx_pass, target_ig_username)
                        if new_code and new_code != code:  # Đảm bảo code mới khác code cũ
                            print(f"   [Step 4] New code received: {new_code}")
                            code = new_code
                            break
                    else:
                        print("   [Step 4] No new code after polling. Will retry in next attempt.")
                    continue
            else: time.sleep(1)
            
        time.sleep(1) # Giảm xuống 1s
        if checkpoint_passed:
            return True
        else:
            raise Exception("STOP_FLOW_2FA: CHECKPOINT_MAIL: NO CODE")

    def _select_auth_app_method(self, current_state):
        if self._get_page_state() == 'ALREADY_ON': return
        
        # Check if we are already on Key Screen (STRICTER CHECK)
        # Avoid false positives from "Copy" text in footer/copyright
        is_select_app_state = self._get_page_state() == 'SELECT_APP'
        
        if not is_select_app_state:
            # Only check for key screen if NOT definitely in 'Select App' state
            safe_key_check = self.driver.execute_script("""
                var keyBtns = document.querySelectorAll("div[role='button'], span[role='button'], button");
                for (var b of keyBtns) {
                    var t = b.innerText.toLowerCase();
                    if (t === 'copy key' || t === 'sao chép khóa' || t === 'copy' || t === 'sao chép') {
                        // Check context: nearby text should mention 'app' or 'key' to be safe, 
                        // or just rely on the fact we strictly ruled out SELECT_APP
                        return true;
                    }
                }
                return false;
            """)
            if safe_key_check:
                print("   [Step 4] Already on Secret Key screen.")
                return

        print("   [Step 4] Selecting authentication app method...")
        
        # Retry loop for selecting method
        max_retries = 3
        for attempt in range(max_retries):
            print(f"   [Step 4] Selection Attempt {attempt+1}/{max_retries}...")
            
            # [FIX] Check immediately if we are ALREADY on the success screen
            # This prevents loop from trying to click buttons that don't exist and timing out
            is_key_screen_check = self.driver.execute_script("""
                var body = document.body.innerText.toLowerCase();
                // Check if we see the Secret Key directly (Regex for XXXX XXXX ...)
                var mainText = document.body.innerText;
                var keyPattern = /([A-Z2-7]{4}\\s?){4,}/; 
                if (keyPattern.test(mainText) && (body.includes("app") || body.includes("google") || body.includes("duo") || body.includes("otp"))) return true;
                
                // Check strictly for Key Screen signs (Copy Button)
                var keyBtns = document.querySelectorAll("div[role='button'], span[role='button'], button");
                for (var b of keyBtns) {
                        var t = b.innerText.toLowerCase();
                        if (t === 'copy key' || t === 'sao chép khóa' || t === 'copy' || t === 'sao chép') return true;
                }
                return false;
            """)
            
            if is_key_screen_check:
                print("   [Step 4] Already on Secret Key screen (Detected at start of attempt).")
                return

            # Also check if we overshot to OTP Input (Also means we passed this step)
            # The next step (_extract_secret_key) will handle going back if needed.
            state = self._get_page_state()
            if state == 'OTP_INPUT_SCREEN':
                print("   [Step 4] Detected OTP Input Screen. Selection assumed complete (Step 4 will handle key retrieval if missing).")
                return

            # 1. Select Radio/Button - Enhanced Selector
            result = self.driver.execute_script("""
                function clickAuthOption() {
                    var keywords = ["authentication app", "authenticator", "xác thực", "two-factor", "ứng dụng xác thực", "duo mobile", "google authenticator"];
                    
                    // Prioritize Radio Inputs first
                    var radios = document.querySelectorAll("input[type='radio']");
                    for (var r of radios) {
                        var label = (r.getAttribute('aria-label') || r.value || '').toLowerCase();
                        if (keywords.some(k => label.includes(k))) {
                            r.click(); return "CLICKED_RADIO_MATCH";
                        }
                    }

                    // Strategy A: Find by text in clickable elements
                    var els = document.querySelectorAll("div[role='button'], label, span, div");
                    for (var i=0; i<els.length; i++) {
                        if (els[i].offsetParent === null) continue; // Check visibility
                        
                        var txt = els[i].innerText.toLowerCase();
                        // Tránh click nhầm vào Header/Footer
                        if (txt.length > 100) continue; 

                        var isMatch = keywords.some(k => txt.includes(k));
                        
                        if (isMatch) {
                            // Found text, try to find the best click target
                            var target = els[i];
                            
                            // Try to click radio nearby
                            var radio = target.querySelector("input[type='radio']") || 
                                        (target.parentElement ? target.parentElement.querySelector("input[type='radio']") : null);
                            if (radio) { radio.click(); return "CLICKED_RADIO_NEARBY"; }
                            
                            // Click element itself
                            target.click();
                            
                            // Click parent if it's a button
                            var container = target.closest("div[role='button']");
                            if (container && container !== target) { container.click(); }
                            
                            return "CLICKED_TEXT_ELEMENT";
                        }
                    }
                    
                    // Strategy C: Fallback - Click the FIRST radio button available (Usually Auth App is top)
                    if (radios.length > 0) {
                        radios[0].click();
                        return "CLICKED_FIRST_RADIO_FALLBACK";
                    }
                    
                    return false;
                }
                return clickAuthOption();
            """)
            
            if result:
                print(f"   [Step 4] Clicked auth option: {result}")
            else:
                print("   [Step 4] Authentication app option not found via selectors.")
            
            time.sleep(1.5) # Wait for UI update (Next button enable)

            # 2. Click Continue
            if not self._click_continue_robust():
                 print("   [Step 4] Button 'Next' not found or not clickable yet.")
            
            # 3. Wait for transition
            wait_start = time.time()
            wait_timeout = 25 # Increased timeout
            
            while time.time() - wait_start < wait_timeout:
                state = self._get_page_state()
                if state == 'ALREADY_ON': return
                
                # Check for Key Screen indicators (Strict JS check)
                is_key_screen = self.driver.execute_script("""
                    var body = document.body.innerText.toLowerCase();
                    if (body.includes("help protect your account") || (body.includes("authentication app") && !body.includes("copy key"))) return false; // Still on Select App
                    
                    var keyBtns = document.querySelectorAll("div[role='button'], span[role='button'], button");
                    for (var b of keyBtns) {
                         var t = b.innerText.toLowerCase();
                         if (t === 'copy key' || t === 'sao chép khóa' || t === 'copy' || t === 'sao chép') return true;
                    }
                    return false;
                """)
                
                if is_key_screen:
                    print("   [Step 4] Copy key button detected. Transition success.")
                    time.sleep(3)
                    return # SUCCESS
                
                time.sleep(1)
            
            print(f"   [Step 4] Transition timeout (Attempt {attempt+1}). Retrying selection...")
            self.driver.refresh()
            wait_dom_ready(self.driver, timeout=10)
            time.sleep(2)
        
        raise Exception("STOP_FLOW_2FA: Failed to select Auth App method after 3 retries.")

    def _extract_secret_key(self, ig_username):
        """Lấy Secret Key (Có logic Anti-Freeze: Thoát nếu lỗi trang)."""
        max_attempts = 10
        for attempt in range(1, max_attempts + 1):
            print(f"   [Step 4] Attempt {attempt}/{max_attempts}: Starting secret key extraction...")
            secret_key = ""
            end_wait = time.time() + 120  # Increased from 80 to 120 to wait longer
            while time.time() < end_wait:
                try:
                    # [ANTI-FREEZE Check]
                    current_state = self._get_page_state() # Check nhanh bằng JS
                    print(f"   [Step 4] Current page state: {current_state}")
                    if current_state == 'BROKEN' or current_state == 'SUSPENDED' or current_state == 'RESTRICTED':
                         raise Exception("STOP_FLOW_2FA: Page Broken/Suspended/Restricted while waiting for key")
                    if "two_factor" not in self.driver.current_url and "challenge" not in self.driver.current_url:
                         raise Exception("STOP_FLOW_2FA: Redirected away from 2FA page")
                    if current_state == 'ALREADY_ON': return "ALREADY_2FA_ON"

                    # Try to extract secret from otpauth URL first
                    try:
                        otpauth_url = self.driver.execute_script("""
                        var imgs = document.querySelectorAll('img');
                        for (var img of imgs) {
                            if (img.src && img.src.includes('otpauth')) {
                                return img.src;
                            }
                        }
                        var links = document.querySelectorAll('a');
                        for (var link of links) {
                            if (link.href && link.href.includes('otpauth')) {
                                return link.href;
                            }
                        }
                        return null;
                        """)
                        if otpauth_url:
                            parsed = urlparse(otpauth_url)
                            query = parse_qs(parsed.query)
                            if 'secret' in query:
                                raw_key = query['secret'][0].replace(" ", "").strip()
                                if len(raw_key) >= 16 and re.match(r'^[A-Z2-7]+$', raw_key):
                                    if ig_username.lower() not in raw_key.lower():
                                        secret_key = raw_key
                                        print(f"   [Step 4] Extracted from otpauth: {raw_key}")
                                        break
                    except Exception as e:
                        print(f"   [Step 4] Otpauth extraction failed: {e}")

                    # Kiểm tra sự xuất hiện của "Copy key" button trước khi extract
                    copy_key_buttons = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="button"]')
                    has_copy_key = any('Copy key' in btn.text or 'Sao chép' in btn.text or 'Copy' in btn.text or 'Sao' in btn.text for btn in copy_key_buttons)
                    
                    if has_copy_key:
                        print("   [Step 4] Copy key button found, attempting extraction...")
                        # Click "Copy key" button để copy vào clipboard
                        try:
                            copy_button = next(btn for btn in copy_key_buttons if 'Copy key' in btn.text or 'Sao chép' in btn.text or 'Copy' in btn.text or 'Sao' in btn.text)
                            # Clear clipboard trước khi copy
                            pyperclip.copy('')
                            # Scroll to button and use JS click to avoid interception
                            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});", copy_button)
                            time.sleep(0.5)
                            self.driver.execute_script("arguments[0].click();", copy_button)
                            time.sleep(1.0)  # Tăng delay để chờ copy hoàn tất
                            raw_key = pyperclip.paste().replace(" ", "").strip()
                            print(f"   [Step 4] Copied from clipboard: {raw_key}")
                            if len(raw_key) >= 16 and re.match(r'^[A-Z2-7]+$', raw_key):
                                # Skip if it contains the username (case insensitive)
                                if ig_username.lower() in raw_key.lower():
                                    print(f"   [Step 4] Skipped potential key containing username: {raw_key}")
                                    continue
                                secret_key = raw_key
                                break
                            else:
                                print(f"   [Step 4] Invalid key from clipboard: {raw_key}")
                        except Exception as e:
                            print(f"   [Step 4] Error clicking Copy key or getting from clipboard: {e}")
                            # Fallback: Lấy trực tiếp từ span element
                            try:
                                secret_span = self.driver.find_element(By.CSS_SELECTOR, 'span[class*="x1lliihq"]')
                                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});", secret_span)
                                time.sleep(0.5)
                                raw_key = secret_span.text.replace(" ", "").strip()
                                print(f"   [Step 4] Fallback extracted from span: {raw_key}")
                                if len(raw_key) >= 16 and re.match(r'^[A-Z2-7]+$', raw_key):
                                    if ig_username.lower() in raw_key.lower():
                                        print(f"   [Step 4] Skipped potential key from span: {raw_key}")
                                        continue
                                    secret_key = raw_key
                                    break
                                else:
                                    print(f"   [Step 4] Invalid key from span: {raw_key}")
                            except Exception as e2:
                                print(f"   [Step 4] Fallback span extraction failed: {e2}")
                    else:
                        print("   [Step 4] 'Copy key' button not detected. Waiting...")
                        # Nếu chưa có "Copy key", tiếp tục chờ
                        continue

                    if current_state == 'OTP_INPUT_SCREEN' and not secret_key:
                        print("   [Step 4] Warning: Detected OTP Input Screen without Key! Initiating Back Navigation...")
                        
                        # 1. Try clicking strict "Back" button (aria-label)
                        back_clicked = self.driver.execute_script("""
                            var btns = document.querySelectorAll('div[role="button"], button');
                            for (var b of btns) {
                                var label = (b.getAttribute('aria-label') || '').toLowerCase();
                                if (label === 'back' || label === 'quay lại' || label === 'go back') {
                                    b.click(); return true;
                                }
                            }
                            return false;
                        """)
                        
                        # 2. If strict back failed, try finding header back button (top-left SVG)
                        if not back_clicked:
                             print("   [Step 4] Back button (aria-label) not found. Trying heuristic (Header SVG)...")
                             back_clicked = self.driver.execute_script("""
                                var svgs = document.querySelectorAll('svg');
                                for (var svg of svgs) {
                                    // Check if svg is inside a button-like wrapper
                                    var btn = svg.closest("div[role='button'], button");
                                    if (btn) {
                                        // Heuristic: Back button is usually on the left (x < 100) and top (y < 200)
                                        var rect = btn.getBoundingClientRect();
                                        if (rect.x < 100 and rect.y < 200 && rect.width > 0 && rect.height > 0) {
                                            btn.click(); return true;
                                        }
                                    }
                                }
                                return false;
                             """)

                        # 3. Last resort: Browser Back (Use with caution in SPA, but better than sticking)
                        if not back_clicked:
                             print("   [Step 4] all Back buttons failed. Attempting window.history.back()...")
                             self.driver.execute_script("window.history.back();")
                        
                        time.sleep(3) 
                        # Removed refresh here to avoid resetting the wizard to step 1
                        wait_dom_ready(self.driver)
                        time.sleep(2)
                        continue

                    # Fallback: regex trên body text (nếu cần)
                    if not secret_key:
                        full_text = self.driver.find_element(By.TAG_NAME, "body").text
                        m = re.search(r'([A-Z2-7]{4}\s?){4,}', full_text)
                        if m:
                            clean = m.group(0).replace(" ", "").strip()
                            if len(clean) >= 16:
                                # Skip if it contains the username (case insensitive)
                                if clean.lower()  in  ig_username.lower():
                                    print(f"   [Step 4] Skipped potential key containing username: {clean}")
                                    continue
                                secret_key = clean; break

                    if not secret_key:
                        inputs = self.driver.find_elements(By.TAG_NAME, "input")
                        for inp in inputs:
                            val = inp.get_attribute("value")
                            if val:
                                clean_val = val.replace(" ", "").strip()
                                if len(clean_val) >= 16 and re.match(r'^[A-Z2-7]+$', clean_val):
                                    # Skip if it contains the username
                                    if ig_username.lower() in clean_val.lower():
                                        print(f"   [Step 4] Skipped potential key from input containing username: {clean_val}")
                                        continue
                                    secret_key = clean_val; break
                    if len(secret_key) >= 16: break
                except Exception as e:
                    if "STOP_FLOW" in str(e): raise e
                    pass
                time.sleep(1)  # Poll every 1s to avoid skipping too fast

            if secret_key: return secret_key
            else:
                print(f"   [Step 4] Secret Key NOT found! Attempt {attempt}/{max_attempts}.")
                time.sleep(2)

        raise Exception("STOP_FLOW_2FA: Secret Key NOT found after 10 retries! Blocking flow.")
    def _validate_masked_email_robust(self, primary_email, secondary_email=None):
        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            match = re.search(r'\b([a-zA-Z0-9][\w\*]*@[\w\*]+\.[a-zA-Z\.]+)\b', body_text)
            if not match: return True 
            masked = match.group(1).lower().strip()
            print(f"   [Step 4] Mask Hint: {masked}")
            def check(real, mask):
                if not real or "@" not in real: return False
                r_u, r_d = real.lower().split("@"); m_u, m_d = mask.lower().split("@")
                if m_d[0] != '*' and m_d[0] != r_d[0]: return False
                if "." in m_d and m_d.split('.')[-1] != r_d.split('.')[-1]: return False
                if m_u[0] != '*' and m_u[0] != r_u[0]: return False
                return True
            if check(primary_email, masked): return True
            if secondary_email and check(secondary_email, masked): return True
            print(f"   [CRITICAL] Hint {masked} mismatch!"); return False
        except: return True

    def _click_continue_robust(self):
        return self.driver.execute_script("""
            var keywords = ["Next", "Tiếp", "Continue", "Submit", "Xác nhận", "Confirm", "Done", "Xong", "This Was Me", "Đây là tôi", "Đúng là tôi"];
            var btns = document.querySelectorAll("button, div[role='button']");
            for (var b of btns) {
                var txt = b.innerText.trim();
                for(var k of keywords) { 
                    if(txt.includes(k) && b.offsetParent !== null && !b.disabled && b.offsetHeight > 0) { b.click(); return true; } 
                }
            }
            return false;
        """)

    def _robust_fill_input(self, text_value):
        val = str(text_value).strip()
        
        def fill_action():
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
                if len(val) != len(multiple_inputs):
                    print(f"   [Step 4] Code length {len(val)} doesn't match input fields {len(multiple_inputs)}")
                    return False
                for i, inp in enumerate(multiple_inputs):
                    try:
                        ActionChains(self.driver).move_to_element(inp).click().perform()
                        inp.clear()
                        inp.send_keys(val[i])
                        time.sleep(0.1)
                    except Exception as e:
                        print(f"   [Step 4] Failed to fill input {i}: {e}")
                        return False
                time.sleep(0.3)
                # Check if all inputs have the correct values
                all_correct = True
                for i, inp in enumerate(multiple_inputs):
                    try:
                        if inp.get_attribute("value") != val[i]:
                            all_correct = False
                            break
                    except:
                        all_correct = False
                        break
                return all_correct
            
            # Fallback to single input
            input_el = self._find_code_input()
            if not input_el:
                return False
            
            # Nhập từng ký tự với delay để mô phỏng nhập thật
            ActionChains(self.driver).move_to_element(input_el).click().perform()
            # Đảm bảo xóa code cũ: select all và delete
            ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).send_keys(Keys.DELETE).perform()
            input_el.clear()  # Thêm clear() để đảm bảo
            for char in val:
                input_el.send_keys(char)
                time.sleep(0.05)  # Giảm delay xuống 0.05s để nhập nhanh hơn
            time.sleep(0.3)  # Giảm wait xuống 0.3s
            return input_el.get_attribute("value").replace(" ", "") == val
        
        try:
            return self._safe_element_action(fill_action)
        except Exception as e:
            print(f"   [Step 4] Input fill failed after retries: {e}")
            return False