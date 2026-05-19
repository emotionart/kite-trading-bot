# -*- coding: utf-8 -*-
"""
CLOUD TRADING BOT - Railway.app ke liye
Telegram se /auth bhejo → Link milega → Click karo → Bot start!
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os
import time
import logging
import threading
import http.server
import urllib.parse
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from kiteconnect import KiteConnect

# ================================================================
#  CONFIG - Environment Variables se milega (Railway pe set karo)
# ================================================================

API_KEY        = os.environ.get("KITE_API_KEY", "zhve1lfpjxtie9rv")
API_SECRET     = os.environ.get("KITE_API_SECRET", "wr1cwi6ijdpa2phztvhbtm48z79a9jsu")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8701616355:AAGvetI7MfI2f6vJh7LkeujpxHmmtB0OtXE")
CHAT_ID        = os.environ.get("CHAT_ID", "8757681357")
PORT           = int(os.environ.get("PORT", 8080))

# Trading config
MAX_DAILY_LOSS     = 10000
MAX_TRADES_PER_DAY = 5
TRADE_START_TIME   = "09:30"
TRADE_END_TIME     = "15:00"
SQUAREOFF_TIME     = "15:15"

# Instruments
NIFTY50_STOCKS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
    "LT", "AXISBANK", "MARUTI", "TITAN", "SUNPHARMA",
    "BAJFINANCE", "WIPRO", "TATAMOTORS", "HCLTECH", "TECHM"
]

MCX_INSTRUMENTS = [
    {"symbol": "SILVERM26JUNFUT",    "exchange": "MCX", "lots": 1, "lot_size": 30,   "product": "NRML"},
    {"symbol": "CRUDEOIL26JUNFUT",   "exchange": "MCX", "lots": 1, "lot_size": 100,  "product": "NRML"},
    {"symbol": "GOLD26JUNFUT",       "exchange": "MCX", "lots": 1, "lot_size": 100,  "product": "NRML"},
    {"symbol": "NATURALGAS26JUNFUT", "exchange": "MCX", "lots": 1, "lot_size": 1250, "product": "NRML"},
]

EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
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
    handlers=[SafeStreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

# ================================================================
#  GLOBAL STATE
# ================================================================

kite = KiteConnect(api_key=API_KEY)
access_token = None
bot_running = False
trade_count = 0
daily_pnl = 0
scanned_today = set()
pending_signal = None

# ================================================================
#  TELEGRAM
# ================================================================

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        log.error(f"[TELEGRAM ERROR] {e}")

def get_updates(offset=None):
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
#  WEB SERVER - Auth callback + Health check
# ================================================================

class BotHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global access_token, bot_running, scanned_today, trade_count

        parsed = urllib.parse.urlparse(self.path)

        # Health check
        if parsed.path == "/" or parsed.path == "/health":
            status = "RUNNING" if bot_running else "WAITING FOR AUTH"
            self.send_response(200)
            self.end_headers()
            self.wfile.write(f"""
                <html><body style='font-family:Arial;background:#0a0a0f;color:white;text-align:center;padding:50px'>
                <h1 style='color:#00d4aa'>Kite Trading Bot</h1>
                <h2>Status: {status}</h2>
                <p>P&L: Rs.{daily_pnl:.2f} | Trades: {trade_count}/{MAX_TRADES_PER_DAY}</p>
                <p style='color:#666'>Send /auth to @StockWalaBhaiBot on Telegram to authenticate</p>
                </body></html>
            """.encode())

        # Kite OAuth callback
        elif parsed.path == "/callback":
            params = urllib.parse.parse_qs(parsed.query)
            request_token = params.get("request_token", [None])[0]

            if request_token:
                try:
                    session = kite.generate_session(request_token, api_secret=API_SECRET)
                    access_token = session["access_token"]
                    kite.set_access_token(access_token)
                    bot_running = True
                    scanned_today = set()
                    trade_count = 0

                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"""
                        <html><body style='font-family:Arial;background:#0a0a0f;color:white;text-align:center;padding:50px'>
                        <h1 style='color:#00d4aa'>Authentication Successful!</h1>
                        <h2>Trading Bot Started!</h2>
                        <p>Close this window and check Telegram for signals.</p>
                        </body></html>
                    """)

                    log.info("[AUTH] Token received! Bot starting...")
                    send_telegram("""
Trading Bot Started!
Scanning: Nifty50 + MCX
Max Loss: Rs.10,000
Max Trades: 5/day
Trading: 09:30 - 15:00

