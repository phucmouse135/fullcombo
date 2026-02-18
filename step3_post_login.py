# step3_post_login.py
import time
import re
from selenium.webdriver.common.by import By
from config_utils import wait_element, wait_and_click, wait_dom_ready

class InstagramPostLoginStep:
    def __init__(self, driver):
        self.driver = driver

    def process_post_login(self, username):
        """
        Luồng chính xử lý sau khi Login thành công:
        1. Xử lý các màn hình chắn (Cookie, Terms, Lỗi Page, Popup...).
        2. Điều hướng vào Profile.
        3. Crawl Dữ liệu (Post, Follower, Following).
        4. Trích xuất Cookie mới.
        """
        print(f"[{username}]   [Step 3] Processing Post-Login for {username}...")
        
        # 1. Xử lý các Popup/Màn hình chắn (Vòng lặp check)
        self._handle_interruptions()
        
        # 1.5. Đảm bảo đã vào Instagram trước khi navigate
        self.driver.get("https://www.instagram.com/")
        wait_dom_ready(self.driver, timeout=10)
        
        self._handle_interruptions()
        self._ensure_instagram_ready()
        
        
        
        # 2. Điều hướng vào Profile
        self._navigate_to_profile(username)
        
        # las t check các popup lần nữa trước khi crawl
        self._handle_interruptions()
        
        # 3. Crawl Dữ liệu
        data = self._crawl_data(username)
        
        # 4. Lấy Cookie mới
        data['cookie'] = self._get_cookie_string()
        
        return data

    def _handle_interruptions(self):
        """
        Chiến thuật 'Aggressive Scan' (Tối ưu hóa bằng JS):
        Gộp kiểm tra Popup và kiểm tra Home vào 1 lần gọi JS để tăng tốc độ.
        """
        print("   [Step 3] Starting Aggressive Popup Scan...")
        
        # Check for ad subscription popup and reload if found
        
        
        end_time = time.time() + 120  # Quét trong 120 giây 
        popup_handling_attempts = 0
        max_popup_attempts = 20  # Prevent infinite loops
        
        while time.time() < end_time and popup_handling_attempts < max_popup_attempts: 
            try:
                # Try to click on visible dialog to focus before scrolling
                try:
                    dialogs = self.driver.find_elements(By.CSS_SELECTOR, "div[role='dialog'], div[role='alertdialog'], div[aria-modal='true']")
                    for dialog in dialogs:
                        if dialog.is_displayed():
                            # Click on the dialog to focus it
                            self.driver.execute_script("arguments[0].click();", dialog)
                            break
                except: pass
                
                time.sleep(0.5)
                
                # ---------------------------------------------------------
                # 0. INDIVIDUAL POPUP HANDLERS (Riêng lẻ cho từng loại)
                # ---------------------------------------------------------
                if self._handle_age_verification():
                    print("   [Step 3] Handled Age Verification individually")
                    time.sleep(3)
                    continue
                
                if self._handle_accounts_center():
                    print("   [Step 3] Handled Accounts Center individually")
                    time.sleep(1)
                    continue
                
                if self._handle_cookie_consent():
                    print("   [Step 3] Handled Cookie Consent individually")
                    time.sleep(1)
                    continue
                
                if self._handle_confirm_your_account():
                    print("   [Step 3] Handled Confirm Your Account individually")
                    time.sleep(1)
                    continue
                
                try:
                    current_url = self.driver.current_url.lower()
                    if "ad_free_subscription" in current_url:
                        print("   [Step 3] Detected ad_free_subscription URL. Reloading Instagram...")
                        self.driver.get("https://www.instagram.com/")
                        wait_dom_ready(self.driver, timeout=10)
                        time.sleep(3)
                        return  # Exit after reload
                    
                    # Check if body element exists before accessing
                    try:
                        body_element = self.driver.find_element(By.TAG_NAME, "body")
                        body_text = body_element.text.lower()
                    except Exception as body_e:
                        print(f"   [Step 3] Body element not found, skipping text check: {body_e}")
                        body_text = ""
                    
                    if body_text and "want to subscribe or continue using our products free of charge with ads?" in body_text:
                        print("   [Step 3] Detected ad subscription popup text. Reloading Instagram...")
                        self.driver.get("https://www.instagram.com/")
                        wait_dom_ready(self.driver, timeout=10)
                        time.sleep(3)
                        return  # Exit after reload
                    

                    if body_text and ("page isn’t working" in body_text or "http error" in body_text or
                        'something went wrong' in body_text or 'đã xảy ra sự cố' in body_text or
                        "this page isn’t working" in body_text or 'the site is temporarily unavailable' in body_text or
                        "reload" in body_text  or "useragent mismatch" in body_text):
                        print("   [Step 3] Error page detected. Reloading Home...")
                        self.driver.get("https://www.instagram.com/")
                        time.sleep(4); continue
                except Exception as e:
                    print(f"   [Step 3] Error checking for ad subscription: {e}")
                
                # --------------------------------------------------------- 
                # 1. SEQUENTIAL SCAN (POPUP + HOME) BẰNG JS
                # ---------------------------------------------------------
                action_result = self.driver.execute_script("""
                    // 1. KIỂM TRA HOME TRƯỚC (Điều kiện thoát nhanh)
                    // Nếu thấy icon Home và không có dialog nào che -> Báo về Home ngay
                    var homeIcon = document.querySelector("svg[aria-label='Home']") || document.querySelector("svg[aria-label='Trang chủ']");
                    var dialogs = document.querySelectorAll("div[role='dialog']");
                    var hasVisibleDialog = Array.from(dialogs).some(d => d.offsetParent !== null);
                    
                    if (homeIcon && !hasVisibleDialog) {
                        return 'HOME_SCREEN_CLEAR';
                    }

                    // 2. TỪ KHÓA POPUP
                    const keywords = {
                        'get_started': ['get started', 'bắt đầu'],
                        'agree_confirm': ['agree', 'đồng ý', 'update', 'cập nhật', 'confirm', 'xác nhận'],
                        'next_step': ['next', 'tiếp'],
                        'use_data_opt': ['use data across accounts', 'sử dụng dữ liệu trên các tài khoản'],
                        'cookie': ['allow all cookies', 'cho phép tất cả'],
                        'popup': ['not now', 'lúc khác', 'cancel', 'ok', 'hủy'], 
                        'age_check': ['18 or older', '18 tuổi trở lên', 'trên 18 tuổi'],
                        'account_center_check': ['choose an option', 'accounts center', 'use data across accounts', 'keep using your info across these accounts?'] 
                    };
                    const bodyText = (document.body && document.body.innerText.toLowerCase()) || '';

                    // --- ƯU TIÊN: POPUP "ACCOUNTS CENTER" ---
                    if (keywords.account_center_check.some(k => bodyText.includes(k))) {
                        if (bodyText.includes('keep using your info across these accounts?')) {
                             var found = false;
                             
                             // 1. Try to find the specific text element (Exact match first)
                             var candidates = document.querySelectorAll("span, div, label");
                             for (var el of candidates) {
                                 if (el.offsetParent === null) continue;
                                 var txt = el.innerText ? el.innerText.toLowerCase().trim() : "";
                                 if (txt === "use info across accounts" || txt === "sử dụng thông tin trên các tài khoản") {
                                     el.click();
                                     if (el.closest("div[role='button']")) el.closest("div[role='button']").click();
                                     found = true; 
                                     break; 
                                 }
                             }
                             
                             // 2. Fallback: Click the first radio button (usually "Use info across accounts")
                             if (!found) {
                                 var radios = document.querySelectorAll("input[type='radio']");
                                 if (radios.length > 0) {
                                     radios[0].click();
                                     found = true;
                                 }
                             }

                             // 3. Click Next if we selected something or just try to click Next anyway
                             setTimeout(() => {
                                var buttons = document.querySelectorAll('button, div[role="button"]');
                                for (var btn of buttons) {
                                    var t = btn.innerText.toLowerCase().trim();
                                    if (btn.offsetParent !== null && !btn.disabled && (t === 'next' || t === 'tiếp' || t === 'continue')) {
                                        btn.click();
                                    }
                                }
                             }, 1000); 
                             
                             return 'KEEP_INFO_USE_SELECTED';

                        } else {
                            let buttons = document.querySelectorAll('button, div[role="button"], span');
                            for (let btn of buttons) {
                                let t = btn.innerText.toLowerCase().trim();
                                if (btn.offsetParent !== null && !btn.disabled && (t === 'next' || t === 'tiếp' || t === 'continue')) {
                                    btn.click();
                                    if (btn.tagName === 'SPAN' && btn.parentElement) btn.parentElement.click();
                                    return 'ACCOUNTS_CENTER_NEXT';
                                }
                            }
                        }
                    }
                    
                    // --- POST VIOLATES COMMUNITY STANDARDS ---
                    if (bodyText.includes('your post goes against our community standards') || 
                        bodyText.includes('bài đăng của bạn vi phạm các tiêu chuẩn cộng đồng của chúng tôi') || 
                        bodyText.includes('how we make decisions')) {
                        let buttons = document.querySelectorAll('button, div[role="button"]');
                        for (let btn of buttons) {
                            if (btn.innerText.toLowerCase().trim() === 'ok') {
                                btn.click();
                                return 'POST_VIOLATES_OK_CLICKED';
                            }
                        }
                    }
                    
                    // --- UNUSUAL ACTIVITY DETECTED ---
                    if (bodyText.includes('we suspect automated behavior on your account') || 
                        bodyText.includes('prevent your account from being temporarily') || 
                        bodyText.includes('verify you are a real person') || 
                        bodyText.includes('suspicious activity')) {
                        let buttons = document.querySelectorAll('button, div[role="button"]');
                        for (let btn of buttons) {
                            if (btn.innerText.toLowerCase().trim() === 'dismiss') {
                                btn.click();
                                return 'UNUSUAL_ACTIVITY_DETECTED';
                            }
                        }
                    }
                    
                    // --- XỬ LÝ CHECKPOINT TUỔI (RADIO BUTTON) ---
                    let radio18 = document.querySelector('input[type="radio"][value="above_18"]');
                    if (radio18) {
                        radio18.click();
                        let container = radio18.closest('div[role="button"]');
                        if (container) container.click();
                        let visualCircle = radio18.previousElementSibling;
                        if (visualCircle) visualCircle.click();

                        // Auto click Agree sau 1s
                        setTimeout(() => {
                            let btns = document.querySelectorAll('button, div[role="button"]');
                            for(let b of btns) {
                                if(b.innerText.toLowerCase().includes('agree') || b.innerText.toLowerCase().includes('đồng ý')) { b.click(); }
                            }
                        }, 500); 
                        return 'AGE_CHECK_CLICKED';
                    }
                    
                    // Fallback tuổi theo text
                    let ageLabels = document.querySelectorAll("span, label");
                    for(let el of ageLabels) {
                        if (el.innerText.includes("18 or older") || el.innerText.includes("18 tuổi trở lên")) {
                             let parentBtn = el.closest('div[role="button"]');
                             if (parentBtn) { parentBtn.click(); return 'AGE_CHECK_CLICKED'; }
                        }
                    }

                    // Scroll before handling options

                    // A. TÌM VÀ CHỌN OPTION (Use Data)
                    const labels = document.querySelectorAll('div, span, label');
                    for (let el of labels) {
                        if (el.offsetParent === null) continue;
                        let txt = el.innerText.toLowerCase().trim();
                        if (keywords.use_data_opt.some(k => txt === k)) {
                            el.scrollIntoView({behavior: "instant", block: "center"});
                            el.click(); return 'OPTION_SELECTED';
                        }
                    }

                    // B. TÌM VÀ CLICK NÚT BẤM CHUNG
                    const elements = document.querySelectorAll('button, div[role="button"]');
                    for (let el of elements) {
                        if (el.offsetParent === null) continue; 
                        let txt = el.innerText.toLowerCase().trim();
                        if (!txt) continue;

                        if (keywords.get_started.some(k => txt === k)) {
                            el.scrollIntoView({behavior: "instant", block: "center"});
                            el.click(); return 'GET_STARTED_CLICKED';
                        }
                        if (keywords.agree_confirm.some(k => txt.includes(k))) {
                            el.scrollIntoView({behavior: "instant", block: "center"});
                            el.click(); return 'AGREE_CLICKED';
                        }
                        if (keywords.next_step.some(k => txt === k)) {
                            el.scrollIntoView({behavior: "instant", block: "center"});
                            el.click(); return 'NEXT_CLICKED';
                        }
                        if (keywords.cookie.some(k => txt.includes(k))) {
                            el.click(); return 'COOKIE_CLICKED';
                        }
                        if (keywords.popup.some(k => txt === k)) {
                            el.click(); return 'POPUP_CLICKED';
                        }
                    }
                    return null;
                """)

                if action_result == 'HOME_SCREEN_CLEAR':
                    print("   [Step 3] Home Screen detected. Verifying no remaining popups...")
                    # Double-check that we're actually ready to proceed
                    time.sleep(2)  # Wait a bit more
                    try:
                        # Check again for any remaining dialogs or overlays
                        final_check = self.driver.execute_script("""
                            var dialogs = document.querySelectorAll('div[role="dialog"], div[role="alertdialog"], div[aria-modal="true"]');
                            var hasVisibleDialog = Array.from(dialogs).some(d => d.offsetParent !== null && d.getAttribute('aria-hidden') !== 'true');
                            
                            // Check for overlays that might block interaction
                            var overlays = document.querySelectorAll('div[aria-hidden="false"], div[data-testid*="modal"], div[style*="z-index"]');
                            var hasVisibleOverlay = Array.from(overlays).some(o => {
                                var style = window.getComputedStyle(o);
                                return style.display !== 'none' && style.visibility !== 'hidden' && o.offsetParent !== null;
                            });
                            
                            // Check for unusual login popups specifically
                            var bodyText = (document.body && document.body.innerText.toLowerCase()) || '';
                            var unusualLogin = bodyText.includes('we detected an unusual login attempt') ||
                                              bodyText.includes('continue') ||
                                              bodyText.includes('this was me');
                            
                            return !(hasVisibleDialog || hasVisibleOverlay || unusualLogin);
                        """)
                        
                        if final_check:
                            print("   [Step 3] Home Screen Clear confirmed. Done.")
                            break  # [EXIT LOOP] Đã thành công
                        else:
                            print("   [Step 3] Still have popups/overlays/unusual login elements, continuing...")
                            # Try to handle any remaining unusual login popups
                            self._handle_remaining_popups()
                            popup_handling_attempts += 1
                            continue
                    except Exception as e:
                        print(f"   [Step 3] Error in final verification: {e}")
                        popup_handling_attempts += 1
                        continue

                if action_result:
                    print(f"   [Step 3] Action triggered: {action_result}")
                    
                    if action_result == 'AGREE_CLICKED':
                        time.sleep(3); self._check_crash_recovery()
                    elif action_result == 'OPTION_SELECTED':
                        print("   [Step 3] Option selected. Waiting for Next button...")
                        time.sleep(1)
                    elif action_result == 'AGE_CHECK_CLICKED': 
                        print("   [Step 3] Handled Age Verification (18+). Waiting...")
                        time.sleep(3)
                    elif action_result == 'KEEP_INFO_MANAGE_SELECTED':
                        print("   [Step 3] Selected manage accounts and clicked next. Waiting...")
                        time.sleep(2)
                    elif action_result == 'KEEP_INFO_USE_SELECTED':
                        print("   [Step 3] Selected use info across accounts and clicked next. Waiting...")
                        time.sleep(2)
                    elif action_result == 'UNUSUAL_ACTIVITY_DETECTED':
                        print("   [Step 3] Dismissed unusual activity popup. Waiting...")
                        time.sleep(2)
                    else:
                        time.sleep(1.5)
                    continue

                else:
                    # Fallback: If no specific popup detected, find and click buttons in dialogs
                    self._fallback_click_buttons()
                    popup_handling_attempts += 1
                    continue

                # ---------------------------------------------------------
                # 2. CHECK CRASH (Python side fallback)
                # ---------------------------------------------------------
                try:
                    curr_url = self.driver.current_url.lower()
                    if "ig_sso_users" in curr_url or "/api/v1/" in curr_url or "error" in curr_url:
                        print(f"   [Step 3] Crash URL detected. Reloading Home...")
                        self.driver.get("https://www.instagram.com/")
                        time.sleep(4); continue

                    body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                    if ("page isn’t working" in body_text or "http error" in body_text or
                        'something went wrong' in body_text or 'đã xảy ra sự cố' in body_text or
                        "this page isn’t working" in body_text or 'the site is temporarily unavailable' in body_text or
                        "reload" in body_text or "HTTP ERROR" in body_text or "HTTP 500" in body_text or
                        "HTTP 502" in body_text or "HTTP 504" in body_text or "useragent mismatch" in body_text):
                        print("   [Step 3] Error page detected. Reloading Home...")
                        self.driver.get("https://www.instagram.com/")
                        time.sleep(4); continue
                except: pass

                time.sleep(0.5)

            except Exception as e:
                popup_handling_attempts += 1
                time.sleep(1)
        
        if popup_handling_attempts >= max_popup_attempts:
            print(f"   [Step 3] Exceeded max popup handling attempts ({max_popup_attempts}). Proceeding anyway.")
            return  # Exit the method to continue with navigation

    def _check_crash_recovery(self):
        """Hàm phụ trợ check crash nhanh sau khi click Agree."""
        try:
            wait_dom_ready(self.driver, timeout=5)
        except: pass

    def _handle_remaining_popups(self):
        """Handle any remaining unusual login or other popups that Step 2 might have missed."""
        print("   [Step 3] Attempting to handle remaining popups...")
        try:
            # Try to click Continue or This Was Me buttons
            continue_buttons = self.driver.execute_script("""
                var buttons = document.querySelectorAll('button, div[role="button"]');
                var found = [];
                for (var btn of buttons) {
                    var text = btn.textContent.toLowerCase().trim();
                    if (text.includes('continue') || text.includes('tiếp tục') || 
                        text.includes('this was me') || text.includes('đây là tôi')) {
                        found.push(btn);
                    }
                }
                return found.slice(0, 3); // Return up to 3 buttons
            """)
            
            for btn in continue_buttons:
                try:
                    btn.click()
                    print("   [Step 3] Clicked remaining popup button")
                    time.sleep(3)
                    return True
                except:
                    continue
                    
            # Try ESC key as fallback
            self.driver.execute_script("""
                var event = new KeyboardEvent('keydown', {key: 'Escape'});
                document.dispatchEvent(event);
            """)
            print("   [Step 3] Sent ESC key to close popup")
            time.sleep(2)
            
        except Exception as e:
            print(f"   [Step 3] Error handling remaining popups: {e}")
        
        return False

    def _fallback_click_buttons(self):
        """Fallback: Find visible buttons in popups and click the first one."""
        print("   [Step 3] Fallback: Searching for buttons in popups...")
        
        try:
            # Find all visible dialogs
            dialogs = self.driver.find_elements(By.CSS_SELECTOR, "div[role='dialog'], div[role='alertdialog'], div[aria-modal='true']")
            
            for dialog in dialogs:
                if dialog.is_displayed():
                    # Scroll to the dialog first
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});", dialog)
                    time.sleep(0.5)
                    # Find buttons inside the dialog
                    buttons = dialog.find_elements(By.CSS_SELECTOR, "button, div[role='button']")
                    
                    for button in buttons:
                        if button.is_displayed() and button.is_enabled():
                            button_text = button.text.strip()
                            print(f"   [Step 3] Clicking fallback button: '{button_text}'")
                            button.click()
                            time.sleep(2)  # Wait after click
                            return True  # Clicked one, return
                    
                    # If no buttons found, try other clickable elements
                    clickable = dialog.find_elements(By.CSS_SELECTOR, "div[role='button'], span[role='button']")
                    
                    for elem in clickable:
                        if elem.is_displayed() and elem.is_enabled():
                            print("   [Step 3] Clicking fallback clickable element")
                            elem.click()
                            time.sleep(2)
                            return True
            
            print("   [Step 3] No clickable buttons found in popups")
            return False
        
        except Exception as e:
            print(f"   [Step 3] Error in fallback click: {e}")
            return False

    def _handle_age_verification(self):
        """Handle age verification popup individually."""
        try:
            time.sleep(0.5)
            radio = self.driver.find_element(By.CSS_SELECTOR, 'input[type="radio"][value="above_18"]')
            radio.click()
            
            # Try to click container
            try:
                container = radio.find_element(By.XPATH, './ancestor::div[@role="button"]')
                if container:
                    container.click()
            except:
                pass
            
            # Try visual circle
            try:
                visual_circle = radio.find_element(By.XPATH, './preceding-sibling::*')
                if visual_circle:
                    visual_circle.click()
            except:
                pass
            
            # Auto click agree after 0.5s
            time.sleep(0.5)
            buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button, div[role="button"]')
            for b in buttons:
                if 'agree' in b.text.lower() or 'đồng ý' in b.text.lower():
                    b.click()
                    return True
            
            return True  # Even if agree not clicked, age was handled
        except:
            return False

    def _handle_accounts_center(self):
        """Handle accounts center popup individually."""
        try:
            time.sleep(0.5)
            body_text = self.driver.find_element(By.TAG_NAME, 'body').text.lower()
            if 'choose an option' in body_text or 'accounts center' in body_text or 'use data across accounts' in body_text:
                buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button, div[role="button"], span')
                for b in buttons:
                    if b.text.lower().strip() in ['next', 'tiếp', 'continue']:
                        b.click()
                        return True
            return False
        except:
            return False

    def _handle_cookie_consent(self):
        """Handle cookie consent popup individually."""
        try:
            time.sleep(0.5)
            buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button, div[role="button"]')
            for b in buttons:
                if 'allow all cookies' in b.text.lower() or 'cho phép tất cả' in b.text.lower():
                    b.click()
                    return True
            return False
        except:
            return False

    def _handle_confirm_your_account(self):
        """Handle 'Confirm Your Account' popup individually."""
        try:
            time.sleep(0.5)
            body_text = self.driver.find_element(By.TAG_NAME, 'body').text.lower()
            if 'confirm your account' in body_text or 'xác nhận tài khoản của bạn' in body_text:
                # 1. Click "Get started" / "Bắt đầu"
                buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button, div[role="button"]')
                get_started_clicked = False
                for b in buttons:
                    if 'get started' in b.text.lower() or 'bắt đầu' in b.text.lower():
                        b.click()
                        get_started_clicked = True
                        break
                
                if not get_started_clicked:
                    # Try alternative selectors
                    try:
                        self.driver.find_element(By.CSS_SELECTOR, "button._acan._acap._acas").click()
                        get_started_clicked = True
                    except:
                        pass
                
                wait_dom_ready(self.driver, timeout=10)
                time.sleep(2)
                
                # 2. Select radio button "Use data across accounts" / "Sử dụng dữ liệu trên các tài khoản"
                labels = self.driver.find_elements(By.CSS_SELECTOR, 'label')
                for label in labels:
                    if 'use data across accounts' in label.text.lower() or 'sử dụng dữ liệu trên các tài khoản' in label.text.lower():
                        label.click()
                        break
                
                time.sleep(1)
                
                # 3. Click "Next" / "Tiếp theo"
                buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button, div[role="button"]')
                for b in buttons:
                    if 'next' in b.text.lower() or 'tiếp theo' in b.text.lower():
                        b.click()
                        return True
                
                return True  # Even if next not clicked, we handled the popup
            return False
        except:
            return False

    def _ensure_instagram_ready(self):
        """Đảm bảo đã vào Instagram và sẵn sàng để navigate."""
        print("   [Step 3] Ensuring Instagram is ready...")
        
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                current_url = self.driver.current_url
                print(f"   [Step 3] Current URL: {current_url}")
                
                # Check if we're on Instagram domain
                if "instagram.com" not in current_url:
                    print("   [Step 3] Not on Instagram domain, navigating to home...")
                    self.driver.get("https://www.instagram.com/")
                    wait_dom_ready(self.driver, timeout=10)
                    time.sleep(3)
                    continue
                
                # Check for basic Instagram elements
                body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                
                # If we see login form, something went wrong
                if "log in" in body_text or "username" in body_text or "password" in body_text:
                    print("   [Step 3] Detected login form, something went wrong. Refreshing...")
                    self.driver.refresh()
                    wait_dom_ready(self.driver, timeout=10)
                    time.sleep(3)
                    continue
                
                # Check for common Instagram elements
                instagram_indicators = [
                    "home", "search", "explore", "reels", "messages", 
                    "notifications", "create", "profile", "posts", "followers"
                ]
                
                found_indicators = sum(1 for indicator in instagram_indicators if indicator in body_text)
                
                if found_indicators >= 3:
                    print(f"   [Step 3] Instagram ready (found {found_indicators} indicators)")
                    return True
                else:
                    print(f"   [Step 3] Instagram not ready yet (found {found_indicators} indicators), waiting...")
                    time.sleep(2)
                    
            except Exception as e:
                print(f"   [Step 3] Error checking Instagram readiness: {e}")
                time.sleep(2)
        
        print("   [Step 3] Warning: Could not confirm Instagram readiness, proceeding anyway")
        return False

    def _navigate_to_profile(self, username):
        """Truy cập thẳng URL profile để đảm bảo vào đúng trang."""
        print(f"   [Step 3] Navigating to Profile: {username}...")
        
        # Luôn truy cập thẳng URL để tránh lỗi click icon
        profile_url = f"https://www.instagram.com/{username}/"
        self.driver.get(profile_url)
        
        wait_dom_ready(self.driver, timeout=15)
        time.sleep(3)  # Wait for dynamic content
        
        # Chờ Username xuất hiện (Confirm đã vào đúng trang), retry nếu cần
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                current_url = self.driver.current_url
                print(f"   [Step 3] Attempt {attempt+1}/{max_attempts} - Current URL: {current_url}")
                
                # Check if we're on the correct profile URL
                if username.lower() not in current_url.lower():
                    print(f"   [Step 3] URL mismatch, expected username '{username}' in URL")
                    self.driver.get(profile_url)
                    wait_dom_ready(self.driver, timeout=10)
                    time.sleep(2)
                    continue
                
                # Check for profile-specific elements
                profile_indicators = [
                    f"@{username}", username, "posts", "followers", "following"
                ]
                
                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                
                # Check if profile loaded
                username_found = any(indicator in body_text for indicator in profile_indicators)
                
                if username_found:
                    print(f"   [Step 3] Profile page confirmed for {username}")
                    
                    # Additional check: look for profile picture or bio area
                    try:
                        profile_elements = self.driver.find_elements(By.CSS_SELECTOR, 
                            "img[alt*='" + username + "'], div[data-testid='user-biography'], header section")
                        if profile_elements:
                            print("   [Step 3] Profile elements found, navigation successful")
                            return True
                    except:
                        pass
                    
                    return True
                
                # Check for error pages
                if "sorry, this page isn't available" in body_text.lower():
                    print(f"   [Step 3] Profile not found or private: {username}")
                    return False
                
                if "this account is private" in body_text.lower():
                    print(f"   [Step 3] Private account: {username}")
                    return False
                
                print(f"   [Step 3] Profile not loaded yet, attempt {attempt+1}/{max_attempts}")
                time.sleep(2)
                
            except Exception as e:
                print(f"   [Step 3] Error checking profile: {e}")
                time.sleep(2)
        
        print(f"   [Step 3] Warning: Could not confirm profile page for {username}, proceeding anyway")
        return False

    def _crawl_data(self, username):
        print(f"   [Step 3] Crawling data for {username}...")
        
        # Verify we're on the correct profile page before crawling
        current_url = self.driver.current_url
        if username.lower() not in current_url.lower():
            print(f"   [Step 3] ERROR: Not on profile page for {username}. Current URL: {current_url}")
            return {"posts": "0", "followers": "0", "following": "0"}
        
        final_data = {"posts": "0", "followers": "0", "following": "0"}
        
        time.sleep(1)
        
        js_crawl = """
            function getInfo() {
                let res = {posts: "0", followers: "0", following: "0", source: "none"};
                
                // 1. DÙNG MỎ NEO LINK FOLLOWERS (Tương thích cả UL/LI và DIV)
                let folLink = document.querySelector("a[href*='followers']");
                
                if (folLink) {
                    // CÁCH A: Cấu trúc DIV
                    let wrapper = folLink.closest('div'); 
                    if (wrapper && wrapper.parentElement) {
                        let container = wrapper.parentElement;
                        let divs = Array.from(container.children).filter(el => el.tagName === 'DIV');
                        if (divs.length >= 3) {
                            res.posts = divs[0].innerText;
                            res.followers = divs[1].innerText;
                            res.following = divs[2].innerText;
                            res.source = "div_structure";
                            return res;
                        }
                    }
                    // CÁCH B: Cấu trúc UL/LI
                    let ulContainer = folLink.closest("ul");
                    if (ulContainer) {
                        let items = ulContainer.querySelectorAll("li");
                        if (items.length >= 3) {
                            res.posts = items[0].innerText;
                            res.followers = items[1].innerText;
                            res.following = items[2].innerText;
                            res.source = "ul_structure";
                            return res;
                        }
                    }
                }

                // 2. FALLBACK: META TAG
                try {
                    let meta = document.querySelector('meta[property="og:description"]') || document.querySelector('meta[name="description"]');
                    if (meta) {
                        res.raw_meta = meta.getAttribute('content');
                        res.source = "meta";
                        return res;
                    }
                } catch(e) {}

                return res;
            }
            return getInfo();
        """

        # Hàm làm sạch số (100 posts -> 100)
        def clean_num(val):
            if not val: return "0"
            val = str(val).replace("\n", " ").strip()
            m = re.search(r'([\d.,]+[kKmM]?)', val)
            return m.group(1) if m else "0"

        def parse_meta(text):
            if not text: return "0", "0", "0"
            text = text.lower().replace(",", "").replace(".", ".")
            p = re.search(r'(\d+[km]?)\s+(posts|bài viết|beiträge)', text)
            f1 = re.search(r'(\d+[km]?)\s+(followers|người theo dõi)', text)
            f2 = re.search(r'(\d+[km]?)\s+(following|đang theo dõi)', text)
            if not p: p = re.search(r'(posts|bài viết)\s+(\d+[km]?)', text)
            return (p.group(1) if p else "0"), (f1.group(1) if f1 else "0"), (f2.group(1) if f2 else "0")

        for i in range(1, 4):
            try:
                time.sleep(1.5)
                raw_js = self.driver.execute_script(js_crawl)
                
                p, f1, f2 = "0", "0", "0"
                
                # Ưu tiên nguồn cấu trúc (DIV hoặc UL)
                if raw_js and raw_js.get("source") in ["div_structure", "ul_structure"]:
                    p = clean_num(raw_js.get("posts"))
                    f1 = clean_num(raw_js.get("followers"))
                    f2 = clean_num(raw_js.get("following"))
                    print(f"   [Step 3] Crawled via DOM ({raw_js.get('source')}): P={p}, F1={f1}, F2={f2}")

                # Nguồn Meta Tag
                elif raw_js and raw_js.get("source") == "meta":
                    p, f1, f2 = parse_meta(raw_js.get("raw_meta"))
                    print(f"   [Step 3] Crawled via META: P={p}, F1={f1}, F2={f2}")

                temp_data = {"posts": p, "followers": f1, "following": f2}

                # Điều kiện chấp nhận: Ít nhất 1 trường có dữ liệu
                if temp_data["followers"] != "0" or temp_data["posts"] != "0" or temp_data["following"] != "0":
                    final_data = temp_data
                    print(f"   [Step 3] Success (Attempt {i}): {final_data}")
                    break
                else:
                    print(f"   [Step 3] Attempt {i}: Data empty. Retrying...")

            except Exception as e:
                print(f"   [Step 3] Crawl Error (Attempt {i}): {e}")

        return final_data

    def _get_cookie_string(self):
        """Lấy toàn bộ cookie hiện tại và gộp thành chuỗi, với chuẩn hóa."""
        try:
            cookies = self.driver.get_cookies()
            # Chuẩn hóa: loại bỏ khoảng trắng và encode value
            import urllib.parse
            cookie_parts = []
            for c in cookies:
                name = c['name']
                value = urllib.parse.quote(c['value'].strip())
                cookie_parts.append(f"{name}={value}")
            return "; ".join(cookie_parts)
        except:
            return ""