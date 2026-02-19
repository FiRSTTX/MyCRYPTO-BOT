import ccxt
import pandas as pd
import requests
import os
import sys
import json
import time
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# ==========================================
# ⚙️ CONFIG (ตั้งค่าส่วนตัว)
# ==========================================
PORTFOLIO_SIZE = 50         # เงินทุนในพอร์ต (USDT)
RISK_PER_TRADE = 0.02       # ยอมขาดทุน 2% ต่อไม้
MAX_LEVERAGE_LIMIT = 10     # Leverage สูงสุดที่จะยอมใช้
RR_RATIO = 1.5              # Risk:Reward Ratio (เสีย 1 ได้ 1.5)

# 🔑 Secrets (Telegram & Google Drive)
TELEGRAM_TOKEN = '8524742326:AAG41qwiKCr9HYzQXzCf0bAooaOAwzqg75k' 
TELEGRAM_CHAT_ID = '1623135330'
GDRIVE_API_CREDENTIALS = os.environ.get('GDRIVE_API_CREDENTIALS')

# 💱 Exchange Config (Kraken Spot)
exchange = ccxt.kraken({'enableRateLimit': True})
SYMBOLS = ['BTC/USD', 'ETH/USD', 'SOL/USD', 'XRP/USD', 'DOGE/USD']
TIMEFRAME = '1h'

# ==========================================
# 🧮 INDICATORS & MATH
# ==========================================
def calculate_indicators(df):
    # 1. EMA Trend Filter
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

    # 2. RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # 3. MACD (12, 26, 9)
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['hist'] = df['macd'] - df['signal']

    # 4. Swing High/Low (สำหรับหา SL และ Fibonacci ในรอบ 20 แท่ง)
    df['swing_low'] = df['low'].rolling(window=20).min()
    df['swing_high'] = df['high'].rolling(window=20).max()

    return df

def get_fib_level(high, low, level):
    return high - ((high - low) * level)

# ==========================================
# 🛡️ RISK MANAGEMENT
# ==========================================
def calculate_position_size(entry_price, stop_loss):
    # หาระยะ Stop Loss เป็น %
    sl_distance = abs(entry_price - stop_loss)
    sl_percent = sl_distance / entry_price

    if sl_percent == 0: return 0, 1, 0, 0 # กัน Error หาร 0

    # คำนวณเงินที่ยอมเสียได้ (Risk Amount)
    risk_amount = PORTFOLIO_SIZE * RISK_PER_TRADE

    # คำนวณขนาด Position ทั้งหมด (Notional Value)
    position_size_usd = risk_amount / sl_percent

    # คำนวณ Leverage ที่ปลอดภัย (จุด Liquidation ไกลกว่า SL เสมอ)
    safe_leverage = int(1 / (sl_percent * 1.5))
    final_leverage = min(safe_leverage, MAX_LEVERAGE_LIMIT)
    if final_leverage < 1: final_leverage = 1

    # คำนวณ Margin (เงินต้นที่ต้องวางจริง)
    margin_cost = position_size_usd / final_leverage

    return position_size_usd, final_leverage, margin_cost, sl_percent * 100

# ==========================================
# ☁️ GOOGLE SHEETS LOGGING
# ==========================================
def log_to_sheet(timestamp, symbol, side, entry, tp, sl):
    try:
        if not GDRIVE_API_CREDENTIALS:
            print("⚠️ No Google Sheet Credentials (Skip Logging)")
            return

        creds_dict = json.loads(GDRIVE_API_CREDENTIALS)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        sheet = client.open("CryptoBot_Logs").sheet1
        row = [timestamp, symbol, side, entry, tp, sl, "Waiting"]
        sheet.append_row(row)
        print("✅ Sheet Updated")
    except Exception as e:
        print(f"❌ Sheet Error: {e}")

# ==========================================
# 📡 TELEGRAM NOTIFICATION
# ==========================================
def send_telegram(message):
    try:
        if not TELEGRAM_TOKEN: return
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'})
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

