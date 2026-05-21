# config.py - Saari settings ek jagah
import os

# ================================================================
# KITE API
# ================================================================
KITE_API_KEY    = os.environ.get("KITE_API_KEY", "zhve1lfpjxtie9rv")
KITE_API_SECRET = os.environ.get("KITE_API_SECRET", "wr1cwi6ijdpa2phztvhbtm48z79a9jsu")

# ================================================================
# TELEGRAM
# ================================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8701616355:AAGvetI7MfI2f6vJh7LkeujpxHmmtB0OtXE")
CHAT_ID        = os.environ.get("CHAT_ID", "8757681357")

# ================================================================
# SERVER
# ================================================================
PORT          = int(os.environ.get("PORT", 8080))
RAILWAY_URL   = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "web-production-f4bb5.up.railway.app")
CALLBACK_URL  = f"https://{RAILWAY_URL}/callback"

# ================================================================
# TRADING SETTINGS
# ================================================================
MAX_DAILY_LOSS     = float(os.environ.get("MAX_DAILY_LOSS", "50000"))
MAX_TRADES_PER_DAY = int(os.environ.get("MAX_TRADES_PER_DAY", "5"))
MAX_LOTS           = int(os.environ.get("MAX_LOTS", "2"))
TRADE_START_TIME   = "09:30"
TRADE_END_TIME     = "15:00"
SQUAREOFF_TIME     = "15:15"
SIGNAL_TIMEOUT     = 120  # seconds to wait for YES/NO

# ================================================================
# INDICATOR SETTINGS
# ================================================================
EMA_FAST        = 9
EMA_SLOW        = 21
RSI_PERIOD      = 14
MACD_FAST       = 12
MACD_SLOW       = 26
MACD_SIGNAL     = 9
CANDLE_INTERVAL = "5minute"
MIN_CONFIDENCE  = 60  # Minimum confidence score for signal

# ================================================================
# INSTRUMENTS - Nifty 50 Stocks
# ================================================================
NIFTY50_STOCKS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
    "LT", "AXISBANK", "MARUTI", "TITAN", "SUNPHARMA",
    "BAJFINANCE", "WIPRO", "TATAMOTORS", "HCLTECH", "TECHM",
    "ADANIENT", "ONGC", "NTPC", "POWERGRID", "COALINDIA",
    "JSWSTEEL", "TATASTEEL", "ULTRACEMCO", "NESTLEIND", "ASIANPAINT",
    "BAJAJFINSV", "HDFCLIFE", "SBILIFE", "DIVISLAB", "DRREDDY",
    "CIPLA", "EICHERMOT", "HEROMOTOCO", "APOLLOHOSP", "TRENT",
    "INDUSINDBK", "SHRIRAMFIN", "BPCL", "HINDALCO", "VEDL",
    "GRASIM", "BRITANNIA", "LTIM", "TECHM", "UPL"
]

# BankNifty Stocks
BANKNIFTY_STOCKS = [
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

# Stock position size (Rs. per trade)
STOCK_POSITION_SIZE = 10000  # Rs. 10,000 per stock trade
