# -*- coding: utf-8 -*-
"""
COMPLETE KITE TRADING SYSTEM v2
- Railway pe seedha chalta hai (no input() required)
- Nifty 50 + BankNifty + MCX Scanner
- Telegram Signal + Approval + Auto Execute
- /analyze SYMBOL command support
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import time
import logging
import threading
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from kiteconnect import KiteConnect

# ================================================================
#  CONFIG
# ================================================================

import os
API_KEY        = os.environ.get("API_KEY",        "zhve1lfpjxtie9rv")
API_SECRET     = os.environ.get("API_SECRET",     "wr1cwi6ijdpa2phztvhbtm48z79a9jsu")
ACCESS_TOKEN   = os.environ.get("ACCESS_TOKEN",   "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8701616355:AAGvetI7MfI2f6vJh7LkeujpxHmmtB0OtXE")
CHAT_ID        = os.environ.get("CHAT_ID",        "8757681357")

# Risk Settings
MAX_DAILY_LOSS     = 10000
MAX_TRADES_PER_DAY = 5
MAX_LOTS           = 2
TRADE_START_TIME   = "09:30"
TRADE_END_TIME     = "15:00"
SQUAREOFF_TIME     = "15:15"

# Nifty 50 stocks
NIFTY50_STOCKS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
    "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "TITAN",
    "SUNPHARMA", "ULTRACEMCO", "BAJFINANCE", "WIPRO", "NESTLEIND",
    "ADANIENT", "ONGC", "NTPC", "POWERGRID", "COALINDIA",
    "TATAMOTORS", "TATASTEEL", "JSWSTEEL", "HCLTECH", "TECHM"
]

BANKEX_STOCKS = [
    "HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "SBIN",
    "INDUSINDBK", "BANDHANBNK", "FEDERALBNK", "IDFCFIRSTB", "AUBANK"
]

MCX_INSTRUMENTS = [
    {"symbol": "SILVERM26JUNFUT",    "exchange": "MCX", "lots": 1, "lot_size": 30,   "product": "NRML"},
    {"symbol": "CRUDEOIL26JUNFUT",   "exchange": "MCX", "lots": 1, "lot_size": 100,  "product": "NRML"},
    {"symbol": "GOLD26JUNFUT",       "exchange": "MCX", "lots": 1, "lot_size": 100,  "product": "NRML"},
    {"symbol": "NATURALGAS26JUNFUT", "exchange": "MCX", "lots": 1, "lot_size": 1250, "product": "NRML"},
]

EMA_FAST        = 9
EMA_SLOW        = 21
RSI_PERIOD      = 14
MACD_FAST       = 12
MACD_SLOW       = 26
MACD_SIGNAL     = 9
CANDLE_INTERVAL = "5minute"

# ================================================================
#  LOGGING
# ================================================================

class SafeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            self.stream.write(msg + self.terminator)
            self.flush()
        except:
            pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(f'trading_{datetime.now().strftime("%Y%m%d")}.log', encoding='utf-8'),
        SafeStreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)

# ================================================================
#  TELEGRAM
# ================================================================

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        log.info("[TELEGRAM] Sent")
    except Exception as e:
        log.error(f"[TELEGRAM ERROR] {e}")

def tg_get_updates(offset=None):
    try:
        url    = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        params = {"timeout": 5, "allowed_updates": ["message"]}
        if offset:
            params["offset"] = offset
        r = requests.get(url, params=params, timeout=10)
        return r.json().get("result", [])
    except:
        return []

def send_signal_telegram(signal_data):
    s    = signal_data
    icon = "BUY" if s['signal'] == 'BUY' else "SELL"
    msg  = f"""<b>SIGNAL: {icon}</b>

<b>Stock:</b> {s['symbol']} [{s['exchange']}]
<b>Entry:</b> Rs.{s['entry']}
<b>Stop Loss:</b> Rs.{s['sl']}
<b>Target 1:</b> Rs.{s['t1']}
<b>Target 2:</b> Rs.{s['t2']}

<b>Confidence:</b> {s['confidence']}/100
<b>Risk:Reward:</b> 1:{s['rr']}

<b>Reason:</b>
{s['reason']}

<b>Lots:</b> {s['lots']} | <b>Product:</b> {s['product']}