Signals aayenge Telegram pe!
Reply YES to buy, NO to skip.
                    """)

                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(f"Error: {e}".encode())
                    log.error(f"[AUTH ERROR] {e}")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"No token found")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass

def start_web_server():
    server = http.server.HTTPServer(("0.0.0.0", PORT), BotHandler)
    log.info(f"[SERVER] Running on port {PORT}")
    server.serve_forever()

# ================================================================
#  INDICATORS
# ================================================================

def calculate_ema(prices, period):
    return pd.Series(prices).ewm(span=period, adjust=False).mean().values

def calculate_rsi(prices, period=14):
    prices = pd.Series(prices)
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    return (100 - (100 / (1 + rs))).values

def calculate_macd(prices, fast=12, slow=26, signal=9):
    prices = pd.Series(prices)
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line.values, signal_line.values

def calculate_vwap(df):
    typical = (df["high"] + df["low"] + df["close"]) / 3
    return (typical * df["volume"]).cumsum() / df["volume"].cumsum()

def analyze(symbol, exchange, lots=1, lot_size=1, product="MIS"):
    try:
        instrument = kite.ltp(f"{exchange}:{symbol}")
        token = list(instrument.values())[0].get("instrument_token")
        to_date = datetime.now()
        from_date = to_date - timedelta(days=5)
        data = kite.historical_data(token, from_date.strftime("%Y-%m-%d"), to_date.strftime("%Y-%m-%d"), CANDLE_INTERVAL)
        if len(data) < 30:
            return None
        df = pd.DataFrame(data)
        df.columns = ["date", "open", "high", "low", "close", "volume"]
        closes = df["close"].values
        volumes = df["volume"].values
        ema_fast = calculate_ema(closes, EMA_FAST)
        ema_slow = calculate_ema(closes, EMA_SLOW)
        rsi = calculate_rsi(closes, RSI_PERIOD)
        macd_line, signal_line = calculate_macd(closes, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
        vwap = calculate_vwap(df)
        curr_price = closes[-1]
        curr_vwap = vwap.iloc[-1]
        curr_rsi = rsi[-1]
        ema_bullish = (ema_fast[-2] <= ema_slow[-2]) and (ema_fast[-1] > ema_slow[-1])
        ema_bearish = (ema_fast[-2] >= ema_slow[-2]) and (ema_fast[-1] < ema_slow[-1])
        macd_bullish = (macd_line[-2] <= signal_line[-2]) and (macd_line[-1] > signal_line[-1])
        macd_bearish = (macd_line[-2] >= signal_line[-2]) and (macd_line[-1] < signal_line[-1])
        avg_vol = np.mean(volumes[-20:])
        vol_spike = volumes[-1] > avg_vol * 1.5

        buy_score = sum([
            curr_price > curr_vwap,
            ema_bullish,
            40 <= curr_rsi <= 65,
            macd_bullish,
            vol_spike
        ]) * 20

        sell_score = sum([
            curr_price < curr_vwap,
            ema_bearish,
            35 <= curr_rsi <= 60,
            macd_bearish,
            vol_spike
        ]) * 20

        if buy_score >= 60:
            signal = "BUY"
            sl = round(df.iloc[-2]["low"] * 0.998, 2)
            risk = curr_price - sl
            t1 = round(curr_price + risk * 1.5, 2)
            t2 = round(curr_price + risk * 2.5, 2)
            confidence = buy_score
        elif sell_score >= 60:
            signal = "SELL"
            sl = round(df.iloc[-2]["high"] * 1.002, 2)
            risk = sl - curr_price
            t1 = round(curr_price - risk * 1.5, 2)
            t2 = round(curr_price - risk * 2.5, 2)
            confidence = sell_score
        else:
            return None

        reasons = []
        if curr_price > curr_vwap: reasons.append(f"Price {'above' if signal=='BUY' else 'below'} VWAP")
        if ema_bullish or ema_bearish: reasons.append(f"EMA9 {'bullish' if signal=='BUY' else 'bearish'} cross")
        if 35 <= curr_rsi <= 65: reasons.append(f"RSI {round(curr_rsi,1)}")
        if macd_bullish or macd_bearish: reasons.append(f"MACD {'bullish' if signal=='BUY' else 'bearish'}")
        if vol_spike: reasons.append(f"Volume spike {round(volumes[-1]/avg_vol,1)}x")

        return {
            "symbol": symbol, "exchange": exchange,
            "signal": signal, "entry": round(curr_price, 2),
            "sl": sl, "t1": t1, "t2": t2,
            "confidence": confidence,
            "rr": round(abs((t1-curr_price)/(curr_price-sl)) if signal=="BUY" else abs((curr_price-t1)/(sl-curr_price)), 1),
            "reason": "\n".join([f"- {r}" for r in reasons]),
            "lots": lots, "lot_size": lot_size, "product": product
        }
    except Exception as e:
        log.error(f"[ANALYZE ERROR] {symbol}: {e}")
        return None

# ================================================================
#  ORDER EXECUTOR
# ================================================================

def execute_trade(signal_data):
    global trade_count
    symbol = signal_data["symbol"]
    exchange = signal_data["exchange"]
    action = signal_data["signal"]
    quantity = signal_data["lots"] * signal_data["lot_size"]
    product = signal_data["product"]
    sl_price = signal_data["sl"]

    try:
        transaction = KiteConnect.TRANSACTION_TYPE_BUY if action == "BUY" else KiteConnect.TRANSACTION_TYPE_SELL
        product_type = KiteConnect.PRODUCT_MIS if product == "MIS" else KiteConnect.PRODUCT_NRML
        ltp_data = kite.ltp(f"{exchange}:{symbol}")
        ltp = ltp_data[f"{exchange}:{symbol}"]["last_price"]
        price = round(ltp * 1.002, 1) if action == "BUY" else round(ltp * 0.998, 1)

        order_id = kite.place_order(
            variety=KiteConnect.VARIETY_REGULAR,
            exchange=exchange, tradingsymbol=symbol,
            transaction_type=transaction, quantity=quantity,
            product=product_type, order_type=KiteConnect.ORDER_TYPE_LIMIT, price=price,
        )
        trade_count += 1
        log.info(f"[ORDER OK] {action} {symbol} | Price:{price} | ID:{order_id}")

        sl_tx = KiteConnect.TRANSACTION_TYPE_SELL if action == "BUY" else KiteConnect.TRANSACTION_TYPE_BUY
        kite.place_order(
            variety=KiteConnect.VARIETY_REGULAR,
            exchange=exchange, tradingsymbol=symbol,
            transaction_type=sl_tx, quantity=quantity,
            product=product_type, order_type=KiteConnect.ORDER_TYPE_SL_M, trigger_price=sl_price,
        )

        send_telegram(f"ORDER EXECUTED!\n{action} {symbol}\nPrice: Rs.{price}\nSL: Rs.{sl_price}\nT1: Rs.{signal_data['t1']}\nT2: Rs.{signal_data['t2']}")
        return True
    except Exception as e:
        log.error(f"[EXECUTE ERROR] {e}")
        send_telegram(f"ORDER FAILED!\n{symbol}\nError: {str(e)[:100]}")
        return False

# ================================================================
#  TELEGRAM COMMAND HANDLER
# ================================================================

def handle_telegram_commands():
    global access_token, bot_running, pending_signal, scanned_today, trade_count
    last_update_id = None

    while True:
        try:
            updates = get_updates(last_update_id)
            for update in updates:
                last_update_id = update["update_id"] + 1
                msg = update.get("message", {})
                if str(msg.get("chat", {}).get("id", "")) != CHAT_ID:
                    continue

                text = msg.get("text", "").strip()
                log.info(f"[TELEGRAM CMD] {text}")

                if text == "/auth":
                    # Generate login URL
                    login_url = kite.login_url()
                    # Replace redirect to our server
                    railway_url = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "localhost")
                    callback_url = f"https://{railway_url}/callback"
                    send_telegram(f"Kite Login Link:\n{login_url}\n\nNote: After login, you'll be redirected automatically.\n\nIf not working, visit:\n{callback_url}")

                elif text == "/status":
                    status = "RUNNING" if bot_running else "WAITING FOR AUTH"
                    send_telegram(f"Bot Status: {status}\nP&L: Rs.{daily_pnl:.2f}\nTrades: {trade_count}/{MAX_TRADES_PER_DAY}\nTime: {datetime.now().strftime('%H:%M:%S')}")

                elif text == "/stop":
                    bot_running = False
                    send_telegram("Bot stopped!")

                elif text == "/start":
                    send_telegram("Commands:\n/auth - Authenticate with Kite\n/status - Bot status\n/stop - Stop bot\n\nSend YES or NO to approve/reject signals.")

                elif text.upper() in ["YES", "Y", "HAAN", "OK"] and pending_signal:
                    send_telegram(f"Executing {pending_signal['signal']} on {pending_signal['symbol']}...")
                    execute_trade(pending_signal)
                    scanned_today.add(pending_signal["symbol"])
                    pending_signal = None

                elif text.upper() in ["NO", "N", "NAHI", "SKIP"] and pending_signal:
                    send_telegram(f"Skipped {pending_signal['symbol']}")
                    scanned_today.add(pending_signal["symbol"])
                    pending_signal = None

        except Exception as e:
            log.error(f"[CMD HANDLER ERROR] {e}")

        time.sleep(2)

# ================================================================
#  TRADING LOOP
# ================================================================

def trading_loop():
    global bot_running, daily_pnl, scanned_today, trade_count, pending_signal

    while True:
        try:
            if not bot_running or not access_token:
                time.sleep(10)
                continue

            now = datetime.now().strftime("%H:%M")

            # Squareoff
            if now >= SQUAREOFF_TIME:
                log.info("[SQUAREOFF] Closing positions...")
                try:
                    positions = kite.positions()
                    for pos in positions.get("net", []):
                        if pos["quantity"] != 0:
                            action = "SELL" if pos["quantity"] > 0 else "BUY"
                            product_type = KiteConnect.PRODUCT_MIS if pos["product"] == "MIS" else KiteConnect.PRODUCT_NRML
                            transaction = KiteConnect.TRANSACTION_TYPE_BUY if action == "BUY" else KiteConnect.TRANSACTION_TYPE_SELL
                            ltp_data = kite.ltp(f"{pos['exchange']}:{pos['tradingsymbol']}")
                            ltp = ltp_data[f"{pos['exchange']}:{pos['tradingsymbol']}"]["last_price"]
                            price = round(ltp * 1.002, 1) if action == "BUY" else round(ltp * 0.998, 1)
                            kite.place_order(
                                variety=KiteConnect.VARIETY_REGULAR,
                                exchange=pos["exchange"], tradingsymbol=pos["tradingsymbol"],
                                transaction_type=transaction, quantity=abs(pos["quantity"]),
                                product=product_type, order_type=KiteConnect.ORDER_TYPE_LIMIT, price=price,
                            )
                    send_telegram("All positions closed for today!")
                except Exception as e:
                    log.error(f"[SQUAREOFF ERROR] {e}")
                bot_running = False
                time.sleep(3600)
                continue

            # Update PnL
            try:
                positions = kite.positions()
                daily_pnl = sum(pos.get("pnl", 0) for pos in positions.get("net", []))
            except:
                pass

            # Max loss check
            if daily_pnl <= -MAX_DAILY_LOSS:
                send_telegram(f"MAX LOSS HIT! P&L: Rs.{daily_pnl:.2f}\nStopping trading!")
                bot_running = False
                continue

            # Max trades
            if trade_count >= MAX_TRADES_PER_DAY:
                time.sleep(300)
                continue

            # Trading hours
            if not (TRADE_START_TIME <= now <= TRADE_END_TIME):
                time.sleep(60)
                continue

            # Pending signal wait
            if pending_signal:
                time.sleep(5)
                continue

            # Scan stocks
            log.info(f"[SCAN] Scanning... P&L: Rs.{daily_pnl:.2f} | Trades: {trade_count}/{MAX_TRADES_PER_DAY}")

            signals = []
            for stock in NIFTY50_STOCKS:
                if stock in scanned_today:
                    continue
                result = analyze(stock, "NSE", lots=1, lot_size=1, product="MIS")
                if result:
                    signals.append(result)
                time.sleep(0.3)

            for inst in MCX_INSTRUMENTS:
                if inst["symbol"] in scanned_today:
                    continue
                result = analyze(inst["symbol"], inst["exchange"], inst["lots"], inst["lot_size"], inst["product"])
                if result:
                    signals.append(result)
                time.sleep(0.3)

            signals.sort(key=lambda x: x["confidence"], reverse=True)

            if signals:
                s = signals[0]
                pending_signal = s
                msg = f"""
