# -*- coding: utf-8 -*-
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import time
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from kiteconnect import KiteConnect

# ================================================================
#  CONFIG
# ================================================================

API_KEY = "zhve1lfpjxtie9rv"
API_SECRET = "wr1cwi6ijdpa2phztvhbtm48z79a9jsu"
ACCESS_TOKEN = "nwbM8lH7WR56RP5u3nqQMFWZKmVrxE9J"  # Har roz update karo

# ================================================================
#  INSTRUMENTS
#  NFO = Nifty/BankNifty F&O  -> PRODUCT_MIS
#  MCX = Commodity            -> PRODUCT_NRML
# ================================================================

INSTRUMENTS = [
    # --- NFO ---
    {"symbol": "NIFTY26MAYFUT",    "exchange": "NFO", "lots": 1, "lot_size": 25,  "product": "MIS", "trade_end": "15:00", "squareoff": "15:15"},

    # --- MCX ---
    {"symbol": "SILVERM26JUNFUT",  "exchange": "MCX", "lots": 1, "lot_size": 30,  "product": "NRML", "trade_end": "23:25", "squareoff": "23:30"},
    {"symbol": "CRUDEOIL26JUNFUT", "exchange": "MCX", "lots": 1, "lot_size": 100, "product": "NRML", "trade_end": "23:25", "squareoff": "23:30"},
    {"symbol": "GOLD26JUNFUT",     "exchange": "MCX", "lots": 1, "lot_size": 100, "product": "NRML", "trade_end": "23:25", "squareoff": "23:30"},
    {"symbol": "NATURALGAS26JUNFUT","exchange": "MCX", "lots": 1, "lot_size": 1250,"product": "NRML", "trade_end": "23:25", "squareoff": "23:30"},
]

MAX_DAILY_LOSS = 5000
MAX_TRADES_PER_DAY = 10
TRADE_START_TIME = "09:30"

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
        except Exception:
            self.handleError(record)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(f'trading_log_{datetime.now().strftime("%Y%m%d")}.log', encoding='utf-8'),
        SafeStreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)

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
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    return (typical_price * df['volume']).cumsum() / df['volume'].cumsum()

# ================================================================
#  SIGNAL
# ================================================================

