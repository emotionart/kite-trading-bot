# telegram_bot.py - Telegram commands & notifications
# UPDATED: /analyze command added
import requests
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from config import TELEGRAM_TOKEN, CHAT_ID

log = logging.getLogger(__name__)

# ================================================================
#  SEND / RECEIVE
# ================================================================

def send(msg, chat_id=None):
    """Send message to Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": chat_id or CHAT_ID,
            "text": msg,
            "parse_mode": "HTML"
        }, timeout=10)
    except Exception as e:
        log.error(f"[TG] Send error: {e}")

def get_updates(offset=None):
    """Get new messages"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        params = {"timeout": 5, "allowed_updates": ["message"]}
        if offset:
            params["offset"] = offset
        r = requests.get(url, params=params, timeout=10)
        return r.json().get("result", [])
    except:
        return []

# ================================================================
#  EXISTING NOTIFICATIONS
# ================================================================

def send_signal(signal_data):
    """Send formatted signal"""
    s = signal_data
    msg = f"""<b>SIGNAL: {s['signal']}</b>

<b>Symbol:</b> {s['symbol']} [{s['exchange']}]
<b>Entry:</b> Rs.{s['entry']}
<b>Stop Loss:</b> Rs.{s['sl']}
<b>Target 1:</b> Rs.{s['t1']}
<b>Target 2:</b> Rs.{s['t2']}

<b>Confidence:</b> {s['confidence']}/100
<b>Risk:Reward:</b> 1:{s['rr']}

<b>Indicators:</b>
- RSI: {s['tech']['rsi']}
- VWAP: {'Above' if s['signal']=='BUY' else 'Below'}
- EMA: {'Bullish Cross' if s['signal']=='BUY' else 'Bearish Cross'}
- Volume: {'Spike!' if s['tech']['vol_spike'] else 'Normal'}

<b>Kitne lots/shares chahiye?</b>
Reply with number: <b>1</b> / <b>2</b> / <b>5</b> / <b>10</b>
Or reply <b>NO</b> to skip

<i>Auto-cancel in 2 minutes</i>"""
    send(msg)

def send_order_confirmation(action, symbol, price, quantity, sl, t1, t2, order_id):
    msg = f"""<b>ORDER EXECUTED!</b>

{action} {symbol}
Quantity: {quantity}
Price: Rs.{price}
Stop Loss: Rs.{sl}
Target 1: Rs.{t1}
Target 2: Rs.{t2}
Order ID: {order_id}"""
    send(msg)

def send_pnl_update(pnl, trades, status):
    icon = "+" if pnl >= 0 else ""
    msg = f"""<b>P&L Update</b>

Daily P&L: Rs.{icon}{pnl:.2f}
Trades: {trades}
Status: {status}"""
    send(msg)

# ================================================================
#  /analyze COMMAND
# ================================================================

