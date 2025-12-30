import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import re
import bcrypt
import smtplib
from email.mime.text import MIMEText
import random
import string
import time

# === 頁面設定 ===
st.set_page_config(page_title="經銷牌價系統", layout="wide")

# === CSS: 進階隱藏 (隱藏開發者選項與紅色錯誤細節) ===
st.markdown("""
<style>
/* 隱藏右上角漢堡選單 */
#MainMenu {visibility: hidden;}
/* 隱藏頁尾 */
footer {visibility: hidden;}
/* 隱藏標頭裝飾 */
header {visibility: hidden;}
/* 隱藏工具列 */
[data-testid="stElementToolbar"] { display: none; }
</style>
""", unsafe_allow_html=True)

# ==========================================
#  🔐 雲端資安設定 (讀取 Secrets)
# ==========================================
if "email" in st.secrets:
    SMTP_EMAIL = st.secrets["email"]["smtp_email"]
    SMTP_PASSWORD = st.secrets["email"]["smtp_password"]
else:
    SMTP_EMAIL = ""
    SMTP_PASSWORD = ""

GOOGLE_SHEET_NAME = '經銷牌價表_資料庫'
SEARCH_COLS = ['NO.', '規格', '說明']
DISPLAY_COLS = ['規格', '牌價', '經銷價', '說明', '訂購品(V)']

# === Session State ===
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = ""
if 'real_name' not in st.session_state:
    st.session_state.real_name = ""

# === 連線函式 ===
def get_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    # 優先讀取雲端 Secrets
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    # 本機備援
    elif os.path.exists('service_account.json'):
        creds = ServiceAccountCredentials.from_json_keyfile_name('service_account.json', scope)
        return gspread.authorize(creds)
    else:
        return None

# === 加密與工具函式 ===
def check_password(plain_text, hashed_text):
    try:
        return bcrypt.checkpw(plain_text.encode('utf-8'), hashed_text.encode('utf-8'))
    except: return False

def hash_password(plain_text):
    return bcrypt.hashpw(plain_text.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def generate_random_password(length=8):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for i in range(length))

# === 寄信函式 ===
def send_reset_email(to_email, new_password):
    if not SMTP_EMAIL or not SMTP_PASSWORD: 
        return False, "系統未設定寄信信箱，請聯繫管理員。"
        
    subject = "【經銷牌價系統】密碼重置通知"
    body = f"""
    您好：
    
    您的系統密碼已重置。
    
    新密碼為：{new_password}
    
    請使用此密碼登入後，盡快修改為您習慣的密碼。
    """
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = SMTP_EMAIL
    msg['To'] = to_email

    try:
        # 使用 587 Port (TLS)
        with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(SMTP_EMAIL, SMTP_PASSWORD)
            smtp.send_message(msg)
        return True, "信件發送成功"
    except Exception as e:
        return False, "寄信失敗，請稍後再試或聯繫管理員。"

# === 業務邏輯 ===
def login(email, password):
    client = get_client()
    if not client: return False, "系統連線失敗"
    try:
        sh = client.open(GOOGLE_SHEET_NAME)
        ws = sh.worksheet("Users")
        users = ws.get_all_records()
        
        for user in users:
            if str(user.get('email')).strip() == email.strip():
                if check_password(password, str(user.get('password'))):
                    found_name = str(user.get('name')) if user.get('name') else email
                    return True, found_name
                else:
                    return False, "密碼錯誤"
        return False, "此 Email 尚未註冊"
    except Exception as e:
        return False, "登入過程發生錯誤"

def change_password(email, new_password):
    client = get_client()
    if not client: return False
    try:
        sh = client.open(GOOGLE_SHEET_NAME)
        ws = sh.worksheet("Users")
        cell = ws.find(email)
        if cell:
            ws.update_cell(cell.row, 2, hash_password(new_password))
            return True
        return False
    except: return False

def reset_password_flow(target_email):
    client = get_client()
    if not client: return False, "連線失敗"
    try:
        sh = client.open(GOOGLE_SHEET_NAME)
        ws = sh.worksheet("Users")
        try:
            cell = ws.find(target_email.strip())
        except gspread.exceptions.CellNotFound:
             return False, "此 Email 尚未註冊"
        
        new_pw = generate_random_password()
        sent, msg = send_reset_email(target_email, new_pw)
        if not sent:
            return False, msg
            
        ws.update_cell(cell.row, 2, hash_password(new_pw))
        return True, "重置成功！新密碼已寄送到您的信箱。"
    except Exception as e:
        return False, "重置失敗，請稍後再試"