def get_signal(df):
    if len(df) < 30:
        return "WAIT", {}

    closes = df['close'].values
    ema_fast = calculate_ema(closes, EMA_FAST)
    ema_slow = calculate_ema(closes, EMA_SLOW)
    rsi = calculate_rsi(closes, RSI_PERIOD)
    macd_line, signal_line = calculate_macd(closes, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
    vwap = calculate_vwap(df)

    curr_price = closes[-1]
    curr_vwap = vwap.iloc[-1]
    curr_rsi = rsi[-1]

    ema_bullish_cross = (ema_fast[-2] <= ema_slow[-2]) and (ema_fast[-1] > ema_slow[-1])
    ema_bearish_cross = (ema_fast[-2] >= ema_slow[-2]) and (ema_fast[-1] < ema_slow[-1])
    macd_bullish = (macd_line[-2] <= signal_line[-2]) and (macd_line[-1] > signal_line[-1])
    macd_bearish = (macd_line[-2] >= signal_line[-2]) and (macd_line[-1] < signal_line[-1])

    indicators = {
        "price": curr_price,
        "vwap": round(curr_vwap, 2),
        "ema9": round(ema_fast[-1], 2),
        "ema21": round(ema_slow[-1], 2),
        "rsi": round(curr_rsi, 2),
        "macd": round(macd_line[-1], 4),
    }

    if curr_price > curr_vwap and ema_bullish_cross and 40 <= curr_rsi <= 65 and macd_bullish:
        return "BUY", indicators
    elif curr_price < curr_vwap and ema_bearish_cross and 35 <= curr_rsi <= 60 and macd_bearish:
        return "SELL", indicators
    else:
        return "WAIT", indicators

# ================================================================
#  ORDER MANAGER
# ================================================================

class OrderManager:
    def __init__(self, kite):
        self.kite = kite
        self.daily_pnl = 0
        self.trade_count = 0

    def get_ltp(self, exchange, symbol):
        try:
            ltp_data = self.kite.ltp(f"{exchange}:{symbol}")
            return ltp_data[f"{exchange}:{symbol}"]["last_price"]
        except:
            return None

    def place_order(self, symbol, exchange, action, quantity, product="MIS"):
        try:
            transaction = KiteConnect.TRANSACTION_TYPE_BUY if action == "BUY" else KiteConnect.TRANSACTION_TYPE_SELL
            product_type = KiteConnect.PRODUCT_MIS if product == "MIS" else KiteConnect.PRODUCT_NRML

            ltp = self.get_ltp(exchange, symbol)
            if ltp is None or ltp == 0:
                log.error(f"[ORDER FAILED] Could not get LTP for {symbol}")
                return None

            # Limit price with small buffer
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
            log.info(f"[ORDER OK] {action} | {symbol} | Qty:{quantity} | Price:{price} | Product:{product} | ID:{order_id}")
            self.trade_count += 1
            return order_id
        except Exception as e:
            log.error(f"[ORDER FAILED] {symbol} | {e}")
            return None

    def set_stop_loss(self, symbol, exchange, action, quantity, sl_price, product="MIS"):
        try:
            sl_transaction = KiteConnect.TRANSACTION_TYPE_SELL if action == "BUY" else KiteConnect.TRANSACTION_TYPE_BUY
            product_type = KiteConnect.PRODUCT_MIS if product == "MIS" else KiteConnect.PRODUCT_NRML
            order_id = self.kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=symbol,
                transaction_type=sl_transaction,
                quantity=quantity,
                product=product_type,
                order_type=KiteConnect.ORDER_TYPE_SL_M,
                trigger_price=sl_price,
            )
            log.info(f"[SL SET] {symbol} | SL:{sl_price} | ID:{order_id}")
        except Exception as e:
            log.error(f"[SL FAILED] {e}")

    def square_off_all(self, product="MIS"):
        log.info(f"[SQUAREOFF] Closing {product} positions...")
        try:
            positions = self.kite.positions()
            for pos in positions.get('net', []):
                if pos['quantity'] != 0:
                    action = "SELL" if pos['quantity'] > 0 else "BUY"
                    self.place_order(pos['tradingsymbol'], pos['exchange'], action, abs(pos['quantity']), product)
            log.info("[SQUAREOFF] Done!")
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
#  MAIN BOT
# ================================================================