def handle_analyze(symbol_input, kite):
    """
    /analyze RELIANCE           -> NSE equity
    /analyze NIFTY26MAYFUT NFO  -> NFO futures
    /analyze GOLD26JUNFUT MCX   -> MCX commodity
    """
    parts = symbol_input.strip().upper().split()
    symbol = parts[0]

    # Exchange auto-detect
    if len(parts) >= 2:
        exchange = parts[1]
    elif any(x in symbol for x in ["FUT", "CE", "PE"]):
        if any(x in symbol for x in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCAP"]):
            exchange = "NFO"
        elif any(x in symbol for x in ["GOLD", "SILVER", "CRUDE", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM"]):
            exchange = "MCX"
        else:
            exchange = "NFO"
    else:
        exchange = "NSE"

    send(f"🔍 <b>Analyzing {symbol} [{exchange}]...</b>\nEk second...")

    try:
        result = _analyze_stock(symbol, exchange, kite)
        if result:
            send(result)
        else:
            send(
                f"❌ <b>{symbol}</b> ka data nahi mila.\n\n"
                f"Check karo:\n"
                f"- Symbol sahi hai? (e.g. RELIANCE, NIFTY26MAYFUT)\n"
                f"- Market open hai?\n"
                f"- Exchange sahi hai? Try: /analyze {symbol} NSE"
            )
    except Exception as e:
        log.error(f"[ANALYZE] {symbol} error: {e}")
        send(f"❌ Error: {str(e)}")


def _analyze_stock(symbol, exchange, kite):
    """Core analysis logic — returns formatted HTML message"""

    # --- LTP + token ---
    try:
        ltp_data = kite.ltp(f"{exchange}:{symbol}")
        info     = ltp_data[f"{exchange}:{symbol}"]
        ltp      = info["last_price"]
        token    = info["instrument_token"]
    except Exception as e:
        log.error(f"[ANALYZE] LTP failed {symbol}: {e}")
        return None

    # --- Historical candles ---
    try:
        to_date   = datetime.now()
        from_date = to_date - timedelta(days=5)
        candles   = kite.historical_data(
            token,
            from_date.strftime("%Y-%m-%d"),
            to_date.strftime("%Y-%m-%d"),
            "5minute"
        )
        if not candles or len(candles) < 30:
            return None
        df = pd.DataFrame(candles)
        df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
    except Exception as e:
        log.error(f"[ANALYZE] Historical failed {symbol}: {e}")
        return None

    closes  = df['close'].values
    highs   = df['high'].values
    lows    = df['low'].values
    volumes = df['volume'].values

    # EMA 9 / 21
    ema9  = pd.Series(closes).ewm(span=9,  adjust=False).mean().values
    ema21 = pd.Series(closes).ewm(span=21, adjust=False).mean().values

    # RSI 14
    delta = pd.Series(closes).diff()
    gain  = delta.where(delta > 0, 0).rolling(14).mean()
    loss  = -delta.where(delta < 0, 0).rolling(14).mean()
    rsi   = (100 - (100 / (1 + gain / loss))).values

    # MACD 12/26/9
    ema12       = pd.Series(closes).ewm(span=12, adjust=False).mean()
    ema26       = pd.Series(closes).ewm(span=26, adjust=False).mean()
    macd_line   = (ema12 - ema26).values
    signal_line = pd.Series(macd_line).ewm(span=9, adjust=False).mean().values

    # VWAP
    typical = (df['high'] + df['low'] + df['close']) / 3
    vwap    = ((typical * df['volume']).cumsum() / df['volume'].cumsum()).values

    # Bollinger Bands 20,2
    sma20    = pd.Series(closes).rolling(20).mean().values
    std20    = pd.Series(closes).rolling(20).std().values
    bb_upper = sma20 + 2 * std20
    bb_lower = sma20 - 2 * std20

    # Volume
    avg_vol   = np.mean(volumes[-20:])
    vol_spike = volumes[-1] > avg_vol * 1.5
    vol_ratio = round(volumes[-1] / avg_vol, 1)

    # Day OHLC
    today    = datetime.now().date()
    today_df = df[pd.to_datetime(df['date']).dt.date == today]
    if len(today_df) > 0:
        day_open = today_df.iloc[0]['open']
        day_high = today_df['high'].max()
        day_low  = today_df['low'].min()
    else:
        day_open = df.iloc[-1]['open']
        day_high = highs[-1]
        day_low  = lows[-1]

    # Current values
    curr_price = closes[-1]
    curr_vwap  = vwap[-1]
    curr_rsi   = rsi[-1]
    curr_macd  = macd_line[-1]
    curr_sig   = signal_line[-1]
    curr_ema9  = ema9[-1]
    curr_ema21 = ema21[-1]

    # --- Conditions ---
    ema_bullish   = (ema9[-2] <= ema21[-2]) and (ema9[-1] > ema21[-1])
    ema_bearish   = (ema9[-2] >= ema21[-2]) and (ema9[-1] < ema21[-1])
    macd_bullish  = (macd_line[-2] <= signal_line[-2]) and (macd_line[-1] > signal_line[-1])
    macd_bearish  = (macd_line[-2] >= signal_line[-2]) and (macd_line[-1] < signal_line[-1])
    above_vwap    = curr_price > curr_vwap
    rsi_overbought = curr_rsi > 70
    rsi_oversold   = curr_rsi < 30

    # Scoring
    buy_score = sum([
        above_vwap,
        ema_bullish or curr_ema9 > curr_ema21,
        40 <= curr_rsi <= 65,
        macd_bullish or curr_macd > curr_sig,
        vol_spike
    ]) * 20

    sell_score = sum([
        not above_vwap,
        ema_bearish or curr_ema9 < curr_ema21,
        35 <= curr_rsi <= 60,
        macd_bearish or curr_macd < curr_sig,
        vol_spike
    ]) * 20

    # Signal + levels
    if buy_score >= 60:
        signal     = "🟢 BUY"
        sl         = round(min(lows[-3:]) * 0.998, 2)
        risk       = curr_price - sl
        t1         = round(curr_price + risk * 1.5, 2)
        t2         = round(curr_price + risk * 2.5, 2)
        confidence = buy_score
    elif sell_score >= 60:
        signal     = "🔴 SELL"
        sl         = round(max(highs[-3:]) * 1.002, 2)
        risk       = sl - curr_price
        t1         = round(curr_price - risk * 1.5, 2)
        t2         = round(curr_price - risk * 2.5, 2)
        confidence = sell_score
    else:
        signal     = "⚪ WAIT"
        sl         = round(min(lows[-3:]) * 0.998, 2)
        risk       = curr_price - sl if curr_price > sl else 1
        t1         = round(curr_price + risk * 1.5, 2)
        t2         = round(curr_price + risk * 2.5, 2)
        confidence = max(buy_score, sell_score)

    rr = round(risk * 1.5 / risk, 1) if risk > 0 else 1.5

    # Indicator status lines
    ema_txt  = ("✅ Bullish cross" if ema_bullish else
                "❌ Bearish cross" if ema_bearish else
                "📈 Above EMA21"  if curr_ema9 > curr_ema21 else "📉 Below EMA21")
    vwap_txt = f"{'✅ Above' if above_vwap else '❌ Below'} (₹{round(curr_vwap,2)})"
    rsi_txt  = (f"🔥 Overbought ({round(curr_rsi,1)})" if rsi_overbought else
                f"💚 Oversold ({round(curr_rsi,1)})"   if rsi_oversold   else
                f"✅ Normal ({round(curr_rsi,1)})")
    macd_txt = (f"✅ Bullish ({round(curr_macd,3)})" if macd_bullish or curr_macd > curr_sig else
                f"❌ Bearish ({round(curr_macd,3)})")
    vol_txt  = (f"🔥 Spike! {vol_ratio}x avg" if vol_spike else f"😐 Normal ({vol_ratio}x avg)")
    bb_txt   = ("⚠️ Near Upper Band" if curr_price > bb_upper[-1] * 0.998 else
                "⚠️ Near Lower Band" if curr_price < bb_lower[-1] * 1.002 else
                "✅ Inside Bands")

    # Day change
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
R:R = 1:{rr}

<i>⏰ {datetime.now().strftime('%d-%b-%Y %H:%M')} | Chart: 5min</i>"""

    return msg


# ================================================================
#  COMMAND HANDLER
#  main.py ke bot loop mein yeh integrate karo (neeche dekho)
# ================================================================

def process_command(text, kite):
    """
    Bot loop mein call karo:
        process_command(msg_text, bot.kite)
    """
    text = text.strip()

    # /analyze SYMBOL [EXCHANGE]
    if text.lower().startswith("/analyze"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send(
                "📊 <b>Usage:</b>\n"
                "/analyze RELIANCE\n"
                "/analyze HDFCBANK\n"
                "/analyze NIFTY26MAYFUT NFO\n"
                "/analyze GOLD26JUNFUT MCX\n"
                "/analyze CRUDEOIL26JUNFUT MCX"
            )
        else:
            handle_analyze(parts[1], kite)

    # /help
    elif text.lower() == "/help":
        send(
            "🤖 <b>Bot Commands:</b>\n\n"
            "/analyze SYMBOL — Full technical analysis\n"
            "/analyze SYMBOL EXCHANGE — e.g. /analyze NIFTY26MAYFUT NFO\n\n"
            "<b>Examples:</b>\n"
            "/analyze RELIANCE\n"
            "/analyze NIFTY26MAYFUT NFO\n"
            "/analyze GOLD26JUNFUT MCX"
        )

    else:
        # Unknown command — ignore silently or log
        log.info(f"[CMD] Unknown: {text}")
