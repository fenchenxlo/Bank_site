from django.apps import AppConfig


class NotifyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = 'notify'

# -------------------------------
# 新增 Streamlit 查詢 SQLite 功能
# -------------------------------
import sqlite3
import streamlit as st
import os

st.title("SQLite 查詢工具 (單專案版)")

# 🔍 確認資料庫檔案路徑
db_path = "data/sqlite.db3"  # 每個專案的 sqlite.db3 放在 data/ 下

if not os.path.exists(db_path):
    st.error(f"找不到資料庫檔案: {db_path}")
    st.stop()

# 建立連線
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1️⃣ 取得所有 table
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in cursor.fetchall()]

if not tables:
    st.warning("這個資料庫沒有任何 table")
    st.stop()

table_choice = st.selectbox("選擇 Table", tables)

# 2️⃣ 取得欄位資訊
cursor.execute(f"PRAGMA table_info({table_choice});")
columns = [row[1] for row in cursor.fetchall()]

if not columns:
    st.warning("這個 table 沒有欄位")
    st.stop()

column_choice = st.selectbox("選擇欄位", columns)

# 3️⃣ 輸入查詢值
value_input = st.text_input("輸入查詢值 (精確比對)")

# 4️⃣ 執行查詢
if st.button("查詢"):
    try:
        query = f"SELECT * FROM {table_choice} WHERE {column_choice} = ?"
        cursor.execute(query, (value_input,))
        rows = cursor.fetchall()

        if rows:
            st.success(f"查詢到 {len(rows)} 筆結果")
            st.dataframe(rows)
        else:
            st.info("沒有符合的資料")
    except Exception as e:
        st.error(f"查詢錯誤: {e}")

conn.close()