class TradingBot:
    def __init__(self):
        self.kite = KiteConnect(api_key=API_KEY)
        self.kite.set_access_token(ACCESS_TOKEN)
        self.order_mgr = OrderManager(self.kite)
        self.active_positions = {}
        log.info("=" * 55)
        log.info("KITE AUTO BOT STARTED! v4")
        log.info("Strategy: VWAP + EMA9/21 + RSI + MACD")
        log.info("NFO: MIS | MCX: NRML")
        log.info(f"Max Loss: Rs.{MAX_DAILY_LOSS} | Max Trades: {MAX_TRADES_PER_DAY}")
        log.info("Instruments:")
        for i in INSTRUMENTS:
            log.info(f"  >> {i['symbol']} [{i['exchange']}] {i['product']}")
        log.info("=" * 55)

    def get_candles(self, symbol, exchange):
        try:
            instrument = self.kite.ltp(f"{exchange}:{symbol}")
            token = list(instrument.values())[0].get('instrument_token')
            to_date = datetime.now()
            from_date = to_date - timedelta(days=5)
            data = self.kite.historical_data(token, from_date.strftime("%Y-%m-%d"), to_date.strftime("%Y-%m-%d"), CANDLE_INTERVAL)
            df = pd.DataFrame(data)
            df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
            return df
        except Exception as e:
            log.error(f"[CANDLE ERROR] {symbol}: {e}")
            return None

    def run(self):
        log.info("Bot running... Ctrl+C to stop")

        while True:
            try:
                now = datetime.now().strftime("%H:%M")
                pnl = self.order_mgr.update_pnl()

                # Daily loss check
                if pnl <= -MAX_DAILY_LOSS:
                    log.warning(f"[STOP] Max loss hit! P&L: Rs.{pnl:.2f}")
                    self.order_mgr.square_off_all("MIS")
                    self.order_mgr.square_off_all("NRML")
                    break

                # Max trades check
                if self.order_mgr.trade_count >= MAX_TRADES_PER_DAY:
                    log.info(f"[STOP] Max {MAX_TRADES_PER_DAY} trades done!")
                    break

                # Process each instrument
                for inst in INSTRUMENTS:
                    symbol = inst['symbol']
                    exchange = inst['exchange']
                    quantity = inst['lots'] * inst['lot_size']
                    product = inst['product']
                    trade_end = inst['trade_end']
                    squareoff_time = inst['squareoff']

                    # Squareoff time for this instrument
                    if now >= squareoff_time and symbol in self.active_positions:
                        log.info(f"[SQUAREOFF TIME] {symbol}")
                        self.order_mgr.square_off_all(product)
                        if symbol in self.active_positions:
                            del self.active_positions[symbol]
                        continue

                    # Skip if already in position
                    if symbol in self.active_positions:
                        continue

                    # Skip if past trade end time
                    if now >= trade_end:
                        continue

                    # Skip if before start time
                    if now < TRADE_START_TIME:
                        continue

                    df = self.get_candles(symbol, exchange)
                    if df is None or len(df) < 30:
                        continue

                    signal, ind = get_signal(df)

                    print(f"\n{'='*55}")
                    print(f"TIME:{datetime.now().strftime('%H:%M:%S')} | {symbol} [{exchange}] [{product}]")
                    print(f"Price:{ind.get('price')} | VWAP:{ind.get('vwap')} | RSI:{ind.get('rsi')}")
                    print(f"EMA9:{ind.get('ema9')} | EMA21:{ind.get('ema21')} | MACD:{ind.get('macd')}")
                    print(f"SIGNAL: >>> {signal} <<<")
                    print(f"P&L: Rs.{self.order_mgr.daily_pnl:.2f} | Trades:{self.order_mgr.trade_count}/{MAX_TRADES_PER_DAY}")
                    print(f"{'='*55}")

                    if signal in ["BUY", "SELL"]:
                        prev = df.iloc[-2]
                        sl = round(prev['low'] * 0.998, 2) if signal == "BUY" else round(prev['high'] * 1.002, 2)
                        order_id = self.order_mgr.place_order(symbol, exchange, signal, quantity, product)
                        if order_id:
                            self.order_mgr.set_stop_loss(symbol, exchange, signal, quantity, sl, product)
                            self.active_positions[symbol] = signal

                if now < TRADE_START_TIME:
                    log.info(f"[WAIT] Trading starts at {TRADE_START_TIME}...")
                    time.sleep(60)
                    continue

                log.info("[WAIT] Next check in 5 min...")
                time.sleep(300)

            except KeyboardInterrupt:
                log.info("[STOP] User stopped bot!")
                self.order_mgr.square_off_all("MIS")
                self.order_mgr.square_off_all("NRML")
                break
            except Exception as e:
                log.error(f"[ERROR] {e}")
                time.sleep(30)

# ================================================================
#  START
# ================================================================

if __name__ == "__main__":
    print("=" * 55)
    print("  KITE AUTO TRADING BOT v4")
    print("  NFO: Nifty F&O (MIS)")
    print("  MCX: Silver, CrudeOil, Gold, NaturalGas (NRML)")
    print("  Strategy: VWAP + EMA + RSI + MACD")
    print("  WARNING: Real money trading!")
    print("=" * 55)
    confirm = input("Start live trading? (yes/no): ")
    if confirm.lower() == "yes":
        bot = TradingBot()
        bot.run()
    else:
        print("Cancelled. Stay safe!")
