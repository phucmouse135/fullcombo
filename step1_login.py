# step1_login.py
import json
import time
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from config_utils import wait_element, wait_and_click, wait_and_send_keys, wait_dom_ready

class InstagramLoginStep:
    def __init__(self, driver):
        self.driver = driver
        self.base_url = "https://www.instagram.com/"
        self.count = 0

    def load_base_cookies(self, json_path):
        """
        Nạp cookie mồi từ file JSON để giả lập thiết bị cũ/phiên làm việc cũ.
        Tối ưu: Sử dụng wait_dom_ready thay vì time.sleep.
        """
        if not os.path.exists(json_path):
            print(f"   [Step 1] Warning: Cookie file {json_path} not found.")
            return False

        try:
            print("   [Step 1] Loading base cookies...")
            self.driver.get(self.base_url) # Truy cập lần 1 để nhận domain
            
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                cookies = data.get("cookies", [])
            
            for cookie in cookies:
                cookie_dict = {
                    'name': cookie.get('name'),
                    'value': cookie.get('value'),
                    'domain': cookie.get('domain', '.instagram.com'),
                    'path': cookie.get('path', '/'),
                    'secure': cookie.get('secure', True)
                }
                if 'expirationDate' in cookie:
                    cookie_dict['expiry'] = int(cookie['expirationDate'])
                try: self.driver.add_cookie(cookie_dict)
                except: pass
            
            self.driver.refresh()
            # TỐI ƯU: Chờ DOM load xong thay vì ngủ cứng 3s
            wait_dom_ready(self.driver, timeout=15)
            return True
        except Exception as e:
            print(f"   [Step 1] Error loading cookies: {e}")
            return False

    def perform_login(self, username, password):
        print(f"[{username}]   [Step 1] Login as {username}...")

        # --- GIAI ĐOẠN 1: CLICK ALLOW ALL COOKIES POPUP ---
        print(f"[{username}]   [Step 1] Checking for 'Allow all cookies' popup...")
        # Maximize window to ensure buttons are not obscured
        # self.driver.maximize_window()
        cookie_button_selectors = [
            (By.CSS_SELECTOR, "button._a9--._ap36._asz1[tabindex='0']"),
            (By.XPATH, "//button[contains(@class, '_a9--') and contains(@class, '_ap36') and contains(@class, '_asz1') and contains(text(), 'Allow all cookies')]"),
            (By.XPATH, "//button[contains(text(), 'Allow all cookies')]"),
            (By.CSS_SELECTOR, "button[aria-label*='Accept cookies']"),
            (By.XPATH, "//button[contains(@aria-label, 'Accept')]"),
            (By.XPATH, "//button[contains(@title, 'Accept')]"),
            (By.CSS_SELECTOR, "button[class*='cookie']"),
            (By.CSS_SELECTOR, "button[data-action*='accept']"),
            (By.CSS_SELECTOR, "button[data-testid*='accept']")
        ]

        for by, selector in cookie_button_selectors:
            if wait_and_click(self.driver, by, selector, timeout=5):
                print(f"[{username}]   [Step 1] Clicked 'Allow all cookies' button")
                time.sleep(2)  # Wait for popup to disappear
                break
        else:
            print(f"[{username}]   [Step 1] 'Allow all cookies' button not found or already dismissed")

        # Ensure page is fully loaded before input
        wait_dom_ready(self.driver, timeout=10)

        # --- GIAI ĐOẠN 2: NHẬP USER (TỐI ƯU TỐC ĐỘ) ---
        print(f"[{username}]   [Step 1] Entering Username...")
        user_css_group = "input[name='email'], input[name='username'], input[id^='_r_'][type='text'], input[placeholder*='username'], input[placeholder*='email'], input[placeholder*='phone'], input[aria-label*='username'], input[aria-label*='email']"
        user_start = time.time()
        # Max 60s for user input
        while time.time() - user_start < 60:
            user_input = wait_element(self.driver, By.CSS_SELECTOR, user_css_group, timeout=3)
            if user_input:
                try:
                    user_input.clear()
                    user_input.send_keys(username)
                except:
                    print(f"[{username}]   [Step 1] Retry sending username...")
                    wait_and_send_keys(self.driver, By.CSS_SELECTOR, user_css_group, username)
                break
            time.sleep(1)
        else:
            return "FAIL_FIND_INPUT_USER_TIMEOUT"

        # --- GIAI ĐOẠN 3: NHẬP PASSWORD (TỐI ƯU TỐC ĐỘ) ---
        print(f"[{username}]   [Step 1] Entering Password...")
        pass_css_group = "input[name='pass'], input[name='password'], input[id^='_r_'][type='password'], input[placeholder*='password'], input[aria-label*='password']"
        pass_start = time.time()
        # Max 60s for password input
        while time.time() - pass_start < 60:
            pass_input = wait_element(self.driver, By.CSS_SELECTOR, pass_css_group, timeout=3)
            if pass_input:
                try:
                    pass_input.clear()
                    pass_input.send_keys(password)
                except:
                    wait_and_send_keys(self.driver, By.CSS_SELECTOR, pass_css_group, password)
                break
            time.sleep(1)
        else:
            return "FAIL_FIND_INPUT_PASS_TIMEOUT"

        # --- GIAI ĐOẠN 4: CLICK LOGIN ---
        print(f"[{username}]   [Step 1] Clicking Login...")
        login_start = time.time()
        # Max 60s for login button
        while time.time() - login_start < 60:
            try:
                pass_input.send_keys(Keys.ENTER)
                break
            except:
                login_btn_xpath = "//button[@type='submit'] | //div[contains(text(), 'Log in')] | //button[contains(text(), 'Log in')] | //button[contains(text(), 'Login')] | //div[@role='button' and contains(text(), 'Log in')]"
                if wait_and_click(self.driver, By.XPATH, login_btn_xpath, timeout=3):
                    break
            time.sleep(1)
        else:
            return "FAIL_LOGIN_BUTTON_TIMEOUT"
        wait_dom_ready(self.driver , timeout=30)
        # Chờ trang web load xong sau khi nhấn Login (đợi URL thay đổi)
        initial_url = self.driver.current_url
        start_time = time.time()
        while time.time() - start_time < 40:
            if self.driver.current_url != initial_url:
                wait_dom_ready(self.driver, timeout=20)
                break
            time.sleep(3)
        status = self._wait_for_login_result(username, timeout=120)
        
        # Handle cookie consent popup after login if detected
        if status == "COOKIE_CONSENT_POPUP":
            print(f"[{username}]   [Step 1] Handling cookie consent popup after login...")
            for by, selector in cookie_button_selectors:
                if wait_and_click(self.driver, by, selector, timeout=5):
                    print(f"[{username}]   [Step 1] Clicked 'Allow all cookies' button after login")
                    time.sleep(2)  # Wait for popup to disappear
                    break
            else:
                print(f"[{username}]   [Step 1] 'Allow all cookies' button not found after login")
            
            wait_dom_ready(self.driver, timeout=30)
            status = self._detect_initial_status(username)
            print(f"[{username}]   [Step 1] Status after cookie handling: {status}")
        
        print(f"[{username}]   [Step 1] Login result detected: {status}")
        return status

    def _wait_for_login_result(self, username, timeout=180):
        print(f"   [{username}] [Step 1] Waiting for login result...")
        end_time = time.time() + timeout
        
        while time.time() < end_time:
            status = self._detect_initial_status(username)
            print(f"   [{username}] [Step 1] Intermediate login status: {status}")
            
            # Nếu status đã rõ ràng (không phải Unknown/Retry) -> Return ngay
            if status not in ["LOGGED_IN_UNKNOWN_STATE"]:
                return status
            
            time.sleep(3)  # Poll nhẹ
            
        print(f"   [{username}] [Step 1] Timeout reached after {timeout} seconds. Current URL: {self.driver.current_url}")
        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            print(f"   [{username}] [Step 1] Body text at timeout: {body_text[:500]}...")  # First 500 chars
        except Exception as e:
            print(f"   [{username}] [Step 1] Could not get body text at timeout: {e}")
        return "TIMEOUT_LOGIN_CHECK"
    def _detect_initial_status(self, username):
        """
        Quét DOM để xác định trạng thái sơ bộ sau khi nhấn Login.
        (GIỮ NGUYÊN TEXT LỖI TỪ BẢN GỐC)
        """
        try:
            wait_dom_ready(self.driver, timeout=5)
            
            # Check URL for cookie choice
            current_url = self.driver.current_url.lower()
            
            # unblock in url 
            if "unblock" in current_url:
                return "UNBLOCK_ACCOUNT"
            
            
            if "user_cookie_choice" in current_url:
                return "COOKIE_CONSENT_POPUP"
            
            try:
                body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            except Exception as e:
                error_str = str(e).lower()
                if "stale" in error_str or "element" in error_str and "reference" in error_str:
                    print(f"   [{username}] [Step 1] Stale element when getting body text, retrying...")
                    time.sleep(1)
                    try:
                        body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                    except Exception as e2:
                        print(f"   [{username}] [Step 1] Stale element retry also failed, returning unknown state")
                        return "LOGGED_IN_UNKNOWN_STATE"
                else:
                    return f"ERROR_DETECT: {str(e)}"
                
                
            # you need to request help logging in To secure your account, you need to request help logging in
                if "you need to request help logging in" in body_text or "to secure your account, you need to request help logging in" in body_text:
                    return "GET_HELP_LOG_IN"
            # The login information you entered is incorrect
            if "the login information you entered is incorrect" in body_text or \
                       "incorrect username or password" in body_text or \
                        "thông tin đăng nhập bạn đã nhập không chính xác" in body_text or "find your account and log in" in body_text:
                return "LOGIN_FAILED_INCORRECT"
            
            # We suspect automated behavior on your account
            if 'we suspect automated behavior on your account' in body_text or 'prevent your account from being temporarily ' in body_text or 'verify you are a real person' in body_text or 'suspicious activity' in body_text:
                return "AUTOMATED_BEHAVIOR_DETECTED"
            
            # We suspect automated behavior on your account
            if 'we suspect automated behavior on your account' in body_text:
                return "AUTOMATED_BEHAVIOR_DETECTED"
                
            if 'prevent your account from being temporarily ' in body_text or 'verify you are a real person' in body_text or 'suspicious activity' in body_text:
                return "AUTOMATED_BEHAVIOR_DETECTED"
            
            
            #  We couldn't connect to Instagram. Make sure you're connected to the internet and try again. 
            if "we couldn't connect to instagram" in body_text and "make sure you're connected to the internet" in body_text:
                return "NOT_CONNECT_INSTAGRAM"
            
            # Use another profile => Văng về chọn tài khoản
            if "use another profile" in body_text or "Log into Instagram" in body_text or "create new account" in body_text:
                if self.count >=20:
                    return "FAIL_LOGIN_REDIRECTED_TO_PROFILE_SELECTION"
                else:
                    self.count += 1
            
            if "choose a way to recover" in body_text:
                return "RECOVERY_CHALLENGE"
            
            # Choose if we process your data for ads
            if "choose if we process your data for ads" in body_text or "chọn nếu chúng tôi xử lý dữ liệu của bạn cho quảng cáo" in body_text:
                return "DATA_PROCESSING_FOR_ADS"
            
            # Check for no internet connection
            if "we couldn't connect to instagram" in body_text and "make sure you're connected to the internet" in body_text:
                return "NOT_CONNECT_INSTAGRAM"
            
            # 1. Các trường hợp Exception / Checkpoint
            if "enter the 6-digit code" in body_text and ("email" in body_text or "mail" in body_text):
                return "CHECKPOINT_MAIL"
            if "check your email" in body_text or " we sent to the email address" in body_text:
                return "CHECKPOINT_MAIL"
            
            # Enter the 6-digit code we sent to the number ending in
            if "enter the 6-digit code we sent to the number ending in" in body_text:
                return "CHECKPOINT_PHONE"
            
            # enter your email
            if "enter your email" in body_text or "please enter your email address to continue" in body_text:
                return "DISABLE_ACCOUNT"
            
            # Log in on another device to continue
            if "log in on another device to continue" in body_text or "đăng nhập trên thiết bị khác để tiếp tục" in body_text:
                return "LOG_IN_ANOTHER_DEVICE"
            
            if "add phone number to get back into instagram" in body_text or "send confirmation" in body_text or "log into another account" in body_text or "we will send a confirmation code via sms to your phone." in body_text: 
                return "SUSPENDED_PHONE"
            # this was me / let us know if it was you
            if "this was me" in body_text or "let us know if it was you" in body_text or "to secure your account" in body_text:
                return "CONFIRM_TRUSTED_DEVICE"
            
            # yêu cầu đổi mật khẩu 
            if "we noticed unusual activity" in body_text or "change your password" in body_text or "yêu cầu đổi mật khẩu" in body_text:
                return "REQUIRE_PASSWORD_CHANGE"
            
            if 'for you' in body_text or 'following' in body_text or 'suggested for you' in body_text or 'get fresh updates here when you follow accounts' in body_text: 
                return "LOGGED_IN_SUCCESS"
            # Nếu đã vào trong (có Post/Follower/Nav bar)
            if "posts" in body_text or "followers" in body_text or "search" in body_text or "home" in body_text or "suggestions for you" in body_text:
                return "LOGGED_IN_SUCCESS"

            if("save your login info?" in body_text or "we can save your login info on this browser so you don't need to enter it again." in body_text or "lưu thông tin đăng nhập của bạn" in body_text or "save info" in body_text):
                return "LOGGED_IN_SUCCESS"
            
            # [NEW] Detect "Confirm your accounts" (Meta Accounts Center)
            if "confirm your accounts" in body_text or "xác nhận tài khoản của bạn" in body_text:
                if "get started" in body_text or "bắt đầu" in body_text:
                    return "CONFIRM_YOUR_ACCOUNTS"
            
            
            
            try:
                wait_dom_ready(self.driver, timeout=5)
                start_time = time.time()
                last_url = self.driver.current_url
                while True:
                    try:
                        body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                    except Exception as e:
                        error_str = str(e).lower()
                        if "stale" in error_str or ("element" in error_str and "reference" in error_str):
                            print(f"   [{username}] [Step 1] Stale element in status check loop, retrying...")
                            time.sleep(1)
                            continue
                        else:
                            raise e  # Re-raise to be caught by outer except
                    current_url = self.driver.current_url
                    
                    # We suspect automated behavior on your account
                    if 'we suspect automated behavior on your account' in body_text or 'prevent your account from being temporarily ' in body_text or 'verify you are a real person' in body_text or 'suspicious activity' in body_text:
                        return "AUTOMATED_BEHAVIOR_DETECTED"
                    
                    # We suspect automated behavior on your account
                    if 'we suspect automated behavior on your account' in body_text:
                        return "AUTOMATED_BEHAVIOR_DETECTED"
                        
                    if 'prevent your account from being temporarily ' in body_text or 'verify you are a real person' in body_text or 'suspicious activity' in body_text:
                        return "AUTOMATED_BEHAVIOR_DETECTED"

                    # you need to request help logging in To secure your account, you need to request help logging in
                    if "you need to request help logging in" in body_text or "to secure your account, you need to request help logging in" in body_text:
                        return "GET_HELP_LOG_IN"
                    
                    # [NEW] Detect "Confirm your accounts" (Meta Accounts Center)
                    if "confirm your accounts" in body_text or "xác nhận tài khoản của bạn" in body_text:
                        if "get started" in body_text or "bắt đầu" in body_text:
                            return "CONFIRM_YOUR_ACCOUNTS"
                        
                    # keep using your personal data across these accounts / use data across accounts / manage accounts
                    if "keep using your personal data across these accounts" in body_text or "use data across accounts" in body_text or "manage accounts" in body_text:
                        return "ACCOUNTS_CENTER_DATA_SHARING"
                        
                    if "the login information you entered is incorrect" in body_text or \
                       "incorrect username or password" in body_text or \
                        "thông tin đăng nhập bạn đã nhập không chính xác" in body_text:
                        return "LOGIN_FAILED_INCORRECT"
                    
                    # We Detected An Unusual Login Attempt 
                    if ("we detected an unusual login attempt" in body_text or "to secure your account, we'll send you a security code." in body_text) :
                        if "email" in body_text or "mail" in body_text:            
                            return "CONTINUE_UNUSUAL_LOGIN"
                        if "this was me" in body_text or "let us know if it was you" in body_text:
                            return "CONFIRM_TRUSTED_DEVICE"
                        return "CONTINUE_UNUSUAL_LOGIN_PHONE"
                    
                    # Check for no internet connection
                    if "we couldn't connect to instagram" in body_text and "make sure you're connected to the internet" in body_text:
                        return "NOT_CONNECT_INSTAGRAM"
                
                    if "choose a way to recover" in body_text:
                        return "RECOVERY_CHALLENGE"
                    # 1. Các trường hợp Exception / Checkpoint
                    if "check your email" in body_text or " we sent to the email address" in body_text:
                        return "CHECKPOINT_MAIL"

                    # Log in on another device to continue
                    if "log in on another device to continue" in body_text or "đăng nhập trên thiết bị khác để tiếp tục" in body_text:
                        return "LOG_IN_ANOTHER_DEVICE"
                    
                    # your account has been disabled
                    if "your account has been disabled" in body_text:
                        return "ACCOUNT_DISABLED"

                    if "add phone number to get back into instagram" in body_text or "send confirmation" in body_text or "log into another account" in body_text or "we will send a confirmation code via sms to your phone." in body_text: 
                        return "SUSPENDED_PHONE"

                    # yêu cầu đổi mật khẩu 
                    if "we noticed unusual activity" in body_text or "change your password" in body_text or "yêu cầu đổi mật khẩu" in body_text:
                        return "REQUIRE_PASSWORD_CHANGE"
                    # this was me / let us know if it was you
                    if "this was me" in body_text or "let us know if it was you" in body_text or "to secure your account" in body_text:
                        return "CONFIRM_TRUSTED_DEVICE"

                    # Try another device to continue
                    if "try another device" in body_text or "try another device to continue" in body_text or "can’t try another device?" in body_text:
                        return "TRY_ANOTHER_DEVICE"

                    if "suspended" in body_text or "đình chỉ" in body_text:
                        return "SUSPENDED"

                    # The login information you entered is incorrect
                    if "the login information you entered is incorrect" in body_text or \
                       "incorrect username or password" in body_text or \
                        "thông tin đăng nhập bạn đã nhập không chính xác" in body_text:
                        return "LOGIN_FAILED_INCORRECT"
                    # Something went wrong
                    if "something went wrong" in body_text or "something went wrong" in body_text:
                        return "LOGIN_FAILED_SOMETHING_WENT_WRONG"

                    # 2. Các trường hợp Thành công / Tiếp tục
                    if "select your birthday" in body_text or "add your birthday" in body_text:
                        return "BIRTHDAY_SCREEN"

                    # 
                    # check your text messages
                    if "check your text messages" in body_text or "kiểm tra tin nhắn văn bản của bạn" in body_text:
                        return "2FA_TEXT_MESSAGE"
                    
                    # if "allow the use of cookies" in body_text:
                    #     return "COOKIE_CONSENT"
                    
                    
                    
                    # Help us confirm it's you
                    if "help us confirm it's you" in body_text or "xác nhận đó là bạn" in body_text:
                        return "CONFIRM_YOUR_IDENTITY"

                    

                    # SMS 2FA screen "Enter a 6-digit login code generated by an authentication app." or vietnamese
                    if "mã đăng nhập 6 chữ số được tạo bởi ứng dụng xác thực" in body_text or "enter a 6-digit login code generated by an authentication app." in body_text:
                        return "2FA_SMS"

                    # Check your WhatsApp messages 
                    if "check your whatsapp messages" in body_text or "kiểm tra tin nhắn whatsapp của bạn" in body_text or "we sent via whatsapp to" in body_text:
                        return "2FA_WHATSAPP"


                    # Confirm your info on the app 
                    if "confirm your info on the app" in body_text:
                        return "2FA_APP"
                    
                    if "use another account" in body_text or "create new account" in body_text:
                        if "continue" in body_text:
                            return "RETRY_LOGIN"
                        if "log into instagram" in body_text:
                            return "FAIL_LOGIN_REDIRECTED_TO_PROFILE_SELECTION"

                    # your post goes against our community standards / How we make decisions
                    if "your post goes against our community standards" in body_text or "bài đăng của bạn vi phạm các tiêu chuẩn cộng đồng của chúng tôi" in body_text or "how we make decisions" in body_text:
                        return "POST_VIOLATES_COMMUNITY_STANDARDS"
                    

                    # Check your notifications  && Check your notifications there and approve the login to continue.
                    if "check your notifications" in body_text or "xem thông báo của bạn" in body_text or "check your notifications there and approve the login to continue." in body_text:
                        return "2FA_NOTIFICATIONS"
                    
                    # Nếu đã vào trong (có Post/Follower/Nav bar)
                    if "posts" in body_text or "followers" in body_text or "search" in body_text or "home" in body_text:
                        return "LOGGED_IN_SUCCESS"

                    if("save your login info?" in body_text or "we can save your login info on this browser so you don't need to enter it again." in body_text or "lưu thông tin đăng nhập của bạn" in body_text):
                        return "LOGGED_IN_SUCCESS"
                    
                    # Log into Instagram , password input 
                    if "log into instagram" in body_text or "password" in body_text or "mobile number, username, or email" in body_text or "log in with facebook" in body_text or "create new account" in body_text:
                        self.count += 1
                        if self.count >=30:
                            return "LOGIN_FAILED"
                    
                    # Nếu vẫn còn ô password -> Login chưa qua (có thể đang loading)
                    if len(self.driver.find_elements(By.CSS_SELECTOR, "input[type='password']")) > 0:
                        self.count += 1
                        if self.count >=30:
                            return "LOGIN_FAILED_RETRY"

                    # Nếu không xác định được trạng thái, kiểm tra loading hoặc url đứng yên
                    loading_selectors = [
                        "div[role='progressbar']", "div[aria-busy='true']", "._ab8w", ".loading-spinner", "[data-testid='loading-indicator']"
                    ]
                    loading_found = False
                    for sel in loading_selectors:
                        try:
                            if len(self.driver.find_elements(By.CSS_SELECTOR, sel)) > 0:
                                loading_found = True
                                break
                        except:
                            pass

                    # Nếu có loading hoặc url không đổi thì tiếp tục chờ
                    if loading_found or current_url == last_url:
                        if time.time() - start_time > 180:
                            print(f"   [{username}] [Step 1] Inner loop timeout after 180 seconds. Current URL: {current_url}")
                            try:
                                body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                                print(f"   [{username}] [Step 1] Body text at inner timeout: {body_text[:500]}...")
                            except Exception as e:
                                print(f"   [{username}] [Step 1] Could not get body text at inner timeout: {e}")
                            break
                        time.sleep(1)
                        last_url = current_url
                        continue

                    # Nếu không xác định được trạng thái, trả về Unknown State
                    break
                return "LOGGED_IN_UNKNOWN_STATE"
            except Exception as e:
                return f"ERROR_DETECT: {str(e)}" 
        except Exception as e:
            return f"ERROR_DETECT_EXCEPTION: {str(e)}"
        
    