# ==========================================
# 🧠 CORE LOGIC (CONFLUENCE STRATEGY)
# ==========================================
def analyze_market(symbol):
    try:
        print(f"🔍 Checking {symbol}...")
        bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=300)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = calculate_indicators(df)
        
        last = df.iloc[-1]   # แท่งปัจจุบัน
        prev = df.iloc[-2]   # แท่งก่อนหน้า (ใช้ยืนยันสัญญาณ)
        curr_price = last['close']

        signal = None
        setup_reason = ""
        stop_loss = 0
        take_profit = 0
        
        # ดึงค่า Fibonacci จาก Swing ล่าสุด
        recent_high = df['swing_high'].iloc[-2]
        recent_low = df['swing_low'].iloc[-2]
        fib_05 = get_fib_level(recent_high, recent_low, 0.5)

        # 🟢 LONG CONDITIONS
        if (prev['close'] > prev['ema200']) and (prev['close'] > prev['ema50']):
            if (prev['rsi'] > 40 and prev['rsi'] < 70):
                if (prev['macd'] > prev['signal']):  
                     if (curr_price >= fib_05):      
                        signal = "LONG 🚀"
                        stop_loss = recent_low * 0.995 
                        risk_dist = curr_price - stop_loss
                        take_profit = curr_price + (risk_dist * RR_RATIO)
                        setup_reason = "Trend Up + MACD Cross + Above Fib 0.5"

        # 🔴 SHORT CONDITIONS
        elif (prev['close'] < prev['ema200']) and (prev['close'] < prev['ema50']):
             if (prev['rsi'] < 60 and prev['rsi'] > 30):
                if (prev['macd'] < prev['signal']):  
                    if (curr_price <= fib_05):       
                        signal = "SHORT 🔻"
                        stop_loss = recent_high * 1.005
                        risk_dist = stop_loss - curr_price
                        take_profit = curr_price - (risk_dist * RR_RATIO)
                        setup_reason = "Trend Down + MACD Cross + Below Fib 0.5"

        # 🎯 ACTION & EXECUTION
        if signal:
            pos_size, leverage, margin, sl_pct = calculate_position_size(curr_price, stop_loss)
            
            msg = (
                f"🚨 *CONFLUENCE SIGNAL: {signal}*\n"
                f"Coin: #{symbol.split('/')[0]}\n"
                f"Price: {curr_price:.4f}\n"
                f"Reason: {setup_reason}\n"
                f"----------------------------\n"
                f"🛡️ *Risk Management*\n"
                f"Entry: {curr_price:.4f}\n"
                f"TP: {take_profit:.4f} (RR 1:{RR_RATIO})\n"
                f"SL: {stop_loss:.4f} (-{sl_pct:.2f}%)\n"
                f"Max Risk: ${PORTFOLIO_SIZE * RISK_PER_TRADE:.2f}\n"
                f"----------------------------\n"
                f"⚡ *Execution Setup*\n"
                f"Lev: x{leverage}\n"
                f"Margin Use: ${margin:.2f}\n"
                f"Position Size: ${pos_size:.2f}"
            )
            
            print(f"✅ SIGNAL FOUND: {signal} on {symbol}")
            send_telegram(msg)
            
            # บันทึกลง Google Sheets
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_to_sheet(now_str, symbol, signal, curr_price, take_profit, stop_loss)
            
        else:
            print(f"   Status: No Signal | RSI: {prev['rsi']:.1f}")

    except Exception as e:
        print(f"❌ Error analysis {symbol}: {e}")

# ==========================================
# 🚀 MAIN RUNNER
# ==========================================
if __name__ == "__main__":
    print("========================================")
    print(f"🤖 Bot V2 Started | Confluence + Risk Mgmt")
    print(f"💼 Port: ${PORTFOLIO_SIZE} | Risk: {RISK_PER_TRADE*100}% | Max Lev: x{MAX_LEVERAGE_LIMIT}")
    print("========================================")
    
    for coin in SYMBOLS:
        analyze_market(coin)
        time.sleep(1) # พัก 1 วินาทีป้องกัน Rate Limit จาก Exchange
        
    print("========================================")
    print("✅ All pairs checked. Done.")
