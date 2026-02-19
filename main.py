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
# ⚙️ CONFIG (OKX EDITION)
# ==========================================
PORTFOLIO_SIZE = 100         # เงินทุน (USDT)
RISK_PER_TRADE = 0.02       # ความเสี่ยง 2%
MAX_LEVERAGE_LIMIT = 10     # Leverage สูงสุด
RR_RATIO = 1.5              # Risk:Reward 1:1.5

# 🔑 Secrets
TELEGRAM_TOKEN = 'YOUR_TOKEN' 
TELEGRAM_CHAT_ID = 'YOUR_CHAT_ID'
GDRIVE_API_CREDENTIALS = os.environ.get('GDRIVE_API_CREDENTIALS')

# ⚠️ OKX API CONFIG
OKX_API_KEY = '514d91e8-02ea-4e04-8cfb-a6237dab9257'
OKX_SECRET = '88EFEBD9CA4CD391601F0F1ECFCBC646'
OKX_PASSWORD = 'FTonepiece-1637'  # <--- ใส่ Passphrase ที่ตั้งตอนสร้าง Key
PROXY_URL = os.environ.get('PROXY_URL') # ดึง Proxy จาก Secrets

# 💱 Exchange Setup (OKX Futures)
config = {
    'apiKey': OKX_API_KEY,
    'secret': OKX_SECRET,
    'password': OKX_PASSWORD,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',
    }
}

# 👇 เพิ่ม Logic การใส่ Proxy (ถ้ามี)
if PROXY_URL:
    print(f"🌍 Using Proxy: {PROXY_URL[:10]}...******") # ปริ้นท์เช็คแต่ปิดบังข้อมูลสำคัญ
    config['proxies'] = {
        'http': PROXY_URL,
        'https': PROXY_URL,
    }
exchange = ccxt.okx(config)    
# 🛠️ เปิดโหมด Demo (ถ้าจะเทรดจริงให้ลบบรรทัดนี้ทิ้ง หรือแก้เป็น False)
exchange.set_sandbox_mode(True) 

# คู่เหรียญสำหรับ Futures (ต้องลงท้ายด้วย :USDT)
SYMBOLS = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'DOGE/USDT:USDT', 'XRP/USDT:USDT']
TIMEFRAME = '1h'

# ==========================================
# 🧮 INDICATORS & MATH (เหมือนเดิม)
# ==========================================
def calculate_indicators(df):
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    df['swing_low'] = df['low'].rolling(window=20).min()
    df['swing_high'] = df['high'].rolling(window=20).max()

    return df

def get_fib_level(high, low, level):
    return high - ((high - low) * level)

# ==========================================
# 🛡️ RISK MANAGEMENT (ปรับให้เข้ากับ OKX)
# ==========================================
def calculate_position_size(entry_price, stop_loss):
    sl_distance = abs(entry_price - stop_loss)
    sl_percent = sl_distance / entry_price
    if sl_percent == 0: return 0, 1, 0, 0

    risk_amount = PORTFOLIO_SIZE * RISK_PER_TRADE
    position_size_usd = risk_amount / sl_percent
    
    safe_leverage = int(1 / (sl_percent * 1.5))
    final_leverage = min(safe_leverage, MAX_LEVERAGE_LIMIT)
    if final_leverage < 1: final_leverage = 1

    # คำนวณจำนวนเหรียญ (Contracts)
    # OKX ขั้นต่ำในการซื้อขายต่างกันไป แต่เราคำนวณเป็น USD ก่อน
    amount_coin = position_size_usd / entry_price
    
    margin_cost = position_size_usd / final_leverage
    return amount_coin, final_leverage, margin_cost, sl_percent * 100

# ==========================================
# ☁️ GOOGLE SHEETS & TELEGRAM
# ==========================================
def log_to_sheet(timestamp, symbol, side, entry, tp, sl):
    try:
        if not GDRIVE_API_CREDENTIALS: return
        creds_dict = json.loads(GDRIVE_API_CREDENTIALS)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("CryptoBot_Logs").sheet1
        sheet.append_row([timestamp, symbol, side, entry, tp, sl, "OKX-Demo"])
    except: pass

def send_telegram(message):
    try:
        if not TELEGRAM_TOKEN: return
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'})
    except: pass

# ==========================================
# 🧠 CORE LOGIC (OKX EXECUTION)
# ==========================================
def analyze_market(symbol):
    try:
        print(f"🔍 Checking {symbol} on OKX...")
        # OKX limits: ดึง 100 แท่งพอกันเหนียว
        bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=300)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = calculate_indicators(df)
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        curr_price = last['close']

        signal = None
        setup_reason = ""
        stop_loss = 0
        take_profit = 0
        
        recent_high = df['swing_high'].iloc[-2]
        recent_low = df['swing_low'].iloc[-2]
        fib_05 = get_fib_level(recent_high, recent_low, 0.5)

        # Signal Logic (เหมือนเดิม)
        if (prev['close'] > prev['ema200'] and prev['close'] > prev['ema50'] and
            40 < prev['rsi'] < 70 and prev['macd'] > prev['signal'] and curr_price >= fib_05):
            signal = "LONG 🚀"
            stop_loss = recent_low * 0.995
            take_profit = curr_price + ((curr_price - stop_loss) * RR_RATIO)
            setup_reason = "OKX Bullish Confluence"

        elif (prev['close'] < prev['ema200'] and prev['close'] < prev['ema50'] and
              30 < prev['rsi'] < 60 and prev['macd'] < prev['signal'] and curr_price <= fib_05):
            signal = "SHORT 🔻"
            stop_loss = recent_high * 1.005
            take_profit = curr_price - ((stop_loss - curr_price) * RR_RATIO)
            setup_reason = "OKX Bearish Confluence"

        # Execution Logic (จุดที่เปลี่ยนสำหรับ OKX)
        if signal:
            amount_coin, leverage, margin, sl_pct = calculate_position_size(curr_price, stop_loss)
            
            # ⚠️ OKX Specific Params
            params = {
                'tdMode': 'cross',      # ใช้โหมด Cross Margin (เงินทั้งพอร์ตค้ำ)
                'posSide': 'net',       # Net Mode (ซื้อขายทางเดียว ไม่ใช่ Hedge)
                'leverage': leverage,
            }

            msg = (
                f"🚨 *OKX SIGNAL: {signal}*\n"
                f"Coin: #{symbol.split('/')[0]}\n"
                f"Price: {curr_price:.4f}\n"
                f"-------------------\n"
                f"Lev: x{leverage} (Cross)\n"
                f"Size: {amount_coin:.4f} {symbol.split('/')[0]}\n"
                f"Margin: ${margin:.2f}\n"
            )
            
            print(f"✅ SIGNAL: {signal} | Lev: x{leverage}")
            send_telegram(msg)
            
            # ถ้าจะยิงออเดอร์จริง ให้ Uncomment บรรทัดล่างนี้
            # exchange.create_order(symbol, 'market', signal.split()[0].lower(), amount_coin, params=params)

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_to_sheet(now_str, symbol, signal, curr_price, take_profit, stop_loss)

    except Exception as e:
        print(f"❌ Error {symbol}: {e}")

if __name__ == "__main__":
    # บังคับเปิด Sandbox Mode ตรงนี้เลยเพื่อความชัวร์
    exchange.set_sandbox_mode(True) 
    
    print("🤖 OKX Bot Started (Sandbox: Active)") # <-- แก้ข้อความตรงนี้ให้เป็น text ธรรมดา
    
    for coin in SYMBOLS:
        analyze_market(coin)
        time.sleep(1)



