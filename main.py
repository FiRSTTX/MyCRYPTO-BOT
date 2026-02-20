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
# CONFIG & SETUP
# ==========================================
ACCOUNT_BALANCE = 50  
RISK_PER_TRADE_USD = 10 
LEVERAGE = 10           
RR_RATIO = 1.5
STOP_LOSS_PCT = 0.02    

SYMBOLS = ['BTC/USD', 'ETH/USD', 'SOL/USD']
TIMEFRAME = '1h'
SIGNAL_FILE = "signals.csv"

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
            msg = f"{emoji} <b>POSITION CLOSED</b>\nCoin: {symbol}\nSide: {row['side']}\nResult: <b>{new_status}</b>\nPrice: {curr_price}"
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

        if prev['close'] > prev['ema200'] and prev['rsi'] > 50:
            signal = "LONG"
            reason = "Price > EMA200 + RSI Bull"

        if prev['close'] < prev['ema200'] and prev['rsi'] < 50:
            signal = "SHORT"
            reason = "Price < EMA200 + RSI Bear"
        
        if not signal: return

        # Money Management
        if signal == "LONG":
            sl = price * (1 - STOP_LOSS_PCT)
            tp = price * (1 + (STOP_LOSS_PCT * RR_RATIO))
        else:
            sl = price * (1 + STOP_LOSS_PCT)
            tp = price * (1 - (STOP_LOSS_PCT * RR_RATIO))

        sl_pct = abs(price - sl) / price
        pos_size = RISK_PER_TRADE_USD / sl_pct
        margin = pos_size / LEVERAGE

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        data = {
            "time": now, "symbol": symbol, "side": signal, "entry": price,
            "tp": round(tp, 4), "sl": round(sl, 4), "status": "OPEN",
            "leverage": LEVERAGE, "margin": round(margin, 2),
            "position_size": round(pos_size, 2), "reason": reason
        }
        save_signal(data)

        # --- TELEGRAM FORMAT (แก้ไขส่วนนี้) ---
        side_emoji = "🟢" if signal == "LONG" else "🔴"
        
        msg = f"""
{side_emoji} <b>{signal} SIGNAL</b> 
Coin: <b>#{symbol.split('/')[0]}</b>
Price: {price}
Reason: {reason}
-----------------------------
🛡️ <b>Risk Management</b>
TP: {round(tp, 4)}
SL: {round(sl, 4)} ({round(STOP_LOSS_PCT*100, 2)}%)
Max Risk: ${RISK_PER_TRADE_USD}
-----------------------------
⚡ <b>Execution Setup</b>
Lev: x{LEVERAGE}
Margin: ${round(margin, 2)}
Size: ${round(pos_size, 2)}
"""
        send_telegram(msg)

        log_to_sheet([str(now), symbol, signal, price, data['tp'], data['sl'], "OPEN", LEVERAGE, margin, pos_size, reason])

    except Exception as e:
        print(f"Error {symbol}: {e}")

def run():
    print("--- Bot Started ---")
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
