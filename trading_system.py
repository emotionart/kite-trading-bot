# -*- coding: utf-8 -*-
"""
COMPLETE KITE TRADING SYSTEM
- Nifty 50 + BankNifty stocks scan karta hai
- BUY/SELL signal aata hai
- Telegram pe notification aata hai
- Tum YES/NO karo
- Auto execute with SL + Target
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import time
import logging
import threading
import webbrowser
import http.server
import urllib.parse
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from kiteconnect import KiteConnect

# ================================================================
#  CONFIG - SIRF EK BAAR BHARO
# ================================================================

API_KEY        = "zhve1lfpjxtie9rv"
API_SECRET     = "wr1cwi6ijdpa2phztvhbtm48z79a9jsu"
TELEGRAM_TOKEN = "8701616355:AAGvetI7MfI2f6vJh7LkeujpxHmmtB0OtXE"
CHAT_ID        = "8757681357"

# Risk Settings
MAX_DAILY_LOSS    = 10000   # Rs. 10000 loss pe band
MAX_TRADES_PER_DAY = 5      # Max 5 trades per day
MAX_LOTS          = 2       # Max 2 lots per trade
TRADE_START_TIME  = "09:30"
TRADE_END_TIME    = "15:00"
SQUAREOFF_TIME    = "15:15"

# Nifty 50 + BankNifty stocks to scan
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

# MCX Instruments
MCX_INSTRUMENTS = [
    {"symbol": "SILVERM26JUNFUT",    "exchange": "MCX", "lots": 1, "lot_size": 30,   "product": "NRML"},
    {"symbol": "CRUDEOIL26JUNFUT",   "exchange": "MCX", "lots": 1, "lot_size": 100,  "product": "NRML"},
    {"symbol": "GOLD26JUNFUT",       "exchange": "MCX", "lots": 1, "lot_size": 100,  "product": "NRML"},
    {"symbol": "NATURALGAS26JUNFUT", "exchange": "MCX", "lots": 1, "lot_size": 1250, "product": "NRML"},
]

# EMA/RSI/MACD settings
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
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})
        log.info(f"[TELEGRAM] Message sent")
    except Exception as e:
        log.error(f"[TELEGRAM ERROR] {e}")

def send_signal_telegram(signal_data):
    """Send formatted signal to Telegram"""
    s = signal_data
    icon = "BUY" if s['signal'] == 'BUY' else "SELL"
    pnl_icon = "+" if s['signal'] == 'BUY' else "-"
    
    msg = f"""
<b>SIGNAL: {icon}</b>

<b>Stock/Instrument:</b> {s['symbol']}
<b>Exchange:</b> {s['exchange']}
<b>Type:</b> {s.get('type', 'FUT')}

<b>Entry Price:</b> Rs.{s['entry']}
<b>Stop Loss:</b> Rs.{s['sl']}
<b>Target 1:</b> Rs.{s['t1']}
<b>Target 2:</b> Rs.{s['t2']}

<b>Confidence:</b> {s['confidence']}/100
<b>Risk:Reward:</b> 1:{s['rr']}

<b>Reason:</b>
{s['reason']}

<b>Lots:</b> {s['lots']} | <b>Product:</b> {s['product']}

