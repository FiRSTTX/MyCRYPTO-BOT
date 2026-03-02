import ccxt
import pandas as pd
import ta
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timezone
import json
import os
import requests

# ==========================================
# ⚙️ CONFIGURATION & SECRETS
# ==========================================
SYMBOLS = ['DOGE/USDT', 'ETH/USDT', 'BTC/USDT', 'BNB/USDT', 'XRP/USDT']
TIMEFRAME = '5m'
SHEET_NAME = 'CryptoBot_TEST_TF5MIN'

# 💰 Money Management Settings
PCT_BALANCE_PER_TRADE = 0.10  # 👈 ใช้เงิน 10% ของยอดคงเหลือ (เริ่ม 200$ = 20$)
LEVERAGE = 10

# ⚙️ Strategy Settings
INITIAL_SL_ROE = 0.10      # เริ่มต้น SL ที่ -10% ROE
TRAILING_STEP_ROE = 0.15   # ขยับ SL ทุกๆ กำไร 15% ROE

# ⏰ Time Filter (UTC 07:00 - 22:00)
START_HOUR_UTC = 7
END_HOUR_UTC = 22

# 🔐 Load Secrets from GitHub Environment
CREDS_JSON = os.environ.get('GDRIVE_API_CREDENTIALS')
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK')

exchange = ccxt.okx()

# ==========================================
# 🔔 DISCORD NOTIFICATION
# ==========================================
def send_discord_alert(action_type, symbol, side, price, size_usdt=0, pnl_usdt=0, pnl_roe=0, balance=0, reason=""):
    if not DISCORD_WEBHOOK_URL: return

    if action_type == "OPEN":
        title = f"🚀 OPEN {side}: {symbol}"
        color = 0x00ff00 if side == "LONG" else 0xff0000
        desc = (f"**Entry:** `{price:.4f}`\n"
                f"**Size:** `{size_usdt:.2f} USDT` (Margin)\n"
                f"**Current Balance:** `{balance:.2f} USDT`")
    elif action_type == "CLOSE":
        color = 0xffd700 if pnl_usdt > 0 else 0x95a5a6
        icon = "🤑" if pnl_usdt > 0 else "🩸"
        title = f"{icon} CLOSED {side}: {symbol}"
        desc = (f"**Exit:** `{price:.4f}`\n"
                f"**PnL:** `{pnl_usdt:+.2f} USDT` ({pnl_roe:+.2f}% ROE)\n"
                f"**New Balance:** `{balance:.2f} USDT`\n"
                f"**Reason:** {reason}")
    else:
        return

    data = {
        "username": "Infinity Bot ♾️",
        "embeds": [{
            "title": title,
            "description": desc,
            "color": color,
            "fields": [{"name": "⏰ Time (UTC)", "value": datetime.now(timezone.utc).strftime('%H:%M:%S'), "inline": True}]
        }]
    }
    try: requests.post(DISCORD_WEBHOOK_URL, json=data)
    except: pass

# ==========================================
# 📚 GOOGLE SHEETS FUNCTIONS (ACCOUNTING)
# ==========================================
def connect_google_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(CREDS_JSON), scope)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME)

def get_balance(sheet):
    try:
        ws = sheet.worksheet('summary')
        val = ws.acell('B1').value
        # ถ้าอ่านค่าไม่ได้ หรือยังไม่มีค่า ให้เริ่มที่ 200.0
        return float(val) if val else 200.0
    except:
        return 200.0

def update_balance(sheet, new_balance):
    try:
        ws = sheet.worksheet('summary')
        ws.update('B1', new_balance)
        print(f"💰 Balance Updated: {new_balance:.2f} USDT")
    except Exception as e:
        print(f"❌ Error updating balance: {e}")

def get_active_trades(sheet):
    try:
        ws = sheet.worksheet('active_trades')
        return pd.DataFrame(ws.get_all_records())
    except: return pd.DataFrame()

