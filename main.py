# -*- coding: utf-8 -*-
# main.py - Main entry point
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

from config import *
from broker import broker
from risk import risk
from execution import executor
from signal_engine import scan_all, get_signal
from telegram_bot import send, get_updates, send_signal, send_order_confirmation, send_pnl_update

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
#  STATE
# ================================================================

pending_signal   = None
scanned_today    = set()
waiting_quantity = False

# ================================================================
#  WEB SERVER
# ================================================================

class BotHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global pending_signal, scanned_today

        parsed = urllib.parse.urlparse(self.path)

        if parsed.path in ["/", "/health"]:
            status = "RUNNING" if broker.is_authenticated else "WAITING FOR AUTH"
            self.send_response(200)
            self.end_headers()
            self.wfile.write(f"""
                <html><body style='font-family:Arial;background:#0a0a0f;color:white;text-align:center;padding:50px'>
                <h1 style='color:#00d4aa'>Kite Trading Bot</h1>
                <h2>Status: {status}</h2>
                <p>P&L: Rs.{risk.daily_pnl:.2f} | Trades: {risk.trade_count}/{MAX_TRADES_PER_DAY}</p>
                <p style='color:#666'>Send /auth to @StockWalaBhaiBot on Telegram</p>
                </body></html>
            """.encode())

        elif parsed.path == "/callback":
            params = urllib.parse.parse_qs(parsed.query)
            request_token = params.get("request_token", [None])[0]

            if request_token:
                success = broker.generate_session(request_token)
                if success:
                    scanned_today = set()
                    risk.trade_count = 0
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"""
                        <html><body style='font-family:Arial;background:#0a0a0f;color:white;text-align:center;padding:50px'>
                        <h1 style='color:#00d4aa'>Authentication Successful!</h1>
                        <h2>Trading Bot Started!</h2>
                        <p>Close this window and check Telegram for signals.</p>
                        </body></html>
                    """)
                    send("""<b>Trading Bot Started!</b>

Scanning: Nifty50 + BankNifty + MCX
Max Loss: Rs.50,000
Max Trades: 5/day
Trading: 09:30 - 15:00

Commands:
/analyze SYMBOL - Analyze karo
/status - Status check karo
/stop - Bot band karo

Signals aayenge automatically!""")
                else:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b"Auth failed!")
            else:
                self.send_response(400)
                self.end_headers()
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
#  TELEGRAM COMMAND HANDLER
# ================================================================

def handle_commands():
    global pending_signal, scanned_today, waiting_quantity
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
                log.info(f"[CMD] {text}")

                # /start
                if text == "/start":
                    send("""<b>Kite Trading Bot</b>

Commands:
/auth - Kite authenticate karo
/status - Bot status
/stop - Bot band karo
/analyze RELIANCE - Stock analyze karo
/analyze CRUDEOIL - Commodity analyze karo
/pnl - Today's P&L

Signals aane pe number bhejo (quantity):
1, 2, 5, 10... ya NO to skip""")

                # /auth
                elif text == "/auth":
                    login_url = broker.get_login_url()
                    send(f"""<b>Kite Login:</b>

<a href="{login_url}">Click here to login to Kite</a>

After login, automatically redirect hoga.""")

                # /status
                elif text == "/status":
                    risk.update_pnl()
                    status = "RUNNING" if broker.is_authenticated else "WAITING FOR AUTH"
                    from datetime import datetime
                    send(f"""<b>Bot Status: {status}</b>

P&L: Rs.{risk.daily_pnl:.2f}
Trades: {risk.trade_count}/{MAX_TRADES_PER_DAY}
Open Positions: {len(risk.open_positions)}
Time: {datetime.now().strftime('%H:%M:%S')}
Auth: {'YES' if broker.is_authenticated else 'NO'}""")

                # /pnl
                elif text == "/pnl":
                    risk.update_pnl()
                    send_pnl_update(risk.daily_pnl, risk.trade_count, "RUNNING" if broker.is_authenticated else "STOPPED")

                # /stop
                elif text == "/stop":
                    broker.is_authenticated = False
                    send("Bot stopped!")

                # /analyze SYMBOL
                elif text.upper().startswith("/ANALYZE"):
                    parts = text.split()
                    if len(parts) < 2:
                        send("Usage: /analyze SYMBOL\nExample: /analyze RELIANCE")
                        continue

                    symbol = parts[1].upper()
                    send(f"Analyzing {symbol}... Please wait...")

                    mcx_keywords = ["CRUDEOIL", "SILVER", "SILVERM", "GOLD", "NATURALGAS", "ZINC", "COPPER"]
                    exchange = "MCX" if any(k in symbol for k in mcx_keywords) else "NSE"

                    symbol_map = {
                        "CRUDEOIL":   "CRUDEOIL26JUNFUT",
                        "SILVER":     "SILVERM26JUNFUT",
                        "SILVERM":    "SILVERM26JUNFUT",
                        "GOLD":       "GOLD26JUNFUT",
                        "NATURALGAS": "NATURALGAS26JUNFUT",
                    }
                    kite_symbol = symbol_map.get(symbol, symbol)

                    if broker.is_authenticated:
                        result = get_signal(kite_symbol, exchange)
                        if result:
                            msg = f"""<b>Analysis: {symbol}</b>

<b>Signal: {result['signal']}</b>
Price: Rs.{result['tech']['price']}
VWAP: {result['tech']['vwap']}
RSI: {result['tech']['rsi']}
EMA9: {result['tech']['ema9']}
EMA21: {result['tech']['ema21']}
MACD: {result['tech']['macd']}

Entry: Rs.{result['entry']}
SL: Rs.{result['sl']}
T1: Rs.{result['t1']}
T2: Rs.{result['t2']}

Confidence: {result['confidence']}/100

{result['reason']}"""
                            send(msg)
                        else:
                            send(f"{symbol}: No strong signal at the moment. WAIT.")
                    else:
                        send(f"{symbol}: Please /auth first to get live data.")

                # Quantity input (number) for pending signal
                elif text.isdigit() and pending_signal:
                    qty = int(text)
                    send(f"Executing {pending_signal['signal']} {pending_signal['symbol']} x{qty} lots...")
                    order_id, price = executor.execute(pending_signal, quantity=qty)
                    if order_id:
                        send_order_confirmation(
                            pending_signal["signal"], pending_signal["symbol"],
                            price, qty * pending_signal.get("lot_size", 1),
                            pending_signal["sl"], pending_signal["t1"], pending_signal["t2"],
                            order_id
                        )
                    else:
                        send(f"Order failed: {price}")
                    scanned_today.add(pending_signal["symbol"])
                    pending_signal = None
                    waiting_quantity = False

                # NO - skip signal
                elif text.upper() in ["NO", "N", "NAHI", "SKIP"] and pending_signal:
                    send(f"Skipped {pending_signal['symbol']}")
                    scanned_today.add(pending_signal["symbol"])
                    pending_signal = None
                    waiting_quantity = False

        except Exception as e:
            log.error(f"[CMD] Error: {e}")

        time.sleep(2)