@st.cache_data(ttl=600)
def load_data():
    client = get_client()
    if not client: return pd.DataFrame()
    try:
        sh = client.open(GOOGLE_SHEET_NAME)
        data = sh.sheet1.get_all_records()
        return pd.DataFrame(data).astype(str)
    except: return pd.DataFrame()

def clean_currency(val):
    if not val or pd.isna(val): return None
    val_str = str(val)
    clean_str = re.sub(r'[^\d.]', '', val_str)
    try: return float(clean_str)
    except ValueError: return None

# ==========================================
#               主程式 (包在 main 裡)
# ==========================================
def main_app():
    # --- 1. 登入畫面 ---
    if not st.session_state.logged_in:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("<br><br>", unsafe_allow_html=True)
            st.header("🔒 經銷牌價系統")
            
            tab1, tab2 = st.tabs(["會員登入", "忘記密碼"])
            
            with tab1:
                with st.form("login_form"):
                    input_email = st.text_input("Email")
                    input_pass = st.text_input("密碼", type="password")
                    submitted = st.form_submit_button("登入", use_container_width=True)
                    
                    if submitted:
                        success, result = login(input_email, input_pass)
                        if success:
                            st.session_state.logged_in = True
                            st.session_state.user_email = input_email
                            st.session_state.real_name = result
                            st.rerun()
                        else:
                            st.error(result)
            
            with tab2:
                st.caption("系統將發送新密碼至您的 Email")
                with st.form("reset_form"):
                    reset_email = st.text_input("請輸入註冊 Email")
                    reset_submit = st.form_submit_button("發送重置信", use_container_width=True)
                    
                    if reset_submit:
                        if reset_email:
                            with st.spinner("處理中..."):
                                success, msg = reset_password_flow(reset_email)
                                if success:
                                    st.success(msg)
                                else:
                                    st.error(msg)
                        else:
                            st.warning("請輸入 Email")
        return # 停止執行後續

    # --- 2. 側邊欄 ---
    with st.sidebar:
        st.write(f"👤 **{st.session_state.real_name}**")
        
        with st.expander("🔑 修改密碼"):
            new_pwd = st.text_input("新密碼", type="password")
            if st.button("確認修改"):
                if new_pwd:
                    if change_password(st.session_state.user_email, new_pwd):
                        st.success("密碼已更新！")
                    else:
                        st.error("修改失敗")
                else:
                    st.warning("密碼不能為空")
        
        st.markdown("---")
        if st.button("登出", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user_email = ""
            st.session_state.real_name = ""
            st.rerun()

    # --- 3. 主查詢介面 ---
    st.title("🔍 經銷牌價查詢系統")
    st.markdown("---")

    df = load_data()

    if not df.empty:
        search_term = st.text_input("輸入關鍵字搜尋", "", placeholder="例如: FX5U / SDC / 馬達")
        
        display_df = df.copy()
        if search_term:
            valid_search = [c for c in SEARCH_COLS if c in display_df.columns]
            mask = display_df[valid_search].apply(lambda x: x.str.contains(search_term, case=False, na=False)).any(axis=1)
            display_df = display_df[mask]

        final_cols = [c for c in DISPLAY_COLS if c in display_df.columns]
        
        if not display_df.empty and final_cols:
            final_df = display_df[final_cols].copy()
            
            for col in ['牌價', '經銷價']:
                if col in final_df.columns:
                    final_df[col] = final_df[col].apply(clean_currency)

            st.info(f"搜尋結果：共 {len(final_df)} 筆")

            styler = final_df.style.format("{:,.0f}", subset=['牌價', '經銷價'], na_rep="")
            styler = styler.set_properties(subset=['牌價', '經銷價'], **{'text-align': 'right'})
            
            if '訂購品(V)' in final_df.columns:
                styler = styler.set_properties(subset=['訂購品(V)'], **{'text-align': 'center'})

            st.dataframe(
                styler,
                use_container_width=True,
                hide_index=True,
                height=600
            )
        else:
            if search_term:
                st.warning("查無資料")
    else:
        st.error("資料庫連線異常，請稍後再試。")

# ==========================================
#  🛡️ 全域防護罩 (進入點)
# ==========================================
if __name__ == "__main__":
    try:
        main_app()
    except Exception as e:
        # 當發生未知錯誤時，只顯示這行，不顯示程式碼
        st.error("系統暫時忙碌中，請重新整理或聯繫管理員。")
        # 如果您自己在後台看，可以把 e 印出來 debug，但網頁上不顯示
        print(f"Error: {e}")