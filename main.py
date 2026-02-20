import ccxt
import pandas as pd
import requests
import os
import json
import time
import numpy as np
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. CONFIGURATION (ปรับปรุงใหม่)
# ==========================================

# --- การตั้งค่าความเสี่ยง (Money Management) ---
ACCOUNT_BALANCE = 1000  # สมมติเงินในพอร์ต $1,000 (ใช้คำนวณ Position Sizing)
RISK_PER_TRADE_USD = 10 # ยอมเสียได้ $10 ต่อไม้ (Fix Risk)
LEVERAGE = 10           # เลเวอเรจ x10

# RR Ratio
RR_RATIO = 1.5
STOP_LOSS_PCT = 0.02    # ระยะ SL 2%

# คู่เหรียญและ Timeframe
SYMBOLS = ['BTC/USD', 'ETH/USD', 'SOL/USD']
TIMEFRAME = '1h'

SIGNAL_FILE = "signals.csv"

# Credentials
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GDRIVE_API_CREDENTIALS = os.environ.get("GDRIVE_API_CREDENTIALS")

exchange = ccxt.kraken({
    'enableRateLimit': True,
})

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"Error sending Telegram: {e}")

def log_to_sheet(row):
    if not GDRIVE_API_CREDENTIALS: return
    try:
        creds_dict = json.loads(GDRIVE_API_CREDENTIALS)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("CryptoBot").sheet1
        sheet.append_row(row)
    except Exception as e:
        print(f"Error logging to Sheet: {e}")

# ==========================================
# 3. INDICATORS
# ==========================================

def indicators(df):
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['ema200'] = df['close'].ewm(span=200).mean()
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss
    df['rsi'] = 100 - (100 / (1 + rs))
    return df

# ==========================================
# 4. SIGNAL MANAGEMENT
# ==========================================

def save_signal(data):
    df = pd.DataFrame([data])
    if os.path.exists(SIGNAL_FILE):
        df.to_csv(SIGNAL_FILE, mode='a', header=False, index=False)
    else:
        df.to_csv(SIGNAL_FILE, index=False)

def update_signals():
    if not os.path.exists(SIGNAL_FILE): return
    try:
        df = pd.read_csv(SIGNAL_FILE)
        if df.empty: return
    except: return

    updated = False
    for i, row in df.iterrows():
        if row['status'] != "OPEN": continue
        
        symbol = row['symbol']
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
        except: continue

        new_status = None
        if row['side'] == "LONG":
            if current_price >= row['tp']: new_status = "TP"
            elif current_price <= row['sl']: new_status = "SL"
        elif row['side'] == "SHORT":
            if current_price <= row['tp']: new_status = "TP"
            elif current_price >= row['sl']: new_status = "SL"

        if new_status:
            df.at[i, 'status'] = new_status
            updated = True
            # ส่งแจ้งเตือนปิดออเดอร์
            emoji = "✅" if new_status == "TP" else "❌"
            msg = f"{emoji} <b>CLOSE SIGNAL</b>\nCoin: {symbol}\nResult: <b>{new_status}</b>\nPrice: {current_price}"
            send_telegram(msg)

    if updated: df.to_csv(SIGNAL_FILE, index=False)

def check_open_orders(symbol):
    if not os.path.exists(SIGNAL_FILE): return False
    try:
        df = pd.read_csv(SIGNAL_FILE)
        return not df[(df['symbol'] == symbol) & (df['status'] == 'OPEN')].empty
    except: return False

# ==========================================
# 5. ANALYSIS CORE (หัวใจหลักที่แก้ใหม่)
# ==========================================

def analyze(symbol):
    print(f"Analyzing {symbol}...")
    if check_open_orders(symbol):
        print(f"Skipping {symbol}: Position already OPEN.")
        return

    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=100)
        df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df = indicators(df)

        last = df.iloc[-1]
        prev = df.iloc[-2]
        price = last['close']
        signal = None
        reason = ""

        # --- LOGIC ---
        if prev['close'] > prev['ema200'] and prev['rsi'] > 50:
            signal = "LONG"
            reason = "Price > EMA200 + RSI Bullish"

        if prev['close'] < prev['ema200'] and prev['rsi'] < 50:
            signal = "SHORT"
            reason = "Price < EMA200 + RSI Bearish"
        
        if not signal: return

        # --- MONEY MANAGEMENT CALCULATION ---
        # 1. คำนวณราคา TP/SL
        if signal == "LONG":
            sl = price * (1 - STOP_LOSS_PCT)
            tp = price * (1 + (STOP_LOSS_PCT * RR_RATIO))
        elif signal == "SHORT":
            sl = price * (1 + STOP_LOSS_PCT)
            tp = price * (1 - (STOP_LOSS_PCT * RR_RATIO))

        # 2. คำนวณ Position Sizing (สูตร: Risk $ / ระยะ SL %)
        sl_distance_pct = abs(price - sl) / price
        position_size_usd = RISK_PER_TRADE_USD / sl_distance_pct
        
        # 3. คำนวณ Margin ที่ต้องใช้จริง
        margin_use = position_size_usd / LEVERAGE

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # --- DATA PREPARATION ---
        data = {
            "time": now,
            "symbol": symbol,
            "side": signal,
            "entry": price,
            "tp": round(tp, 4),
            "sl": round(sl, 4),
            "status": "OPEN",
            "leverage": LEVERAGE,
            "margin": round(margin_use, 2),
            "position_size": round(position_size_usd, 2),
            "reason": reason
        }

        save_signal(data)

        # --- TELEGRAM MESSAGE FORMAT (ตามรูปตัวอย่าง) ---
        msg = f"""
Coin: <b>#{symbol.split('/')[0]}</b>
Price: {price}
Reason: {reason}
-----------------------------
🛡️ <b>Risk Management</b>
Entry: {price}
TP: {round(tp, 4)} (RR 1:{RR_RATIO})
SL: {round(sl, 4)} ({STOP_LOSS_PCT*100}%)
Max Risk: ${RISK_PER_TRADE_USD}
-----------------------------
⚡ <b>Execution Setup</b>
Lev: x{LEVERAGE}
Margin Use: ${round(margin_use, 2)}
Position Size: ${round(position_size_usd, 2)}
"""
        send_telegram(msg)

        # Log to Sheet (เพิ่มคอลัมน์ใหม่ต่อท้าย)
        log_to_sheet([
            str(now), symbol, signal, price, data['tp'], data['sl'], "OPEN",
            LEVERAGE, data['margin'], data['position_size'], reason
        ])

    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")
        # raise e # uncomment for debug

# ==========================================
# 6. RUN
# ==========================================

def run():
    print("--- Bot Started (Rich Notification) ---")
    try:
        update_signals()
        for s in SYMBOLS:
            analyze(s)
            time.sleep(1)
        print("--- Job Finished ---")
    except Exception as e:
        print(f"Global Error: {e}")
        raise e

if __name__ == "__main__":
    run()
