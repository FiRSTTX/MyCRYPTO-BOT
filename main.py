import ccxt
import pandas as pd
import requests
import os
import sys

# ==========================================
# ⚙️ CONFIG & SECRETS
# ==========================================

# ดึงค่าจาก GitHub Secrets (เพื่อความปลอดภัย)
TELEGRAM_TOKEN = os.environ.get('8524742326:AAG41qwiKCr9HYzQXzCf0bAooaOAwzqg75k')
TELEGRAM_CHAT_ID = os.environ.get('1623135330')

# ถ้าไม่มี Secret (เช่น รันในคอมตัวเอง) ให้ใส่ค่าตรงนี้แทนได้ (ไม่แนะนำถ้าเอาขึ้น Git)
# TELEGRAM_TOKEN = 'YOUR_TOKEN' 
# TELEGRAM_CHAT_ID = 'YOUR_CHAT_ID'

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ Error: ไม่พบ TELEGRAM_TOKEN หรือ TELEGRAM_CHAT_ID ใน Environment Variables")
    sys.exit(1) # จบการทำงานแบบ Error

# ตั้งค่า Binance (Public Data Only)
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

# รายชื่อเหรียญ
SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 
    'BNB/USDT', 'XRP/USDT', 'DOGE/USDT'
]

TIMEFRAME = '1h'

# ==========================================
# 🧮 INDICATORS (No Library)
# ==========================================
def calculate_indicators(df):
    # EMA 50
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    # ATR 14
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df['atr'] = true_range.ewm(alpha=1/14, adjust=False).mean()
    
    return df

# ==========================================
# 📡 TELEGRAM SENDER
# ==========================================
def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'Markdown'
        }
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"❌ Telegram Error: {response.text}")
    except Exception as e:
        print(f"❌ Telegram Exception: {e}")

# ==========================================
# 🧠 ANALYSIS LOGIC
# ==========================================
def analyze_market(symbol):
    try:
        print(f"🔍 Checking {symbol}...")
        bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=100)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df = calculate_indicators(df)
        
        # ข้อมูลแท่งที่แล้ว (Confirmed Candle)
        last = df.iloc[-2]
        curr_price = last['close']
        
        signal = None
        trend = "SIDEWAY"
        
        # --- UPTREND LOGIC ---
        if last['close'] > last['ema50']:
            trend = "UPTREND 🟢"
            dist_to_ema = abs(last['low'] - last['ema50']) / last['ema50'] * 100
            
            # Pullback Condition (<= 1.5% from EMA) + Green Candle
            if dist_to_ema <= 1.5 and last['close'] > last['open']:
                signal = "LONG 🚀"
                stop_loss = last['low'] - (last['atr'] * 0.5)
                take_profit = curr_price + ((curr_price - stop_loss) * 2)

        # --- DOWNTREND LOGIC ---
        elif last['close'] < last['ema50']:
            trend = "DOWNTREND 🔴"
            dist_to_ema = abs(last['high'] - last['ema50']) / last['ema50'] * 100
            
            # Pullback Condition (<= 1.5% from EMA) + Red Candle
            if dist_to_ema <= 1.5 and last['close'] < last['open']:
                signal = "SHORT 🔻"
                stop_loss = last['high'] + (last['atr'] * 0.5)
                take_profit = curr_price - ((stop_loss - curr_price) * 2)

        # --- ACTION ---
        if signal:
            msg = (
                f"🚨 *SIGNAL ALERT: {signal}*\n"
                f"Coin: #{symbol.split('/')[0]}\n"
                f"Price: {curr_price}\n"
                f"Trend: {trend}\n"
                f"SL: {stop_loss:.4f}\n"
                f"TP: {take_profit:.4f}"
            )
            print(f"✅ SIGNAL FOUND: {symbol}")
            send_telegram(msg)
        else:
            print(f"   Status: {trend} | No Signal")

    except Exception as e:
        print(f"❌ Error checking {symbol}: {e}")

# ==========================================
# 🚀 MAIN RUNNER (Single Run)
# ==========================================
if __name__ == "__main__":
    print("🤖 GitHub Actions Bot Started...")
    
    # วนลูปเช็คทุกเหรียญ 1 รอบ แล้วจบการทำงาน (รอ Schedule รอบหน้า)
    for coin in SYMBOLS:
        analyze_market(coin)
        
    print("✅ All coins checked. Exiting.")