import bcrypt

# 在這裡輸入您想設定的初始管理員密碼
my_password = "admin"  # <--- 您可以改成您要的密碼

# 產生加密字串
hashed = bcrypt.hashpw(my_password.encode('utf-8'), bcrypt.gensalt())
print("請將下方這串亂碼，複製貼上到 Google Sheet 的 password 欄位：")
print("-" * 30)
print(hashed.decode('utf-8'))
print("-" * 30)