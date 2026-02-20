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
# CONFIGURATION (สำหรับทุน $50)
# ==========================================
ACCOUNT_BALANCE = 50        # 💰 เงินทุนของคุณ (ใส่ $50)
RISK_PCT_PER_TRADE = 0.03   # 📉 ยอมเสี่ยง 3% ต่อไม้ (ทุน $50 = เสี่ยง $1.5)

LEVERAGE = 10               # อัตราทด x10
RR_RATIO = 1.5              # กำไร 1.5 เท่าของความเสี่ยง
STOP_LOSS_PCT = 0.02        # ระยะ Stop Loss 2%

SYMBOLS = ['BTC/USD', 'ETH/USD', 'SOL/USD', 'DOGE/USD', 'XRP/USD'] # เพิ่มเหรียญได้
TIMEFRAME = '1h'
SIGNAL_FILE = "signals.csv"

# Credentials
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GDRIVE_API_CREDENTIALS = os.environ.get("GDRIVE_API_CREDENTIALS")

exchange = ccxt.kraken({'enableRateLimit': True})

# ==========================================
# FUNCTIONS
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
        print(f"Error Sheet: {e}")

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

def save_signal(data):
    df = pd.DataFrame([data])
    if os.path.exists(SIGNAL_FILE):
        df.to_csv(SIGNAL_FILE, mode='a', header=False, index=False)
    else:
        df.to_csv(SIGNAL_FILE, index=False)

def check_open_orders(symbol):
    if not os.path.exists(SIGNAL_FILE): return False
    try:
        df = pd.read_csv(SIGNAL_FILE)
        # ตรวจสอบว่ามีสถานะ OPEN ของเหรียญนี้อยู่หรือไม่
        return not df[(df['symbol'] == symbol) & (df['status'] == 'OPEN')].empty
    except: return False

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
            curr_price = ticker['last']
        except: continue

        new_status = None
        if row['side'] == "LONG":
            if curr_price >= row['tp']: new_status = "TP"
            elif curr_price <= row['sl']: new_status = "SL"
        elif row['side'] == "SHORT":
            if curr_price <= row['tp']: new_status = "TP"
            elif curr_price >= row['sl']: new_status = "SL"

        if new_status:
            df.at[i, 'status'] = new_status
            updated = True
            emoji = "✅" if new_status == "TP" else "❌"
            # คำนวณกำไร/ขาดทุนจริง (โดยประมาณ)
            pnl_text = "Profit" if new_status == "TP" else "Loss"
            
            msg = f"{emoji} <b>POSITION CLOSED</b>\nCoin: {symbol}\nResult: <b>{new_status}</b> ({pnl_text})\nClose Price: {curr_price}"
            send_telegram(msg)

    if updated: df.to_csv(SIGNAL_FILE, index=False)

def analyze(symbol):
    print(f"Analyzing {symbol}...")
    if check_open_orders(symbol):
        print(f"Skipping {symbol}: Open position exists.")
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

        # Strategy Logic
        if prev['close'] > prev['ema200'] and prev['rsi'] > 50:
            signal = "LONG"
            reason = "Price > EMA200 + RSI Bull"

        if prev['close'] < prev['ema200'] and prev['rsi'] < 50:
            signal = "SHORT"
            reason = "Price < EMA200 + RSI Bear"
        
        if not signal: return

        # --- 💰 MONEY MANAGEMENT (สูตรใหม่สำหรับทุนน้อย) ---
        
        # 1. คำนวณราคา TP/SL
        if signal == "LONG":
            sl = price * (1 - STOP_LOSS_PCT)
            tp = price * (1 + (STOP_LOSS_PCT * RR_RATIO))
        else:
            sl = price * (1 + STOP_LOSS_PCT)
            tp = price * (1 - (STOP_LOSS_PCT * RR_RATIO))

        # 2. คำนวณความเสี่ยงเป็นดอลลาร์ (Risk $)
        # ทุน $50 * 3% = เสี่ยง $1.5
        risk_usd = ACCOUNT_BALANCE * RISK_PCT_PER_TRADE 

        # 3. คำนวณขนาดไม้ (Position Size)
        # สูตร: Risk $ / ระยะ SL % = ขนาด Position ที่ต้องถือ
        # เช่น $1.5 / 0.02 = $75
        sl_distance_pct = STOP_LOSS_PCT 
        position_size_usd = risk_usd / sl_distance_pct
        
        # 4. คำนวณ Margin ที่ต้องใช้ (เงินต้นจริง)
        # $75 / Leverage 10 = $7.5
        margin_use = position_size_usd / LEVERAGE

        # ตรวจสอบขนาดขั้นต่ำ (Kraken อาจมีขั้นต่ำประมาณ $10-$15 ในบางคู่)
        # ถ้า Margin น้อยกว่า $2 ให้ขยับขึ้นมาเพื่อให้เทรดได้จริง
        if margin_use < 2:
            margin_use = 2
            position_size_usd = margin_use * LEVERAGE

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        data = {
            "time": now, "symbol": symbol, "side": signal, "entry": price,
            "tp": round(tp, 4), "sl": round(sl, 4), "status": "OPEN",
            "leverage": LEVERAGE, "margin": round(margin_use, 2),
            "position_size": round(position_size_usd, 2), "reason": reason
        }
        save_signal(data)

        # --- TELEGRAM MESSAGE ---
        side_emoji = "🟢" if signal == "LONG" else "🔴"
        
        msg = f"""
{side_emoji} <b>{signal} SIGNAL</b> 
Coin: <b>#{symbol.split('/')[0]}</b>
Price: {price}
Reason: {reason}
-----------------------------
🛡️ <b>Risk Plan (Small Port)</b>
TP: {round(tp, 4)}
SL: {round(sl, 4)} (Risk {RISK_PCT_PER_TRADE*100}%)
Max Risk: ${round(risk_usd, 2)}
-----------------------------
⚡ <b>Execution</b>
Lev: x{LEVERAGE}
<b>Margin Use: ${round(margin_use, 2)}</b>
Size: ${round(position_size_usd, 2)}
"""
        send_telegram(msg)

        log_to_sheet([str(now), symbol, signal, price, data['tp'], data['sl'], "OPEN", LEVERAGE, margin_use, position_size_usd, reason])

    except Exception as e:
        print(f"Error {symbol}: {e}")

def run():
    print("--- Bot Started (Small Port Logic) ---")
    try:
        update_signals()
        for s in SYMBOLS:
            analyze(s)
            time.sleep(1)
        print("--- Finished ---")
    except Exception as e:
        print(f"Error: {e}")
        raise e

if __name__ == "__main__":
    run()