# ================================================================
#  TRADING LOOP
# ================================================================

def trading_loop():
    global pending_signal, scanned_today, waiting_quantity

    while True:
        try:
            if not broker.is_authenticated:
                time.sleep(10)
                continue

            from datetime import datetime
            now = datetime.now().strftime("%H:%M")

            # Update P&L
            risk.update_pnl()

            # Squareoff time
            if risk.is_squareoff_time():
                count = risk.squareoff_all()
                if count > 0:
                    send(f"Squareoff complete!\nFinal P&L: Rs.{risk.daily_pnl:.2f}")
                broker.is_authenticated = False
                time.sleep(3600)
                continue

            # Max loss check
            if risk.is_max_loss_hit():
                send(f"MAX LOSS HIT! P&L: Rs.{risk.daily_pnl:.2f}\nStopping trading!")
                risk.squareoff_all()
                broker.is_authenticated = False
                continue

            # Max trades check
            if risk.is_max_trades_hit():
                time.sleep(300)
                continue

            # Trading hours
            if not risk.is_trading_time():
                time.sleep(60)
                continue

            # Wait if pending signal
            if pending_signal or waiting_quantity:
                time.sleep(5)
                continue

            # Scan
            log.info(f"[MAIN] Scanning... P&L: Rs.{risk.daily_pnl:.2f} | Trades: {risk.trade_count}/{MAX_TRADES_PER_DAY}")
            signals = scan_all()

            # Filter already scanned
            signals = [s for s in signals if s["symbol"] not in scanned_today]

            if signals:
                best = signals[0]
                pending_signal = best
                waiting_quantity = True
                send_signal(best)
                log.info(f"[MAIN] Signal sent: {best['signal']} {best['symbol']}")

                # Auto cancel after timeout
                time.sleep(SIGNAL_TIMEOUT)
                if pending_signal and pending_signal["symbol"] == best["symbol"]:
                    send(f"Timeout! {best['symbol']} signal cancelled.")
                    scanned_today.add(best["symbol"])
                    pending_signal = None
                    waiting_quantity = False
            else:
                log.info("[MAIN] No signals found.")
                time.sleep(300)

        except Exception as e:
            log.error(f"[MAIN] Error: {e}")
            time.sleep(30)

# ================================================================
#  START
# ================================================================

if __name__ == "__main__":
    log.info("=" * 55)
    log.info("KITE TRADING BOT STARTING...")
    log.info(f"Port: {PORT}")
    log.info("=" * 55)

    # Web server
    threading.Thread(target=start_web_server, daemon=True).start()

    # Telegram commands
    threading.Thread(target=handle_commands, daemon=True).start()

    send("""<b>Bot Online!</b>

Send /auth to start trading.

Commands:
/auth - Authenticate
/analyze SYMBOL - Analyze any stock
/status - Check status
/stop - Stop bot""")

    # Trading loop
    trading_loop()
