# mail_handler_v2.py
import imaplib
import email
import re
import time
import socket
import html
from email.header import decode_header
from email.utils import parseaddr

# --- CẤU HÌNH SEZNAM ---
IMAP_SERVER = "imap.seznam.cz"
IMAP_PORT = 993

# Danh sách folder cần quét
TARGET_FOLDERS = ["newsletters", "spam", "INBOX"]

# --- CẤU HÌNH BỔ SUNG ---
SEZNAM_HOST = IMAP_SERVER
SENDER_FILTER = "Instagram"
# Chuỗi subject bắt buộc (lowercase)
TARGET_SUBJECTS = [
    "we've made it easy to get back on instagram",
    "chúng tôi giúp bạn dễ dàng đăng nhập lại trên instagram"
]

# --- REGEX & CONFIG ---
RE_USER_HI = re.compile(r'Hi\s+([a-zA-Z0-9_.]+),', re.IGNORECASE)
RE_UID_LINK = re.compile(r'uid=([0-9]{6,30})')

RESET_LINK_HREF_HINTS = [
    "instagram.com/accounts/password/reset/confirm",
    "instagram.com/accounts/password/reset",
    "password/reset/confirm",
    "one_click_login_email",
    "deref-gmx.net/mail/client",
    "redirecturl=",
]

CONFIRM_KEYWORDS = [
    "password has been changed", "password changed",
    "your instagram password has been changed", "your password has been changed",
    "password was changed", "your password was changed",
    "password reset successful", "password has been reset",
    "your password has been reset",
    "mật khẩu đã được thay đổi", "bạn vừa thay đổi mật khẩu",
    "mật khẩu instagram của bạn đã được thay đổi", "bạn đã thay đổi mật khẩu instagram",
    "bạn vừa đổi mật khẩu instagram", "bạn vừa đổi mật khẩu",
    "mật khẩu đã được đặt lại", "mật khẩu của bạn đã được thay đổi",
]
SENDER_NAME = "instagram"
IMAP_POLL_TIMEOUT = 30  # Tăng lên 30s theo yêu cầu
IMAP_POLL_INTERVAL = 1.5
IMAP_MAX_FETCH_VERIFY = 5

def _decode_str(header_value):
    if not header_value: return ""
    try:
        decoded_list = decode_header(header_value)
        text = ""
        for content, encoding in decoded_list:
            if isinstance(content, bytes):
                text += content.decode(encoding or "utf-8", errors="ignore")
            else:
                text += str(content)
        return text.strip()
    except:
        return str(header_value)

# ==========================================
# KHU VỰC HELPER FUNCTIONS MỚI
# ==========================================

def _decode_header_fast(header_value):
    """Giải mã header nhanh."""
    if not header_value: return ""
    try:
        decoded_list = decode_header(header_value)
        result = []
        for content, encoding in decoded_list:
            if isinstance(content, bytes):
                result.append(content.decode(encoding or "utf-8", errors="ignore"))
            else:
                result.append(str(content))
        return "".join(result)
    except:
        return str(header_value)

