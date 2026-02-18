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

    def process_reset_password(self, gmx_user, gmx_pass, new_password):
        """
        Thực hiện quy trình lấy link reset -> đổi pass -> checkpoint mail (nếu có).
        Trả về tuple:
          (status, found_username, full_step0_link)
          - status: "SUCCESS", "SKIP_STEP0", "FAIL_..."
          - found_username: username tìm thấy trong mail (hoặc None)
          - full_step0_link: link reset full (hoặc None)
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
            return "SKIP_STEP0", None, None  # Không lấy được mail thì thử login bình thường

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
            return "SKIP_STEP0", None, None
        
        full_url = link_match.group(1)
        print(f"   [Step 0] Found link: {full_url}")
        if found_username:
            print(f"   [Step 0] Found username in mail: {found_username}")

        # 2. Xử lý URL (Regex lấy short link)
        # Pattern: lấy đến hết phần token (trước dấu : nếu có, hoặc hết chuỗi)
        # Ví dụ: ...token=XYZ:one_click... -> ...token=XYZ
        # Logic user yêu cầu: regex lấy link clean để dùng thử trước
        
        # Thử clean url bằng regex: giữ lại phần cơ bản của confirm link
        # https://instagram.com/accounts/password/reset/confirm/?uidb36=...&token=...
        
        clean_url = full_url
        match = re.search(r'(https?://.*?/accounts/password/reset/confirm/\?uidb36=[^&]+&token=[^:&]+)', full_url)
        if match:
            clean_url = match.group(1)
            # URL Decode để đảm bảo sạch sẽ
            clean_url = urllib.parse.unquote(clean_url)
            print(f"   [Step 0] URL Raw Processed: {clean_url}")
        else:
            print("   [Step 0] Could not clean URL, using full URL.")

        # 3. Mở tab mới với giao diện Mobile (Sử dụng CDP command)
        # Bắt buộc phải dùng CDP để set device emulation cho riêng tab này (nếu driver support)
        # Hoặc simpler: set user agent và window size.
        # Tuy nhiên Selenium cơ bản thay đổi cả browser session. 
        # Để an toàn và đơn giản, ta sẽ chỉ thay đổi kích thước cửa sổ cho giống mobile 
        # và hy vọng Instagram responsive sẽ hiển thị giao diện mobile.
        # Nếu muốn devtool mobile chuẩn, phải dùng Chrome DevTools Protocol (CDP).
        
        current_window = self.driver.current_window_handle
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
            
            # If Clean URL failed after 3 attempts, fallback to Full URL
            if not clean_url_success:
                print("   [Step 0] Clean URL failed 3 times (Page N/A or Missing Inputs). Retrying with FULL URL...")
                self.driver.get(full_url)
                time.sleep(5)
                
                # Handle popup again for full url
                try:
                    buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button, div[role="button"]')
                    for b in buttons:
                        if not b.is_displayed(): continue
                        txt = b.text.lower()
                        if 'allow all cookies' in txt or 'chấp nhận' in txt:
                            b.click()
                            break
                except: pass

            # 4. Final Verification
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            if "Sorry, this page isn't available" in body_text or "This page isn't available" in body_text:
                print("   [Step 0] Full URL also invalid (or Clean URL failed and Full URL failed).")
                self.driver.close()
                self.driver.switch_to.window(current_window)
                return "SKIP_STEP0", None, None

            # 5. Entering Password
            # Re-locate elements (because we might have reloaded or switched to full url)
            print("   [Step 0] Entering new password...")
            
            # Use wait_element normally now
            pass_input = wait_element(self.driver, By.CSS_SELECTOR, 'input[data-testid="new-password-field"]', timeout=10)
            verify_input = wait_element(self.driver, By.CSS_SELECTOR, 'input[data-testid="verify-password-field"]', timeout=10)
            
            if not pass_input or not verify_input:
                # Có thể link trỏ thẳng về trang login hoặc trang khác
                print("   [Step 0] Keep inputs not found. Maybe link is instant login or invalid.")
                # Nếu không thấy ô nhập pass, có thể nó đã login luôn (one click login).
                # Check thử xem đã login chưa
                if "instagram.com/accounts/onetap" in self.driver.current_url or "instagram.com/" == self.driver.current_url:
                     print("   [Step 0] Seems like instant login.")
                     return "SUCCESS", found_username, full_url # Coi như thành công, sang Step 2 check lại
                
                self.driver.close()
                self.driver.switch_to.window(current_window)
                return "SKIP_STEP0", None, None

            # Điền pass
            # Pass lấy từ tham số new_password (là pass mail theo yêu cầu)
            pass_input.clear()
            pass_input.send_keys(new_password)
            time.sleep(0.5)
            verify_input.clear()
            verify_input.send_keys(new_password)
            time.sleep(0.5)
            
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
                if current_url_before_click is not None:
                    for _ in range(10):
                        time.sleep(1)
                        try:
                            if self.driver.current_url != current_url_before_click:
                                url_changed = True
                                print(f"   [Step 0] URL Changed to: {self.driver.current_url}")
                                break
                        except:
                            pass

                if url_changed:
                    print("   [Step 0] URL Changed - Reset Successful.")
                    
                    # [Step 0] Wait for UI load after URL change
                    print("   [Step 0] Waiting 7s for full page load/UI rendering...")
                    time.sleep(7)

                    # Disable Mobile Emulation (Restore PC View)
                    try:
                        print("   [Step 0] Disabling Mobile Emulation (Switching to PC Mode)...")
                        self.driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
                        # Clear user agent override (reset to default browser UA)
                        self.driver.execute_cdp_cmd("Emulation.setUserAgentOverride", {"userAgent": ""})
                        
                        # Optionally maximize or set window size for PC
                        try:
                            self.driver.maximize_window()
                        except: pass
                        
                        print("   [Step 0] Switched to PC Mode in current tab.")
                    except Exception as e:
                        print(f"   [Step 0] Warning disabling mobile emulation: {e}")

                    # Step 2 will continue in this tab
                    return "SUCCESS", (found_username if found_username else "unknown_user"), full_url
            else:
                 print("   [Step 0] CRITICAL: Reset button not found. Dumping page source for debug...")
                 # Có thể raise exception để retry outer loop hoặc return SKIP
                 # Tuy nhiên, ta thử tìm input rồi submit form
                 try:
                     pass_input.submit()
                     print("   [Step 0] Submitted via input.submit() fallback.")
                 except: 
                     print("   [Step 0] Fallback submit failed.")
                     return "SKIP_STEP0", None, None

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
                        
                    time.sleep(10) # Chờ load sau khi submit code
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

            # Open a fresh tab for Step 2 at instagram.com
            try:
                self.driver.execute_script("window.open('https://www.instagram.com/','_blank');")
                self.driver.switch_to.window(self.driver.window_handles[-1])
                time.sleep(3)
            except Exception as e:
                print(f"   [Step 0] Failed to open new tab for Step 2: {e}")
                try:
                    if 'current_window' in locals() and current_window in self.driver.window_handles:
                        self.driver.switch_to.window(current_window)
                        self.driver.get("https://www.instagram.com/")
                        time.sleep(3)
                except: pass

            # Trả về cả link full
            return "SUCCESS", found_username, full_url # Báo hiệu đã xong Step 0 thành công -> Skip Step 1

        except Exception as e:
            print(f"   [Step 0] Exception: {e}")
            try:
                self.driver.close()
                self.driver.switch_to.window(current_window)
            except: pass
            return "SKIP_STEP0", None, None

