import streamlit as st
import pandas as pd
import plotly.express as px
import time

# --- 1. ตั้งค่าหน้าเว็บ ---
st.set_page_config(
    page_title="Crypto Bot Monitor",
    page_icon="🤖",
    layout="wide"
)

# --- 2. ฟังก์ชันโหลดข้อมูล (Cache ไว้ 1 นาที เพื่อไม่ให้ยิง GitHub ถี่เกินไป) ---
# ⚠️ เปลี่ยน URL นี้ให้เป็นของ Repo คุณ (ต้องเป็น Public Repo หรือดูวิธีแก้ด้านล่างถ้าเป็น Private)
CSV_URL = "https://raw.githubusercontent.com/FiRSTTX/MyCRYPTO-BOT/main/signals.csv"

@st.cache_data(ttl=60)
def load_data():
    try:
        # ลองดึงจาก GitHub ก่อน
        df = pd.read_csv(CSV_URL)
        return df
    except Exception as e:
        # ถ้าดึงไม่ได้ (เช่น เน็ตหลุด หรือ Repo เป็น Private) ให้ลองอ่านไฟล์ในเครื่องแทน
        try:
            return pd.read_csv("signals.csv")
        except:
            return pd.DataFrame() # ส่งค่าว่างกลับไปถ้าไม่เจออะไรเลย

# --- 3. ส่วนแสดงผลหลัก ---
st.title("🤖 Crypto Bot Live Dashboard")
st.markdown(f"**Data Source:** `{CSV_URL}`")

# ปุ่ม Refresh ข้อมูล
if st.button('🔄 Refresh Data'):
    st.cache_data.clear() # ล้าง Cache
    st.rerun() # โหลดหน้าใหม่

# โหลดข้อมูล
df = load_data()

if df.empty:
    st.warning("⚠️ ยังไม่พบข้อมูล Signal หรือไฟล์ signals.csv อ่านไม่ได้ (ตรวจสอบว่า Repo เป็น Public หรือยัง?)")
else:
    # --- 4. คำนวณ KPI ---
    total_trades = len(df)
    
    # กรองเฉพาะออเดอร์ที่ปิดแล้ว (TP/SL)
    closed_trades = df[df['status'].isin(['TP', 'SL'])]
    wins = len(closed_trades[closed_trades['status'] == 'TP'])
    losses = len(closed_trades[closed_trades['status'] == 'SL'])
    open_trades = len(df[df['status'] == 'OPEN'])

    winrate = 0
    if len(closed_trades) > 0:
        winrate = (wins / len(closed_trades)) * 100

    # --- 5. แสดงตัวเลข (Metrics) ---
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("Total Signals", total_trades, delta=f"{open_trades} Open")
    col2.metric("Win Rate", f"{winrate:.2f}%")
    col3.metric("Wins (TP)", wins, delta_color="normal")
    col4.metric("Losses (SL)", losses, delta_color="inverse")

    st.divider()

    # --- 6. กราฟและตาราง ---
    c1, c2 = st.columns([1, 2])

    with c1:
        st.subheader("📈 Win/Loss Ratio")
        if len(closed_trades) > 0:
            # สร้างกราฟวงกลม
            fig = px.donut(
                names=['Win', 'Loss'], 
                values=[wins, losses], 
                color=['Win', 'Loss'],
                color_discrete_map={'Win':'#00CC96', 'Loss':'#EF553B'},
                hole=0.5
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Waiting for closed trades...")

    with c2:
        st.subheader("📜 Recent Signals")
        
        # จัดรูปแบบสีในตาราง
        def highlight_status(val):
            color = 'black'
            if val == 'TP': color = 'green'
            elif val == 'SL': color = 'red'
            elif val == 'OPEN': color = 'orange'
            return f'color: {color}; font-weight: bold'

        # แสดงตาราง (เรียงใหม่เอาล่าสุดขึ้นบน)
        st.dataframe(
            df.sort_values(by='time', ascending=False).style.applymap(highlight_status, subset=['status']),
            use_container_width=True,
            height=400
        )