Reply <b>YES</b> to execute or <b>NO</b> to skip
<i>Auto-cancel in 2 minutes</i>"""
    send_telegram(msg)

def get_telegram_reply(timeout=120):
    """Wait for YES/NO reply"""
    start          = time.time()
    last_update_id = None
    while time.time() - start < timeout:
        try:
            url    = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {"timeout": 10, "allowed_updates": ["message"]}
            if last_update_id:
                params["offset"] = last_update_id + 1
            r    = requests.get(url, params=params, timeout=15)
            data = r.json()
            for update in data.get('result', []):
                last_update_id = update['update_id']
                msg  = update.get('message', {})
                if str(msg.get('chat', {}).get('id', '')) == CHAT_ID:
                    text = msg.get('text', '').strip().upper()
                    if text in ['YES', 'Y', 'HAN', 'HAAN', 'OK']:
                        return True
                    elif text in ['NO', 'N', 'NAI', 'NAHI', 'SKIP']:
                        return False
        except:
            pass
        time.sleep(2)
    return None

# ================================================================
#  INDICATORS
# ================================================================

def calculate_ema(prices, period):
    return pd.Series(prices).ewm(span=period, adjust=False).mean().values

def calculate_rsi(prices, period=14):
    prices = pd.Series(prices)
    delta  = prices.diff()
    gain   = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss   = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs     = gain / loss
    return (100 - (100 / (1 + rs))).values

def calculate_macd(prices, fast=12, slow=26, signal=9):
    prices      = pd.Series(prices)
    ema_fast    = prices.ewm(span=fast, adjust=False).mean()
    ema_slow    = prices.ewm(span=slow, adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line.values, signal_line.values

def calculate_vwap(df):
    typical = (df['high'] + df['low'] + df['close']) / 3
    return (typical * df['volume']).cumsum() / df['volume'].cumsum()

def get_confidence_score(conditions):
    weights = {'vwap': 25, 'ema_cross': 25, 'rsi': 20, 'macd': 20, 'volume': 10}
    return sum(weights[k] for k, v in conditions.items() if v and k in weights)

# ================================================================
#  ANALYZE INSTRUMENT
# ================================================================

def analyze_instrument(kite, symbol, exchange, lots=1, lot_size=1, product="MIS"):
    try:
        instrument = kite.ltp(f"{exchange}:{symbol}")
        token      = list(instrument.values())[0].get('instrument_token')
        ltp        = list(instrument.values())[0].get('last_price', 0)

        to_date   = datetime.now()
        from_date = to_date - timedelta(days=5)
        data      = kite.historical_data(token, from_date.strftime("%Y-%m-%d"), to_date.strftime("%Y-%m-%d"), CANDLE_INTERVAL)

        if len(data) < 30:
            return None

        df         = pd.DataFrame(data)
        df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']

        closes  = df['close'].values
        volumes = df['volume'].values

        ema_fast   = calculate_ema(closes, EMA_FAST)
        ema_slow   = calculate_ema(closes, EMA_SLOW)
        rsi        = calculate_rsi(closes, RSI_PERIOD)
        macd_line, signal_line = calculate_macd(closes, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
        vwap       = calculate_vwap(df)

        curr_price = closes[-1]
        curr_vwap  = vwap.iloc[-1]
        curr_rsi   = rsi[-1]

        ema_bullish  = (ema_fast[-2] <= ema_slow[-2]) and (ema_fast[-1] > ema_slow[-1])
        ema_bearish  = (ema_fast[-2] >= ema_slow[-2]) and (ema_fast[-1] < ema_slow[-1])
        macd_bullish = (macd_line[-2] <= signal_line[-2]) and (macd_line[-1] > signal_line[-1])
        macd_bearish = (macd_line[-2] >= signal_line[-2]) and (macd_line[-1] < signal_line[-1])

        avg_volume  = np.mean(volumes[-20:])
        curr_volume = volumes[-1]
        vol_spike   = curr_volume > avg_volume * 1.5

        buy_conditions  = {'vwap': curr_price > curr_vwap, 'ema_cross': ema_bullish, 'rsi': 40 <= curr_rsi <= 65, 'macd': macd_bullish, 'volume': vol_spike}
        sell_conditions = {'vwap': curr_price < curr_vwap, 'ema_cross': ema_bearish, 'rsi': 35 <= curr_rsi <= 60, 'macd': macd_bearish, 'volume': vol_spike}

        buy_score  = get_confidence_score(buy_conditions)
        sell_score = get_confidence_score(sell_conditions)

        if buy_score >= 70:
            signal     = 'BUY'
            confidence = buy_score
            conditions = buy_conditions
            sl         = round(df.iloc[-2]['low'] * 0.998, 2)
            risk       = curr_price - sl
            t1         = round(curr_price + risk * 1.5, 2)
            t2         = round(curr_price + risk * 2.5, 2)
        elif sell_score >= 70:
            signal     = 'SELL'
            confidence = sell_score
            conditions = sell_conditions
            sl         = round(df.iloc[-2]['high'] * 1.002, 2)
            risk       = sl - curr_price
            t1         = round(curr_price - risk * 1.5, 2)
            t2         = round(curr_price - risk * 2.5, 2)
        else:
            return None

        reasons = []
        if conditions['vwap']:     reasons.append(f"Price {'above' if signal=='BUY' else 'below'} VWAP ({round(curr_vwap,2)})")
        if conditions['ema_cross']: reasons.append(f"EMA9 {'bullish' if signal=='BUY' else 'bearish'} crossover")
        if conditions['rsi']:      reasons.append(f"RSI at {round(curr_rsi,1)}")
        if conditions['macd']:     reasons.append(f"MACD {'bullish' if signal=='BUY' else 'bearish'}")
        if conditions['volume']:   reasons.append(f"Volume spike ({round(curr_volume/avg_volume,1)}x avg)")

        rr = round(abs((t1 - curr_price) / (curr_price - sl)), 1) if signal == 'BUY' else round(abs((curr_price - t1) / (sl - curr_price)), 1)

        return {
            'symbol': symbol, 'exchange': exchange, 'signal': signal,
            'entry': round(curr_price, 2), 'sl': sl, 't1': t1, 't2': t2,
            'confidence': confidence, 'rr': abs(rr),
            'reason': '\n'.join([f"- {r}" for r in reasons]),
            'lots': lots, 'lot_size': lot_size, 'product': product, 'type': 'FUT'
        }
    except Exception as e:
        log.error(f"[ANALYZE ERROR] {symbol}: {e}")
        return None

# ================================================================
#  /analyze COMMAND - Full technical analysis
# ================================================================

def cmd_analyze(symbol_input, kite):
    parts  = symbol_input.strip().upper().split()
    symbol = parts[0]

    if len(parts) >= 2:
        exchange = parts[1]
    elif any(x in symbol for x in ["FUT", "CE", "PE"]):
        if any(x in symbol for x in ["NIFTY", "BANKNIFTY", "FINNIFTY"]):
            exchange = "NFO"
        elif any(x in symbol for x in ["GOLD", "SILVER", "CRUDE", "NATURALGAS", "COPPER"]):
            exchange = "MCX"
        else:
            exchange = "NFO"
    else:
        exchange = "NSE"

    send_telegram(f"🔍 <b>Analyzing {symbol} [{exchange}]...</b>\nEk second...")

    try:
        ltp_data = kite.ltp(f"{exchange}:{symbol}")
        info     = ltp_data[f"{exchange}:{symbol}"]
        token    = info["instrument_token"]

        to_date   = datetime.now()
        from_date = to_date - timedelta(days=5)
        candles   = kite.historical_data(token, from_date.strftime("%Y-%m-%d"), to_date.strftime("%Y-%m-%d"), "5minute")

        if not candles or len(candles) < 30:
            send_telegram(f"❌ {symbol} ka data nahi mila. Market open hai?")
            return

        df         = pd.DataFrame(candles)
        df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']

        closes  = df['close'].values
        highs   = df['high'].values
        lows    = df['low'].values
        volumes = df['volume'].values

        ema9  = pd.Series(closes).ewm(span=9,  adjust=False).mean().values
        ema21 = pd.Series(closes).ewm(span=21, adjust=False).mean().values

        delta = pd.Series(closes).diff()
        gain  = delta.where(delta > 0, 0).rolling(14).mean()
        loss  = -delta.where(delta < 0, 0).rolling(14).mean()
        rsi   = (100 - (100 / (1 + gain / loss))).values

        ema12       = pd.Series(closes).ewm(span=12, adjust=False).mean()
        ema26       = pd.Series(closes).ewm(span=26, adjust=False).mean()
        macd_line   = (ema12 - ema26).values
        signal_line = pd.Series(macd_line).ewm(span=9, adjust=False).mean().values

        typical = (df['high'] + df['low'] + df['close']) / 3
        vwap    = ((typical * df['volume']).cumsum() / df['volume'].cumsum()).values

        sma20    = pd.Series(closes).rolling(20).mean().values
        std20    = pd.Series(closes).rolling(20).std().values
        bb_upper = sma20 + 2 * std20
        bb_lower = sma20 - 2 * std20

        avg_vol   = np.mean(volumes[-20:])
        vol_spike = volumes[-1] > avg_vol * 1.5
        vol_ratio = round(volumes[-1] / avg_vol, 1)

        today    = datetime.now().date()
        today_df = df[pd.to_datetime(df['date']).dt.date == today]
        day_open = today_df.iloc[0]['open']  if len(today_df) > 0 else df.iloc[-1]['open']
        day_high = today_df['high'].max()    if len(today_df) > 0 else highs[-1]
        day_low  = today_df['low'].min()     if len(today_df) > 0 else lows[-1]

        curr_price = closes[-1]
        curr_vwap  = vwap[-1]
        curr_rsi   = rsi[-1]
        curr_macd  = macd_line[-1]
        curr_sig   = signal_line[-1]
        curr_ema9  = ema9[-1]
        curr_ema21 = ema21[-1]

        ema_bullish  = (ema9[-2] <= ema21[-2]) and (ema9[-1] > ema21[-1])
        ema_bearish  = (ema9[-2] >= ema21[-2]) and (ema9[-1] < ema21[-1])
        macd_bullish = (macd_line[-2] <= signal_line[-2]) and (macd_line[-1] > signal_line[-1])
        macd_bearish = (macd_line[-2] >= signal_line[-2]) and (macd_line[-1] < signal_line[-1])
        above_vwap   = curr_price > curr_vwap

        buy_score = sum([above_vwap, ema_bullish or curr_ema9 > curr_ema21,
                         40 <= curr_rsi <= 65, macd_bullish or curr_macd > curr_sig, vol_spike]) * 20
        sell_score = sum([not above_vwap, ema_bearish or curr_ema9 < curr_ema21,
                          35 <= curr_rsi <= 60, macd_bearish or curr_macd < curr_sig, vol_spike]) * 20

        if buy_score >= 60:
            signal     = "🟢 BUY"
            sl         = round(min(lows[-3:]) * 0.998, 2)
            risk       = max(curr_price - sl, 1)
            t1         = round(curr_price + risk * 1.5, 2)
            t2         = round(curr_price + risk * 2.5, 2)
            confidence = buy_score
        elif sell_score >= 60:
            signal     = "🔴 SELL"
            sl         = round(max(highs[-3:]) * 1.002, 2)
            risk       = max(sl - curr_price, 1)
            t1         = round(curr_price - risk * 1.5, 2)
            t2         = round(curr_price - risk * 2.5, 2)
            confidence = sell_score
        else:
            signal     = "⚪ WAIT"
            sl         = round(min(lows[-3:]) * 0.998, 2)
            risk       = max(curr_price - sl, 1)
            t1         = round(curr_price + risk * 1.5, 2)
            t2         = round(curr_price + risk * 2.5, 2)
            confidence = max(buy_score, sell_score)

        ema_txt  = ("✅ Bullish cross" if ema_bullish else "❌ Bearish cross" if ema_bearish else
                    "📈 EMA9 > EMA21" if curr_ema9 > curr_ema21 else "📉 EMA9 < EMA21")
        vwap_txt = f"{'✅ Above' if above_vwap else '❌ Below'} (₹{round(curr_vwap,2)})"
        rsi_txt  = (f"🔥 Overbought ({round(curr_rsi,1)})" if curr_rsi > 70 else
                    f"💚 Oversold ({round(curr_rsi,1)})"   if curr_rsi < 30 else
                    f"✅ Normal ({round(curr_rsi,1)})")
        macd_txt = (f"✅ Bullish ({round(curr_macd,3)})" if macd_bullish or curr_macd > curr_sig
                    else f"❌ Bearish ({round(curr_macd,3)})")
        vol_txt  = f"🔥 Spike! {vol_ratio}x avg" if vol_spike else f"😐 Normal ({vol_ratio}x)"
        bb_txt   = ("⚠️ Near Upper Band" if curr_price > bb_upper[-1] * 0.998 else
                    "⚠️ Near Lower Band" if curr_price < bb_lower[-1] * 1.002 else "✅ Inside Bands")

        change_pct  = round(((curr_price - day_open) / day_open) * 100, 2) if day_open else 0
        change_icon = "📈" if change_pct >= 0 else "📉"

        msg = f"""<b>📊 ANALYSIS: {symbol} [{exchange}]</b>
