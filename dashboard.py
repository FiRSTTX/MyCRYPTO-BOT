import streamlit as st
import pandas as pd
import plotly.express as px
import time

# --- 1. CONFIG & PAGE SETUP ---
st.set_page_config(
    page_title="Crypto Bot AI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- 2. CUSTOM CSS (ส่วนสำคัญที่ทำให้สวยเหมือนแอป) ---
st.markdown("""
    <style>
        /* นำเข้าฟอนต์ให้ดูทันสมัย */
        @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&display=swap');

        /* เปลี่ยนสีพื้นหลังทั้งหน้าเป็น Gradient น้ำเงินเข้ม-ม่วง */
        .stApp {
            background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
            font-family: 'Rajdhani', sans-serif;
        }

        /* ปรับแต่ง Headers */
        h1, h2, h3 {
            color: #ffffff;
            text-shadow: 0 0 10px rgba(0, 242, 255, 0.5); /* นีออนสีฟ้า */
        }

        /* ตกแต่งกล่อง Metrics (ตัวเลข) ให้เหมือนการ์ด */
        div[data-testid="stMetric"] {
            background-color: rgba(255, 255, 255, 0.05); /* พื้นหลังโปร่งแสง */
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 15px;
            border-radius: 15px; /* มุมโค้ง */
            backdrop-filter: blur(10px); /* เอฟเฟกต์กระจกฝ้า */
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
            transition: all 0.3s ease;
        }
        
        div[data-testid="stMetric"]:hover {
            transform: translateY(-5px); /* ลอยขึ้นเมื่อเอาเมาส์ชี้ */
            border-color: #00f2ff; /* ขอบสีนีออน */
            box-shadow: 0 0 15px rgba(0, 242, 255, 0.3);
        }

        /* ปรับสีตัวเลขใน Metric */
        div[data-testid="stMetricValue"] {
            color: #00f2ff !important; /* สีฟ้านีออน */
            font-size: 28px !important;
            font-weight: 700;
        }

        div[data-testid="stMetricLabel"] {
            color: #e0e0e0 !important;
        }

        /* ปรับแต่งปุ่มกด */
        .stButton>button {
            background: linear-gradient(90deg, #00c6ff, #0072ff);
            color: white;
            border: none;
            border-radius: 25px;
            padding: 10px 24px;
            font-weight: bold;
            box-shadow: 0 0 10px rgba(0, 114, 255, 0.5);
            transition: 0.3s;
        }
        .stButton>button:hover {
            background: linear-gradient(90deg, #0072ff, #00c6ff);
            box-shadow: 0 0 20px rgba(0, 114, 255, 0.8);
        }

        /* ปรับแต่งตาราง Dataframe */
        div[data-testid="stDataFrame"] {
            background-color: rgba(0, 0, 0, 0.2);
            border-radius: 10px;
            padding: 10px;
        }
    </style>
""", unsafe_allow_html=True)

# --- 3. DATA LOADING ---
# URL ของไฟล์ CSV (เปลี่ยนเป็น Link ของคุณ)
CSV_URL = "https://raw.githubusercontent.com/FiRSTTX/MyCRYPTO-BOT/main/signals.csv"

@st.cache_data(ttl=60)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        return df
    except:
        # Fallback กรณีอ่าน GitHub ไม่ได้
        try:
            return pd.read_csv("signals.csv")
        except:
            return pd.DataFrame()

# --- 4. HEADER SECTION ---
col_head1, col_head2 = st.columns([3, 1])
with col_head1:
    st.markdown("# ⚡ Crypto Signal AI")
    st.markdown("Automated Trading System | `Kraken`")
with col_head2:
    if st.button('🔄 Sync Data'):
        st.cache_data.clear()
        st.rerun()

st.divider()

# --- 5. METRICS SECTION (DASHBOARD) ---
df = load_data()

if df.empty:
    st.info("Waiting for data stream...")
else:
    # Logic คำนวณ (เหมือนเดิม)
    total_trades = len(df)
    closed_trades = df[df['status'].isin(['TP', 'SL'])]
    wins = len(closed_trades[closed_trades['status'] == 'TP'])
    losses = len(closed_trades[closed_trades['status'] == 'SL'])
    open_trades = len(df[df['status'] == 'OPEN'])
    
    winrate = 0
    if len(closed_trades) > 0:
        winrate = (wins / len(closed_trades)) * 100

    # แสดงผลแบบ Grid (Mobile Friendly)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Signals", total_trades)
    m2.metric("Win Rate", f"{winrate:.0f}%")
    m3.metric("Wins", wins)
    m4.metric("Open Position", open_trades)

    st.markdown("<br>", unsafe_allow_html=True) # เว้นบรรทัด

    # --- 6. CHARTS & TABLES ---
    c1, c2 = st.columns([1, 2])

    with c1:
        st.markdown("### 📊 Performance")
        if len(closed_trades) > 0:
            # ใช้สีแบบ Neon: Cyan vs Hot Pink
            fig = px.donut(
                names=['Win', 'Loss'], 
                values=[wins, losses], 
                color=['Win', 'Loss'],
                color_discrete_map={'Win':'#00f2ff', 'Loss':'#ff0055'}, # สีตรงนี้ปรับให้เข้าธีม
                hole=0.6
            )
            # ปรับพื้นหลังกราฟให้โปร่งใส
            fig.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                showlegend=False,
                margin=dict(t=0, b=0, l=0, r=0),
                font=dict(color='white')
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # ใส่ข้อความตรงกลางโดนัท
            st.markdown(f"""
            <div style="text-align: center; margin-top: -150px; margin-bottom: 120px;">
                <h2 style="margin:0; color:white;">{winrate:.0f}%</h2>
                <p style="margin:0; color:#aaa;">Success Rate</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.warning("No closed trades yet.")

    with c2:
        st.markdown("### 📜 Live Signals")
        
        # ฟังก์ชันแต่งสีในตาราง
        def highlight_status(val):
            color = ''
            if val == 'TP': color = 'color: #00ff00; font-weight: bold;'
            elif val == 'SL': color = 'color: #ff0055; font-weight: bold;'
            elif val == 'OPEN': color = 'color: #00f2ff; font-weight: bold;'
            return color

        # เลือกเฉพาะคอลัมน์ที่จำเป็นและแสดงผล
        display_df = df[['time', 'symbol', 'side', 'entry', 'tp', 'status']].sort_values(by='time', ascending=False)
        
        st.dataframe(
            display_df.style.applymap(highlight_status, subset=['status']),
            use_container_width=True,
            height=350,
            hide_index=True
        )
