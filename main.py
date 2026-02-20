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
# 1. CONFIGURATION
# ==========================================

# การบริหารเงินทุน (Risk Management)
STOP_LOSS_PCT = 0.02  # ตั้ง SL ห่างจากราคาเข้า 2%
RR_RATIO = 1.5        # Risk:Reward = 1:1.5 (TP จะเป็น 3%)

# คู่เหรียญและ Timeframe
SYMBOLS = ['BTC/USD', 'ETH/USD', 'SOL/USD'] # Kraken มักใช้ USD แทน USDT ในคู่หลัก
TIMEFRAME = '1h'

# ไฟล์เก็บข้อมูล
SIGNAL_FILE = "signals.csv"

# Credentials (ดึงจาก Environment Variables เพื่อความปลอดภัย)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GDRIVE_API_CREDENTIALS = os.environ.get("GDRIVE_API_CREDENTIALS")

# ตั้งค่า Exchange: KRAKEN
exchange = ccxt.kraken({
    'enableRateLimit': True,
    # 'apiKey': 'YOUR_API_KEY', # ใส่ถ้าต้องการเทรดจริง
    # 'secret': 'YOUR_SECRET',
})

# ==========================================
# 2. HELPER FUNCTIONS (Telegram & Sheets)
# ==========================================

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg
        }, timeout=10)
    except Exception as e:
        print(f"Error sending Telegram: {e}")

def log_to_sheet(row):
    if not GDRIVE_API_CREDENTIALS:
        return

    try:
        creds_dict = json.loads(GDRIVE_API_CREDENTIALS)
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # เปิดชีทชื่อ CryptoBot (ต้องสร้างไฟล์ชื่อนี้รอไว้ใน Google Drive)
        sheet = client.open("CryptoBot").sheet1
        sheet.append_row(row)
        print("Logged to Google Sheet successfully.")
    except Exception as e:
        print(f"Error logging to Sheet: {e}")

# ==========================================
# 3. TECHNICAL INDICATORS
# ==========================================

def indicators(df):
    # EMA
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['ema200'] = df['close'].ewm(span=200).mean()

    # RSI (Standard Wilder's Smoothing)
    delta = df['close'].diff()
    
    # แยกกำไร/ขาดทุน
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    # ใช้ ewm แทน rolling เพื่อความแม่นยำแบบ TradingView
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()

    rs = avg_gain / avg_loss
    df['rsi'] = 100 - (100 / (1 + rs))

    return df

# ==========================================
# 4. SIGNAL MANAGEMENT (CSV)
# ==========================================

def save_signal(data):
    df = pd.DataFrame([data])
    if os.path.exists(SIGNAL_FILE):
        df.to_csv(SIGNAL_FILE, mode='a', header=False, index=False)
    else:
        df.to_csv(SIGNAL_FILE, index=False)

def check_open_orders(symbol):
    """เช็คว่ามีออเดอร์ของเหรียญนี้ค้างอยู่หรือไม่"""
    if not os.path.exists(SIGNAL_FILE):
        return False
    
    try:
        df = pd.read_csv(SIGNAL_FILE)
        # กรองดูว่ามี symbol นี้ และ status เป็น OPEN หรือไม่
        open_trades = df[(df['symbol'] == symbol) & (df['status'] == 'OPEN')]
        return not open_trades.empty
    except pd.errors.EmptyDataError:
        return False

