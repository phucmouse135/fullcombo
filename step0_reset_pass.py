import time
import re
import urllib.parse
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from mail_handler_v2 import verify_account_live, get_verify_code_v2
from config_utils import wait_element, wait_and_click, wait_and_send_keys

class InstagramResetPasswordStep:
    def __init__(self, driver):
        self.driver = driver

    def process_reset_password(self, gmx_user, gmx_pass, new_password, window_rect=None):
        """
        Thực hiện quy trình lấy link reset -> đổi pass -> checkpoint mail (nếu có).
        Trả về tuple:
          (status, found_username, full_step0_link[, adjusted_pass])
          - status:
            "SUCCESS"                    : Đổi pass thành công
            "SUCCESS_WITH_ADJUSTED_PASS" : Đổi pass thành công với pass điều chỉnh (+@)
            "FAIL_MAIL_FETCH_ERROR"       : verify_account_live() throw exception
            "FAIL_MAIL_NOT_FOUND"         : Mail không chứa reset link (no success)
            "FAIL_MAIL_NO_LINK"           : Mail parse được nhưng không có LINK=
            "LINK_RESET_PASS_DIE"         : Clean URL thử 3 lần vẫn fail (link hết hạn)
            "FAIL_RESET_PAGE_UNAVAILABLE": Page 'not available' sau khi vào được URL
            "FAIL_RESET_INPUTS_NOT_FOUND": Không tìm thấy ô nhập password trên trang reset
            "FAIL_RESET_BTN_NOT_FOUND"    : Không tìm thấy nút Reset và submit fallback cũng fail
            "FAIL_RELOCATE_INPUTS"        : Không re-locate được inputs sau lỗi same password
            "FAIL_RETRY_TIMEOUT"          : Timeout 15s sau khi retry với adjusted pass
            "FAIL_EXCEPTION"              : Exception không xử lý được ở outer try-catch
        """
        # [NEW] Initial: Access Instagram Home and handle Cookie Popup
        print(f"   [Step 0] Initializing: Visiting Instagram Home to handle cookies...")
        try:
            self.driver.get("https://www.instagram.com/")
            time.sleep(3)
            
            # Handle Cookie Popup
            print("   [Step 0] Checking for initial cookie popup...")
            try:
                buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button, div[role="button"]')
                cookie_clicked = False
                for b in buttons:
                    if not b.is_displayed(): continue
                    txt = b.text.lower()
                    if 'allow all cookies' in txt or 'cho phép tất cả' in txt or 'accept' in txt or 'chấp nhận' in txt:
                        print("   [Step 0] Closing initial cookie popup (Allow)...")
                        b.click()
                        cookie_clicked = True
                        time.sleep(2)
                        break
                    elif 'decline optional cookies' in txt or 'từ chối' in txt:
                        print("   [Step 0] Closing initial cookie popup (Decline)...")
                        b.click()
                        cookie_clicked = True
                        time.sleep(2)
                        break
            except Exception as e:
                print(f"   [Step 0] Initial cookie popup warning: {e}")
        except Exception as e:
            print(f"   [Step 0] Error accessing Instagram home: {e}")

        print(f"   [Step 0] Searching for reset password email for {gmx_user}...")
        
        # 1. Lấy link reset từ mail
        # Hàm verify_account_live trả về string dạng "success|USER=...|UID=...|LINK=..." hoặc "Fail..."
        try:
            result = verify_account_live(gmx_user, gmx_pass)
        except Exception as e:
            print(f"   [Step 0] Error fetching mail: {e}")
            return "FAIL_MAIL_FETCH_ERROR", None, None

        if "success" not in result:
             print(f"   [Step 0] Reset mail not found: {result}")
             return "FAIL_MAIL_NOT_FOUND", None, None

        # Parse kết quả để lấy link
        link_match = re.search(r'LINK=(http[^|]+)', result)
        user_match = re.search(r'USER=([^|]+)', result)
        
        found_username = None
        if user_match:
            found_username = user_match.group(1).strip()
            if found_username == "None" or found_username == "":
                found_username = None
        
        if not link_match:
            print("   [Step 0] Link not found in mail result.")
            return "FAIL_MAIL_NO_LINK", None, None
        
        # Print raw link first (as requested)
        raw_link = link_match.group(1)
        print(f"   [Step 0] Found link: {raw_link}")

        # Then decode for usage (so it handles %3A -> : correctly)
        full_url = urllib.parse.unquote(raw_link)

        if found_username:
            print(f"   [Step 0] Found username in mail: {found_username}")

        # 2. Xử lý URL (Regex lấy short link)
        # Pattern: lấy đến hết phần token (trước dấu : nếu có, hoặc hết chuỗi)
        # Ví dụ: ...token=XYZ:one_click... -> ...token=XYZ
        # Logic user yêu cầu: regex lấy link clean để dùng thử trước
        
        # Thử clean url bằng regex: giữ lại phần cơ bản của confirm link
        # https://instagram.com/accounts/password/reset/confirm/?uidb36=...&token=...
        # Lưu ý: full_url đã được decode ở trên, nên nếu có :one_click... thì regex sẽ loại bỏ phần sau dấu :
        
        clean_url = full_url
        match = re.search(r'(https?://.*?/accounts/password/reset/confirm/\?uidb36=[^&]+&token=[^:&]+)', full_url)
        if match:
            clean_url = match.group(1)
            # URL Decode lần nữa để đảm bảo (dù đã decode full_url rồi)
            clean_url = urllib.parse.unquote(clean_url)
            print(f"   [Step 0] Clean URL Processed (Regex): {clean_url}")
        else:
            print("   [Step 0] Could not clean URL, using full URL as clean URL.")

        # 3. Mở tab mới với giao diện Mobile (Sử dụng CDP command)
        # Bắt buộc phải dùng CDP để set device emulation cho riêng tab này (nếu driver support)
        # Hoặc simpler: set user agent và window size.
        # Tuy nhiên Selenium cơ bản thay đổi cả browser session. 
        # Để an toàn và đơn giản, ta sẽ chỉ thay đổi kích thước cửa sổ cho giống mobile 
        # và hy vọng Instagram responsive sẽ hiển thị giao diện mobile.
        # Nếu muốn devtool mobile chuẩn, phải dùng Chrome DevTools Protocol (CDP).
        
        current_window = self.driver.current_window_handle

        # Lưu lại kích thước PC gốc trước khi set mobile (ưu tiên window_rect từ slot, fallback get_window_size)
        try:
            pc_size = self.driver.get_window_size()  # {"width": W, "height": H}
            pc_width  = pc_size.get("width", 1280)
            pc_height = pc_size.get("height", 800)
        except:
            pc_width, pc_height = 1280, 800
        # Nếu window_rect được truyền vào (từ slot layout), dùng nó để override cho chính xác
        if window_rect and len(window_rect) == 4:
            _, _, slot_w, slot_h = window_rect
            if slot_w > 0 and slot_h > 0:
                pc_width, pc_height = slot_w, slot_h
        print(f"   [Step 0] PC window size for restore: {pc_width}x{pc_height}")

        self.driver.execute_script("window.open('');")
        self.driver.switch_to.window(self.driver.window_handles[-1])
        
        # [NEW] Enable Mobile Emulation via CDP for this target
        try:
            self.driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                "width": 375,
                "height": 812,
                "deviceScaleFactor": 3,
                "mobile": True
            })
            self.driver.execute_cdp_cmd("Emulation.setUserAgentOverride", {
                "userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1"
            })
            print("   [Step 0] Enabled Mobile Emulation for Reset Tab.")
        except Exception as e:
            print(f"   [Step 0] Failed to enable mobile emulation: {e}")

        try:
            # Retry logic for Clean URL (3 attempts)
            clean_url_success = False
            for attempt in range(3):
                print(f"   [Step 0] Accessing Clean URL (Attempt {attempt + 1}/3)...")
                print(f"   [Step 0] Navigating to: {clean_url}")
                self.driver.get(clean_url)
                
                # Chờ page load hoàn tất
                try:
                    WebDriverWait(self.driver, 10).until(lambda d: d.execute_script("return document.readyState") == "complete")
                    print("   [Step 0] Page loaded (readyState=complete).")
                except:
                    print("   [Step 0] Page load timeout (readyState).")

                time.sleep(2) # Thêm chút delay ổn định DOM
                
                # Check for "Sorry, this page isn't available"
                body_text = ""
                try:
                    body_el = WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                    body_text = body_el.text
                except:
                    pass

                if "Sorry, this page isn't available" in body_text or "This page isn't available" in body_text:
                    print(f"   [Step 0] Clean URL attempt {attempt + 1} failed (Page not available).")
                    time.sleep(2)
                    continue # Try again
                
                # [NEW] Handle Cookie Popup inside loop
                print("   [Step 0] Checking for cookie popup...")
                try:
                    buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button, div[role="button"]')
                    for b in buttons:
                        if not b.is_displayed(): continue
                        txt = b.text.lower()
                        if 'allow all cookies' in txt or 'cho phép tất cả' in txt or 'accept' in txt or 'chấp nhận' in txt:
                            print("   [Step 0] Closing cookie popup (Allow)...")
                            b.click()
                            time.sleep(1)
                            break
                        elif 'decline optional cookies' in txt or 'từ chối' in txt:
                            print("   [Step 0] Closing cookie popup (Decline)...")
                            b.click()
                            time.sleep(1)
                            break
                except Exception as e:
                    print(f"   [Step 0] Cookie popup check warning: {e}")

                # Check inputs
                print("   [Step 0] Verifying input fields...")
                # Reduce timeout for quick check inside loop
                try: 
                    pass_input = WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[data-testid="new-password-field"]')))
                    verify_input = WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[data-testid="verify-password-field"]')))
                except:
                    pass_input = None
                    verify_input = None

                if pass_input and verify_input:
                    print("   [Step 0] Inputs found.")
                    clean_url_success = True
                    break
                else:
                    print(f"   [Step 0] Inputs NOT found on attempt {attempt + 1}. Retrying...")
                    time.sleep(2)
            
            # If Clean URL failed after 3 attempts -> link is dead, return immediately
            if not clean_url_success:
                print("   [Step 0] Clean URL (regex) failed 3 times. Link is dead. Returning LINK_RESET_PASS_DIE.")
                self.driver.close()
                try:
                    self.driver.switch_to.window(current_window)
                except: pass
                return "LINK_RESET_PASS_DIE", None, None

            # 4. Final Verification
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            if "Sorry, this page isn't available" in body_text or "This page isn't available" in body_text:
                print("   [Step 0] Page shows 'not available' after clean URL loaded. Link dead.")
                self.driver.close()
                self.driver.switch_to.window(current_window)
                return "FAIL_RESET_PAGE_UNAVAILABLE", None, None

            # 5. Entering Password
            # Create flexible input finding
            print("   [Step 0] Entering new password...")
            
            pass_input = wait_element(self.driver, By.CSS_SELECTOR, 'input[data-testid="new-password-field"]', timeout=10)
            verify_input = None
            try:
                verify_input = wait_element(self.driver, By.CSS_SELECTOR, 'input[data-testid="verify-password-field"]', timeout=5)
            except: pass
            
            if not pass_input:
                # Try finding generic password inputs as fallback
                try:
                    p_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
                    if len(p_inputs) > 0:
                        pass_input = p_inputs[0]
                        if len(p_inputs) > 1: verify_input = p_inputs[1]
                except: pass

            if not pass_input:
                # Có thể link trỏ thẳng về trang login hoặc trang khác
                print(f"   [Step 0] Password inputs not found. Current URL: {self.driver.current_url}")
                # Nếu không thấy ô nhập pass, có thể nó đã login luôn (one click login).
                # Check thử xem đã login chưa
                if "instagram.com/accounts/onetap" in self.driver.current_url or "instagram.com/" == self.driver.current_url:
                     print("   [Step 0] Seems like instant login (one-tap redirect).")
                     return "SUCCESS", found_username, full_url # Coi như thành công, sang Step 2 check lại
                
                self.driver.close()
                self.driver.switch_to.window(current_window)
                return "FAIL_RESET_INPUTS_NOT_FOUND", None, None

            # Điền pass
            # Pass lấy từ tham số new_password (là pass mail theo yêu cầu)
            pass_input.clear()
            pass_input.send_keys(new_password)
            time.sleep(0.5)
            
            if verify_input:
                verify_input.clear()
                verify_input.send_keys(new_password)
                time.sleep(0.5)
            else:
                print("   [Step 0] Verify input not found (Single input mode). proceeding...")
            
            # Click Reset Password Button
            print("   [Step 0] Looking for Reset/Change Password button...")
            reset_btn = None
            
            # 1. Try finding by text in button elements
            try:
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for btn in buttons:
                    if not btn.is_displayed(): continue
                    txt = btn.text.lower()
                    if "reset password" in txt or "change password" in txt or "lưu mật khẩu" in txt or "đặt lại mật khẩu" in txt:
                        reset_btn = btn
                        print(f"   [Step 0] Found button by text: {txt}")
                        break
            except: pass

            # 2. Try finding generic submit button
            if not reset_btn:
                try:
                    reset_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                    print("   [Step 0] Found button by type='submit'")
                except: pass

            # 3. Try finding div role=button with text
            if not reset_btn:
                try:
                    div_btns = self.driver.find_elements(By.CSS_SELECTOR, "div[role='button']")
                    for db in div_btns:
                        if not db.is_displayed(): continue
                        txt = db.text.lower()
                        if "reset password" in txt or "change password" in txt or "lưu mật khẩu" in txt:
                            reset_btn = db
                            print(f"   [Step 0] Found div[role=button] by text: {txt}")
                            break
                except: pass

            # Action: Verify click
            if reset_btn:
                print("   [Step 0] Clicking Reset Password button...")
                try:
                    current_url_before_click = self.driver.current_url
                except:
                    current_url_before_click = None

                try:
                    reset_btn.click()
                except:
                    self.driver.execute_script("arguments[0].click();", reset_btn)

                # Wait for URL change (indicates successful submit) up to 10s
                url_changed = False
                
                # [NEW] Check for error "Create a new password that isn't your current password"
                # If found: Stop trying new pass, fallback to OLD password + logic
                is_old_pass_error = False
                
                if not is_old_pass_error:
                    if current_url_before_click is not None:
                        for _ in range(10):
                            time.sleep(1)
                            # Check URL Change
                            try:
                                if self.driver.current_url != current_url_before_click:
                                    url_changed = True
                                    print(f"   [Step 0] URL Changed to: {self.driver.current_url}")
                                    break
                            except: pass
                            
                            # Check for specific error message in body
                            try:
                                body_src = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                                # "Create a new password that isn't your current password"
                                # "Tạo mật khẩu mới không trùng với mật khẩu hiện tại"
                                if "isn't your current password" in body_src or "không trùng với mật khẩu hiện tại" in body_src:
                                    print("   [Step 0] DETECTED: New password is same as current password.")
                                    is_old_pass_error = True
                                    break
                            except: pass
                
                if is_old_pass_error:
                    print("   [Step 0] Handling 'Same Password' error...")
                    
                    # [FIX] Re-locate elements to avoid StaleElementReferenceException
                    pass_input = None
                    verify_input = None
                    try:
                        print("   [Step 0] Re-locating input fields...")
                        pass_input = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[data-testid="new-password-field"]')))
                        try:
                            verify_input = WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[data-testid="verify-password-field"]')))
                        except: verify_input = None
                    except Exception as e:
                        print(f"   [Step 0] Failed to re-locate inputs: {e}")
                        # If pass_input failed, we try generic
                        if not pass_input:
                             try:
                                pis = self.driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
                                if pis: pass_input = pis[0] 
                                if len(pis) > 1: verify_input = pis[1]
                             except: pass
                        
                        if not pass_input:
                            return "FAIL_RELOCATE_INPUTS", None, None

                    # 1. Clear inputs
                    try:
                        pass_input.clear()
                        if verify_input: verify_input.clear()
                    except: pass
                    time.sleep(1)
                    
                    # 2. Adjusted Pass = gmx_pass + "@" (theo yêu cầu)
                    # new_password ở đây là gmx_pass
                    adjusted_pass = new_password + "@"
                    print(f"   [Step 0] Retrying with adjusted password: {adjusted_pass}")
                    
                    pass_input.send_keys(adjusted_pass)
                    time.sleep(0.5)
                    if verify_input:
                        verify_input.send_keys(adjusted_pass)
                        time.sleep(0.5)
                    
                    # Click reset again with optimized logic
                    print("   [Step 0] Clicking Reset button (Retry)...")
                    try:
                        # 1. Try finding by generic submit first (most reliable for forms)
                        reset_btn = None
                        try:
                            reset_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                        except: pass
                        
                        # 2. Try generic button with text if submit not found
                        if not reset_btn:
                             # Uses JS to find button more robustly by text content
                             reset_btn = self.driver.execute_script("""
                                var buttons = document.querySelectorAll('button, div[role="button"]');
                                for (var i = 0; i < buttons.length; i++) {
                                    var t = buttons[i].innerText.toLowerCase();
                                    if ((t.includes('reset') || t.includes('change') || t.includes('lưu') || t.includes('đặt lại')) && buttons[i].offsetParent !== null) {
                                        return buttons[i];
                                    }
                                }
                                return null;
                             """)

                        if reset_btn:
                            try:
                                reset_btn.click()
                            except:
                                self.driver.execute_script("arguments[0].click();", reset_btn)
                            print("   [Step 0] Clicked Reset button.")
                        else:
                            print("   [Step 0] Reset button not found for retry. Using input.submit()")
                            pass_input.submit()
                    except Exception as e:
                        print(f"   [Step 0] Error clicking retry button: {e}")
                        try: pass_input.submit()
                        except: pass
                    
                    # Wait for success again (Wait 15s and check URL change)
                    print("   [Step 0] Waiting up to 15s for result after retry...")
                    retry_success = False
                    
                    start_wait = time.time()
                    while time.time() - start_wait < 15:
                        # Check URL Change
                        try:
                            if self.driver.current_url != current_url_before_click:
                                retry_success = True
                                print(f"   [Step 0] Retry URL Changed to: {self.driver.current_url}")
                                break
                        except: pass
                        
                        # Check "Something went wrong" or other errors
                        try:
                            body_txt = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                            if "sorry, something went wrong" in body_txt or "lỗi" in body_txt:
                                # Keep waiting or break? Usually fatal.
                                pass
                        except: pass
                        
                        time.sleep(1)
                    
                    if not retry_success:
                        print("   [Step 0] Retry timeout (15s). URL did not change.")
                        # Could return FAIL here, but maybe it just loaded slow or stayed on page?
                        # User said "rồi mới trả lỗi" -> imply return error if not success.
                        return "FAIL_RETRY_TIMEOUT", None, None

                    # Disable Mobile Emulation (Restore PC View via CDP, không đổi kích thước OS)
                    try:
                        self.driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                            "width": pc_width, "height": pc_height,
                            "deviceScaleFactor": 1, "mobile": False
                        })
                        self.driver.execute_cdp_cmd("Emulation.setUserAgentOverride", {"userAgent": ""})
                        self.driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
                        print(f"   [Step 0] Restored PC Mode ({pc_width}x{pc_height}) via CDP.")
                    except: pass
                    
                    # Return tuple with FINAL_PASSWORD adjusted
                    return "SUCCESS_WITH_ADJUSTED_PASS", (found_username if found_username else "unknown_user"), full_url, adjusted_pass

                if url_changed:
                    print("   [Step 0] URL Changed - Reset Successful.")
                    
                    # [Step 0] Wait for UI load after URL change
                    print("   [Step 0] Waiting 7s for full page load/UI rendering...")
                    time.sleep(7)

                    # Disable Mobile Emulation (Restore PC View via CDP, không đổi kích thước OS)
                    try:
                        print("   [Step 0] Disabling Mobile Emulation (Switching to PC Mode via CDP)...")
                        self.driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                            "width": pc_width, "height": pc_height,
                            "deviceScaleFactor": 1, "mobile": False
                        })
                        self.driver.execute_cdp_cmd("Emulation.setUserAgentOverride", {"userAgent": ""})
                        self.driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
                        print(f"   [Step 0] Switched to PC Mode ({pc_width}x{pc_height}) via CDP.")
                    except Exception as e:
                        print(f"   [Step 0] Warning disabling mobile emulation: {e}")

                    # Step 2 will continue in this tab
                    # Return tuple: (Status, FoundUser, Link, NEW_PASSWORD)
                    # For normal success, NEW_PASSWORD = None (use original new_password)
                    return "SUCCESS", (found_username if found_username else "unknown_user"), full_url, None
            else:
                 print(f"   [Step 0] CRITICAL: Reset button not found. URL: {self.driver.current_url}")
                 # Tuy nhiên, ta thử tìm input rồi submit form
                 try:
                     pass_input.submit()
                     print("   [Step 0] Submitted via input.submit() fallback.")
                 except Exception as e_submit:
                     print(f"   [Step 0] Fallback submit failed: {e_submit}")
                     return "FAIL_RESET_BTN_NOT_FOUND", None, None

            time.sleep(5)

            # # [NEW] Check for "Add Your Birthday" (Thêm ngày sinh) page
            # # Dấu hiệu nhận biết: text "Add Your Birthday" hoặc input[name="birthday"]
            # # Nếu gặp trang này -> coi như đổi pass thành công -> done Step 0
            # print("   [Step 0] Checking for 'Add Your Birthday' redirection...")
            # body_text_check = ""
            # try:
            #     body_text_check = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            # except: pass
            
            # if "add your birthday" in body_text_check or "thêm ngày sinh" in body_text_check:
            #     print("   [Step 0] 'Add Your Birthday' page detected. Reset Success!")
            #     try:
            #         self.driver.close()
            #     except: pass

            #     try:
            #         self.driver.execute_script("window.open('https://www.instagram.com/','_blank');")
            #         self.driver.switch_to.window(self.driver.window_handles[-1])
            #         time.sleep(3)
            #     except Exception as e:
            #         print(f"   [Step 0] Failed to open new tab for Birthday flow: {e}")
            #         try:
            #             if 'current_window' in locals() and current_window in self.driver.window_handles:
            #                 self.driver.switch_to.window(current_window)
            #                 self.driver.get("https://www.instagram.com/")
            #                 time.sleep(3)
            #         except: pass

            #     return "SUCCESS", found_username, full_url

            # 6. Check Checkpoint Mail (verify code)
            # Selector: input[aria-label="Enter code"]
            print("   [Step 0] Checking for mail verification checkpoint...")
            
            code_input = wait_element(self.driver, By.CSS_SELECTOR, 'input[aria-label="Enter code"]', timeout=10)
            if code_input:
                print("   [Step 0] Checkpoint detected. Getting code from mail...")
                # Lấy code
                # Target username cho get_verify_code_v2 chưa chắc chắn vì đang ở url reset pass
                # Nhưng logic get_verify... cần user. Tuy nhiên verify code thường gửi về email gốc.
                # get_verify_code_v2(gmx_user, gmx_pass, target_ig_username, target_email=None)
                # Ta có thể truyền gmx_user làm target_email filter nếu cần
                
                # Cần IG username? verify_account_live trả về USER=...
                # Parse lại result để lấy user
                user_match = re.search(r'USER=([^|]+)', result)
                ig_username = user_match.group(1) if user_match else ""
                
                code = get_verify_code_v2(gmx_user, gmx_pass, ig_username, target_email=None) # target_email=None -> check all
                
                if code:
                    print(f"   [Step 0] Found code: {code}. Entering...")
                    code_input.send_keys(code)
                    time.sleep(1)
                    
                    # Click Continue/Confirm
                    # Tìm button Continue
                    continue_btn = None
                    buttons = self.driver.find_elements(By.TAG_NAME, "button")
                    for btn in buttons:
                        if "continue" in btn.text.lower() or "tiếp tục" in btn.text.lower() or "confirm" in btn.text.lower():
                            continue_btn = btn
                            break
                    
                    if continue_btn:
                        continue_btn.click()
                    else:
                        print("   [Step 0] Continue button not found, trying generic submit...")
                        # Thử enter hoặc tìm form submit
                        code_input.submit()
                        
                    time.sleep(3) # Chờ load sau khi submit code
                else:
                    print("   [Step 0] Code not found in mail.")
                    # Có thể return FAIL hoặc để nó chạy tiếp sang Step 2 check status
            
            # 7. Check final state
            # Mở lại tab mới -> instagram.com (Hoặc dùng luôn tab hiện tại)
            # Theo yêu cầu: "mở tab mới, truy cập instagram.com -> chạy step2"
            
            # Ta đóng tab reset pass đi cho gọn
            # self.driver.close() # Giữ lại để debug nếu cần, nhưng theo luồng thì nên chuyển
            
            # Switch confirm
            print("   [Step 0] Reset flow completed. Preparing to switch to Step 2.")
            try:
                self.driver.close() # Close mobile/reset tab
            except: pass
        
            # Trả về cả link full
            return "SUCCESS", found_username, full_url # Báo hiệu đã xong Step 0 thành công -> Skip Step 1

        except Exception as e_step0:
            import traceback
            print(f"   [Step 0] Unhandled exception: {e_step0}")
            print(f"   [Step 0] Traceback: {traceback.format_exc()}")
            try:
                self.driver.close()
                self.driver.switch_to.window(current_window)
            except: pass
            return "FAIL_EXCEPTION", None, None

