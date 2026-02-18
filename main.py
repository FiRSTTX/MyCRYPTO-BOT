import ccxt
import pandas as pd
import requests
import os
import sys

# ==========================================
# ⚙️ CONFIG: ตั้งค่าพอร์ตของคุณ (สำคัญ!)
# ==========================================

# 1. เงินทุนในพอร์ต Futures ของคุณ (USDT)
PORTFOLIO_SIZE = 50  # สมมติมี 1,000 USDT (แก้เป็นของจริงได้เลย)

# 2. ความเสี่ยงที่ยอมรับได้ต่อไม้ (แนะนำ 1-2%)
RISK_PER_TRADE = 0.02  # 0.02 = 2%

# 3. Leverage สูงสุดที่จะใช้ (เพื่อความปลอดภัย)
MAX_LEVERAGE = 10      # ไม่เกิน x10

# Telegram (ดึงจาก GitHub Secrets)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# ถ้าเทสในคอม ให้เปิดบรรทัดนี้แล้วใส่ Token ตรงๆ
# TELEGRAM_TOKEN = 'YOUR_TOKEN'
# TELEGRAM_CHAT_ID = 'YOUR_ID'

# ใช้ Kraken Spot (ไม่โดนบล็อก)
exchange = ccxt.kraken({'enableRateLimit': True})
SYMBOLS = ['BTC/USD', 'ETH/USD', 'SOL/USD', 'XRP/USD', 'DOGE/USD']
TIMEFRAME = '1h'

# ==========================================
# 🧮 INDICATORS (Manual Calculation)
# ==========================================
def calculate_indicators(df):
    # 1. EMA 50
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    # 2. ATR 14 (วัดความผันผวน)
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df['atr'] = true_range.ewm(alpha=1/14, adjust=False).mean()

    # 3. RSI 14 (เพิ่มใหม่!)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    return df

# ==========================================
# 💰 POSITION SIZING CALCULATOR
# ==========================================
def calculate_position(entry_price, stop_loss):
    # ระยะห่าง SL เป็น %
    sl_percent = abs(entry_price - stop_loss) / entry_price
    
    # จำนวนเงินที่ยอมเสียได้ (Risk Amount)
    risk_amount = PORTFOLIO_SIZE * RISK_PER_TRADE
    
    # ขนาดไม้ที่ควรเปิด (Position Size in USDT)
    position_value = risk_amount / sl_percent
    
    # คำนวณ Leverage ที่เหมาะสม
    # ถ้า SL กว้าง ต้องใช้ Lev น้อย / ถ้า SL แคบ ใช้ Lev มากได้
    # แต่ห้ามเกิน MAX_LEVERAGE ที่เราตั้งไว้
    safe_leverage = min(int(1 / sl_percent), MAX_LEVERAGE)
    
    # Margin ที่ต้องวางจริง
    margin_cost = position_value / safe_leverage
    
    return position_value, safe_leverage, margin_cost

# ==========================================
# 📡 TELEGRAM SENDER
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
        
        last = df.iloc[-2] # แท่งจบ
        curr_price = last['close']
        
        signal = None
        trend = "SIDEWAY"
        rsi = last['rsi']
        
        # --- UPTREND LOGIC ---
        if last['close'] > last['ema50']:
            trend = "UPTREND 🟢"
            dist_to_ema = abs(last['low'] - last['ema50']) / last['ema50'] * 100
            
            # เงื่อนไข: Pullback + แท่งเขียว + RSI ไม่ Overbought (<70)
            if dist_to_ema <= 1.5 and last['close'] > last['open'] and rsi < 70:
                signal = "LONG 🚀"
                # Stop Loss: ใต้ Swing Low (ATR * 1.5 เพื่อกันโดนสะบัด)
                stop_loss = last['low'] - (last['atr'] * 1.5)
                take_profit = curr_price + ((curr_price - stop_loss) * 2) # RR 1:2

        # --- DOWNTREND LOGIC ---
        elif last['close'] < last['ema50']:
            trend = "DOWNTREND 🔴"
            dist_to_ema = abs(last['high'] - last['ema50']) / last['ema50'] * 100
            
            # เงื่อนไข: Pullback + แท่งแดง + RSI ไม่ Oversold (>30)
            if dist_to_ema <= 1.5 and last['close'] < last['open'] and rsi > 30:
                signal = "SHORT 🔻"
                # Stop Loss: เหนือ Swing High
                stop_loss = last['high'] + (last['atr'] * 1.5)
                take_profit = curr_price - ((stop_loss - curr_price) * 2)

        # --- ACTION ---
        if signal:
            # คำนวณความเสี่ยง
            pos_size, lev, margin = calculate_position(curr_price, stop_loss)
            
            msg = (
                f"🚨 *SIGNAL ALERT: {signal}*\n"
                f"Coin: #{symbol.split('/')[0]}\n"
                f"Price: {curr_price}\n"
                f"RSI: {rsi:.1f}\n"
                f"----------------------------\n"
                f"🎯 **PLAN (RR 1:2)**\n"
                f"Entry: {curr_price} (Market/Limit)\n"
                f"TP: {take_profit:.4f}\n"
                f"SL: {stop_loss:.4f}\n"
                f"----------------------------\n"
                f"💰 **MONEY MANAGEMENT (Risk 2%)**\n"
                f"Leverage: x{lev}\n"
                f"Margin Use: {margin:.2f} USDT\n"
                f"Total Position: {pos_size:.2f} USDT\n"
                f"*(เปิดไม้ขนาด {pos_size:.0f} USDT)*"
            )
            print(f"✅ SIGNAL FOUND: {symbol}")
            send_telegram(msg)
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
