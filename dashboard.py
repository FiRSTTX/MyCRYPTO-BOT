import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os

# 1. ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="Crypto Bot Dashboard", layout="wide")

# 2. ฟังก์ชันโหลดข้อมูลจาก Google Sheets
@st.cache_data(ttl=60) # โหลดใหม่ทุก 1 นาที
def load_data():
    try:
        # ดึง Key จาก Secrets
        if 'gcp_service_account' in st.secrets:
            creds_dict = st.secrets['gcp_service_account']
        else:
            st.error("ไม่พบ Secrets 'gcp_service_account'")
            return pd.DataFrame()

        # เชื่อมต่อ Google Sheets
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # เปิด Sheet (ต้องชื่อตรงกับใน Drive เป๊ะๆ)
        sheet = client.open("CryptoBot_Logs").sheet1
        data = sheet.get_all_records()
        
        # แปลงเป็น DataFrame
        df = pd.DataFrame(data)
        return df

    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()

# 3. ส่วนแสดงผลหลัก
st.title("🤖 Crypto Bot Dashboard (TF 1H)")
st.markdown("---")

# โหลดข้อมูล
df = load_data()

# ตรวจสอบว่ามีข้อมูลไหม
if not df.empty:
    # --- ส่วนที่ 1: KPI Summary ---
    total_trades = len(df)
    
    # กรองเฉพาะไม้ที่จบแล้ว (Result ไม่ใช่ Waiting)
    finished_trades = df[df['Result'].isin(['Win', 'Loss'])]
    wins = len(finished_trades[finished_trades['Result'] == 'Win'])
    losses = len(finished_trades[finished_trades['Result'] == 'Loss'])
    
    # คำนวณ Win Rate
    if len(finished_trades) > 0:
        win_rate = (wins / len(finished_trades)) * 100
    else:
        win_rate = 0
    
    # แสดงตัวเลข
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Signals", total_trades)
    col2.metric("Win Rate", f"{win_rate:.1f}%")
    col3.metric("Wins", wins)
    col4.metric("Losses", losses)

    st.markdown("---")

    # --- ส่วนที่ 2: กราฟ (Charts) ---
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("Win/Loss Ratio")
        if not finished_trades.empty:
            fig_pie = px.pie(finished_trades, names='Result', 
                             title='Performance Distribution', 
                             color='Result', 
                             color_discrete_map={'Win':'#00CC96', 'Loss':'#EF553B'})
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("รอผลการเทรด (Win/Loss) เพื่อแสดงกราฟวงกลม")

    with col_right:
        st.subheader("Signals by Coin")
        # แก้ไข Logic กราฟแท่งให้รองรับ Pandas เวอร์ชันใหม่
        if 'Symbol' in df.columns:
            symbol_counts = df['Symbol'].value_counts().reset_index()
            symbol_counts.columns = ['Symbol', 'Count'] # ตั้งชื่อคอลัมน์ใหม่ให้ชัดเจน
            
            fig_bar = px.bar(symbol_counts, x='Symbol', y='Count', 
                             color='Symbol', 
                             title="Frequency by Coin")
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.error("ไม่พบคอลัมน์ 'Symbol' ใน Google Sheet กรุณาตรวจสอบหัวตาราง")

    # --- ส่วนที่ 3: ตารางข้อมูล (Data Table) ---
    st.subheader("📜 Trading Logs")
    
    # ฟังก์ชันใส่สีบรรทัด
    def highlight_status(val):
        color = 'green' if val == 'Win' else 'red' if val == 'Loss' else 'orange'
        return f'color: {color}; font-weight: bold'

    # แสดงตาราง
    if 'Result' in df.columns:
        st.dataframe(df.style.applymap(highlight_status, subset=['Result']), use_container_width=True)
    else:
        st.dataframe(df, use_container_width=True)
