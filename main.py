import ccxt
import pandas as pd
import requests

# ==========================================
# ⚙️ CONFIG (ใส่รหัสตรงๆ เลยครับ)
# ==========================================

# 1. เอา Token จาก BotFather มาใส่ในเครื่องหมายคำพูด ' '
TELEGRAM_TOKEN = '8524742326:AAG41qwiKCr9HYzQXzCf0bAooaOAwzqg75k' 

# 2. เอา Chat ID ของคุณมาใส่
TELEGRAM_CHAT_ID = '1623135330' 

# ตั้งค่า Binance
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 
    'BNB/USDT', 'XRP/USDT', 'DOGE/USDT'
]

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
        requests.post(url, json=payload)
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

# ==========================================
# 🧠 ANALYSIS LOGIC
# ==========================================
def analyze_market(symbol):
    try:
        print(f"Checking {symbol}...")
        bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=100)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = calculate_indicators(df)
        
        last = df.iloc[-2]
        curr_price = last['close']
        
        signal = None
        trend = "SIDEWAY"
        
        # UPTREND
        if last['close'] > last['ema50']:
            trend = "UPTREND 🟢"
            dist_to_ema = abs(last['low'] - last['ema50']) / last['ema50'] * 100
            if dist_to_ema <= 1.5 and last['close'] > last['open']:
                signal = "LONG 🚀"
                stop_loss = last['low'] - (last['atr'] * 0.5)
                take_profit = curr_price + ((curr_price - stop_loss) * 2)

        # DOWNTREND
        elif last['close'] < last['ema50']:
            trend = "DOWNTREND 🔴"
            dist_to_ema = abs(last['high'] - last['ema50']) / last['ema50'] * 100
            if dist_to_ema <= 1.5 and last['close'] < last['open']:
                signal = "SHORT 🔻"
                stop_loss = last['high'] + (last['atr'] * 0.5)
                take_profit = curr_price - ((stop_loss - curr_price) * 2)

        if signal:
            msg = (
                f"🚨 *SIGNAL: {signal}*\n"
                f"Coin: #{symbol.split('/')[0]}\n"
                f"Price: {curr_price}\n"
                f"Trend: {trend}\n"
                f"SL: {stop_loss:.4f} | TP: {take_profit:.4f}"
            )
            print(f"✅ Found Signal: {symbol}")
            send_telegram(msg)
        else:
            print(f"   {trend} (No Signal)")

    except Exception as e:
        print(f"❌ Error {symbol}: {e}")

# ==========================================
# 🚀 MAIN RUNNER
# ==========================================
if __name__ == "__main__":
    print("🤖 Bot Started Direct Mode...")
    # ทดสอบส่งข้อความยืนยันว่า Token ถูกต้อง
    # send_telegram("🤖 บอทเชื่อมต่อสำเร็จแล้วครับ (Hardcode Mode)") 
    
    for coin in SYMBOLS:
        analyze_market(coin)
    print("✅ Done.")