def log_new_trade(sheet, symbol, side, entry, sl, margin_size, current_balance):
    ws = sheet.worksheet('active_trades')
    # Row: Symbol, Side, Entry, Current_SL, Trailing_Step, Margin_Size, Timestamp
    ws.append_row([symbol, side, entry, sl, 0, margin_size, str(datetime.now())])
    print(f"✅ Logged Open: {symbol} (Size: {margin_size:.2f} USDT)")
    
    send_discord_alert("OPEN", symbol, side, entry, size_usdt=margin_size, balance=current_balance)

def close_trade(sheet, symbol, side, entry, exit_price, margin_size, reason):
    # Calculate PnL
    # สูตร: (Exit - Entry) / Entry * Leverage * Margin
    if side == 'LONG':
        roe = ((exit_price - entry) / entry) * LEVERAGE
    else:
        roe = ((entry - exit_price) / entry) * LEVERAGE
    
    pnl_usdt = margin_size * (roe / 100)
    
    # 1. Update Balance in Sheet
    current_balance = get_balance(sheet)
    new_balance = current_balance + pnl_usdt
    update_balance(sheet, new_balance)

    # 2. Add to History
    ws_hist = sheet.worksheet('trade_history')
    result = "WIN" if pnl_usdt > 0 else "LOSS"
    # Row: Symbol, Side, Entry, Exit, PnL_USDT, ROE%, Result, Reason, Balance_After, Timestamp
    ws_hist.append_row([symbol, side, entry, exit_price, pnl_usdt, roe, result, reason, new_balance, str(datetime.now())])
    
    # 3. Remove from Active
    ws_active = sheet.worksheet('active_trades')
    try:
        cell = ws_active.find(symbol)
        ws_active.delete_rows(cell.row)
        print(f"❌ Closed {symbol}: {pnl_usdt:+.2f} USDT")
        
        send_discord_alert("CLOSE", symbol, side, exit_price, pnl_usdt=pnl_usdt, pnl_roe=roe, balance=new_balance, reason=reason)
    except: pass

def update_sl(sheet, symbol, new_sl, new_step):
    ws = sheet.worksheet('active_trades')
    try:
        cell = ws.find(symbol)
        ws.update_cell(cell.row, 4, new_sl) # Col 4 = Current_SL
        ws.update_cell(cell.row, 5, new_step) # Col 5 = Step
        print(f"🔄 Updated SL {symbol} (Step {new_step})")
    except: pass

