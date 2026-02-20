import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# ==========================================
# 1. PAGE SETUP & CONFIG
# ==========================================
st.set_page_config(
    page_title="Crypto Bot AI",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==========================================
# 2. CUSTOM CSS (THE MAGIC 🎨)
# ==========================================
st.markdown("""
    <style>
        /* Import Font ให้ดูพรีเมียม */
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600&display=swap');
        
        /* พื้นหลังหลัก (Main Background) - ไล่เฉดม่วงเข้มตามรูป */
        .stApp {
            background: linear-gradient(180deg, #120c29 0%, #302b63 50%, #24243e 100%);
            font-family: 'Poppins', sans-serif;
            color: white;
        }
        
        /* ซ่อน Header มาตรฐานของ Streamlit */
        header {visibility: hidden;}
        
        /* Custom Card Style (เหมือนบัตรเครดิตในรูป) */
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 20px;
            padding: 20px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
            color: white;
            margin-bottom: 20px;
            position: relative;
            overflow: hidden;
        }
        
        .metric-card-secondary {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            padding: 20px;
            backdrop-filter: blur(10px);
        }

        /* Typography */
        .big-number {
            font-size: 36px;
            font-weight: 600;
            margin: 10px 0;
        }
        .label {
            font-size: 14px;
            opacity: 0.8;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .profit-text { color: #00ff88; font-weight: bold; }
        .loss-text { color: #ff0055; font-weight: bold; }

        /* ปรับแต่ง DataFrame ให้เข้าธีม */
        div[data-testid="stDataFrame"] {
            background-color: rgba(255, 255, 255, 0.02);
            border-radius: 15px;
            padding: 10px;
        }
        
        /* ปุ่ม Refresh */
        .stButton>button {
            background: linear-gradient(90deg, #00c6ff, #0072ff);
            border: none;
            border-radius: 50px;
            color: white;
            padding: 10px 30px;
            font-weight: bold;
            box-shadow: 0 4px 15px rgba(0, 114, 255, 0.4);
        }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 3. DATA LOADING
# ==========================================
# ⚠️ เปลี่ยน URL เป็น GitHub Raw Link ของคุณ
CSV_URL = "https://raw.githubusercontent.com/FiRSTTX/MyCRYPTO-BOT/main/signals.csv"

@st.cache_data(ttl=60)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        # แปลงเวลาเป็น datetime object
        df['time'] = pd.to_datetime(df['time'])
        return df
    except:
        return pd.DataFrame()

# ==========================================
# 4. DASHBOARD LOGIC
# ==========================================

# Header ส่วนบน
c1, c2 = st.columns([0.85, 0.15])
with c1:
    st.markdown("### 👋 Hello, Trader")
    st.markdown("<p style='opacity:0.6; margin-top:-15px;'>Your Automated Portfolio is Active</p>", unsafe_allow_html=True)
with c2:
    if st.button("Sync ↻"):
        st.cache_data.clear()
        st.rerun()

df = load_data()

# --- คำนวณ Stats ---
initial_balance = 50.0  # ทุนเริ่มต้น
current_balance = initial_balance
est_pnl = 0.0
win_count = 0
loss_count = 0
total_trades = 0

if not df.empty:
    total_trades = len(df)
    closed_trades = df[df['status'].isin(['TP', 'SL'])]
    win_count = len(closed_trades[closed_trades['status'] == 'TP'])
    loss_count = len(closed_trades[closed_trades['status'] == 'SL'])
    
    # คำนวณกำไร/ขาดทุนสะสม (สมมติ TP=+$1.5, SL=-$1.5 จากไม้ละ 3%)
    est_pnl = (win_count * 1.5) - (loss_count * 1.5)
    current_balance += est_pnl

# ==========================================
# 5. UI: HERO CARDS (เหมือนบัตรเครดิตในรูป)
# ==========================================

col1, col2 = st.columns([1, 1])

with col1:
    # การ์ดแสดง Balance (สีม่วง)
    st.markdown(f"""
        <div class="metric-card">
            <div class="label">Total Balance</div>
            <div class="big-number">${current_balance:.2f}</div>
            <div style="display:flex; justify-content:space-between; align-items:flex-end;">
                <div>**** **** **** 4242</div>
                <div style="font-size:12px;">VALID THRU<br>12/28</div>
            </div>
            <div style="position:absolute; top:20px; right:20px; opacity:0.5;">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="white"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"/></svg>
            </div>
        </div>
    """, unsafe_allow_html=True)

with col2:
    # การ์ดแสดง Profit/Loss (สีเข้ม)
    pnl_color = "#00ff88" if est_pnl >= 0 else "#ff0055"
    pnl_sign = "+" if est_pnl >= 0 else ""
    
    st.markdown(f"""
        <div class="metric-card-secondary">
            <div class="label">Net Profit (Est.)</div>
            <div class="big-number" style="color: {pnl_color};">{pnl_sign}${est_pnl:.2f}</div>
            <div style="margin-top:10px;">
                <span style="background:rgba(255,255,255,0.1); padding:5px 10px; border-radius:10px; font-size:12px;">
                    🏆 Wins: {win_count}
                </span>
                &nbsp;
                <span style="background:rgba(255,255,255,0.1); padding:5px 10px; border-radius:10px; font-size:12px;">
                    💀 Loss: {loss_count}
                </span>
            </div>
        </div>
    """, unsafe_allow_html=True)

# ==========================================
# 6. UI: CHARTS (นีออน & Curve)
# ==========================================

st.markdown("### 📈 Analytics")

if not df.empty and total_trades > 0:
    chart_col1, chart_col2 = st.columns([2, 1])
    
    with chart_col1:
        # สร้างกราฟจำลองการเติบโตของพอร์ต (Cumulative PnL)
        # สร้างข้อมูลจำลองเพื่อให้กราฟดูมีมิติ
        df_sorted = df.sort_values('time')
        df_sorted['pnl_value'] = df_sorted['status'].map({'TP': 1.5, 'SL': -1.5, 'OPEN': 0})
        df_sorted['cumulative_pnl'] = df_sorted['pnl_value'].cumsum() + initial_balance
        
        # Area Chart แบบไล่สีนีออน (เหมือนรูป 2586bb.jpg)
        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(
            x=df_sorted['time'], 
            y=df_sorted['cumulative_pnl'],
            mode='lines',
            fill='tozeroy',
            line=dict(color='#00c6ff', width=3, shape='spline'), # เส้นโค้งสีฟ้า
            fillcolor='rgba(0, 198, 255, 0.1)', # พื้นหลังโปร่งแสง
            name='Balance'
        ))
        
        fig_line.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=0, b=0),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)', showticklabels=True),
            font=dict(color='white'),
            height=250
        )
        st.plotly_chart(fig_line, use_container_width=True)

    with chart_col2:
        # Donut Chart (Win Rate)
        win_rate = (win_count / (win_count + loss_count) * 100) if (win_count + loss_count) > 0 else 0
        
        fig_donut = go.Figure(data=[go.Pie(
            labels=['Win', 'Loss'],
            values=[max(win_count, 1) if win_count==0 and loss_count==0 else win_count, loss_count], # กัน Error
            hole=.7,
            marker_colors=['#00e676', '#2d3446'] if win_count > 0 else ['#2d3446', '#2d3446']
        )])
        
        fig_donut.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            showlegend=False,
            margin=dict(t=0, b=0, l=0, r=0),
            height=200,
            annotations=[dict(text=f"{int(win_rate)}%", x=0.5, y=0.5, font_size=24, showarrow=False, font_color='white')]
        )
        st.markdown("<div style='text-align:center; font-size:14px; margin-bottom:10px;'>Win Rate</div>", unsafe_allow_html=True)
        st.plotly_chart(fig_donut, use_container_width=True)

else:
    st.info("Waiting for first signal to plot charts...")

# ==========================================
# 7. UI: RECENT TRANSACTIONS LIST
# ==========================================

st.markdown("### ⚡ Recent Activity")

if not df.empty:
    # เตรียมข้อมูลสำหรับตาราง
    display_df = df[['time', 'symbol', 'side', 'entry', 'status']].sort_values(by='time', ascending=False).head(5)
    
    # ใช้ Column Config แต่งตารางให้มินิมอล
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "time": st.column_config.DatetimeColumn("Time", format="HH:mm", width="small"),
            "symbol": st.column_config.TextColumn("Coin", width="small"),
            "side": st.column_config.TextColumn("Type", width="small"),
            "entry": st.column_config.NumberColumn("Price", format="$%.2f"),
            "status": st.column_config.TextColumn("Status"),
        }
    )