def _get_body_fast(msg):
    """Lấy body nhanh."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() in ["text/html", "text/plain"]:
                try:
                    return part.get_payload(decode=True).decode("utf-8", errors="ignore")
                except: pass
    else:
        try:
            return msg.get_payload(decode=True).decode("utf-8", errors="ignore")
        except: pass
    return ""

def _is_reset_href(href):
    if not href: return False
    href_low = href.lower()
    if "reset" not in href_low and "password" not in href_low and "one_click_login_email" not in href_low:
        return False
    return any(hint in href_low for hint in RESET_LINK_HREF_HINTS)

def _extract_reset_link_from_html(raw_html):
    if not raw_html: return ""
    raw_html = html.unescape(raw_html)
    for match in re.finditer(r'(?:href|data-href|data-url)\s*=\s*["\']([^"\']+)["\']', raw_html, re.IGNORECASE):
        href = match.group(1).strip()
        if _is_reset_href(href): return href
    for match in re.finditer(r"https?://[^\s\"'>]+", raw_html, re.IGNORECASE):
        href = match.group(1).strip()
        if _is_reset_href(href): return href
    return ""

def _text_contains_confirm(text, ig_user=None):
    if not text: return False
    text_low = text.lower()
    if ig_user:
        ig_user_low = ig_user.strip().lower()
        if ig_user_low and ig_user_low not in text_low: return False
    return any(kw in text_low for kw in CONFIRM_KEYWORDS)

def _fetch_latest_unseen_mail(email_user, email_pass, subject_keywords, target_username=None, target_email=None, loop_duration=45):
    """
    Phiên bản Fix: 
    1. Mark Seen ngay lập tức để không lặp lại.
    2. Regex chặn dấu chấm (.) để không bắt nhầm username dạng 78.969269
    3. Xóa username khỏi body trước khi scan.
    """
    if not email_user or not email_pass: return None
    if "@" not in email_user: email_user += "@seznam.cz" 

    mail = None
    start_time = time.time()

    # --- REGEX THÔNG MINH (STRICT MODE) ---
    # (?<![._\-\d]): Đằng trước KHÔNG ĐƯỢC là dấu chấm, gạch dưới, gạch ngang, hoặc số
    # (\d{6,8}|\d{3}\s\d{3}): Lấy 6-8 số hoặc dạng 123 456
    # (?![._\-\d]): Đằng sau KHÔNG ĐƯỢC là dấu chấm, gạch dưới, gạch ngang, hoặc số
    code_pattern = re.compile(r'(?<![._\-\d])\b(\d{6,8}|\d{3}\s\d{3})\b(?![._\-\d])')

    try:
        socket.setdefaulttimeout(30)
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        try:
            mail.login(email_user, email_pass)
        except Exception as e:
            if any(k in str(e).lower() for k in ["authentication failed", "login failed", "credentials"]):
                raise Exception("LOGIN_DIE")
            raise e

        while time.time() - start_time < loop_duration:
            
            for folder_name in TARGET_FOLDERS:
                try:
                    # Select folder (readonly=False để mark seen)
                    status, _ = mail.select(f'"{folder_name}"', readonly=False)
                    if status != "OK": continue

                    status, messages = mail.search(None, 'ALL')
                    if status != "OK" or not messages[0]: continue 

                    mail_ids = messages[0].split()
                    recent_ids = mail_ids[-6:]
                    recent_ids.reverse()

                    for mail_id in recent_ids:
                        # 1. Fetch Header & Flags
                        _, fetch_data = mail.fetch(mail_id, '(BODY.PEEK[HEADER] FLAGS)')
                        
                        # Check đã đọc (Tránh loop vĩnh viễn mail cũ)
                        is_read = False
                        for item in fetch_data:
                            if isinstance(item, bytes):
                                if b'\\Seen' in item or b'\\SEEN' in item: is_read = True; break
                            elif isinstance(item, tuple) and len(item) > 0:
                                if b'\\Seen' in item[0] or b'\\SEEN' in item[0]: is_read = True; break
                        
                        if is_read: continue 

                        # Parse Header
                        msg_header = None
                        for item in fetch_data:
                            if isinstance(item, tuple):
                                msg_header = email.message_from_bytes(item[1])
                                break
                        if not msg_header: continue

                        subject = _decode_str(msg_header.get("Subject", "")).lower()
                        sender = _decode_str(msg_header.get("From", "")).lower()
                        to_addr = _decode_str(msg_header.get("To", "")).lower()

                        # Filter cơ bản
                        if "instagram" not in sender: continue
                        if not any(k.lower() in subject for k in subject_keywords): continue 
                        if target_email and target_email.lower().strip() not in to_addr: continue
                        
                        # [LOCK] MARK AS SEEN NGAY LẬP TỨC
                        try: mail.store(mail_id, '+FLAGS', '\\Seen')
                        except: pass

                        # 2. Tải Body
                        _, msg_data = mail.fetch(mail_id, "(BODY.PEEK[])") 
                        full_msg = email.message_from_bytes(msg_data[0][1])
                        body = ""
                        if full_msg.is_multipart():
                            for part in full_msg.walk():
                                ctype = part.get_content_type()
                                if ctype == "text/plain":
                                    body += part.get_payload(decode=True).decode('utf-8', errors='ignore'); break
                                elif ctype == "text/html":
                                     body += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        else:
                            body = full_msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                        
                        if not body: body = ""

                        # --- [BƯỚC VỆ SINH QUAN TRỌNG] ---
                        # Xóa sạch HTML tag
                        clean_body = re.sub(r'<[^>]+>', ' ', body)
                        # Chuyển về lowercase để xử lý
                        clean_body_lower = clean_body.lower()

                        # 3. XOÁ USERNAME KHỎI BODY (Tránh bắt nhầm số trong username)
                        if target_username:
                            u_name = target_username.lower().strip()
                            
                            # Xóa user nguyên bản (ví dụ: 78.969269)
                            if u_name:
                                clean_body_lower = clean_body_lower.replace(u_name, "")
                            
                            # Xóa user bỏ dấu (ví dụ: 78969269) đề phòng email hiển thị khác
                            u_name_no_dot = u_name.replace(".", "").replace("_", "")
                            if u_name_no_dot:
                                clean_body_lower = clean_body_lower.replace(u_name_no_dot, "")

                        # 4. Tìm Code bằng Regex "Khắt khe"
                        matches = code_pattern.findall(clean_body_lower)
                        
                        if matches:
                            for code_candidate in matches:
                                final_code = code_candidate.replace(" ", "")
                                
                                # Kiểm tra độ dài
                                if len(final_code) in [6, 8]:
                                    # Chặn các số năm (False positive phổ biến)
                                    if final_code in ["2024", "2025", "2026", "2027"]: 
                                        continue
                                    
                                    # Kiểm tra lại lần cuối: Đảm bảo code tìm được KHÔNG nằm trong username (Double check)
                                    if target_username and final_code in target_username.replace(".", ""):
                                        print(f"   [IMAP Warning] Ignored code {final_code} because it looks like part of username.")
                                        continue

                                    print(f"   [IMAP] FOUND CODE: {final_code} for {target_username} in '{folder_name}'")
                                    return final_code
                    
                except Exception:
                    continue
            
            time.sleep(2.5)
            try: mail.noop()
            except: pass
        
        elapsed = time.time() - start_time
        print(f"   [IMAP] Timeout {elapsed:.1f}s: No new code found")
        return None

    except Exception as e:
        if "LOGIN_DIE" in str(e): raise e
        print(f"   [IMAP Error] {e}"); return None
    finally:
        if mail:
            try: mail.close(); mail.logout()
            except: pass

# ... (Các hàm get_verify_code_v2, get_2fa_code_v2 giữ nguyên) ...
def get_verify_code_v2(gmx_user, gmx_pass, target_ig_username, target_email=None):
    keywords = ["verify", "xác thực", "confirm", "code", "security", "mã bảo mật", "is your instagram code", "bạn vừa yêu cầu"]
    return _fetch_latest_unseen_mail(gmx_user, gmx_pass, keywords, target_ig_username, target_email, loop_duration=30)

def get_2fa_code_v2(gmx_user, gmx_pass, target_ig_username, target_email=None):
    keywords = ["authenticate", "two-factor", "security", "bảo mật", "2fa", "login code", "mã đăng nhập"]
    return _fetch_latest_unseen_mail(gmx_user, gmx_pass, keywords, target_ig_username, target_email, loop_duration=30)

# ==========================================
# LOGIC CHÍNH MỚI (VERIFY LIVE & PASSWORD CHANGED)
# ==========================================

def verify_account_live(email_login, password):
    """
    Seznam Logic: Connect -> Loop 30s -> Filter FROM -> Filter SUBJECT -> Fetch BODY PEEK -> Extract
    """
    mail = None
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            # 1. KẾT NỐI SERVER SEZNAM với retry
            mail = imaplib.IMAP4_SSL(SEZNAM_HOST, IMAP_PORT)
            mail.login(email_login, password)
            break  # Connection successful, exit retry loop
        except Exception as e:
            error_msg = str(e)
            if attempt < max_retries - 1:
                print(f"IMAP connection failed (attempt {attempt + 1}/{max_retries}): {error_msg}. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                continue
            else:
                return f"Login Mail Failed after {max_retries} attempts: {error_msg}"
    
    try:
        # [QUAN TRỌNG] readonly=True: Lớp bảo vệ 1 để mail luôn UNREAD
        mail.select("INBOX", readonly=True) 

        # --- SETUP LOOP ---
        start_time = time.time()
        timeout = IMAP_POLL_TIMEOUT
        found_data = None

        while time.time() - start_time < timeout:
            try:
                # BƯỚC 1: QUÉT FROM (Server side filter)
                # Chỉ lấy mail từ Instagram, chưa đọc (UNSEEN) càng tốt
                # Nhưng Seznam đôi khi delay flag UNSEEN, nên search FROM là chắc nhất
                status, messages = mail.search(None, f'(FROM "{SENDER_FILTER}")')
                
                if status != "OK" or not messages[0]:
                    time.sleep(2)
                    continue

                # Lấy 5 mail mới nhất
                mail_ids = messages[0].split()
                recent_ids = mail_ids[-5:] 
                
                for mid in reversed(recent_ids):
                    try:
                        # BƯỚC 2: QUÉT SUBJECT
                        # Dùng BODY.PEEK[HEADER] để KHÔNG đánh dấu đã đọc
                        _, data = mail.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
                        
                        raw_header = data[0][1]
                        msg_header = email.message_from_bytes(raw_header)
                        subject = _decode_header_fast(msg_header["Subject"]).lower()

                        # [LOGIC CHẶT CHẼ] Subject phải chứa đúng chuỗi này mới đi tiếp
                        is_target = any(k in subject for k in TARGET_SUBJECTS)
                        if not is_target:
                            continue 
                        
                        # BƯỚC 3: XÉT NỘI DUNG & TRÍCH XUẤT
                        # Dùng BODY.PEEK[] để lấy full content mà vẫn giữ Unread
                        _, data_body = mail.fetch(mid, "(BODY.PEEK[])")
                        msg_body = email.message_from_bytes(data_body[0][1])
                        
                        # Fix for duplicate headers or complex multipart
                        body_content = _get_body_fast(msg_body)
                        
                        # Trích xuất dữ liệu bằng các hàm helper cũ của bạn
                        user_extracted = ""
                        uid_extracted = ""
                        link_extracted = ""
                        
                        # Tìm User
                        m_user = RE_USER_HI.search(body_content)
                        if m_user: user_extracted = m_user.group(1).lower()
                        
                        # Tìm UID
                        m_uid = RE_UID_LINK.search(body_content)
                        if m_uid: uid_extracted = m_uid.group(1)
                        
                        # Tìm Link (Dùng hàm mạnh mẽ có sẵn của bạn)
                        link_extracted = _extract_reset_link_from_html(body_content)
                        
                        if user_extracted or uid_extracted or link_extracted:
                            # [CUSTOM LOGIC] Nếu tìm thấy, không đánh dấu đã đọc (đã dùng PEEK nên ok)
                            found_data = f"success|USER={user_extracted}|UID={uid_extracted}|LINK={link_extracted}"
                            break # Break vòng for loop mail ID
                    
                    except Exception:
                        continue  # Skip this email if there's an error processing it
                
                if found_data:
                    break # Break vòng while loop
                
                # Polling interval
                time.sleep(IMAP_POLL_INTERVAL)
                mail.noop() # Giữ kết nối

            except Exception as e:
                error_str = str(e).lower()
                # Check for socket/connection errors that might be recoverable
                if "socket" in error_str or "eof" in error_str or "connection" in error_str:
                    print(f"Connection error during polling: {e}. Will retry...")
                    time.sleep(3)  # Longer delay for connection issues
                    continue
                else:
                    # For other errors, still continue polling
                    time.sleep(1)
                    continue

        # Clean up
        try: mail.logout()
        except: pass

        if found_data:
            return found_data
             
        return "Fail: Timeout - Reset Mail not found"

    except Exception as e:  
        return f"Error System: {str(e)}"

def verify_password_changed(email_login, password, ig_user=None, timeout=IMAP_POLL_TIMEOUT):
    """
    Check đổi pass thành công.
    Logic: Connect -> Loop Folder -> Lấy 5 mail cuối -> Check Keyword (Subject/Body).
    Bỏ qua việc check username.
    """
    if not email_login or not password: return False
    
    imap_conn = None
    max_retries = 3
    retry_delay = 2
    
    # Retry connection
    for attempt in range(max_retries):
        try:
            imap_conn = imaplib.IMAP4_SSL(SEZNAM_HOST, IMAP_PORT)
            imap_conn.login(email_login, password)
            break  # Connection successful
        except Exception as exc:
            if attempt < max_retries - 1:
                print(f"IMAP verify connection failed (attempt {attempt + 1}/{max_retries}): {exc}. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                continue
            else:
                print(f"IMAP verify connection failed after {max_retries} attempts: {exc}")
                return False

    try:
        end_time = time.time() + timeout
        
        # 2. VÒNG LẶP THỜI GIAN (POLLING)
        while time.time() < end_time:
            
            # 3. VÒNG LẶP QUA CÁC FOLDER (Newsletters -> Spam -> Inbox)
            for folder in TARGET_FOLDERS:
                try:
                    status, _ = imap_conn.select(f'"{folder}"', readonly=True)
                    if status != "OK": continue 
                    
                    # Search mail từ Instagram
                    status, data = imap_conn.search(None, f'(FROM "{SENDER_FILTER}")')
                    
                    if status == "OK" and data[0]:
                        mail_ids = data[0].split()
                        
                        # [QUAN TRỌNG] CHỈ LẤY 5 MAIL MỚI NHẤT
                        recent_ids = mail_ids[-IMAP_MAX_FETCH_VERIFY:]
                        
                        for msg_id in reversed(recent_ids):
                            # --- A. CHECK SUBJECT ---
                            subject = ""
                            try:
                                _, d = imap_conn.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
                                msg = email.message_from_bytes(d[0][1])
                                subject = _decode_header_fast(msg["Subject"]).lower()
                            except: continue

                            # Check keyword trong Subject
                            is_subject_ok = any(kw in subject for kw in CONFIRM_KEYWORDS)
                            
                            if is_subject_ok:
                                # print(f"[VERIFY] Success via Subject: {subject}")
                                return True # -> DONE NGAY

                            # --- B. CHECK BODY (Nếu subject chưa đủ confirm) ---
                            # Chỉ fetch body nếu subject có vẻ nghi vấn hoặc muốn chắc chắn
                            # Nhưng để tối ưu, ta cứ fetch body check cho chắc ăn
                            try:
                                _, d_body = imap_conn.fetch(msg_id, "(BODY.PEEK[])")
                                msg_obj = email.message_from_bytes(d_body[0][1])
                                body = _get_body_fast(msg_obj).lower()
                                
                                is_body_ok = any(kw in body for kw in CONFIRM_KEYWORDS)
                                
                                if is_body_ok:
                                    # print(f"[VERIFY] Success via Body content.")
                                    return True # -> DONE NGAY
                            except: continue
                                
                except Exception:
                    continue # Bỏ qua lỗi folder, sang folder tiếp theo
            
            # Nghỉ 1 chút rồi quét lại
            time.sleep(IMAP_POLL_INTERVAL)
            try: imap_conn.noop() # Giữ kết nối
            except: pass
            
    except Exception:
        pass
    finally:
        try: imap_conn.logout()
        except: pass
        
    return False