━━━━━━━━━━━━━━━━━━━━

<b>💰 PRICE</b>
LTP:  <b>₹{round(curr_price,2)}</b>  {change_icon} {change_pct:+.2f}%
Open: ₹{round(day_open,2)}
High: ₹{round(day_high,2)}  Low: ₹{round(day_low,2)}

<b>📐 INDICATORS (5min)</b>
EMA 9/21 : {ema_txt}
VWAP     : {vwap_txt}
RSI(14)  : {rsi_txt}
MACD     : {macd_txt}
Volume   : {vol_txt}
Bollinger: {bb_txt}

<b>🎯 SIGNAL: {signal}</b>
Confidence: {confidence}/100

<b>📌 KEY LEVELS</b>
Entry  : ₹{round(curr_price,2)}
SL     : ₹{sl}
Target1: ₹{t1}
Target2: ₹{t2}
R:R = 1:1.5

<i>⏰ {datetime.now().strftime('%d-%b-%Y %H:%M')} | 5min chart</i>"""

        send_telegram(msg)

    except Exception as e:
        log.error(f"[CMD_ANALYZE] {e}")
        send_telegram(f"❌ Error analyzing {symbol}: {str(e)}")

# ================================================================
#  TELEGRAM COMMAND LISTENER (background thread)
# ================================================================

def telegram_listener(kite):
    log.info("[TG] Listener started!")
    send_telegram(
        "🤖 <b>Trading System Online! v2</b>\n\n"
        "/analyze RELIANCE — stock analysis\n"
        "/analyze NIFTY26MAYFUT NFO — futures\n"
        "/analyze GOLD26JUNFUT MCX — commodity\n"
        "/help — all commands"
    )
    offset = None
    while True:
        try:
            updates = tg_get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                msg    = update.get("message", {})
                text   = msg.get("text", "").strip()

                if text.lower().startswith("/analyze"):
                    parts = text.split(maxsplit=1)
                    if len(parts) < 2:
                        send_telegram(
                            "📊 <b>Usage:</b>\n"
                            "/analyze RELIANCE\n"
                            "/analyze NIFTY26MAYFUT NFO\n"
                            "/analyze GOLD26JUNFUT MCX"
                        )
                    else:
                        threading.Thread(target=cmd_analyze, args=(parts[1], kite), daemon=True).start()

                elif text.lower() == "/help":
                    send_telegram(
                        "🤖 <b>Commands:</b>\n\n"
                        "/analyze SYMBOL — Full analysis\n"
                        "/analyze SYMBOL EXCHANGE\n\n"
                        "<b>Examples:</b>\n"
                        "/analyze RELIANCE\n"
                        "/analyze NIFTY26MAYFUT NFO\n"
                        "/analyze GOLD26JUNFUT MCX\n"
                        "/analyze CRUDEOIL26JUNFUT MCX"
                    )
        except Exception as e:
            log.error(f"[TG LISTENER] {e}")
        time.sleep(1)

# ================================================================
#  ORDER EXECUTOR
# ================================================================

class OrderExecutor:
    def __init__(self, kite):
        self.kite        = kite
        self.daily_pnl   = 0
        self.trade_count = 0

    def get_ltp(self, exchange, symbol):
        try:
            data = self.kite.ltp(f"{exchange}:{symbol}")
            return data[f"{exchange}:{symbol}"]["last_price"]
        except:
            return None

    def execute(self, signal_data):
        symbol   = signal_data['symbol']
        exchange = signal_data['exchange']
        action   = signal_data['signal']
        quantity = signal_data['lots'] * signal_data['lot_size']
        product  = signal_data['product']
        sl_price = signal_data['sl']

        try:
            transaction  = KiteConnect.TRANSACTION_TYPE_BUY if action == "BUY" else KiteConnect.TRANSACTION_TYPE_SELL
            product_type = KiteConnect.PRODUCT_MIS if product == "MIS" else KiteConnect.PRODUCT_NRML

            ltp = self.get_ltp(exchange, symbol)
            if not ltp:
                return False

            price    = round(ltp * 1.002, 1) if action == "BUY" else round(ltp * 0.998, 1)
            order_id = self.kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR, exchange=exchange,
                tradingsymbol=symbol, transaction_type=transaction,
                quantity=quantity, product=product_type,
                order_type=KiteConnect.ORDER_TYPE_LIMIT, price=price,
            )
            log.info(f"[ORDER OK] {action} | {symbol} | Qty:{quantity} | Price:{price} | ID:{order_id}")
            self.trade_count += 1

            sl_tx = KiteConnect.TRANSACTION_TYPE_SELL if action == "BUY" else KiteConnect.TRANSACTION_TYPE_BUY
            self.kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR, exchange=exchange,
                tradingsymbol=symbol, transaction_type=sl_tx,
                quantity=quantity, product=product_type,
                order_type=KiteConnect.ORDER_TYPE_SL_M, trigger_price=sl_price,
            )
            log.info(f"[SL SET] {symbol} | SL:{sl_price}")
            send_telegram(f"✅ <b>ORDER EXECUTED!</b>\n{action} {symbol}\nPrice: ₹{price}\nSL: ₹{sl_price}\nT1: ₹{signal_data['t1']}\nT2: ₹{signal_data['t2']}")
            return True

        except Exception as e:
            log.error(f"[EXECUTE ERROR] {e}")
            send_telegram(f"❌ <b>ORDER FAILED!</b> {symbol}\nError: {e}")
            return False

    def square_off_all(self):
        log.info("[SQUAREOFF] Closing all positions...")
        send_telegram("⚠️ Squaring off all positions...")
        try:
            positions = self.kite.positions()
            for pos in positions.get('net', []):
                if pos['quantity'] != 0:
                    action       = "SELL" if pos['quantity'] > 0 else "BUY"
                    product      = "NRML" if pos['product'] == "NRML" else "MIS"
                    product_type = KiteConnect.PRODUCT_MIS if product == "MIS" else KiteConnect.PRODUCT_NRML
                    transaction  = KiteConnect.TRANSACTION_TYPE_BUY if action == "BUY" else KiteConnect.TRANSACTION_TYPE_SELL
                    ltp          = self.get_ltp(pos['exchange'], pos['tradingsymbol'])
                    if ltp:
                        price = round(ltp * 1.002, 1) if action == "BUY" else round(ltp * 0.998, 1)
                        self.kite.place_order(
                            variety=KiteConnect.VARIETY_REGULAR, exchange=pos['exchange'],
                            tradingsymbol=pos['tradingsymbol'], transaction_type=transaction,
                            quantity=abs(pos['quantity']), product=product_type,
                            order_type=KiteConnect.ORDER_TYPE_LIMIT, price=price,
                        )
            log.info("[SQUAREOFF] Done!")
            send_telegram("✅ All positions closed!")
        except Exception as e:
            log.error(f"[SQUAREOFF ERROR] {e}")

    def update_pnl(self):
        try:
            positions      = self.kite.positions()
            self.daily_pnl = sum(pos.get('pnl', 0) for pos in positions.get('net', []))
            return self.daily_pnl
        except:
            return 0

# ================================================================
#  MAIN TRADING SYSTEM
# ================================================================

class TradingSystem:
    def __init__(self, kite):
        self.kite        = kite
        self.executor    = OrderExecutor(kite)
        self.scanned_today = set()

        log.info("=" * 55)
        log.info("COMPLETE TRADING SYSTEM STARTED! v2")
        log.info(f"Scanning: Nifty50 + BankNifty + MCX")
        log.info(f"Max Loss: Rs.{MAX_DAILY_LOSS} | Max Trades: {MAX_TRADES_PER_DAY}")
        log.info("=" * 55)

        # Start Telegram listener in background
        tg_thread = threading.Thread(target=telegram_listener, args=(kite,), daemon=True)
        tg_thread.start()
        log.info("[TG] Telegram listener started!")

    def scan_all(self):
        signals = []

        log.info("[SCAN] Scanning Nifty 50...")
        for stock in NIFTY50_STOCKS:
            if stock in self.scanned_today:
                continue
            try:
                result = analyze_instrument(self.kite, stock, "NSE", 1, 1, "MIS")
                if result:
                    signals.append(result)
                    log.info(f"[SIGNAL] {stock} - {result['signal']} - {result['confidence']}")
                time.sleep(0.3)
            except:
                pass

        log.info("[SCAN] Scanning MCX...")
        for inst in MCX_INSTRUMENTS:
            try:
                result = analyze_instrument(self.kite, inst['symbol'], inst['exchange'], inst['lots'], inst['lot_size'], inst['product'])
                if result:
                    signals.append(result)
                    log.info(f"[SIGNAL] {inst['symbol']} - {result['signal']} - {result['confidence']}")
                time.sleep(0.3)
            except:
                pass

        signals.sort(key=lambda x: x['confidence'], reverse=True)
        return signals[:3]

    def run(self):
        log.info("System running...")
        squared_off = False

        while True:
            try:
                now = datetime.now().strftime("%H:%M")
                pnl = self.executor.update_pnl()

                if now >= SQUAREOFF_TIME and not squared_off:
                    self.executor.square_off_all()
                    squared_off = True
                    log.info("Trading done for today!")
                    send_telegram(f"🏁 Trading done for today!\nFinal P&L: ₹{pnl:.2f}")
                    time.sleep(3600)
                    continue

                if pnl <= -MAX_DAILY_LOSS:
                    log.warning(f"[STOP] Max loss! P&L: Rs.{pnl:.2f}")
                    send_telegram(f"🚨 <b>MAX LOSS HIT!</b>\nP&L: ₹{pnl:.2f}\nAll positions closing...")
                    self.executor.square_off_all()
                    break

                if self.executor.trade_count >= MAX_TRADES_PER_DAY:
                    log.info(f"[STOP] Max trades done!")
                    send_telegram(f"✅ <b>{MAX_TRADES_PER_DAY} trades complete!</b>\nP&L: ₹{pnl:.2f}")
                    time.sleep(3600)
                    continue

                if now < TRADE_START_TIME:
                    log.info(f"[WAIT] Market opens at {TRADE_START_TIME}...")
                    time.sleep(60)
                    continue

                if now > TRADE_END_TIME:
                    log.info("[WAIT] Market closed...")
                    time.sleep(300)
                    continue

                log.info(f"[SCAN] P&L: Rs.{pnl:.2f} | Trades: {self.executor.trade_count}/{MAX_TRADES_PER_DAY}")
                signals = self.scan_all()

                if not signals:
                    log.info("[SCAN] No signals. Waiting 5 min...")
                    time.sleep(300)
                    continue

                for signal in signals:
                    if self.executor.trade_count >= MAX_TRADES_PER_DAY:
                        break
                    symbol = signal['symbol']
                    if symbol in self.scanned_today:
                        continue

                    log.info(f"[SIGNAL] {signal['signal']} on {symbol} | Confidence: {signal['confidence']}")
                    send_signal_telegram(signal)
                    log.info("[WAIT] Waiting for Telegram approval (2 min)...")

                    reply = get_telegram_reply(timeout=120)

                    if reply is True:
                        log.info(f"[APPROVED] Executing {signal['signal']} on {symbol}")
                        success = self.executor.execute(signal)
                        if success:
                            self.scanned_today.add(symbol)
                    elif reply is False:
                        log.info(f"[SKIPPED] {symbol}")
                        send_telegram(f"⏭️ {symbol} skipped.")
                        self.scanned_today.add(symbol)
                    else:
                        log.info(f"[TIMEOUT] {symbol}")
                        send_telegram(f"⏰ No reply — {symbol} cancelled.")
                        self.scanned_today.add(symbol)

                    time.sleep(2)

                log.info("[WAIT] Next scan in 5 min...")
                time.sleep(300)

            except KeyboardInterrupt:
                log.info("[STOP] Stopping...")
                self.executor.square_off_all()
                break
            except Exception as e:
                log.error(f"[ERROR] {e}")
                time.sleep(30)

# ================================================================
#  START - NO input() - Railway pe direct chalta hai
# ================================================================

if __name__ == "__main__":
    log.info("=" * 55)
    log.info("  COMPLETE KITE TRADING SYSTEM v2")
    log.info("  Nifty50 + BankNifty + MCX Scanner")
    log.info("  Telegram: /analyze command active!")
    log.info("=" * 55)

    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(ACCESS_TOKEN)
    log.info("[AUTH] Token set. Starting system...")

    system = TradingSystem(kite)
    system.run()

    log.info("Session complete!")
