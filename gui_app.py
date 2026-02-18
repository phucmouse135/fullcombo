import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import time
import csv
import os
import math  # [NEW] Import math để tính toán chia lưới màn hình

# --- IMPORT MODULES ---
from config_utils import get_driver
from step1_login import InstagramLoginStep
from step2_exceptions import InstagramExceptionStep
from step3_post_login import InstagramPostLoginStep
from step4_2fa import Instagram2FAStep
from step0_reset_pass import InstagramResetPasswordStep
from step5_confirm import InstagramStep5Confirm
# ----------------------

class AutomationGUI:
    def _on_password_changed(self, username, new_password):
        """
        Callback này sẽ được gọi khi đổi mật khẩu thành công.
        Tìm dòng có username, cập nhật cột mật khẩu (index 1) trên treeview.
        """
        for item_id in self.tree.get_children():
            vals = self.tree.item(item_id, "values")
            if str(vals[0]) == str(username):
                self.update_tree_item(item_id, {1: new_password})
                break

    def __init__(self, root):
        self.root = root
        self.root.title("Instagram Automation Tool Pro")
        self.root.geometry("1280x720")
        
        # Variables
        self.file_path_var = tk.StringVar()
        self.thread_count_var = tk.IntVar(value=10)   # Mặc định 10 luồng để test chia màn hình
        self.headless_var = tk.BooleanVar(value=False) # Mặc định False để hiện trình duyệt
        self.status_var = tk.StringVar(value="Ready")
        
        # Stats
        self.total_count = 0
        self.processed_count = 0
        self.success_count = 0
        self.fail_count = 0
        
        # Control Flags
        self.is_running = False
        self.stop_event = threading.Event()
        self.msg_queue = queue.Queue()
        
        # [NEW] Queue quản lý vị trí cửa sổ (Slot ID)
        self.window_slots = queue.Queue()

        # Callback: cập nhật mật khẩu mới lên GUI khi đổi pass thành công
        self.on_password_changed = self._on_password_changed
    
        # --- CẤU HÌNH CỘT (INDEX 0 -> 9) ---
        self.columns = (
            "user",          # 0
            "pass",          # 1
            "2fa",           # 2
            "origin_mail",   # 3
            "pass_mail",     # 4
            "post",          # 5
            "followers",     # 6
            "following",     # 7
            "cookie",        # 8
            "note"           # 9
        )
        
        self.setup_ui()
        self.process_queue()

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Treeview", rowheight=25)
        style.map('Treeview', background=[('selected', '#3498db')])

        # TOP FRAME
        top_frame = ttk.LabelFrame(self.root, text="Configuration & Input", padding=10)
        top_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(top_frame, text="Input File (.txt):").grid(row=0, column=0, sticky="w")
        ttk.Entry(top_frame, textvariable=self.file_path_var, width=50).grid(row=0, column=1, padx=5)
        ttk.Button(top_frame, text="Browse", command=self.browse_file).grid(row=0, column=2, padx=5)
        ttk.Button(top_frame, text="Reload Data", command=self.reload_data).grid(row=0, column=3, padx=5)
        ttk.Button(top_frame, text="Manual Input", command=self.open_manual_input).grid(row=0, column=4, padx=5)

        ttk.Label(top_frame, text="Threads:").grid(row=1, column=0, sticky="w", pady=10)
        tk.Spinbox(top_frame, from_=1, to=50, textvariable=self.thread_count_var, width=5).grid(row=1, column=1, sticky="w", padx=5)
        ttk.Checkbutton(top_frame, text="Run Headless (Hidden)", variable=self.headless_var).grid(row=1, column=1, sticky="e", padx=5)

        self.btn_start = ttk.Button(top_frame, text="START", command=self.start_automation, width=15)
        self.btn_start.grid(row=1, column=3, padx=5)
        self.btn_stop = ttk.Button(top_frame, text="STOP", command=self.stop_automation, state="disabled", width=15)
        self.btn_stop.grid(row=1, column=4, padx=5)

        # STATS FRAME
        stats_frame = ttk.Frame(self.root)
        stats_frame.pack(fill="x", padx=10)
        self.lbl_progress = ttk.Label(stats_frame, text="Progress: 0/0", font=("Arial", 10, "bold"))
        self.lbl_progress.pack(side="left", padx=10)
        self.lbl_success = ttk.Label(stats_frame, text="Success: 0", foreground="green", font=("Arial", 10, "bold"))
        self.lbl_success.pack(side="left", padx=10)
        self.lbl_status = ttk.Label(stats_frame, textvariable=self.status_var, foreground="blue")
        self.lbl_status.pack(side="right", padx=10)

        # TABLE FRAME
        table_frame = ttk.Frame(self.root)
        table_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        y_scroll = ttk.Scrollbar(table_frame, orient="vertical")
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal")
        
        self.tree = ttk.Treeview(table_frame, columns=self.columns, show="headings", 
                                 yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set, selectmode="extended")
        
        y_scroll.config(command=self.tree.yview); y_scroll.pack(side="right", fill="y")
        x_scroll.config(command=self.tree.xview); x_scroll.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)

        # Headers & Widths
        headers = {
            "user": "USER", "pass": "PASS_IG", "2fa": "2FA",
            "origin_mail": "PHÔI_GỐC", "pass_mail": "PASS_MAIL",
            "post": "Post", "followers": "Followers", "following": "Following",
            "cookie": "COOKIE", "note": "NOTE"
        }
        col_width = {
            "user": 100, "pass": 80, 
            "2fa": 150, "origin_mail": 150, "pass_mail": 80, 
            "post": 50, "followers": 60, "following": 60, "cookie": 100, "note": 100
        }
        for col in self.columns:
            self.tree.heading(col, text=headers.get(col, col))
            self.tree.column(col, width=col_width.get(col, 100), minwidth=50)

        self.tree.tag_configure("success", background="#d4edda")
        self.tree.tag_configure("error", background="#f8d7da")
        self.tree.tag_configure("running", background="#fff3cd")

        # Context Menu
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Copy Cell Value", command=self.copy_cell_value)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Delete Selected Rows", command=self.delete_selected_rows)
        self.tree.bind("<Button-3>", self.show_context_menu)

        # BOTTOM FRAME
        bottom_frame = ttk.LabelFrame(self.root, text="Data Operations", padding=10)
        bottom_frame.pack(fill="x", padx=10, pady=5)
        ttk.Button(bottom_frame, text="Delete Selected", command=self.delete_selected_rows).pack(side="left", padx=5)
        ttk.Button(bottom_frame, text="Clear All", command=self.clear_all_data).pack(side="left", padx=5)
        ttk.Separator(bottom_frame, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(bottom_frame, text="Export Success", command=lambda: self.export_data("success")).pack(side="left", padx=5)
        ttk.Button(bottom_frame, text="Export 2FA Errors", command=lambda: self.export_data("2fa_errors")).pack(side="left", padx=5)
        ttk.Button(bottom_frame, text="Export Failed", command=lambda: self.export_data("failed")).pack(side="left", padx=5)
        ttk.Button(bottom_frame, text="Export No Success", command=lambda: self.export_data("no_success")).pack(side="left", padx=5)
        ttk.Button(bottom_frame, text="Export All", command=lambda: self.export_data("all")).pack(side="left", padx=5)

    # --- [NEW] HÀM TÍNH TOÁN VỊ TRÍ CỬA SỔ (GRID LAYOUT) ---
    def calculate_window_rect(self, slot_id, total_slots):
        """
        Tính toán x, y, width, height dựa trên Slot ID và kích thước màn hình.
        Chia màn hình theo chiều ngang, giữ nguyên chiều dọc để xếp các cửa sổ Chrome.
        """
        try:
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight() - 50 # Trừ thanh Taskbar
            
            # Giữ nguyên chiều dọc, chia theo chiều ngang
            rows = 1
            cols = total_slots
            
            win_w = int(screen_width / cols)
            win_h = screen_height  # Giữ nguyên chiều cao màn hình
            
            # Tính tọa độ
            curr_row = 0  # Luôn ở hàng đầu
            curr_col = slot_id % cols
            
            x = curr_col * win_w
            y = 0
            
            return (x, y, win_w, win_h)
        except:
            return None

    # --- PROCESS LOGIC (ĐÃ CẬP NHẬT WINDOW RECT) ---
    def process_single_account(self, item_id, window_rect=None):
        import time
        import shutil
        start_time = time.time()
        elapsed = 0  # Initialize elapsed time
        values = list(self.tree.item(item_id)['values'])
        acc = {
            "uid": str(values[0]), "linked_mail": values[3], "username": values[0],
            "password": values[1], "gmx_user": values[3], "gmx_pass": values[4]
        }
        self.msg_queue.put(("UPDATE_STATUS", (item_id, "", "running")))
        
        # Create unique user data directory for this thread/account
        current_dir = os.path.dirname(os.path.abspath(__file__))
        user_data_dir = os.path.join(current_dir, "temp_profiles", f"profile_{acc['username']}_{int(time.time())}")
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir, exist_ok=True)

        # Single driver creation with retry on creation failure only
        max_driver_retries = 3
        driver = None
        
        for driver_attempt in range(max_driver_retries):
            try:
                print(f"   [Driver] Attempt {driver_attempt + 1}/{max_driver_retries} to create Chrome driver...")
                driver = get_driver(headless=self.headless_var.get(), window_rect=window_rect, user_data_dir=user_data_dir)
                print("   [Driver] Chrome driver created successfully")
                
                # Check for data: URL error and redirect
                try:
                    current_url = driver.current_url
                    if current_url == "data:," or current_url.startswith("data:"):
                        print("   [Driver] Detected data: URL error, redirecting to Instagram...")
                        driver.get("https://www.instagram.com/")
                        time.sleep(2)
                except Exception as url_check_e:
                    print(f"   [Driver] Error checking URL: {url_check_e}")
                
                break  # Success, exit retry loop
            except Exception as driver_error:
                print(f"   [Driver] Failed to create Chrome driver (attempt {driver_attempt + 1}): {driver_error}")
                if driver_attempt < max_driver_retries - 1:
                    print("   [Driver] Retrying in 3 seconds...")
                    time.sleep(3)
                    continue
                else:
                    # All retries failed
                    end_time = time.time()
                    elapsed = end_time - start_time
                    note_time = f"Chrome Crash in {elapsed:.1f}s"
                    self.msg_queue.put(("FAIL_CRITICAL", (item_id, f"Chrome driver failed after {max_driver_retries} attempts: {str(driver_error)}", note_time)))
                    return
        
        # Main process - no retry loop for application errors
        try:


            # --- START STEP 0: RESET PASSWORD FIRST ---
            # Call Step 0 -> Get status & link
            step0 = InstagramResetPasswordStep(driver)
            full_step0_link = ""
            found_username = None
            
            # Theo yêu cầu: "Tiến hành điền password(password cột password mail) vào các ô input"
            new_pass_for_reset = acc['gmx_pass'] 
            
            # Update: Step 0 now returns (status, username, full_link)
            step0_status = "FAIL_UNKNOWN"
            try:
                 result_tuple = step0.process_reset_password(acc['gmx_user'], acc['gmx_pass'], new_pass_for_reset)
                 if isinstance(result_tuple, tuple):
                     step0_status, found_username, full_step0_link = result_tuple
                 else:
                     step0_status = result_tuple
            except Exception as e:
                 print(f"   [Step 0] Exception calling process: {e}")
                 step0_status = "SKIP_STEP0"

            status = "FAIL_UNKNOWN" # Default status
            
            if step0_status == "SUCCESS":
                print(f"   [Step 0] SUCCESS. Skipping Step 1 Login.")
                
                # Cập nhật username nếu tìm thấy từ mail
                if found_username and found_username != "unknown_user":
                    print(f"   [Main] Updating username from mail: {found_username}")
                    acc['username'] = found_username
                    # Cập nhật cột User (index 0)
                    self.update_tree_item(item_id, {0: found_username})

                # Cập nhật pass mới vào cây GUI và biến acc
                self._on_password_changed(acc['username'], new_pass_for_reset)
                acc['password'] = new_pass_for_reset
                
                # Giả lập status thành công để vào Step 2 check lại
                status = "LOGGED_IN_SUCCESS"
                
                # Step 0 đã redirect/load instagram.com ở tab hiện tại (PC mode)
                # Không cần mở tab mới hay làm gì thêm

            elif step0_status == "FAIL_MAIL_NOT_FOUND":
                print(f"   [Step 0] Failed: Reset Mail Not Found. Aborting case.")
                end_time = time.time()
                elapsed = end_time - start_time
                note_time = f"Mail Not Found in {elapsed:.1f}s"
                self.msg_queue.put(("FAIL_CRITICAL", (item_id, "Reset Mail Not Found", note_time)))
                if driver: driver.quit()
                return

            else:
                # Step 0 skip hoặc fail nhẹ -> chạy Step 1 Login bình thường
                if step0_status != "SKIP_STEP0":
                    print(f"   [Step 0] Failed ({step0_status}). Fallback to Step 1 Login.")
                else:
                    print(f"   [Step 0] Skipped. Proceeding to Step 1 Login.")
                
                # Step 1: Login
                step1 = InstagramLoginStep(driver)
                # step1.load_base_cookies("Wed New Instgram  2026 .json")
                print("   [Step 1] Loading base cookies...")
                driver.get("https://www.instagram.com/")
                time.sleep(1)
                print("   [Step 1] Logging in...")
                status = step1.perform_login(acc['username'], acc['password'])
                if "FAIL" in status:
                    end_time = time.time()
                    elapsed = end_time - start_time
                    note_time = f"Failed in {elapsed:.1f}s"
                    self.msg_queue.put(("FAIL_CRITICAL", (item_id, status, note_time)))
                    return
                time.sleep(2)  # Chờ ổn định trang sau login
            
            # Step 2: Handle Exception (Common for both flows)
            step2 = InstagramExceptionStep(driver)
            # Truyền callback cập nhật mật khẩu cho step2
            step2.on_password_changed = self.on_password_changed
            final_status = step2.handle_status(status, acc['username'], acc['gmx_user'], acc['gmx_pass'], acc['linked_mail'], acc['password'])
            
            # Check if password was changed and login needs to restart
            if final_status == "RESTART_LOGIN":
                print(f"   [Main] Password changed, restarting login process for {acc['username']}...")
                # Get the updated password from the treeview (updated by callback)
                values = list(self.tree.item(item_id)['values'])
                updated_password = values[3]  # Password is at index 3
                acc['password'] = updated_password  # Update the acc dictionary
                # Restart login with new password
                status = step1.perform_login(acc['username'], updated_password)
                if "FAIL" in status:
                    end_time = time.time()
                    elapsed = end_time - start_time
                    note_time = f"Failed in {elapsed:.1f}s"
                    self.msg_queue.put(("FAIL_CRITICAL", (item_id, status, note_time)))
                    return
                time.sleep(2)  # Chờ ổn định trang sau login
                
                # Handle exceptions again with new password
                final_status = step2.handle_status(status, acc['username'], acc['gmx_user'], acc['gmx_pass'], acc['linked_mail'], updated_password)
            
            # Check if final status indicates success before proceeding to step 3
            success_statuses = [
                "LOGGED_IN_SUCCESS", "COOKIE_CONSENT", "TERMS_AGREEMENT", 
                "NEW_MESSAGING_TAB", "SUCCESS"
            ]
            if final_status not in success_statuses:
                end_time = time.time()
                elapsed = end_time - start_time
                note_time = f"Failed in {elapsed:.1f}s"
                self.msg_queue.put(("FAIL_CRITICAL", (item_id, f"Failed after restart: {final_status}", note_time)))
                return
            
            # [NEW] Kiểm tra lại status sau 5 giây để đảm bảo session không bị logout
            print("   [Main] Waiting 5 seconds to verify session stability...")
            time.sleep(5)
            # Re-check status
            step2.driver = driver # Ensure step2 driver is active
            recheck_status = step2._check_verification_result()
            
            if recheck_status not in success_statuses:
                print(f"   [Main] Session unstable after 5s: {recheck_status}")
                end_time = time.time()
                elapsed = end_time - start_time
                note_time = f"Session unstable in {elapsed:.1f}s"
                # Updated to use actual status instead of hardcoded "LOGOUT AFTER LOGIN"
                self.msg_queue.put(("FAIL_CRITICAL", (item_id, f"{recheck_status}", note_time)))
                return
            
            # Step 3: Crawl in new tab
            # Open new tab for step 3
            driver.execute_script("window.open('https://www.instagram.com/');")
            windows = driver.window_handles
            main_window = windows[0]
            new_window = windows[-1]
            driver.switch_to.window(new_window)
            
            step3 = InstagramPostLoginStep(driver)
            max_step3_retries = 3
            data = None
            for step3_attempt in range(max_step3_retries):
                try:
                    data = step3.process_post_login(acc['username'])
                    # Check if we got valid data
                    if data and data.get('cookie') and data.get('cookie') != '':
                        break  # Success
                    else:
                        print(f"   [Step 3] Attempt {step3_attempt + 1} failed - no cookie, retrying...")
                        if step3_attempt < max_step3_retries - 1:
                            time.sleep(3)
                except Exception as e:
                    print(f"   [Step 3] Attempt {step3_attempt + 1} error: {e}")
                    if step3_attempt < max_step3_retries - 1:
                        time.sleep(3)
                    else:
                        data = None
            
            if not data or not data.get('cookie') or data.get('cookie') == '':
                end_time = time.time()
                elapsed = end_time - start_time
                note_time = f"Failed to access profile in {elapsed:.1f}s"
                self.msg_queue.put(("FAIL_CRITICAL", (item_id, "Profile access failed after retries - no data crawled", note_time)))
                # Close new tab and switch back
                driver.close()
                driver.switch_to.window(main_window)
                return
            
            # Gửi Cookie và Data về GUI
            self.msg_queue.put(("UPDATE_CRAWL", (item_id, {
                "posts": data.get('posts', '0'),
                "followers": data.get('followers', '0'),
                "following": data.get('following', '0'),
                "cookie": data.get('cookie', '')
            })))
            
            # Đánh dấu Success ở cột NOTE sau khi crawl thành công
            self.msg_queue.put(("STEP3_SUCCESS", item_id))
            
            # Close new tab and switch back to main
            driver.close()
            driver.switch_to.window(main_window)
            
            key = ""
            step4_started = False  # Flag to track if step 4 has started
            try:
                # Step 4: 2FA
                step4_started = True  # Mark that step 4 has started
                step4 = Instagram2FAStep(driver)
                # Truyền callback để cập nhật Secret Key vào cột 2FA ngay khi lấy được
                def on_secret_key_found(secret_key):
                    self.msg_queue.put(("UPDATE_STATUS", (item_id, secret_key, None)))
                step4.on_secret_key_found = on_secret_key_found
                key = step4.setup_2fa(acc['gmx_user'], acc['gmx_pass'], acc['username'], acc['linked_mail'])
                
                # Check 2FA Error
                if "ERROR_2FA" in key:
                    end_time = time.time()
                    elapsed = end_time - start_time
                    note_time = f"Failed in {elapsed:.1f}s"
                    self.msg_queue.put(("FAIL_2FA", (item_id, key, note_time)))
                    return

                # --- STEP 5: CONFIRM FLOW (Full Link) ---
                # Chỉ chạy Step 5 nếu có 2FA thành công và có Link Full từ Step 0
                if full_step0_link:
                    step5 = InstagramStep5Confirm(driver)
                    print(f"   [Step 5] Starting confirm flow with password: {acc['password']}")
                    step5_res = step5.process_confirm_flow(full_step0_link, acc['password'], acc['gmx_user'], acc['gmx_pass'])
                    
                    if "SUCCESS_STEP5" in step5_res:
                        print("   [Step 5] Confirmation SUCCESS.")
                    else:
                        print(f"   [Step 5] Finished with status: {step5_res}. Proceeding to success.")
                        # Vẫn coi là thành công vì 2FA đã lấy được, Step 5 là check thêm?
                        # Yêu cầu: "chỉnh sửa điều kiện success -> chạy thành công step 5"
                        # Nếu step 5 fail thì sao? User nói "chỉnh sửa điều kiện success -> chạy thành công step 5"
                        # Nghĩa là phải done step 5 mới tính là Success?
                        # Nếu chỉ check 2FA login thì coi như OK.
                        pass
                else:
                    print("   [Step 5] Skipped because full_step0_link is missing.")

                # Always use the original format for 2FA key
                key_raw = getattr(step4, 'last_secret_key_raw', key)
                end_time = time.time()
                elapsed = end_time - start_time
                note_time = f"Done in {elapsed:.1f}s"
                
                # Success
                self.msg_queue.put(("SUCCESS", (item_id, key_raw, note_time)))

            except Exception as e:
                # Handle step 4/5 specific errors
                end_time = time.time()
                elapsed = end_time - start_time
                note_time = f"Failed in {elapsed:.1f}s"
                msg = str(e).replace("STOP_FLOW_", "")
                # This is a step 4/5 error
                self.msg_queue.put(("FAIL_2FA", (item_id, msg, note_time)))
                return  # Exit the function after handling step 4 error
        except Exception as e:
            error_msg = str(e)
            end_time = time.time()
            elapsed = end_time - start_time
            note_time = f"Failed in {elapsed:.1f}s"
            msg = str(e).replace("STOP_FLOW_", "")
            # This catches step 1-3 errors (step 4 errors are handled in inner try-except)
            self.msg_queue.put(("FAIL_CRITICAL", (item_id, msg, note_time)))
        finally:
            print(f"[TIME] Case {acc['username']} finished in {elapsed:.2f} seconds.")
            if driver: 
                try: 
                    driver.quit()
                except: 
                    pass
            
            # Clean up user data directory
            try:
                if os.path.exists(user_data_dir):
                    time.sleep(1) # Give Chrome a moment to fully release locks
                    shutil.rmtree(user_data_dir, ignore_errors=True)
                    print(f"   [Cleanup] Removed temporary profile: {user_data_dir}")
            except Exception as e:
                print(f"   [Cleanup] Error removing {user_data_dir}: {e}")

    # --- THREAD MANAGER (ĐÃ CẬP NHẬT SLOT MANAGEMENT) ---
    def thread_manager(self, items, n_threads):
        task_queue = queue.Queue()
        for i in items: task_queue.put(i)
        
        # [NEW] Khởi tạo các slot hiển thị (0, 1, 2, ... n-1)
        self.window_slots = queue.Queue()
        for i in range(n_threads):
            self.window_slots.put(i)

        def worker():
            while not self.stop_event.is_set():
                try:
                    # 1. Lấy Account cần chạy
                    item_id = task_queue.get(timeout=1)
                    
                    # 2. Lấy Slot hiển thị (để tính tọa độ cửa sổ)
                    # Nếu hết slot (đang full luồng), nó sẽ chờ ở đây
                    slot_id = self.window_slots.get() 
                    
                    # 3. Tính toán Rect (x, y, w, h)
                    rect = self.calculate_window_rect(slot_id, n_threads)
                    
                    # 4. Chạy
                    self.process_single_account(item_id, window_rect=rect)
                    
                    # 5. Xong việc -> Trả lại Slot ID cho luồng khác dùng
                    self.window_slots.put(slot_id)
                    task_queue.task_done()
                    
                except queue.Empty:
                    break
                except Exception as e:
                    print(f"Worker Error: {e}")
                    # Đảm bảo không bị mất slot nếu lỗi xảy ra ở bước lấy slot
                    self.window_slots.put(slot_id)
                    pass
                
                if not self.is_running: break
        
        # Khởi tạo Threads
        threads = []
        for _ in range(n_threads):
            t = threading.Thread(target=worker, daemon=True)
            t.start()
            threads.append(t)

        for t in threads: t.join()
        self.msg_queue.put(("ALL_DONE", None))

    # --- CÁC HÀM KHÁC (GIỮ NGUYÊN) ---
    def start_automation(self):
        items = self.tree.get_children()
        # Lấy các item Pending
        pending_items = []
        for i in items:
            vals = self.tree.item(i)['values']
            if vals[-1] == "Pending":
                twofa_val = str(vals[2]).strip()
                if twofa_val == "" or "ERROR_2FA" in twofa_val:
                    pending_items.append(i)
                else:
                    # Nếu 2FA đã có, đánh dấu success luôn
                    note_time = "Skipped (2FA exists)"
                    self.update_tree_item(i, {9: f"Success | {note_time}"}, "success")
                    self.success_count += 1
                    self.write_result_to_output(i, result_type="success")
        if not pending_items:
            messagebox.showinfo("Info", "No 'Pending' items to process.")
            self.update_stats_label()
            return

        self.is_running = True
        self.stop_event.clear()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal", text="STOP")
        self.status_var.set("Running...")
        self.processed_count = 0
        self.fail_count = 0
        self.lbl_success.config(text=f"Success: {self.success_count}")
        num_threads = self.thread_count_var.get()
        threading.Thread(target=self.thread_manager, args=(pending_items, num_threads), daemon=True).start()

    def stop_automation(self):
        if messagebox.askyesno("Confirm", "Stop automation process?"):
            self.is_running = False
            self.stop_event.set()
            self.btn_stop.config(text="Stopping...", state="disabled")
            self.status_var.set("Stopping...")

    def process_queue(self):
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                
                if msg_type == "UPDATE_STATUS":
                    item_id, secret_key, tag = data
                    # Cập nhật Secret Key trực tiếp vào cột 2FA (2) ngay khi lấy được
                    self.update_tree_item(item_id, {2: secret_key}, tag)
                
                elif msg_type == "UPDATE_CRAWL":
                    item_id, info = data
                    # Cập nhật Post(5), Follow(6), Following(7), Cookie(8)
                    self.update_tree_item(item_id, {
                        5: info['posts'], 
                        6: info['followers'], 
                        7: info['following'],
                        8: info['cookie']
                    }, "success")
                
                elif msg_type == "STEP3_SUCCESS":
                    item_id = data
                    # Đánh dấu success ở cột NOTE (9)
                    self.update_tree_item(item_id, {9: "success"}, "success")
                
                elif msg_type == "SUCCESS":
                    item_id, key, note_time = data
                    self.success_count += 1
                    self.processed_count += 1
                    # Cập nhật Key 2FA(2), Note(9) với 2FA Success
                    self.update_tree_item(item_id, {2: key, 9: f"2FA Success | {note_time}"}, "success")
                    self.update_stats_label()
                    self.write_result_to_output(item_id, result_type="success")
                
                elif msg_type == "FAIL_CRITICAL":
                    item_id, err, note_time = data
                    self.fail_count += 1
                    self.processed_count += 1
                    self.update_tree_item(item_id, {5: err[:60], 9: f"Failed | {note_time}"}, "error") 
                    self.update_stats_label()
                    self.write_result_to_output(item_id, result_type="fail")
                
                elif msg_type == "FAIL_2FA":
                    item_id, err, note_time = data
                    self.fail_count += 1
                    self.processed_count += 1
                    # Put 2FA error in column 2 (2FA column) instead of post column
                    self.update_tree_item(item_id, {2: f"ERROR_2FA: {err[:50]}", 9: f"2FA Failed | {note_time}"}, "error") 
                    self.update_stats_label()
                    self.write_result_to_output(item_id, result_type="2fa")
                
                elif msg_type == "ALL_DONE":
                    self.is_running = False
                    self.btn_start.config(state="normal")
                    self.btn_stop.config(state="disabled", text="STOP")
                    self.status_var.set("Finished")
                    messagebox.showinfo("Done", "Completed!")

        except queue.Empty: pass
        self.root.after(100, self.process_queue)

    def write_result_to_output(self, item_id, result_type="fail"):
        """Write result to appropriate log file based on result type.
        
        Args:
            item_id: Tree item ID
            result_type: "success", "2fa", or "fail"
        """
        try:
            values = self.tree.item(item_id)['values']
            # Không ghi case có ERROR_2FA vào success.txt
            if result_type == "success":
                twofa_val = str(values[2]).strip()
                if twofa_val.startswith("ERROR_2FA"):
                    return  # Không ghi
            
            filename = {
                "success": "success.txt",
                "2fa": "2fa.txt", 
                "fail": "fail.txt"
            }.get(result_type, "fail.txt")
            
            with open(filename, "a", encoding="utf-8") as f:
                row = [str(v) for v in values]
                f.write("\t".join(row) + "\n")
        except Exception as e:
            print(f"Error writing to {filename}: {e}")

    def update_tree_item(self, id, col_map, tag=None):
        try:
            vals = list(self.tree.item(id, "values"))
            for idx, v in col_map.items(): vals[idx] = v
            kw = {"values": vals}
            if tag: kw["tags"] = (tag,)
            self.tree.item(id, **kw)
        except: pass

    def update_stats_label(self):
        self.lbl_progress.config(text=f"Progress: {self.processed_count}/{self.total_count}")
        self.lbl_success.config(text=f"Success: {self.success_count}")

    # --- UI HELPERS (Manual Input, File Browse...) ---
    def open_manual_input(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Manual Input (Tab Separated)")
        dialog.geometry("800x600")
        dialog.minsize(600, 400)
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(side="bottom", fill="x", padx=10, pady=10)
        
        txt_frame = ttk.Frame(dialog)
        txt_frame.pack(side="top", fill="both", expand=True, padx=10, pady=(10, 0))
        
        scroll_y = ttk.Scrollbar(txt_frame)
        scroll_y.pack(side="right", fill="y")
        
        txt_input = tk.Text(txt_frame, wrap="none", yscrollcommand=scroll_y.set)
        txt_input.pack(side="left", fill="both", expand=True)
        scroll_y.config(command=txt_input.yview)
        
        def submit():
            raw_data = txt_input.get("1.0", "end")
            lines = [line for line in raw_data.splitlines() if line.strip()]
            added_count = 0
            
            # Helper to parse lines similar to the reference code
            for line in lines:
                parts = line.split("\t")
                # Fallback: if no tabs found, try splitting by whitespace? 
                # The reference code does: if len(parts) == 1: parts = line.split()
                # But strictly adhering to tab-separated is safer for empty columns.
                # However, let's follow the reference code's logic if that's what's requested.
                if len(parts) == 1 and "\t" not in line:
                     parts = line.split()
                
                parts = [p.strip() for p in parts]
                
                while len(parts) < len(self.columns): 
                    parts.append("")
                
                if len(parts) > len(self.columns):
                    parts = parts[:len(self.columns)]
                
                # Check column 9 (index 9 is NOTE/Status in reference, here it is 'note')
                # But here we set parts[-1] = "Pending" usually.
                # The reference code preserves the note if it exists.
                if not parts[-1]:
                    parts[-1] = "Pending"
                
                self.tree.insert("", "end", values=parts)
                added_count += 1
            
            self.update_stats()
            messagebox.showinfo("Success", f"Added {added_count} accounts.")
            dialog.destroy()

        ttk.Button(btn_frame, text="Submit Data", command=submit).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Clear", command=lambda: txt_input.delete("1.0", "end")).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Close", command=dialog.destroy).pack(side="right", padx=5)
        ttk.Label(btn_frame, text="Paste data from Excel/Text (Tab separated)", font=("Arial", 9, "italic")).pack(side="left")

    def browse_file(self):
        filename = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if filename:
            self.file_path_var.set(filename)
            self.load_data_from_file(filename)

    def reload_data(self):
        path = self.file_path_var.get()
        if path and os.path.exists(path):
            self.load_data_from_file(path)
        else:
            messagebox.showwarning("Warning", "File path is invalid or empty.")

    def load_data_from_file(self, filepath):
        self.clear_all_data(confirm=False)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            lines = [line for line in content.splitlines() if line.strip()]
            for line in lines:
                parts = line.split("\t")
                if len(parts) == 1 and "\t" not in line:
                    parts = line.split()
                
                parts = [p.strip() for p in parts]
                
                while len(parts) < len(self.columns): parts.append("")
                if len(parts) > len(self.columns): parts = parts[:len(self.columns)]
                
                if not parts[-1]:
                    parts[-1] = "Pending"
                    
                self.tree.insert("", "end", values=parts)
            self.update_stats()
        except Exception as e:
            messagebox.showerror("Error", f"Could not load file: {e}")

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if item:
            self.tree.selection_set(item)
            self.selected_cell_col = col 
            self.context_menu.post(event.x_root, event.y_root)

    def copy_cell_value(self):
        try:
            selected_item = self.tree.selection()[0]
            col_idx = int(self.selected_cell_col.replace("#", "")) - 1
            value = self.tree.item(selected_item)['values'][col_idx]
            self.root.clipboard_clear()
            self.root.clipboard_append(str(value))
        except: pass

    def delete_selected_rows(self):
        selected = self.tree.selection()
        if not selected: return
        if messagebox.askyesno("Confirm", f"Delete {len(selected)} rows?"):
            for item in selected: self.tree.delete(item)
            self.update_stats()

    def clear_all_data(self, confirm=True):
        if confirm and not messagebox.askyesno("Confirm", "Clear ALL data?"): return
        for item in self.tree.get_children(): self.tree.delete(item)
        # Reset all stats when clearing data
        self.success_count = 0
        self.processed_count = 0
        self.fail_count = 0
        self.update_stats()
        self.update_stats_label()

    def update_stats(self):
        items = self.tree.get_children()
        self.total_count = len(items)
        self.lbl_progress.config(text=f"Progress: {self.processed_count}/{self.total_count}")

    def export_data(self, mode):
        filename = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text File", "*.txt")])
        if not filename: return
        count = 0
        with open(filename, "w", encoding="utf-8", newline='') as f:
            writer = csv.writer(f, delimiter='\t')
            for item in self.tree.get_children():
                vals = self.tree.item(item)['values']
                note = vals[-1].lower()
                twofa_val = str(vals[4]).strip()
                should_export = False
                if mode == "all": should_export = True
                elif mode == "success":
                    # Chỉ export success nếu có 2FA key hợp lệ (không phải ERROR_2FA) và đã hoàn thành step4
                    if "success" in note and twofa_val and not twofa_val.startswith("ERROR_2FA"):
                        should_export = True
                elif mode == "2fa_errors" and "error_2fa" in str(vals[2]).lower(): should_export = True
                elif mode == "failed" and ("fail" in note or "error" in note): should_export = True
                elif mode == "no_success" and "success" not in note: should_export = True
                
                if should_export:
                    writer.writerow(vals[:-1])
                    count += 1
        messagebox.showinfo("Export", f"Exported {count} items.")

if __name__ == "__main__":
    root = tk.Tk()
    app = AutomationGUI(root)
    root.mainloop()