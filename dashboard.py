import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime

# ==========================================
# 🎨 1. CYBERPUNK STYLING (CSS INJECTION)
# ==========================================
st.set_page_config(page_title="INFINITY SNIPER", page_icon="🚀", layout="wide")

# Custom CSS สำหรับทำ Neon & Gradient Effect
st.markdown("""
<style>
    /* Background Setup */
    .stApp {
        background-color: #050505;
        background-image: radial-gradient(circle at 50% 50%, #1a1a2e 0%, #000000 100%);
        color: #e0e0e0;
        font-family: 'Courier New', Courier, monospace;
    }
    
    /* Gradient Text */
    .gradient-text {
        background: linear-gradient(to right, #00f2ff, #bd00ff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: bold;
        font-size: 3em;
        text-shadow: 0 0 20px rgba(0, 242, 255, 0.5);
    }

    /* Neon Card Containers */
    .neon-card {
        background: rgba(20, 20, 30, 0.6);
        border: 1px solid rgba(0, 242, 255, 0.3);
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 0 15px rgba(0, 242, 255, 0.1);
        backdrop-filter: blur(10px);
        margin-bottom: 20px;
        transition: transform 0.3s ease;
    }
    .neon-card:hover {
        border: 1px solid rgba(189, 0, 255, 0.8);
        box-shadow: 0 0 25px rgba(189, 0, 255, 0.4);
        transform: translateY(-2px);
    }

    /* Metrics Styling */
    .metric-value {
        font-size: 2.5em;
        font-weight: bold;
        color: #ffffff;
        text-shadow: 0 0 10px rgba(255, 255, 255, 0.5);
    }
    .metric-label {
        font-size: 1em;
        color: #00f2ff;
        text-transform: uppercase;
        letter-spacing: 2px;
    }
    
    /* Table Styling */
    div[data-testid="stDataFrame"] {
        background: transparent;
        border: 1px solid #333;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 🔌 2. CONNECT GOOGLE SHEETS
# ==========================================
# ⚠️ ข้อควรระวัง: ใน Streamlit Cloud ให้เอา JSON ใส่ใน Secrets
# แต่ถ้า รัน Local ให้ใส่ชื่อไฟล์ JSON ตรงนี้ได้เลย
SHEET_NAME = 'CryptoBot_DB'

@st.cache_data(ttl=60) # Cache ข้อมูล 60 วินาที ไม่โหลดถี่เกินไป
def load_data():
    try:
        # กรณีรัน Local: ใส่ path ไฟล์ json ตรงนี้
        # creds_dict = json.load(open("your_key.json")) 
        
        # กรณีรัน Streamlit Cloud (แนะนำ): อ่านจาก st.secrets
        creds_dict = dict(st.secrets["gcp_service_account"])
        
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        
        # Load Data
        summary_val = sheet.worksheet('summary').acell('B1').value
        balance = float(summary_val) if summary_val else 0.0
        
        active_data = sheet.worksheet('active_trades').get_all_records()
        history_data = sheet.worksheet('trade_history').get_all_records()
        
        df_active = pd.DataFrame(active_data)
        df_history = pd.DataFrame(history_data)
        
        return balance, df_active, df_history
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {e}")
        return 0.0, pd.DataFrame(), pd.DataFrame()

# Load Data
current_balance, df_active, df_history = load_data()

# ==========================================
# 📊 3. DASHBOARD LAYOUT
# ==========================================

# --- Header ---
st.markdown('<div class="gradient-text">⚡ INFINITY SNIPER DASHBOARD</div>', unsafe_allow_html=True)
st.markdown(f"Last Update: {datetime.now().strftime('%H:%M:%S')}")
st.markdown("---")

# --- Top Metrics Row ---
col1, col2, col3, col4 = st.columns(4)

# คำนวณ Stats
initial_balance = 200.0 # หรือค่าที่คุณตั้งไว้
total_pnl_usdt = current_balance - initial_balance
pnl_percent = (total_pnl_usdt / initial_balance) * 100

win_rate = 0
if not df_history.empty:
    wins = len(df_history[df_history['Result'] == 'WIN'])
    total_closed = len(df_history)
    win_rate = (wins / total_closed) * 100

def card_metric(label, value, color_hex="#00f2ff"):
    return f"""
    <div class="neon-card">
        <div class="metric-label" style="color: {color_hex};">{label}</div>
        <div class="metric-value">{value}</div>
    </div>
    """

with col1:
    st.markdown(card_metric("Current Balance", f"${current_balance:,.2f}", "#00f2ff"), unsafe_allow_html=True)
with col2:
    color = "#00ff00" if total_pnl_usdt >= 0 else "#ff0000"
    st.markdown(card_metric("Total PnL", f"{total_pnl_usdt:+.2f} ({pnl_percent:+.1f}%)", color), unsafe_allow_html=True)
with col3:
    st.markdown(card_metric("Win Rate", f"{win_rate:.1f}%", "#bd00ff"), unsafe_allow_html=True)
with col4:
    active_count = len(df_active) if not df_active.empty else 0
    st.markdown(card_metric("Active Trades", f"{active_count}", "#ff00aa"), unsafe_allow_html=True)

# --- Charts Section ---
st.markdown("### 📈 Equity Curve & Performance")

if not df_history.empty:
    # สร้างกราฟ Equity Curve แบบ Neon
    df_history['Balance_After'] = pd.to_numeric(df_history['Balance_After'])
    df_history['Timestamp'] = pd.to_datetime(df_history['Timestamp'])
    df_history = df_history.sort_values('Timestamp')
    
    # Plotly Chart
    fig = go.Figure()
    
    # Add Line with Glow effect (Shadow)
    fig.add_trace(go.Scatter(
        x=df_history['Timestamp'], 
        y=df_history['Balance_After'],
        mode='lines',
        name='Balance',
        line=dict(color='#00f2ff', width=3),
        fill='tozeroy', # Gradient Fill under line
        fillcolor='rgba(0, 242, 255, 0.1)'
    ))

    # Layout Customization for Cyberpunk look
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#e0e0e0', family="Courier New"),
        xaxis=dict(showgrid=False, color='#bd00ff'),
        yaxis=dict(showgrid=True, gridcolor='rgba(50,50,50,0.5)', color='#bd00ff'),
        margin=dict(l=0, r=0, t=30, b=0),
        height=400
    )
    
    st.plotly_chart(fig, use_container_width=True)

# --- Tables Section ---
col_active, col_hist = st.columns([1, 1.5])

with col_active:
    st.markdown("### 🟢 Active Positions")
    if not df_active.empty:
        # แต่งตาราง Active
        st.dataframe(
            df_active[['Symbol', 'Side', 'Entry', 'Current_SL', 'Margin_Size']],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("💤 No active trades. Bot is scanning...")

with col_hist:
    st.markdown("### 📜 Trade History")
    if not df_history.empty:
        # คัดมาแค่ 10 ไม้ล่าสุด
        recent_history = df_history.tail(10).sort_values('Timestamp', ascending=False)
        
        # ฟังก์ชันใส่สีให้ตาราง
        def highlight_win_loss(val):
            color = '#00ff00' if val == 'WIN' else '#ff0000'
            return f'color: {color}; font-weight: bold'

        st.dataframe(
            recent_history[['Timestamp', 'Symbol', 'Side', 'PnL_USDT', 'Result']],
            use_container_width=True,
            hide_index=True,
            column_config={
                "PnL_USDT": st.column_config.NumberColumn("PnL ($)", format="$%.2f")
            }
        )
    else:
        st.info("No trade history yet.")

# --- Manual Refresh Button ---
if st.button('🔄 Refresh Data'):
    st.cache_data.clear()
    st.rerun()
