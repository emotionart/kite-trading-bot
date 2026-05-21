# telegram_bot.py - Telegram commands & notifications
import requests
import logging
from config import TELEGRAM_TOKEN, CHAT_ID

log = logging.getLogger(__name__)

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
