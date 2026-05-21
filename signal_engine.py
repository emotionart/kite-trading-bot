# signal_engine.py - Technical indicators & signal generation
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from broker import broker
from config import *
import logging

log = logging.getLogger(__name__)

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

def get_signal(symbol, exchange, lots=1, lot_size=1, product="MIS"):
    try:
        to_date = datetime.now()
        from_date = to_date - timedelta(days=5)

        data = broker.get_historical_data(exchange, symbol, CANDLE_INTERVAL, from_date, to_date)
        if not data or len(data) < 30:
            return None

        df = pd.DataFrame(data)
        df.columns = ["date", "open", "high", "low", "close", "volume"]

        closes  = df["close"].values
        volumes = df["volume"].values

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

        avg_vol   = np.mean(volumes[-20:])
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

        if buy_score >= MIN_CONFIDENCE:
            signal    = "BUY"
            confidence = buy_score
            sl = round(df.iloc[-2]["low"] * 0.998, 2)
            risk = curr_price - sl
            t1 = round(curr_price + risk * 1.5, 2)
            t2 = round(curr_price + risk * 2.5, 2)
        elif sell_score >= MIN_CONFIDENCE:
            signal    = "SELL"
            confidence = sell_score
            sl = round(df.iloc[-2]["high"] * 1.002, 2)
            risk = sl - curr_price
            t1 = round(curr_price - risk * 1.5, 2)
            t2 = round(curr_price - risk * 2.5, 2)
        else:
            return None

        reasons = []
        if curr_price > curr_vwap: reasons.append(f"Price {'above' if signal=='BUY' else 'below'} VWAP ({round(curr_vwap,2)})")
        if ema_bullish or ema_bearish: reasons.append(f"EMA9 {'bullish' if signal=='BUY' else 'bearish'} crossover")
        if 35 <= curr_rsi <= 65: reasons.append(f"RSI: {round(curr_rsi,1)}")
        if macd_bullish or macd_bearish: reasons.append(f"MACD {'bullish' if signal=='BUY' else 'bearish'}")
        if vol_spike: reasons.append(f"Volume spike: {round(volumes[-1]/avg_vol,1)}x")

        rr = round(abs(risk * 1.5 / risk), 1) if risk > 0 else 1.5

        return {
            "symbol":     symbol,
            "exchange":   exchange,
            "signal":     signal,
            "entry":      round(curr_price, 2),
            "sl":         sl,
            "t1":         t1,
            "t2":         t2,
            "confidence": confidence,
            "rr":         rr,
            "reason":     "\n".join([f"- {r}" for r in reasons]),
            "lots":       lots,
            "lot_size":   lot_size,
            "product":    product,
            "tech": {
                "price":     round(curr_price, 2),
                "vwap":      round(curr_vwap, 2),
                "ema9":      round(ema_fast[-1], 2),
                "ema21":     round(ema_slow[-1], 2),
                "rsi":       round(curr_rsi, 2),
                "macd":      round(macd_line[-1], 4),
                "vol_spike": vol_spike,
            }
        }

    except Exception as e:
        log.error(f"[SIGNAL] Error {symbol}: {e}")
        return None

def scan_all():
    """Scan all instruments and return top signals"""
    signals = []

    log.info("[SCAN] Scanning Nifty 50 stocks...")
    for stock in NIFTY50_STOCKS:
        result = get_signal(stock, "NSE", 1, 1, "MIS")
        if result:
            signals.append(result)
            log.info(f"[SIGNAL] {stock} - {result['signal']} - {result['confidence']}%")
        import time; time.sleep(0.3)

    log.info("[SCAN] Scanning BankNifty stocks...")
    for stock in BANKNIFTY_STOCKS:
        if stock not in NIFTY50_STOCKS:
            result = get_signal(stock, "NSE", 1, 1, "MIS")
            if result:
                signals.append(result)
            import time; time.sleep(0.3)

    log.info("[SCAN] Scanning MCX...")
    for inst in MCX_INSTRUMENTS:
        result = get_signal(inst["symbol"], inst["exchange"], inst["lots"], inst["lot_size"], inst["product"])
        if result:
            signals.append(result)
        import time; time.sleep(0.3)

    signals.sort(key=lambda x: x["confidence"], reverse=True)
    return signals[:3]
