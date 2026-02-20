import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# --- 1. SETUP & THEME ---
st.set_page_config(
    page_title="Crypto Bot AI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for Cyberpunk/Pro Look
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&display=swap');
        
        .stApp {
            background-color: #0e1117;
            font-family: 'Rajdhani', sans-serif;
        }
        
        /* Metric Cards */
        div[data-testid="stMetric"] {
            background-color: #1e2130;
            border: 1px solid #2d3446;
            padding: 15px;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        div[data-testid="stMetricValue"] {
            font-size: 28px !important;
            font-weight: 700;
        }
        
        /* Table Headers */
        thead tr th:first-child {display:none}
        tbody th {display:none}
        
        /* Header */
        h1, h2, h3 {
            color: #e0e0e0;
            letter-spacing: 1px;
        }
    </style>
""", unsafe_allow_html=True)

# --- 2. DATA LOADING ---
CSV_URL = "https://raw.githubusercontent.com/FiRSTTX/MyCRYPTO-BOT/main/signals.csv"

@st.cache_data(ttl=60)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        return df
    except:
        return pd.DataFrame()

# --- 3. UI LAYOUT ---

# Top Bar
c1, c2 = st.columns([0.8, 0.2])
with c1:
    st.title("⚡ AI TRADING TERMINAL")
    st.caption("Auto-Trading Bot Control Center | Strategy: EMA200 + RSI")
with c2:
    if st.button("🔄 REFRESH DATA", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

df = load_data()

if df.empty:
    st.info("Waiting for signals...")
else:
    # --- 4. METRICS ROW ---
    total = len(df)
    active = len(df[df['status'] == 'OPEN'])
    
    # Calculate Winrate
    closed = df[df['status'].isin(['TP', 'SL'])]
    wins = len(closed[closed['status'] == 'TP'])
    losses = len(closed[closed['status'] == 'SL'])
    winrate = (wins / len(closed) * 100) if len(closed) > 0 else 0
    
    # Calculate Estimated PnL (สมมติ TP=$15, SL=-$10 ตาม Risk Config)
    est_pnl = (wins * 15) - (losses * 10) 
    pnl_color = "normal" if est_pnl >= 0 else "inverse"

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Signals", total, delta=f"{active} Active", delta_color="off")
    m2.metric("Win Rate", f"{winrate:.1f}%", delta="Target > 50%")
    m3.metric("Est. Net Profit", f"${est_pnl}", delta_color=pnl_color)
    m4.metric("Risk per Trade", "$10", "Fixed")

    st.markdown("---")

    # --- 5. CHARTS ROW ---
    col_chart1, col_chart2 = st.columns([1, 2])
    
    with col_chart1:
        st.subheader("📊 Performance")
        if len(closed) > 0:
            # Modern Donut Chart
            fig = go.Figure(data=[go.Pie(
                labels=['Win', 'Loss'], 
                values=[wins, losses], 
                hole=.6,
                marker_colors=['#00e676', '#ff1744'] # Green/Red Neon
            )])
            fig.update_layout(
                showlegend=True,
                margin=dict(t=0, b=0, l=0, r=0),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='white'),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No closed trades to analyze yet.")

    with col_chart2:
        st.subheader("📜 Active & Recent Log")
        
        # จัดเตรียมข้อมูลตาราง
        view_df = df[['time', 'symbol', 'side', 'entry', 'margin', 'status', 'reason']].copy()
        view_df = view_df.sort_values(by='time', ascending=False)

        # ใช้ st.dataframe แบบใหม่ (Column Config) สวยมาก!
        st.dataframe(
            view_df,
            use_container_width=True,
            height=400,
            column_config={
                "time": st.column_config.DatetimeColumn("Time", format="D MMM, HH:mm"),
                "symbol": st.column_config.TextColumn("Coin", help="Trading Pair"),
                "side": st.column_config.TextColumn("Side"),
                "entry": st.column_config.NumberColumn("Entry Price", format="$%.2f"),
                "margin": st.column_config.ProgressColumn(
                    "Margin Used", 
                    format="$%.2f", 
                    min_value=0, 
                    max_value=20, # ปรับ Max ตามขนาดไม้เฉลี่ยของคุณ
                ),
                "status": st.column_config.TextColumn("Status"),
                "reason": st.column_config.TextColumn("Signal Logic"),
            },
            hide_index=True
        )

# --- 6. FOOTER ---
st.markdown("""
    <div style='text-align: center; color: #666; margin-top: 50px; font-size: 12px;'>
        POWERED BY GITHUB ACTIONS & STREAMLIT | KRAKEN EXCHANGE
    </div>
""", unsafe_allow_html=True)