# ==========================================
# 📊 TECHNICAL ANALYSIS & MAIN LOGIC
# ==========================================
def fetch_data(symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        return df
    except: return None

def calculate_indicators(df):
    df['ema200'] = ta.trend.ema_indicator(df['close'], window=200)
    df['adx'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)
    df['vol_ma'] = df['volume'].rolling(window=20).mean()
    vwap = ta.volume.VolumeWeightedAveragePrice(high=df['high'], low=df['low'], close=df['close'], volume=df['volume'], window=288)
    df['vwap'] = vwap.volume_weighted_average_price()
    df['rsi7'] = ta.momentum.rsi(df['close'], window=7)
    return df

def main():
    print("🤖 Bot Running...")
    
    if not CREDS_JSON: 
        print("❌ Error: Secrets not found")
        return

    try: sheet = connect_google_sheet()
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return

    # 1️⃣ ดึงยอดเงินล่าสุด (Real-time Balance from Sheet)
    current_balance = get_balance(sheet)
    print(f"💰 Current Balance: {current_balance:.2f} USDT")

    active_df = get_active_trades(sheet)
    active_symbols = active_df['Symbol'].tolist() if not active_df.empty else []

    # 2️⃣ MANAGER: ดูแลออเดอร์เก่า (Trailing / Exit)
    if not active_df.empty:
        for index, trade in active_df.iterrows():
            symbol = trade['Symbol']
            side = trade['Side']
            entry = float(trade['Entry'])
            current_sl = float(trade['Current_SL'])
            step = int(trade['Trailing_Step'])
            margin_size = float(trade['Margin_Size']) # ดึงขนาดไม้ที่ลงไป
            
            df = fetch_data(symbol)
            if df is None: continue
            current_price = df['close'].iloc[-1]
            
            # 2.1 Check SL Hit
            hit_sl = False
            if side == 'LONG' and current_price <= current_sl: hit_sl = True
            elif side == 'SHORT' and current_price >= current_sl: hit_sl = True
            
            if hit_sl:
                close_trade(sheet, symbol, side, entry, current_sl, margin_size, "SL/Trailing Hit")
                continue

            # 2.2 Check Trailing Update
            if side == 'LONG':
                max_roe = ((current_price - entry) / entry) * LEVERAGE
                if max_roe >= (step + 1) * TRAILING_STEP_ROE:
                    new_step = step + 1
                    locked_roe = (new_step - 1) * TRAILING_STEP_ROE
                    new_sl = entry * (1 + (locked_roe / LEVERAGE))
                    update_sl(sheet, symbol, new_sl, new_step)
            
            elif side == 'SHORT':
                max_roe = ((entry - current_price) / entry) * LEVERAGE
                if max_roe >= (step + 1) * TRAILING_STEP_ROE:
                    new_step = step + 1
                    locked_roe = (new_step - 1) * TRAILING_STEP_ROE
                    new_sl = entry * (1 - (locked_roe / LEVERAGE))
                    update_sl(sheet, symbol, new_sl, new_step)

    # 3️⃣ SCANNER: หาออเดอร์ใหม่
    current_hour = datetime.now(timezone.utc).hour
    if not (START_HOUR_UTC <= current_hour <= END_HOUR_UTC):
        print("💤 Outside Active Hours.")
        return

# ... (ส่วนเช็คเวลา Time Filter เหมือนเดิม) ...

    print(f"🔎 Scanning markets at {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC...")

    for symbol in SYMBOLS:
        if symbol in active_symbols: 
            print(f"⏩ {symbol}: Holding position. Skip.")
            continue 

        df = fetch_data(symbol)
        if df is None: 
            print(f"⚠️ {symbol}: Fetch Error")
            continue
            
        df = calculate_indicators(df)
        row = df.iloc[-2] 

        # --- ส่วน DEBUG ที่เพิ่มขึ้นมา ---
        # ปริ้นท์ค่า Indicator ออกมาดูเลย ว่าทำไมถึงไม่เข้า
        rsi_val = row['rsi7']
        adx_val = row['adx']
        vol_check = row['volume'] > (row['vol_ma'] * 1.2)
        trend_long = row['close'] > row['ema200'] and row['close'] > row['vwap']
        trend_short = row['close'] < row['ema200'] and row['close'] < row['vwap']
        
        # ปริ้นท์สถานะ (บรรทัดนี้แหละที่จะบอกความจริง!)
        print(f"📊 {symbol} | RSI: {rsi_val:.1f} | ADX: {adx_val:.1f} | Vol: {'✅' if vol_check else '❌'} | Trend: {'🐂' if trend_long else ('🐻' if trend_short else 'Eq')}")
        # -------------------------------

        has_volume = vol_check
        strong_trend = adx_val > 25
        
        trade_margin_size = current_balance * PCT_BALANCE_PER_TRADE

        # ENTRY LOGIC (เหมือนเดิม)
        if trend_long and strong_trend:
            if rsi_val < 40 and has_volume:
                sl = row['close'] * (1 - (INITIAL_SL_ROE / LEVERAGE))
                log_new_trade(sheet, symbol, 'LONG', row['close'], sl, trade_margin_size, current_balance)
            else:
                # ถ้าเจอเทรนด์ แต่ RSI หรือ Volume ไม่ผ่าน ให้ปริ้นท์บอก
                print(f"   Constructor -> 🐂 LONG Candidate but waiting for trigger (RSI<40 or Vol)")

        elif trend_short and strong_trend:
            if rsi_val > 60 and has_volume:
                sl = row['close'] * (1 + (INITIAL_SL_ROE / LEVERAGE))
                log_new_trade(sheet, symbol, 'SHORT', row['close'], sl, trade_margin_size, current_balance)
            else:
                print(f"   Constructor -> 🐻 SHORT Candidate but waiting for trigger (RSI>60 or Vol)")

if __name__ == "__main__":
    main()