Reply <b>YES</b> to execute or <b>NO</b> to skip
<i>Auto-cancel in 2 minutes if no reply</i>
"""
    send_telegram(msg)

def get_telegram_reply(timeout=120):
    """Wait for YES/NO reply from user"""
    start = time.time()
    last_update_id = None
    
    while time.time() - start < timeout:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {"timeout": 10, "allowed_updates": ["message"]}
            if last_update_id:
                params["offset"] = last_update_id + 1
            
            r = requests.get(url, params=params, timeout=15)
            data = r.json()
            
            for update in data.get('result', []):
                last_update_id = update['update_id']
                msg = update.get('message', {})
                if str(msg.get('chat', {}).get('id', '')) == CHAT_ID:
                    text = msg.get('text', '').strip().upper()
                    if text in ['YES', 'Y', 'HAN', 'HAAN', 'OK']:
                        return True
                    elif text in ['NO', 'N', 'NAI', 'NAHI', 'SKIP']:
                        return False
        except:
            pass
        time.sleep(2)
    
    return None  # Timeout

# ================================================================
#  AUTO AUTH
# ================================================================

def auto_get_token():
    kite = KiteConnect(api_key=API_KEY)
    access_token = [None]
    server_done = threading.Event()

    class TokenHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            request_token = params.get('request_token', [None])[0]
            if request_token:
                try:
                    session = kite.generate_session(request_token, api_secret=API_SECRET)
                    access_token[0] = session['access_token']
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"<h1 style='color:green;font-family:Arial;text-align:center;margin-top:100px'>Done! Bot starting...</h1>")
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(f"Error: {e}".encode())
            server_done.set()
            threading.Thread(target=self.server.shutdown).start()

        def log_message(self, *args): pass

    server = http.server.HTTPServer(('127.0.0.1', 3000), TokenHandler)
    t = threading.Thread(target=server.serve_forever)
    t.start()
    webbrowser.open(kite.login_url())
    log.info("[AUTH] Browser opened - Login karein aur Authorize dabao...")
    server_done.wait(timeout=120)
    t.join(timeout=5)
    return access_token[0], kite

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
    typical = (df['high'] + df['low'] + df['close']) / 3
    return (typical * df['volume']).cumsum() / df['volume'].cumsum()

def get_confidence_score(conditions):
    """Calculate confidence score 0-100"""
    score = 0
    weights = {
        'vwap': 25,
        'ema_cross': 25,
        'rsi': 20,
        'macd': 20,
        'volume': 10
    }
    for k, v in conditions.items():
        if v and k in weights:
            score += weights[k]
    return score

def analyze_instrument(kite, symbol, exchange, lots=1, lot_size=1, product="MIS"):
    """Full analysis of an instrument"""
    try:
        instrument = kite.ltp(f"{exchange}:{symbol}")
        token = list(instrument.values())[0].get('instrument_token')
        ltp = list(instrument.values())[0].get('last_price', 0)
        
        to_date = datetime.now()
        from_date = to_date - timedelta(days=5)
        
        data = kite.historical_data(
            token,
            from_date.strftime("%Y-%m-%d"),
            to_date.strftime("%Y-%m-%d"),
            CANDLE_INTERVAL
        )
        
        if len(data) < 30:
            return None
            
        df = pd.DataFrame(data)
        df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        
        closes = df['close'].values
        volumes = df['volume'].values
        
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
        
        # Volume analysis
        avg_volume = np.mean(volumes[-20:])
        curr_volume = volumes[-1]
        volume_spike = curr_volume > avg_volume * 1.5
        
        # BUY conditions
        buy_conditions = {
            'vwap': curr_price > curr_vwap,
            'ema_cross': ema_bullish,
            'rsi': 40 <= curr_rsi <= 65,
            'macd': macd_bullish,
            'volume': volume_spike
        }
        
        # SELL conditions
        sell_conditions = {
            'vwap': curr_price < curr_vwap,
            'ema_cross': ema_bearish,
            'rsi': 35 <= curr_rsi <= 60,
            'macd': macd_bearish,
            'volume': volume_spike
        }
        
        buy_score = get_confidence_score(buy_conditions)
        sell_score = get_confidence_score(sell_conditions)
        
        # Need minimum 70% confidence
        if buy_score >= 70:
            signal = 'BUY'
            confidence = buy_score
            conditions = buy_conditions
            sl = round(df.iloc[-2]['low'] * 0.998, 2)
            risk = curr_price - sl
            t1 = round(curr_price + risk * 1.5, 2)
            t2 = round(curr_price + risk * 2.5, 2)
        elif sell_score >= 70:
            signal = 'SELL'
            confidence = sell_score
            conditions = sell_conditions
            sl = round(df.iloc[-2]['high'] * 1.002, 2)
            risk = sl - curr_price
            t1 = round(curr_price - risk * 1.5, 2)
            t2 = round(curr_price - risk * 2.5, 2)
        else:
            return None
        
        # Build reason
        reasons = []
        if conditions['vwap']: reasons.append(f"Price {'above' if signal=='BUY' else 'below'} VWAP ({round(curr_vwap,2)})")
        if conditions['ema_cross']: reasons.append(f"EMA9 {'bullish' if signal=='BUY' else 'bearish'} crossover")
        if conditions['rsi']: reasons.append(f"RSI at {round(curr_rsi,1)} (healthy zone)")
        if conditions['macd']: reasons.append(f"MACD {'bullish' if signal=='BUY' else 'bearish'} crossover")
        if conditions['volume']: reasons.append(f"Volume spike ({round(curr_volume/avg_volume,1)}x avg)")
        
        rr = round((t1 - curr_price) / (curr_price - sl), 1) if signal == 'BUY' else round((curr_price - t1) / (sl - curr_price), 1)
        
        return {
            'symbol': symbol,
            'exchange': exchange,
            'signal': signal,
            'entry': round(curr_price, 2),
            'sl': sl,
            't1': t1,
            't2': t2,
            'confidence': confidence,
            'rr': abs(rr),
            'reason': '\n'.join([f"- {r}" for r in reasons]),
            'lots': lots,
            'lot_size': lot_size,
            'product': product,
            'type': 'FUT'
        }
        
    except Exception as e:
        log.error(f"[ANALYZE ERROR] {symbol}: {e}")
        return None

# ================================================================
#  ORDER EXECUTOR
# ================================================================

class OrderExecutor:
    def __init__(self, kite):
        self.kite = kite
        self.daily_pnl = 0
        self.trade_count = 0

    def get_ltp(self, exchange, symbol):
        try:
            data = self.kite.ltp(f"{exchange}:{symbol}")
            return data[f"{exchange}:{symbol}"]["last_price"]
        except:
            return None

    def execute(self, signal_data):
        symbol = signal_data['symbol']
        exchange = signal_data['exchange']
        action = signal_data['signal']
        quantity = signal_data['lots'] * signal_data['lot_size']
        product = signal_data['product']
        sl_price = signal_data['sl']

        try:
            transaction = KiteConnect.TRANSACTION_TYPE_BUY if action == "BUY" else KiteConnect.TRANSACTION_TYPE_SELL
            product_type = KiteConnect.PRODUCT_MIS if product == "MIS" else KiteConnect.PRODUCT_NRML

            ltp = self.get_ltp(exchange, symbol)
            if not ltp:
                return False

            price = round(ltp * 1.002, 1) if action == "BUY" else round(ltp * 0.998, 1)

            order_id = self.kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=symbol,
                transaction_type=transaction,
                quantity=quantity,
                product=product_type,
                order_type=KiteConnect.ORDER_TYPE_LIMIT,
                price=price,
            )
            
            log.info(f"[ORDER OK] {action} | {symbol} | Qty:{quantity} | Price:{price} | ID:{order_id}")
            self.trade_count += 1
            
            # Place SL
            sl_tx = KiteConnect.TRANSACTION_TYPE_SELL if action == "BUY" else KiteConnect.TRANSACTION_TYPE_BUY
            self.kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=symbol,
                transaction_type=sl_tx,
                quantity=quantity,
                product=product_type,
                order_type=KiteConnect.ORDER_TYPE_SL_M,
                trigger_price=sl_price,
            )
            log.info(f"[SL SET] {symbol} | SL:{sl_price}")
            
            send_telegram(f"[ORDER EXECUTED]\n{action} {symbol}\nPrice: Rs.{price}\nSL: Rs.{sl_price}\nTarget 1: Rs.{signal_data['t1']}\nTarget 2: Rs.{signal_data['t2']}")
            return True
            
        except Exception as e:
            log.error(f"[EXECUTE ERROR] {e}")
            send_telegram(f"[ORDER FAILED] {symbol}\nError: {e}")
            return False

    def square_off_all(self):
        log.info("[SQUAREOFF] Closing all positions...")
        send_telegram("[SQUAREOFF] All positions closing...")
        try:
            positions = self.kite.positions()
            for pos in positions.get('net', []):
                if pos['quantity'] != 0:
                    action = "SELL" if pos['quantity'] > 0 else "BUY"
                    product = "NRML" if pos['product'] == "NRML" else "MIS"
                    product_type = KiteConnect.PRODUCT_MIS if product == "MIS" else KiteConnect.PRODUCT_NRML
                    transaction = KiteConnect.TRANSACTION_TYPE_BUY if action == "BUY" else KiteConnect.TRANSACTION_TYPE_SELL
                    ltp = self.get_ltp(pos['exchange'], pos['tradingsymbol'])
                    if ltp:
                        price = round(ltp * 1.002, 1) if action == "BUY" else round(ltp * 0.998, 1)
                        self.kite.place_order(
                            variety=KiteConnect.VARIETY_REGULAR,
                            exchange=pos['exchange'],
                            tradingsymbol=pos['tradingsymbol'],
                            transaction_type=transaction,
                            quantity=abs(pos['quantity']),
                            product=product_type,
                            order_type=KiteConnect.ORDER_TYPE_LIMIT,
                            price=price,
                        )
            log.info("[SQUAREOFF] Done!")
            send_telegram("[SQUAREOFF] All positions closed!")
        except Exception as e:
            log.error(f"[SQUAREOFF ERROR] {e}")

    def update_pnl(self):
        try:
            positions = self.kite.positions()
            self.daily_pnl = sum(pos.get('pnl', 0) for pos in positions.get('net', []))
            return self.daily_pnl
        except:
            return 0

# ================================================================
#  MAIN TRADING SYSTEM
# ================================================================

class TradingSystem:
    def __init__(self, kite):
        self.kite = kite
        self.executor = OrderExecutor(kite)
        self.scanned_today = set()
        
        log.info("=" * 55)
        log.info("COMPLETE TRADING SYSTEM STARTED!")
        log.info(f"Scanning: Nifty50 + BankNifty + MCX")
        log.info(f"Max Loss: Rs.{MAX_DAILY_LOSS} | Max Trades: {MAX_TRADES_PER_DAY}")
        log.info("=" * 55)
        send_telegram(f"Trading System Started!\nScanning Nifty50 + BankNifty + MCX\nMax Loss: Rs.{MAX_DAILY_LOSS}\nMax Trades: {MAX_TRADES_PER_DAY}\nTrading: {TRADE_START_TIME} - {TRADE_END_TIME}")

    def scan_all(self):
        """Scan all instruments and return best signals"""
        signals = []
        
        # Scan Nifty 50 stocks
        log.info("[SCAN] Scanning Nifty 50 stocks...")
        for stock in NIFTY50_STOCKS:
            if stock in self.scanned_today:
                continue
            try:
                result = analyze_instrument(self.kite, stock, "NSE", lots=1, lot_size=1, product="MIS")
                if result:
                    signals.append(result)
                    log.info(f"[SIGNAL] {stock} - {result['signal']} - Confidence: {result['confidence']}")
                time.sleep(0.3)
            except:
                pass
        
        # Scan MCX
        log.info("[SCAN] Scanning MCX instruments...")
        for inst in MCX_INSTRUMENTS:
            try:
                result = analyze_instrument(
                    self.kite, inst['symbol'], inst['exchange'],
                    inst['lots'], inst['lot_size'], inst['product']
                )
                if result:
                    signals.append(result)
                    log.info(f"[SIGNAL] {inst['symbol']} - {result['signal']} - Confidence: {result['confidence']}")
                time.sleep(0.3)
            except:
                pass
        
        # Sort by confidence
        signals.sort(key=lambda x: x['confidence'], reverse=True)
        return signals[:3]  # Return top 3 signals

    def run(self):
        log.info("System running... Ctrl+C to stop")
        squared_off = False

        while True:
            try:
                now = datetime.now().strftime("%H:%M")
                pnl = self.executor.update_pnl()

                # Squareoff time
                if now >= SQUAREOFF_TIME and not squared_off:
                    self.executor.square_off_all()
                    squared_off = True
                    log.info("Trading done for today!")
                    break

                # Max loss check
                if pnl <= -MAX_DAILY_LOSS:
                    log.warning(f"[STOP] Max loss hit! P&L: Rs.{pnl:.2f}")
                    send_telegram(f"[STOP] Max loss hit!\nP&L: Rs.{pnl:.2f}\nAll positions closing...")
                    self.executor.square_off_all()
                    break

                # Max trades check
                if self.executor.trade_count >= MAX_TRADES_PER_DAY:
                    log.info(f"[STOP] Max {MAX_TRADES_PER_DAY} trades done!")
                    send_telegram(f"[DONE] {MAX_TRADES_PER_DAY} trades complete!\nP&L: Rs.{pnl:.2f}")
                    break

                # Before market
                if now < TRADE_START_TIME:
                    log.info(f"[WAIT] Market opens at {TRADE_START_TIME}...")
                    time.sleep(60)
                    continue

                # After market
                if now > TRADE_END_TIME:
                    log.info("[WAIT] Market closed for NFO...")
                    time.sleep(300)
                    continue

                # Scan for signals
                log.info(f"[SCAN] Starting scan... P&L: Rs.{pnl:.2f} | Trades: {self.executor.trade_count}/{MAX_TRADES_PER_DAY}")
                signals = self.scan_all()

                if not signals:
                    log.info("[SCAN] No strong signals found. Waiting 5 min...")
                    time.sleep(300)
                    continue

                # Process each signal
                for signal in signals:
                    if self.executor.trade_count >= MAX_TRADES_PER_DAY:
                        break

                    symbol = signal['symbol']
                    if symbol in self.scanned_today:
                        continue

                    log.info(f"[SIGNAL] {signal['signal']} on {symbol} | Confidence: {signal['confidence']}")

                    # Send to Telegram and wait for approval
                    send_signal_telegram(signal)
                    log.info(f"[WAIT] Waiting for approval on Telegram (2 min)...")

                    reply = get_telegram_reply(timeout=120)

                    if reply is True:
                        log.info(f"[APPROVED] Executing {signal['signal']} on {symbol}")
                        success = self.executor.execute(signal)
                        if success:
                            self.scanned_today.add(symbol)
                    elif reply is False:
                        log.info(f"[SKIPPED] User skipped {symbol}")
                        send_telegram(f"[SKIPPED] {symbol} trade skipped.")
                        self.scanned_today.add(symbol)
                    else:
                        log.info(f"[TIMEOUT] No reply for {symbol} - skipping")
                        send_telegram(f"[TIMEOUT] No reply received.\n{symbol} trade cancelled.")
                        self.scanned_today.add(symbol)

                    time.sleep(2)

                log.info("[WAIT] Next scan in 5 minutes...")
                time.sleep(300)

            except KeyboardInterrupt:
                log.info("[STOP] Stopping system...")
                self.executor.square_off_all()
                break
            except Exception as e:
                log.error(f"[ERROR] {e}")
                time.sleep(30)

# ================================================================
#  START
# ================================================================

if __name__ == "__main__":
    print("=" * 55)
    print("  COMPLETE KITE TRADING SYSTEM")
    print("  Nifty50 + BankNifty + MCX Scanner")
    print("  Telegram Signal + Approval + Auto Execute")
    print("  Max Loss: Rs.10,000 | Max Trades: 5/day")
    print("=" * 55)

    confirm = input("\nSystem start karein? (yes/no): ")
    if confirm.lower() != "yes":
        print("Cancelled!")
        sys.exit()

    # Auto Auth
    log.info("[STEP 1] Getting fresh Kite token...")
    access_token, kite = auto_get_token()

    if not access_token:
        log.error("Auth failed!")
        sys.exit()

    kite.set_access_token(access_token)
    log.info("[STEP 2] Starting trading system...")

    system = TradingSystem(kite)
    system.run()

    log.info("Session complete!")