def update_signals():
    """เช็คราคาปัจจุบันเพื่อตัด TP/SL"""
    if not os.path.exists(SIGNAL_FILE):
        return

    try:
        df = pd.read_csv(SIGNAL_FILE)
        if df.empty: return
    except:
        return

    updated = False

    for i, row in df.iterrows():
        if row['status'] != "OPEN":
            continue

        symbol = row['symbol']
        
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
        except Exception as e:
            print(f"Error fetching ticker for {symbol}: {e}")
            continue

        # Logic การตัด TP/SL
        new_status = None
        
        if row['side'] == "LONG":
            if current_price >= row['tp']:
                new_status = "TP"
            elif current_price <= row['sl']:
                new_status = "SL"

        elif row['side'] == "SHORT":
            if current_price <= row['tp']:
                new_status = "TP"
            elif current_price >= row['sl']:
                new_status = "SL"

        # ถ้าสถานะเปลี่ยน ให้บันทึกและแจ้งเตือน
        if new_status:
            df.at[i, 'status'] = new_status
            updated = True
            msg = f"⚠ CLOSE {symbol} ({row['side']})\nResult: {new_status}\nPrice: {current_price}"
            print(msg)
            send_telegram(msg)

    if updated:
        df.to_csv(SIGNAL_FILE, index=False)

# ==========================================
# 5. ANALYSIS CORE
# ==========================================

def analyze(symbol):
    print(f"Analyzing {symbol}...")

    # 1. เช็คก่อนว่ามีออเดอร์ค้างไหม (ป้องกัน Signal ซ้ำ)
    if check_open_orders(symbol):
        print(f"Skipping {symbol}: Position already OPEN.")
        return

    try:
        # ดึงกราฟย้อนหลัง
        bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=100)
        df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        
        # คำนวณอินดิเคเตอร์
        df = indicators(df)

        last = df.iloc[-1]  # แท่งปัจจุบัน
        prev = df.iloc[-2]  # แท่งก่อนหน้า (ที่จบแท่งแล้ว)

        price = last['close']
        signal = None

        # --- STRATEGY LOGIC ---
        # Long: ราคาปิดเหนือ EMA200 และ RSI > 50
        if prev['close'] > prev['ema200'] and prev['rsi'] > 50:
            signal = "LONG"

        # Short: ราคาปิดต่ำกว่า EMA200 และ RSI < 50
        if prev['close'] < prev['ema200'] and prev['rsi'] < 50:
            signal = "SHORT"
        
        if not signal:
            return

        # --- RISK CALCULATION ---
        # คำนวณ TP/SL ตาม Config
        if signal == "LONG":
            sl = price * (1 - STOP_LOSS_PCT)
            tp = price * (1 + (STOP_LOSS_PCT * RR_RATIO))
        elif signal == "SHORT":
            sl = price * (1 + STOP_LOSS_PCT)
            tp = price * (1 - (STOP_LOSS_PCT * RR_RATIO))

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # เตรียมข้อมูลบันทึก
        data = {
            "time": now,
            "symbol": symbol,
            "side": signal,
            "entry": price,
            "tp": round(tp, 4), # ปัดเศษเพื่อความสวยงาม
            "sl": round(sl, 4),
            "status": "OPEN"
        }

        # บันทึก CSV
        save_signal(data)

        # ส่ง Telegram
        msg = f"🚀 NEW SIGNAL: {signal}\n\nSymbol: {symbol}\nEntry: {price}\nTP: {data['tp']}\nSL: {data['sl']}\nTime: {TIMEFRAME}"
        send_telegram(msg)

        # บันทึก Google Sheet
        log_to_sheet([
            str(now), symbol, signal, price, data['tp'], data['sl'], "OPEN"
        ])

    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")

# ==========================================
# 6. MAIN LOOP
# ==========================================

def run():
    print("--- Bot Started (Kraken) ---")
    while True:
        try:
            # 1. อัปเดตสถานะออเดอร์เก่า (Check TP/SL)
            update_signals()

            # 2. หาจังหวะเข้าออเดอร์ใหม่
            for s in SYMBOLS:
                analyze(s)
                time.sleep(1) # พักเล็กน้อยระหว่างเหรียญ

            # 3. รอเวลาก่อนวนรอบใหม่ (เช่น ทุก 1 นาที)
            print("Waiting for next cycle...")
            time.sleep(60) 

        except KeyboardInterrupt:
            print("Bot stopped by user.")
            break
        except Exception as e:
            print(f"Global Error: {e}")
            time.sleep(10) # ถ้า Error ให้พัก 10 วิแล้วลองใหม่

if __name__ == "__main__":
    run()
