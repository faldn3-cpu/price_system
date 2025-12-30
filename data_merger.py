import os
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re

# === 設定區 ===
GOOGLE_SHEET_NAME = '經銷牌價表_資料庫'
JSON_KEY_FILE = 'service_account.json'
EXCEL_FOLDER = './excel_files'
COMBINATION_FILE = '整套搭配.xlsx' # 請確保這個檔案放在 excel_files 資料夾內

# 一般查詢保留的欄位
TARGET_COLUMNS = ['NO.', '規格', '牌價', '經銷價', '說明', '訂購品(V)']

def clean_header_name(header):
    if pd.isna(header): return ""
    s = str(header)
    s = re.sub(r'\s+', '', s)
    s = s.replace('（', '(').replace('）', ')')
    return s

def find_header_row(file_path, sheet_name):
    try:
        df_temp = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=20)
        for idx, row in df_temp.iterrows():
            row_str = "".join([clean_header_name(x) for x in row.values])
            if '規格' in row_str and ('經銷價' in row_str or '牌價' in row_str):
                return idx
    except: pass
    return 0

def process_general_files(client):
    """處理一般經銷牌價 Excel"""
    if not os.path.exists(EXCEL_FOLDER): return None
    files = [f for f in os.listdir(EXCEL_FOLDER) if f.endswith(('.xlsx', '.xls')) and f != COMBINATION_FILE]
    all_data = []
    
    print(f"--- 正在處理一般牌價表 ({len(files)} 個檔案) ---")
    for file in files:
        file_path = os.path.join(EXCEL_FOLDER, file)
        try:
            xls = pd.ExcelFile(file_path)
            for sheet_name in xls.sheet_names:
                header_idx = find_header_row(file_path, sheet_name)
                df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_idx, dtype=str)
                df.columns = [clean_header_name(c) for c in df.columns]
                
                clean_df = pd.DataFrame(columns=TARGET_COLUMNS)
                for col in TARGET_COLUMNS:
                    if col in df.columns: clean_df[col] = df[col]
                    else: clean_df[col] = ""
                
                if '規格' in clean_df.columns:
                    clean_df = clean_df[clean_df['規格'].str.strip() != '']
                    
                if not clean_df.empty:
                    clean_df['來源檔案'] = file
                    clean_df['來源分頁'] = sheet_name
                    all_data.append(clean_df)
                    print(f" - 讀取: {file} / {sheet_name}")
        except Exception as e:
            print(f" X 失敗: {file} - {e}")
            
    if all_data:
        final_df = pd.concat(all_data, ignore_index=True).fillna("")
        try:
            sh = client.open(GOOGLE_SHEET_NAME)
            # 上傳到第一頁 (一般資料庫)
            ws = sh.sheet1 
            ws.clear()
            ws.update([final_df.columns.values.tolist()] + final_df.values.tolist())
            print("✅ 一般牌價資料更新完成！")
        except Exception as e: print(f"❌ 上傳失敗: {e}")

def process_combination_file(client):
    """處理組合搭配 Excel"""
    comb_path = os.path.join(EXCEL_FOLDER, COMBINATION_FILE)
    if not os.path.exists(comb_path):
        print(f"⚠️ 找不到 {COMBINATION_FILE}，跳過組合更新。")
        return

    print(f"--- 正在處理組合搭配檔案 ({COMBINATION_FILE}) ---")
    try:
        xls = pd.ExcelFile(comb_path)
        all_comb_data = []
        
        # 假設組合檔的標題都在第 0 列 (通常是第一列)
        # 我們把所有 Sheet 合併，但多加一個「系列」欄位
        for sheet_name in xls.sheet_names:
            # 跳過非數據頁
            if sheet_name in ['DATA', '經銷價(總)']: continue
            
            # 讀取資料 (假設第一列是標題)
            df = pd.read_excel(comb_path, sheet_name=sheet_name, dtype=str)
            df['系列'] = sheet_name # 把 Sheet 名稱變成系列名稱 (例如: 整套_SDC)
            
            # 簡單清洗：移除全空行
            df.dropna(how='all', inplace=True)
            all_comb_data.append(df)
            print(f" - 讀取組合: {sheet_name}")
            
        if all_comb_data:
            final_comb = pd.concat(all_comb_data, ignore_index=True).fillna("")
            
            sh = client.open(GOOGLE_SHEET_NAME)
            # 嘗試開啟或建立 'Combinations' 分頁
            try:
                ws = sh.worksheet('Combinations')
            except:
                ws = sh.add_worksheet(title='Combinations', rows="1000", cols="20")
            
            ws.clear()
            ws.update([final_comb.columns.values.tolist()] + final_comb.values.tolist())
            print("✅ 組合搭配資料更新完成！")
            
    except Exception as e:
        print(f"❌ 組合檔處理失敗: {e}")

def main():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    if not os.path.exists(JSON_KEY_FILE): return
    creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, scope)
    client = gspread.authorize(creds)
    
    # 1. 處理一般檔案
    process_general_files(client)
    # 2. 處理組合檔案
    process_combination_file(client)

if __name__ == "__main__":
    main()