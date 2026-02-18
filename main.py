import ccxt
import pandas as pd
import requests
import os
import sys
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# ==========================================
# ⚙️ CONFIG
# ==========================================
PORTFOLIO_SIZE = 50   # แก้เป็นเงินพอร์ตจริง (USDT)
RISK_PER_TRADE = 0.02 # ความเสี่ยง 2%
MAX_LEVERAGE = 10     # Leverage สูงสุด

# Secrets
# ใส่ Token ในเครื่องหมาย ' '
TELEGRAM_TOKEN = '8524742326:AAG41qwiKCr9HYzQXzCf0bAooaOAwzqg75k' 
# ใส่ Chat ID ในเครื่องหมาย ' '
TELEGRAM_CHAT_ID = '1623135330'
GDRIVE_API_CREDENTIALS = os.environ.get('GDRIVE_API_CREDENTIALS')

# Exchange (Kraken Spot)
exchange = ccxt.kraken({'enableRateLimit': True})
SYMBOLS = ['BTC/USD', 'ETH/USD', 'SOL/USD', 'XRP/USD', 'DOGE/USD']
TIMEFRAME = '1h'

# ==========================================
# 🧮 INDICATORS
# ==========================================
def calculate_indicators(df):
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df['atr'] = true_range.ewm(alpha=1/14, adjust=False).mean()

    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    return df

# ==========================================
# 💰 POSITION SIZING
# ==========================================
def calculate_position(entry_price, stop_loss):
    if entry_price == stop_loss: return 0, 1, 0 # กัน Error หาร 0
    
    sl_percent = abs(entry_price - stop_loss) / entry_price
    risk_amount = PORTFOLIO_SIZE * RISK_PER_TRADE
    position_value = risk_amount / sl_percent
    safe_leverage = min(int(1 / sl_percent), MAX_LEVERAGE)
    if safe_leverage < 1: safe_leverage = 1
    
    margin_cost = position_value / safe_leverage
    return position_value, safe_leverage, margin_cost

# ==========================================
# ☁️ GOOGLE SHEETS
# ==========================================
def log_to_sheet(timestamp, symbol, side, entry, tp, sl):
    try:
        if not GDRIVE_API_CREDENTIALS:
            print("⚠️ No Google Sheet Credentials")
            return

        creds_dict = json.loads(GDRIVE_API_CREDENTIALS)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # เปิด Sheet ชื่อ CryptoBot_Logs (ต้องสร้างรอก่อนนะ)
        sheet = client.open("CryptoBot_Logs").sheet1
        row = [timestamp, symbol, side, entry, tp, sl, "Waiting"]
        sheet.append_row(row)
        print("✅ Sheet Updated")
    except Exception as e:
        print(f"❌ Sheet Error: {e}")

# ==========================================
# 📡 TELEGRAM
# ==========================================
def send_telegram(message):
    try:
        if not TELEGRAM_TOKEN: return
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'})
    except: pass

# ==========================================
# 🧠 ANALYSIS LOGIC
# ==========================================
def analyze_market(symbol):
    try:
        print(f"🔍 Checking {symbol}...")
        bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=100)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = calculate_indicators(df)
        
        last = df.iloc[-2]
        curr_price = last['close']
        
        signal = None
        trend = "SIDEWAY"
        rsi = last['rsi']
        
        # --- UPTREND ---
        if last['close'] > last['ema50']:
            trend = "UPTREND 🟢"
            dist_to_ema = abs(last['low'] - last['ema50']) / last['ema50'] * 100
            if dist_to_ema <= 1.5 and last['close'] > last['open'] and rsi < 70:
                signal = "LONG 🚀"
                stop_loss = last['low'] - (last['atr'] * 1.5)
                take_profit = curr_price + ((curr_price - stop_loss) * 2)

        # --- DOWNTREND ---
        elif last['close'] < last['ema50']:
            trend = "DOWNTREND 🔴"
            dist_to_ema = abs(last['high'] - last['ema50']) / last['ema50'] * 100
            if dist_to_ema <= 1.5 and last['close'] < last['open'] and rsi > 30:
                signal = "SHORT 🔻"
                stop_loss = last['high'] + (last['atr'] * 1.5)
                take_profit = curr_price - ((stop_loss - curr_price) * 2)

        # --- ACTION ---
        if signal:
            # 1. คำนวณเงิน
            pos_size, lev, margin = calculate_position(curr_price, stop_loss)
            
            # 2. สร้างข้อความ (จุดที่เคย Error คือบรรทัดนี้หายไป หรือย่อหน้าผิด)
            msg = (
                f"🚨 *SIGNAL ALERT: {signal}*\n"
                f"Coin: #{symbol.split('/')[0]}\n"
                f"Price: {curr_price}\n"
                f"RSI: {rsi:.1f}\n"
                f"-------------------\n"
                f"Entry: {curr_price}\n"
                f"TP: {take_profit:.4f}\n"
                f"SL: {stop_loss:.4f}\n"
                f"-------------------\n"
                f"Lev: x{lev}\n"
                f"Size: {pos_size:.1f} USDT"
            )
            
            # 3. ส่ง Telegram
            print(f"✅ SIGNAL FOUND: {symbol}")
            send_telegram(msg)
            
            # 4. บันทึกลง Sheet
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_to_sheet(now_str, symbol, signal, curr_price, take_profit, stop_loss)

        else:
            print(f"   Status: {trend} | RSI: {rsi:.1f} | No Signal")

    except Exception as e:
        print(f"❌ Error {symbol}: {e}")

# ==========================================
# 🚀 MAIN RUNNER
# ==========================================
if __name__ == "__main__":
    print(f"🤖 Bot Started... Port: ${PORTFOLIO_SIZE} | Risk: {RISK_PER_TRADE*100}%")
    for coin in SYMBOLS:
        analyze_market(coin)
    print("✅ Done.")

