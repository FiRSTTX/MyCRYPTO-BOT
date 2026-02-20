import streamlit as st
import pandas as pd
import plotly.express as px

# --- SETUP & CSS ---
st.set_page_config(page_title="Crypto Bot AI", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&display=swap');
        .stApp { background: linear-gradient(135deg, #0f0c29, #302b63, #24243e); font-family: 'Rajdhani', sans-serif; }
        h1, h2, h3, p, div { color: white; }
        div[data-testid="stMetric"] { background-color: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); padding: 10px; border-radius: 10px; backdrop-filter: blur(5px); }
        div[data-testid="stMetricValue"] { color: #00f2ff !important; font-size: 24px !important; }
        div[data-testid="stDataFrame"] { background-color: rgba(0, 0, 0, 0.3); border-radius: 10px; padding: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- LOAD DATA ---
CSV_URL = "https://raw.githubusercontent.com/FiRSTTX/MyCRYPTO-BOT/main/signals.csv"

@st.cache_data(ttl=60)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        return df
    except:
        return pd.DataFrame()

# --- HEADER ---
c1, c2 = st.columns([3, 1])
with c1: st.markdown("# ⚡ Crypto Signal AI")
with c2: 
    if st.button('🔄 Sync Data'): st.cache_data.clear(); st.rerun()

df = load_data()

if df.empty:
    st.info("Waiting for data...")
else:
    # --- METRICS ---
    total = len(df)
    opens = len(df[df['status'] == 'OPEN'])
    wins = len(df[df['status'] == 'TP'])
    
    # ตรวจสอบว่ามีคอลัมน์ใหม่หรือไม่ (เผื่อไฟล์เก่ายังไม่มี)
    recent_margin = df.iloc[-1]['margin'] if 'margin' in df.columns else 0
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Signals", total)
    m2.metric("Active Trades", opens)
    m3.metric("Win Count", wins)
    m4.metric("Last Margin Use", f"${recent_margin}")

    st.divider()

    # --- TABLE ---
    st.markdown("### 📜 Detailed Log")
    
    def color_status(val):
        color = '#00f2ff' if val == 'OPEN' else ('#00ff00' if val == 'TP' else '#ff0055')
        return f'color: {color}; font-weight: bold;'

    # เลือกคอลัมน์ที่จะโชว์
    show_cols = ['time', 'symbol', 'side', 'entry', 'tp', 'sl', 'status', 'reason', 'margin']
    # กรองเฉพาะคอลัมน์ที่มีอยู่จริงใน CSV (กัน Error)
    valid_cols = [c for c in show_cols if c in df.columns]
    
    display_df = df[valid_cols].sort_values(by='time', ascending=False)
    
    st.dataframe(
        display_df.style.applymap(color_status, subset=['status']), 
        use_container_width=True, 
        height=400,
        hide_index=True
    )
