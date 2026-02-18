import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os

# ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="Crypto Bot Dashboard", layout="wide")

# เชื่อมต่อ Google Sheets
@st.cache_data(ttl=60) # โหลดข้อมูลใหม่ทุก 1 นาที
def load_data():
    try:
        # สำหรับรันบน Streamlit Cloud ต้องตั้งค่า Secret ชื่อ 'gcp_service_account'
        # หรือถ้าเทสในคอม ให้ชี้ไปที่ไฟล์ json
        if 'gcp_service_account' in st.secrets:
            creds_dict = st.secrets['gcp_service_account']
        else:
            return pd.DataFrame() # Return empty if no creds

        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("CryptoBot_Logs").sheet1
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()

# โหลดข้อมูล
df = load_data()

st.title("🤖 Algo-Trading Dashboard")

if not df.empty:
    # 1. KPI Summary
    total_trades = len(df)
    
    # คำนวณ Win Rate (เฉพาะไม้ที่จบแล้ว)
    finished_trades = df[df['Result'].isin(['Win', 'Loss'])]
    wins = len(finished_trades[finished_trades['Result'] == 'Win'])
    losses = len(finished_trades[finished_trades['Result'] == 'Loss'])
    
    win_rate = (wins / len(finished_trades) * 100) if len(finished_trades) > 0 else 0
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Signals", total_trades)
    col2.metric("Win Rate", f"{win_rate:.1f}%")
    col3.metric("Wins", wins)
    col4.metric("Losses", losses)

    # 2. Charts
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("Win/Loss Distribution")
        fig_pie = px.pie(finished_trades, names='Result', title='Performance', 
                         color='Result', color_discrete_map={'Win':'green', 'Loss':'red'})
        st.plotly_chart(fig_pie)

    with col_right:
        st.subheader("Signals by Coin")
        fig_bar = px.bar(df['Symbol'].value_counts().reset_index(), x='index', y='Symbol', 
                         labels={'index': 'Coin', 'Symbol': 'Count'}, color='index')
        st.plotly_chart(fig_bar)

    # 3. Data Table (ตารางข้อมูล)
    st.subheader("📜 Recent Signals")
    
    # ไฮไลท์สีตามผลลัพธ์
    def highlight_result(val):
        color = 'green' if val == 'Win' else 'red' if val == 'Loss' else 'orange'
        return f'color: {color}; font-weight: bold'

    st.dataframe(df.style.applymap(highlight_result, subset=['Result']), use_container_width=True)

else:
    st.warning("ยังไม่มีข้อมูลใน Google Sheet หรือเชื่อมต่อไม่สำเร็จ")