<b>SIGNAL: {s['signal']}</b>

<b>Symbol:</b> {s['symbol']}
<b>Exchange:</b> {s['exchange']}
<b>Entry:</b> Rs.{s['entry']}
<b>Stop Loss:</b> Rs.{s['sl']}
<b>Target 1:</b> Rs.{s['t1']}
<b>Target 2:</b> Rs.{s['t2']}
<b>Confidence:</b> {s['confidence']}/100
<b>Risk:Reward:</b> 1:{s['rr']}

<b>Reason:</b>
{s['reason']}

Reply <b>YES</b> to execute or <b>NO</b> to skip
<i>Auto-cancel in 2 min</i>
"""
                send_telegram(msg)
                log.info(f"[SIGNAL SENT] {s['signal']} {s['symbol']}")

                # Auto cancel after 2 min
                time.sleep(120)
                if pending_signal and pending_signal["symbol"] == s["symbol"]:
                    send_telegram(f"Timeout! {s['symbol']} signal cancelled.")
                    scanned_today.add(s["symbol"])
                    pending_signal = None
            else:
                log.info("[SCAN] No signals found.")

            time.sleep(300)

        except Exception as e:
            log.error(f"[TRADING ERROR] {e}")
            time.sleep(30)

# ================================================================
#  START
# ================================================================

if __name__ == "__main__":
    log.info("=" * 50)
    log.info("CLOUD TRADING BOT STARTING...")
    log.info(f"Port: {PORT}")
    log.info("=" * 50)

    # Start web server in background
    server_thread = threading.Thread(target=start_web_server, daemon=True)
    server_thread.start()

    # Start telegram command handler in background
    telegram_thread = threading.Thread(target=handle_telegram_commands, daemon=True)
    telegram_thread.start()

    send_telegram("Bot Online! Send /auth to start trading.")

    # Start trading loop
    trading_loop()
 
