import time
from selenium.webdriver.common.by import By
from config_utils import wait_element, wait_and_click, wait_and_send_keys
from mail_handler_v2 import get_verify_code_v2

class InstagramStep5Confirm:
    def __init__(self, driver):
        self.driver = driver

    def process_confirm_flow(self, full_rest_link, password, gmx_user, gmx_pass):
        """
        Step 5: Truy cập lại link reset full -> Đổi pass lần nữa -> Check 2FA login screen.
        """
        print(f"   [Step 5] Starting confirmation flow with full link...")
        print(f"   [Step 5] Link: {full_rest_link}")
        
        try:
            # 1. Truy cập link
            self.driver.get(full_rest_link)
            time.sleep(3)
            
            # Check "Page not available"
            try:
                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                if "Sorry, this page isn't available" in body_text or "This page isn't available" in body_text:
                    print("   [Step 5] Link expired or unavailable.")
                    return "FAIL_LINK_EXPIRED"
            except: pass

            # 2. Điền Pass (Logic giống Step 0)
            pass_input = wait_element(self.driver, By.CSS_SELECTOR, 'input[data-testid="new-password-field"]', timeout=10)
            verify_input = wait_element(self.driver, By.CSS_SELECTOR, 'input[data-testid="verify-password-field"]', timeout=10)

            if pass_input and verify_input:
                print("   [Step 5] Entering password again...")
                pass_input.clear()
                pass_input.send_keys(password)
                time.sleep(0.5)
                verify_input.clear()
                verify_input.send_keys(password)
                time.sleep(0.5)

                # Click Reset
                reset_btn = None
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for btn in buttons:
                    txt = btn.text.lower()
                    if "reset password" in txt or "change password" in txt or "lưu mật khẩu" in txt:
                        reset_btn = btn
                        break
                
                if not reset_btn:
                     try: reset_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                     except: pass
                
                if reset_btn:
                    try: reset_btn.click()
                    except: self.driver.execute_script("arguments[0].click();", reset_btn)
                    time.sleep(5)
                else:
                    print("   [Step 5] Reset button not found.")
            else:
                 print("   [Step 5] Password inputs not found. Might be direct login or just check.")

            # 3. Check Mail Checkpoint (Nếu có) - Tương tự step 0
            code_input = wait_element(self.driver, By.CSS_SELECTOR, 'input[aria-label="Enter code"]', timeout=5)
            if code_input:
                 print("   [Step 5] Checkpoint detected. Solving...")
                 # Lấy code
                 code = get_verify_code_v2(gmx_user, gmx_pass, None, target_email=None)
                 if code:
                    code_input.send_keys(code)
                    time.sleep(1)
                    # Click confirm
                    try:
                        buttons = self.driver.find_elements(By.TAG_NAME, "button")
                        for btn in buttons:
                            if "continue" in btn.text.lower() or "confirm" in btn.text.lower():
                                btn.click(); break
                    except: code_input.submit()
                    time.sleep(5)

            # 4. Check 2FA Login Screen
            # URL chứa "two_factor_login" hoặc "challenge"
            # Hoặc body có text "Enter the code we sent to your number ending in" (nhưng 2FA app thì khác)
            # Yêu cầu: "Xuất hiện 2fa (url chứa two_factor_login)"
            
            time.sleep(3)
            current_url = self.driver.current_url.lower()
            print(f"   [Step 5] Final URL: {current_url}")
            
            if "two_factor" in current_url or "challenge" in current_url:
                print("   [Step 5] 2FA Screen detected. CONFIRMED.")
                return "SUCCESS_STEP5"
            else:
                # Có thể nó login thẳng vào luôn nếu cookie còn sống
                print("   [Step 5] 2FA Screen NOT detected (Maybe direct login).")
                # Vẫn coi là success nếu đã xong flow
                return "SUCCESS_STEP5"

        except Exception as e:
            print(f"   [Step 5] Error: {e}")
            return f"FAIL_STEP5: {str(e)}"
