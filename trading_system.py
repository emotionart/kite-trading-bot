# -*- coding: utf-8 -*-
"""
KITE AUTO TRADING SYSTEM v4
- Auto daily login (no manual token needed!)
- Multi-strategy: Supertrend + EMA + VWAP + RSI + MACD + Candlestick
- Multi-timeframe: 5min + 15min confirmation  
- Auto position sizing: Rs.20,000 per trade, Rs.1,000 risk
- Trailing SL
- Nifty50 + BankNifty + F&O + MCX
- Telegram signals + YES/NO approval
- Max daily loss: Rs.3,000
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os, time, logging, threading, requests, pyotp, hashlib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from kiteconnect import KiteConnect
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

# ================================================================
#  CONFIG — Railway Variables se
# ================================================================
API_KEY          = os.environ.get("API_KEY",          "zhve1lfpjxtie9rv")
API_SECRET       = os.environ.get("API_SECRET",       "wr1cwi6ijdpa2phztvhbtm48z79a9jsu")
ACCESS_TOKEN     = os.environ.get("ACCESS_TOKEN",     "")
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN",   "8701616355:AAGvetI7MfI2f6vJh7LkeujpxHmmtB0OtXE")
CHAT_ID          = os.environ.get("CHAT_ID",          "8757681357")
ZERODHA_USER_ID  = os.environ.get("ZERODHA_USER_ID",  "BY4317")
ZERODHA_PASSWORD = os.environ.get("ZERODHA_PASSWORD", "")
ZERODHA_TOTP     = os.environ.get("ZERODHA_TOTP",     "ZOO235QJ5DWSPGGXBF6NPV65M33CTMKF")
CALLBACK_URL     = "https://worker-production-5b28.up.railway.app/callback"

# Risk Management
CAPITAL          = 100000
PER_TRADE_CAPITAL = 20000
MAX_RISK_PER_TRADE = 1000
MAX_DAILY_LOSS   = 3000
MAX_TRADES_PER_DAY = 5
TRADE_START_TIME = "09:30"
TRADE_END_TIME   = "15:00"
SQUAREOFF_TIME   = "15:15"

# Instruments
NIFTY50_STOCKS = [
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","ITC",
    "SBIN","BHARTIARTL","KOTAKBANK","LT","AXISBANK","ASIANPAINT","MARUTI",
    "TITAN","SUNPHARMA","ULTRACEMCO","BAJFINANCE","WIPRO","NESTLEIND",
    "ADANIENT","ONGC","NTPC","POWERGRID","COALINDIA","TATAMOTORS",
    "TATASTEEL","JSWSTEEL","HCLTECH","TECHM","BAJAJFINSV","BRITANNIA",
    "CIPLA","DIVISLAB","DRREDDY","EICHERMOT","GRASIM","HEROMOTOCO",
    "HINDALCO","INDUSINDBK","M&M","SBILIFE","TATACONSUM","UPL",
    "BPCL","GAIL","IOC","APOLLOHOSP","ADANIPORTS","TRENT"
]

BANKNIFTY_STOCKS = [
    "HDFCBANK","ICICIBANK","KOTAKBANK","AXISBANK","SBIN",
    "INDUSINDBK","BANDHANBNK","FEDERALBNK","IDFCFIRSTB","AUBANK",
    "PNB","BANKBARODA","CANBK","UNIONBANK"
]

# Global state
kite         = KiteConnect(api_key=API_KEY)
access_token = [ACCESS_TOKEN]
last_login   = [None]

# ================================================================
#  LOGGING
# ================================================================
class SafeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            self.stream.write(self.format(record) + self.terminator)
            self.flush()
        except: pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(f'bot_{datetime.now().strftime("%Y%m%d")}.log', encoding='utf-8'),
        SafeStreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)

# ================================================================
#  AUTO LOGIN — Har roz khud login karta hai!
# ================================================================
def auto_login():
    """Automatic Zerodha login using User ID + Password + TOTP"""
    global access_token
    try:
        log.info("[AUTH] Auto login starting...")

        if not ZERODHA_PASSWORD:
            log.error("[AUTH] ZERODHA_PASSWORD not set!")
            return False

        # Step 1: Generate TOTP
        totp     = pyotp.TOTP(ZERODHA_TOTP)
        otp_code = totp.now()
        log.info(f"[AUTH] TOTP generated: {otp_code}")

        # Step 2: Login via Kite API
        session  = requests.Session()

        # Get login page
        login_url = "https://kite.zerodha.com/api/login"
        resp = session.post(login_url, data={
            "user_id":  ZERODHA_USER_ID,
            "password": ZERODHA_PASSWORD
        }, timeout=15)

        data = resp.json()
        if data.get("status") != "success":
            log.error(f"[AUTH] Login failed: {data.get('message')}")
            return False

        request_id = data["data"]["request_id"]
        log.info(f"[AUTH] Login success, request_id: {request_id}")

        # Step 3: TOTP verification
        twofa_url = "https://kite.zerodha.com/api/twofa"
        resp2 = session.post(twofa_url, data={
            "user_id":    ZERODHA_USER_ID,
            "request_id": request_id,
            "twofa_value": otp_code,
            "twofa_type": "totp"
        }, timeout=15)

        data2 = resp2.json()
        if data2.get("status") != "success":
            log.error(f"[AUTH] 2FA failed: {data2.get('message')}")
            return False

        log.info("[AUTH] 2FA success!")

        # Step 4: Get request token from Kite Connect
        login_url2 = kite.login_url()
        resp3 = session.get(login_url2, timeout=15, allow_redirects=False)

        # Follow redirect to get request_token
        redirect_url = resp3.headers.get("Location", "")
        if not redirect_url:
            resp3 = session.get(login_url2, timeout=15)
            redirect_url = resp3.url

        params = urllib.parse.parse_qs(urllib.parse.urlparse(redirect_url).query)
        req_token = params.get("request_token", [None])[0]

        if not req_token:
            log.error(f"[AUTH] No request_token in redirect: {redirect_url}")
            return False

        log.info(f"[AUTH] Got request_token: {req_token[:10]}...")

        # Step 5: Generate access token
        session_data    = kite.generate_session(req_token, api_secret=API_SECRET)
        new_token       = session_data["access_token"]
        access_token[0] = new_token
        kite.set_access_token(new_token)
        last_login[0]   = datetime.now()

        log.info(f"[AUTH] ✅ Auto login SUCCESS! Token: {new_token[:10]}...")
        send_telegram(f"✅ <b>Auto Login Successful!</b>\nToken refreshed automatically!\n\nBot trading shuru karega {TRADE_START_TIME} pe!")
        return True

    except Exception as e:
        log.error(f"[AUTH] Auto login error: {e}")
        send_telegram(f"❌ <b>Auto Login Failed!</b>\nManual login karo:\n{CALLBACK_URL}\n\nError: {str(e)}")
        return False

def schedule_daily_login():
    """Har roz 8:45 AM pe auto login"""
    while True:
        try:
            now = datetime.now()
            # Login at 8:45 AM every day
            target = now.replace(hour=8, minute=45, second=0, microsecond=0)
            if now > target:
                target += timedelta(days=1)

            wait_seconds = (target - now).total_seconds()
            log.info(f"[AUTH] Next auto login in {wait_seconds/3600:.1f} hours at 8:45 AM")
            time.sleep(wait_seconds)

            # Try auto login
            success = auto_login()
            if not success:
                # Retry after 5 min
                time.sleep(300)
                auto_login()

        except Exception as e:
            log.error(f"[SCHEDULER] {e}")
            time.sleep(60)

# ================================================================
#  TELEGRAM
# ================================================================
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        log.error(f"[TG] {e}")

def tg_get_updates(offset=None):
    try:
        url    = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        params = {"timeout": 5, "allowed_updates": ["message"]}
        if offset: params["offset"] = offset
        r = requests.get(url, params=params, timeout=10)
        return r.json().get("result", [])
    except: return []

# ================================================================
#  CALLBACK SERVER — Manual login fallback
# ================================================================
import json as _json

# Global executor reference for API
_executor_ref = [None]

class CallbackHandler(BaseHTTPRequestHandler):

    def send_cors(self, code=200, content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self.send_cors()

    def do_GET(self):
        global access_token
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        path   = parsed.path

        # ── /api/status ──────────────────────────────
        if path == '/api/status':
            ex  = _executor_ref[0]
            pnl = ex.daily_pnl if ex else 0
            tc  = ex.trade_count if ex else 0
            self.send_cors()
            self.wfile.write(_json.dumps({
                "status":      "online",
                "token":       bool(access_token[0]),
                "last_login":  last_login[0].strftime('%H:%M %d-%b') if last_login[0] else None,
                "pnl":         pnl,
                "trades":      tc,
                "max_trades":  MAX_TRADES_PER_DAY,
                "max_loss":    MAX_DAILY_LOSS,
                "capital":     CAPITAL,
                "login_url":   kite.login_url(),
                "time":        datetime.now().strftime('%H:%M:%S'),
            }).encode())
            return

        # ── /api/analyze ─────────────────────────────
        if path == '/api/analyze':
            sym  = params.get('symbol', [''])[0].upper()
            exch = params.get('exchange', ['NSE'])[0].upper()

            if not sym:
                self.send_cors()
                self.wfile.write(_json.dumps({"error": "Symbol required"}).encode())
                return

            if not access_token[0]:
                self.send_cors()
                self.wfile.write(_json.dumps({"error": "Not logged in"}).encode())
                return

            try:
                # Auto expiry for futures
                aliases = {
                    "NIFTY":     ("NFO", "NIFTY"),
                    "BANKNIFTY": ("NFO", "BANKNIFTY"),
                    "FINNIFTY":  ("NFO", "FINNIFTY"),
                    "GOLD":      ("MCX", "GOLD"),
                    "SILVER":    ("MCX", "SILVERM"),
                    "CRUDE":     ("MCX", "CRUDEOIL"),
                    "NATURALGAS":("MCX", "NATURALGAS"),
                }
                if sym in aliases and "FUT" not in sym:
                    exch, base = aliases[sym]
                    months = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]
                    yr     = str(datetime.now().year)[2:]
                    sym    = f"{base}{yr}{months[datetime.now().month-1]}FUT"

                df5, ltp = get_candles(sym, exch, "5minute", 10)
                if df5 is None:
                    self.send_cors()
                    self.wfile.write(_json.dumps({"error": f"{sym} data not found"}).encode())
                    return

                closes  = df5['close'].values
                highs   = df5['high'].values
                lows    = df5['low'].values
                volumes = df5['volume'].values

                ema9v    = ema(closes, 9)
                ema21v   = ema(closes, 21)
                rsi14    = rsi(closes, 14)
                ml, sl   = macd(closes)
                vwap_v   = vwap(df5).values
                st, std  = supertrend(df5, 10, 3)
                patterns = candlestick_patterns(df5)

                cp   = closes[-1]
                cv   = vwap_v[-1]
                cr   = rsi14[-1]
                cm   = ml[-1]
                e9   = ema9v[-1]; e21 = ema21v[-1]
                av   = cp > cv
                std_val = int(std[-1]) if not np.isnan(std[-1]) else 0

                avg_vol   = np.mean(volumes[-20:])
                vol_spike = bool(volumes[-1] > avg_vol * 1.5)
                vol_ratio = round(float(volumes[-1] / avg_vol), 1)

                eb  = bool((ema9v[-2] <= ema21v[-2]) and (ema9v[-1] > ema21v[-1]))
                ebs = bool((ema9v[-2] >= ema21v[-2]) and (ema9v[-1] < ema21v[-1]))
                mb  = bool((ml[-2] <= sl[-2]) and (ml[-1] > sl[-1]))
                mbs = bool((ml[-2] >= sl[-2]) and (ml[-1] < sl[-1]))

                buy_sc  = sum([std_val==1, eb or e9>e21, av, 40<=cr<=65, mb or cm>sl[-1], vol_spike]) * 16
                sell_sc = sum([std_val==-1, ebs or e9<e21, not av, 35<=cr<=60, mbs or cm<sl[-1], vol_spike]) * 16

                if buy_sc >= 60:    sig = "BUY";  conf = buy_sc
                elif sell_sc >= 60: sig = "SELL"; conf = sell_sc
                else:               sig = "WAIT"; conf = max(buy_sc, sell_sc)

                sl_p = round(float(min(lows[-5:])) * 0.998, 2) if sig != "SELL" else round(float(max(highs[-5:])) * 1.002, 2)
                risk = max(abs(float(cp) - sl_p), 1)
                t1   = round(float(cp) + risk*1.5, 2) if sig != "SELL" else round(float(cp) - risk*1.5, 2)
                t2   = round(float(cp) + risk*2.5, 2) if sig != "SELL" else round(float(cp) - risk*2.5, 2)

                today    = datetime.now().date()
                today_df = df5[pd.to_datetime(df5['date']).dt.date == today]
                d_open   = float(today_df.iloc[0]['open']) if len(today_df) > 0 else float(cp)
                d_high   = float(today_df['high'].max())   if len(today_df) > 0 else float(cp)
                d_low    = float(today_df['low'].min())    if len(today_df) > 0 else float(cp)
                chg      = round(((float(cp) - d_open) / d_open) * 100, 2) if d_open else 0

                self.send_cors()
                self.wfile.write(_json.dumps({
                    "symbol":     sym,
                    "exchange":   exch,
                    "ltp":        round(float(cp), 2),
                    "change":     chg,
                    "open":       d_open,
                    "high":       d_high,
                    "low":        d_low,
                    "supertrend": "Bullish" if std_val==1 else "Bearish" if std_val==-1 else "Neutral",
                    "ema9":       round(float(e9), 2),
                    "ema21":      round(float(e21), 2),
                    "ema_status": "Bullish Cross" if eb else "Bearish Cross" if ebs else "Above" if e9>e21 else "Below",
                    "vwap":       round(float(cv), 2),
                    "vwap_status": "Above" if av else "Below",
                    "rsi":        round(float(cr), 1),
                    "macd":       round(float(cm), 3),
                    "macd_status": "Bullish" if mb or cm>sl[-1] else "Bearish",
                    "volume":     f"Spike {vol_ratio}x" if vol_spike else f"Normal {vol_ratio}x",
                    "patterns":   [p[0] for p in patterns],
                    "signal":     sig,
                    "confidence": min(int(conf), 100),
                    "sl":         sl_p,
                    "t1":         t1,
                    "t2":         t2,
                }).encode())

            except Exception as e:
                self.send_cors()
                self.wfile.write(_json.dumps({"error": str(e)}).encode())
            return

        # ── /api/indices ──────────────────────────────
        if path == '/api/indices':
            try:
                indices = ["NSE:NIFTY 50", "NSE:NIFTY BANK", "NSE:INDIA VIX"]
                result  = {}
                for idx in indices:
                    try:
                        data = kite.ltp(idx)
                        key  = list(data.keys())[0]
                        result[idx] = {
                            "ltp":    data[key].get("last_price", 0),
                            "change": data[key].get("net_change", 0),
                        }
                    except: pass
                self.send_cors()
                self.wfile.write(_json.dumps(result).encode())
            except Exception as e:
                self.send_cors()
                self.wfile.write(_json.dumps({"error": str(e)}).encode())
            return

        # ── /api/login_url ────────────────────────────
        if path == '/api/login_url':
            self.send_cors()
            self.wfile.write(_json.dumps({
                "url": kite.login_url()
            }).encode())
            return

        # ── /callback — Zerodha redirect ─────────────
        if path == '/callback' or path == '/auth':
            req_token = params.get('request_token', [None])[0]
            if req_token:
                try:
                    session_data    = kite.generate_session(req_token, api_secret=API_SECRET)
                    new_token       = session_data["access_token"]
                    access_token[0] = new_token
                    kite.set_access_token(new_token)
                    last_login[0]   = datetime.now()

                    log.info(f"[AUTH] Login success! Token: {new_token[:10]}...")
                    send_telegram("✅ <b>Login Successful!</b>\nToken set! Bot active hai!")

                    self.send_cors(200, "text/html")
                    self.wfile.write("""<!DOCTYPE html>
<html><head><meta charset='UTF-8'>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0f;color:#e0e0f0;font-family:'Segoe UI',sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:#12121e;border:1px solid #1e1e32;border-radius:20px;padding:48px;text-align:center;max-width:420px;width:90%}
.icon{font-size:64px;margin-bottom:20px}
h1{color:#00ff88;font-size:28px;margin-bottom:12px}
p{color:#8888aa;margin-bottom:24px;line-height:1.6}
.btn{display:inline-block;background:#00ff88;color:#000;padding:14px 32px;border-radius:10px;text-decoration:none;font-weight:700;font-size:15px}
.token{background:#141420;border:1px solid #1e1e32;border-radius:10px;padding:12px;font-family:monospace;font-size:12px;color:#4488ff;margin:16px 0;word-break:break-all}
</style></head>
<body><div class='card'>
<div class='icon'>✅</div>
<h1>Login Successful!</h1>
<p>Token set ho gaya! Bot ab trade kar sakta hai.</p>
<div class='token'>Token Active ✓</div>
<a class='btn' href='javascript:window.close()'>Dashboard pe Wapas Jao</a>
</div>
<script>
// Notify parent window if opened as popup
if(window.opener){
  window.opener.postMessage({type:'LOGIN_SUCCESS'},'*');
  setTimeout(()=>window.close(),2000);
}
</script>
</body></html>""".encode())

                except Exception as e:
                    self.send_cors(200, "text/html")
                    self.wfile.write(f"<h1 style='color:red;font-family:monospace;padding:40px'>Error: {e}</h1>".encode())
            else:
                # Show login button
                login_url = kite.login_url()
                self.send_cors(200, "text/html")
                self.wfile.write(f"""<!DOCTYPE html>
<html><head><meta charset='UTF-8'>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0a0a0f;color:#e0e0f0;font-family:'Segoe UI',sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center}}
.card{{background:#12121e;border:1px solid #1e1e32;border-radius:20px;padding:48px;text-align:center;max-width:420px;width:90%}}
.icon{{font-size:64px;margin-bottom:20px}}
h1{{color:#00ff88;font-size:28px;margin-bottom:12px}}
p{{color:#8888aa;margin-bottom:24px;line-height:1.6}}
.btn{{display:inline-block;background:#00ff88;color:#000;padding:16px 40px;border-radius:12px;text-decoration:none;font-weight:700;font-size:16px;transition:all 0.2s}}
.note{{font-size:12px;color:#4444aa;margin-top:16px}}
</style></head>
<body><div class='card'>
<div class='icon'>🔐</div>
<h1>Kite Authentication</h1>
<p>Zerodha se login karo — token automatically set ho jayega!</p>
<a class='btn' href='{login_url}'>👉 Zerodha Login Karo</a>
<div class='note'>Auto login bhi chal raha hai (8:45 AM daily)</div>
</div></body></html>""".encode())
            return

        # ── /dashboard ───────────────────────────────
        if path in ['/dashboard.html', '/dashboard', '/']:
            try:
                with open('dashboard.html', 'rb') as f:
                    html = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(html)
            except:
                self.send_cors(200, "text/plain")
                self.wfile.write(b"Dashboard not found!")
            return

        # ── Default ───────────────────────────────────
        self.send_cors(200, "text/plain")
        self.wfile.write(b"StockWala Bot v4 Running!")

    def log_message(self, *args): pass

def start_callback_server():
    port   = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), CallbackHandler)
    log.info(f"[SERVER] Running on port {port}")
    server.serve_forever()

# ================================================================
#  INDICATORS
# ================================================================
def ema(prices, period):
    return pd.Series(prices).ewm(span=period, adjust=False).mean().values

def rsi(prices, period=14):
    s     = pd.Series(prices)
    delta = s.diff()
    gain  = delta.where(delta > 0, 0).rolling(period).mean()
    loss  = -delta.where(delta < 0, 0).rolling(period).mean()
    return (100 - 100 / (1 + gain/loss)).values

def macd(prices, fast=12, slow=26, signal=9):
    s    = pd.Series(prices)
    ml   = s.ewm(span=fast, adjust=False).mean() - s.ewm(span=slow, adjust=False).mean()
    sl   = ml.ewm(span=signal, adjust=False).mean()
    return ml.values, sl.values

def vwap(df):
    typical = (df['high'] + df['low'] + df['close']) / 3
    return (typical * df['volume']).cumsum() / df['volume'].cumsum()

def supertrend(df, period=10, multiplier=3):
    """Supertrend indicator"""
    hl2  = (df['high'] + df['low']) / 2
    atr  = df['high'].combine(df['close'].shift(), max) - df['low'].combine(df['close'].shift(), min)
    atr  = atr.rolling(period).mean()
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr

    supertrend = pd.Series(index=df.index, dtype=float)
    direction  = pd.Series(index=df.index, dtype=int)

    for i in range(1, len(df)):
        if df['close'].iloc[i] > upper.iloc[i-1]:
            direction.iloc[i] = 1   # Bullish
        elif df['close'].iloc[i] < lower.iloc[i-1]:
            direction.iloc[i] = -1  # Bearish
        else:
            direction.iloc[i] = direction.iloc[i-1]

        supertrend.iloc[i] = lower.iloc[i] if direction.iloc[i] == 1 else upper.iloc[i]

    return supertrend.values, direction.values

def candlestick_patterns(df):
    """Detect candlestick patterns"""
    patterns = []
    if len(df) < 3: return patterns

    o1, h1, l1, c1 = df.iloc[-3]['open'], df.iloc[-3]['high'], df.iloc[-3]['low'], df.iloc[-3]['close']
    o2, h2, l2, c2 = df.iloc[-2]['open'], df.iloc[-2]['high'], df.iloc[-2]['low'], df.iloc[-2]['close']
    o,  h,  l,  c  = df.iloc[-1]['open'], df.iloc[-1]['high'], df.iloc[-1]['low'], df.iloc[-1]['close']

    body      = abs(c - o)
    prev_body = abs(c2 - o2)
    total_range = h - l

    # Bullish Engulfing
    if c2 < o2 and c > o and c > o2 and o < c2:
        patterns.append(("BULLISH_ENGULFING", "bullish"))

    # Bearish Engulfing
    if c2 > o2 and c < o and c < o2 and o > c2:
        patterns.append(("BEARISH_ENGULFING", "bearish"))

    # Hammer (bullish)
    if body > 0 and (l - min(o,c)) > 2 * body and (h - max(o,c)) < body * 0.5:
        patterns.append(("HAMMER", "bullish"))

    # Shooting Star (bearish)
    if body > 0 and (h - max(o,c)) > 2 * body and (min(o,c) - l) < body * 0.5:
        patterns.append(("SHOOTING_STAR", "bearish"))

    # Doji
    if body < total_range * 0.1 and total_range > 0:
        patterns.append(("DOJI", "neutral"))

    # Morning Star (bullish)
    if c1 < o1 and abs(c2-o2) < abs(c1-o1)*0.3 and c > o and c > (o1+c1)/2:
        patterns.append(("MORNING_STAR", "bullish"))

    # Evening Star (bearish)
    if c1 > o1 and abs(c2-o2) < abs(c1-o1)*0.3 and c < o and c < (o1+c1)/2:
        patterns.append(("EVENING_STAR", "bearish"))

    return patterns

# ================================================================
#  GET CANDLES
# ================================================================
def get_candles(symbol, exchange, interval="5minute", days=10):
    try:
        inst     = kite.ltp(f"{exchange}:{symbol}")
        token    = list(inst.values())[0].get('instrument_token')
        to_date  = datetime.now()
        fr_date  = to_date - timedelta(days=days)
        data     = kite.historical_data(token, fr_date.strftime("%Y-%m-%d"), to_date.strftime("%Y-%m-%d"), interval)
        if not data or len(data) < 30: return None, None
        df       = pd.DataFrame(data)
        df.columns = ['date','open','high','low','close','volume']
        ltp      = list(inst.values())[0].get('last_price', df.iloc[-1]['close'])
        return df, ltp
    except Exception as e:
        log.debug(f"[CANDLE] {symbol}: {e}")
        return None, None

# ================================================================
#  MULTI-STRATEGY SIGNAL ENGINE
# ================================================================
def get_signal(symbol, exchange, lots=1, lot_size=1, product="MIS"):
    """
    Multi-strategy signal:
    1. Supertrend (primary trend)
    2. EMA 9/21 crossover
    3. VWAP position
    4. RSI
    5. MACD
    6. Volume spike
    7. Candlestick patterns
    8. 15min confirmation
    """
    try:
        # Get 5min candles
        df5, ltp = get_candles(symbol, exchange, "5minute", 10)
        if df5 is None: return None

        # Get 15min candles for confirmation
        df15, _ = get_candles(symbol, exchange, "15minute", 15)

        closes  = df5['close'].values
        highs   = df5['high'].values
        lows    = df5['low'].values
        volumes = df5['volume'].values

        # --- Indicators ---
        ema9   = ema(closes, 9)
        ema21  = ema(closes, 21)
        ema50  = ema(closes, 50)
        rsi14  = rsi(closes, 14)
        ml, sl = macd(closes)
        vwap_v = vwap(df5).values
        st, st_dir = supertrend(df5, 10, 3)
        patterns   = candlestick_patterns(df5)

        # Current values
        cp  = closes[-1]
        cv  = vwap_v[-1]
        cr  = rsi14[-1]
        cm  = ml[-1]
        cs  = sl[-1]
        e9  = ema9[-1];  e21 = ema21[-1]; e50 = ema50[-1]
        std = st_dir[-1] if not np.isnan(st_dir[-1]) else 0

        # Volume
        avg_vol   = np.mean(volumes[-20:])
        vol_spike = volumes[-1] > avg_vol * 1.5
        vol_ratio = round(volumes[-1] / avg_vol, 1)

        # 15min trend confirmation
        trend_15m = 0
        if df15 is not None and len(df15) >= 20:
            c15    = df15['close'].values
            e9_15  = ema(c15, 9)
            e21_15 = ema(c15, 21)
            _, std15 = supertrend(df15, 10, 3)
            trend_15m = 1 if (e9_15[-1] > e21_15[-1] and std15[-1] == 1) else (-1 if (e9_15[-1] < e21_15[-1] and std15[-1] == -1) else 0)

        # Candlestick bias
        candle_bias = 0
        candle_names = []
        for name, bias in patterns:
            if bias == "bullish": candle_bias += 1; candle_names.append(name)
            elif bias == "bearish": candle_bias -= 1; candle_names.append(name)

        # --- BUY conditions ---
        buy_conditions = {
            "supertrend":  std == 1,
            "ema_cross":   ema9[-2] <= ema21[-2] and ema9[-1] > ema21[-1],
            "ema_trend":   e9 > e21 > e50,
            "vwap_above":  cp > cv,
            "rsi_ok":      40 <= cr <= 65,
            "macd_bull":   ml[-2] <= sl[-2] and ml[-1] > sl[-1],
            "volume":      vol_spike,
            "15min_bull":  trend_15m >= 0,
            "candle_bull": candle_bias > 0,
        }

        # --- SELL conditions ---
        sell_conditions = {
            "supertrend":   std == -1,
            "ema_cross":    ema9[-2] >= ema21[-2] and ema9[-1] < ema21[-1],
            "ema_trend":    e9 < e21 < e50,
            "vwap_below":   cp < cv,
            "rsi_ok":       35 <= cr <= 60,
            "macd_bear":    ml[-2] >= sl[-2] and ml[-1] < sl[-1],
            "volume":       vol_spike,
            "15min_bear":   trend_15m <= 0,
            "candle_bear":  candle_bias < 0,
        }

        # Weights
        weights = {
            "supertrend": 30, "ema_cross": 20, "ema_trend": 10,
            "vwap_above": 10, "vwap_below": 10,
            "rsi_ok": 10, "macd_bull": 10, "macd_bear": 10,
            "volume": 5, "15min_bull": 15, "15min_bear": 15,
            "candle_bull": 10, "candle_bear": 10,
        }

        buy_score  = sum(weights.get(k, 5) for k, v in buy_conditions.items() if v)
        sell_score = sum(weights.get(k, 5) for k, v in sell_conditions.items() if v)

        # Min score threshold
        MIN_SCORE = 60

        if buy_score >= MIN_SCORE and buy_score > sell_score:
            signal = "BUY"
            score  = buy_score
        elif sell_score >= MIN_SCORE and sell_score > buy_score:
            signal = "SELL"
            score  = sell_score
        else:
            return None

        # --- SL + Target calculation ---
        recent_lows  = lows[-5:]
        recent_highs = highs[-5:]
        atr_val      = np.mean(highs[-14:] - lows[-14:])

        if signal == "BUY":
            sl_price = round(min(recent_lows) - atr_val * 0.3, 2)
            risk     = max(cp - sl_price, 1)
            t1       = round(cp + risk * 1.5, 2)
            t2       = round(cp + risk * 2.5, 2)
            t3       = round(cp + risk * 4.0, 2)
        else:
            sl_price = round(max(recent_highs) + atr_val * 0.3, 2)
            risk     = max(sl_price - cp, 1)
            t1       = round(cp - risk * 1.5, 2)
            t2       = round(cp - risk * 2.5, 2)
            t3       = round(cp - risk * 4.0, 2)

        # --- Auto position sizing ---
        # Risk Rs.1000 per trade
        qty_by_risk = max(int(MAX_RISK_PER_TRADE / risk), 1)
        qty_by_cap  = max(int(PER_TRADE_CAPITAL / cp), 1)
        quantity    = min(qty_by_risk, qty_by_cap) * lot_size

        # --- Reasons ---
        reasons = []
        if buy_conditions.get("supertrend") or sell_conditions.get("supertrend"):
            reasons.append(f"✅ Supertrend {'Bullish' if signal=='BUY' else 'Bearish'}")
        if buy_conditions.get("ema_cross") or sell_conditions.get("ema_cross"):
            reasons.append(f"✅ EMA 9/21 {'Bullish' if signal=='BUY' else 'Bearish'} Crossover")
        if buy_conditions.get("vwap_above") or sell_conditions.get("vwap_below"):
            reasons.append(f"✅ Price {'Above' if signal=='BUY' else 'Below'} VWAP (₹{round(cv,2)})")
        if buy_conditions.get("macd_bull") or sell_conditions.get("macd_bear"):
            reasons.append(f"✅ MACD {'Bullish' if signal=='BUY' else 'Bearish'} Crossover")
        if buy_conditions.get("rsi_ok") or sell_conditions.get("rsi_ok"):
            reasons.append(f"✅ RSI: {round(cr,1)} (Normal zone)")
        if vol_spike:
            reasons.append(f"✅ Volume Spike: {vol_ratio}x average")
        if trend_15m != 0:
            reasons.append(f"✅ 15min Trend: {'Bullish' if trend_15m > 0 else 'Bearish'}")
        if candle_names:
            reasons.append(f"✅ Pattern: {', '.join(candle_names)}")

        rr = round(risk * 1.5 / risk, 1)

        return {
            "symbol":    symbol,    "exchange":  exchange,
            "signal":    signal,    "entry":     round(cp, 2),
            "sl":        sl_price,  "t1":        t1,
            "t2":        t2,        "t3":        t3,
            "confidence": min(score, 100),
            "rr":        rr,        "risk":      round(risk, 2),
            "quantity":  quantity,  "lots":      lots,
            "lot_size":  lot_size,  "product":   product,
            "reason":    "\n".join(reasons),
            "rsi":       round(cr, 1),
            "vwap":      round(cv, 2),
            "ema9":      round(e9, 2),
            "ema21":     round(e21, 2),
            "patterns":  candle_names,
        }

    except Exception as e:
        log.debug(f"[SIGNAL] {symbol}: {e}")
        return None

# ================================================================
#  /analyze COMMAND
# ================================================================
def cmd_analyze(symbol_input):
    parts    = symbol_input.strip().upper().split()
    symbol   = parts[0]
    exchange = parts[1] if len(parts) >= 2 else (
        "NFO" if any(x in symbol for x in ["NIFTY","BANKNIFTY","FINNIFTY"]) and "FUT" in symbol else
        "MCX" if any(x in symbol for x in ["GOLD","SILVER","CRUDE","NATURALGAS"]) and "FUT" in symbol else
        "NSE"
    )

    # Auto expiry for index futures
    aliases = {
        "NIFTY": ("NFO","NIFTY"), "BANKNIFTY": ("NFO","BANKNIFTY"),
        "FINNIFTY": ("NFO","FINNIFTY"), "GOLD": ("MCX","GOLD"),
        "SILVER": ("MCX","SILVERM"), "CRUDE": ("MCX","CRUDEOIL"),
    }
    if symbol in aliases and "FUT" not in symbol:
        exch, base = aliases[symbol]
        exchange   = exch
        months     = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]
        yr         = str(datetime.now().year)[2:]
        symbol     = f"{base}{yr}{months[datetime.now().month-1]}FUT"

    send_telegram(f"🔍 <b>Analyzing {symbol} [{exchange}]...</b>")

    try:
        df5, ltp = get_candles(symbol, exchange, "5minute", 10)
        if df5 is None:
            send_telegram(f"❌ {symbol} data nahi mila. Market open hai?")
            return

        closes  = df5['close'].values
        highs   = df5['high'].values
        lows    = df5['low'].values
        volumes = df5['volume'].values

        ema9v   = ema(closes, 9)
        ema21v  = ema(closes, 21)
        rsi14   = rsi(closes, 14)
        ml, sl  = macd(closes)
        vwap_v  = vwap(df5).values
        st, std = supertrend(df5, 10, 3)
        patterns = candlestick_patterns(df5)

        cp  = closes[-1]
        cv  = vwap_v[-1]
        cr  = rsi14[-1]
        cm  = ml[-1]
        e9  = ema9v[-1]; e21 = ema21v[-1]
        av  = cp > cv
        std_val = std[-1] if not np.isnan(std[-1]) else 0

        avg_vol   = np.mean(volumes[-20:])
        vol_spike = volumes[-1] > avg_vol * 1.5
        vol_ratio = round(volumes[-1] / avg_vol, 1)

        eb  = (ema9v[-2] <= ema21v[-2]) and (ema9v[-1] > ema21v[-1])
        ebs = (ema9v[-2] >= ema21v[-2]) and (ema9v[-1] < ema21v[-1])
        mb  = (ml[-2] <= sl[-2]) and (ml[-1] > sl[-1])
        mbs = (ml[-2] >= sl[-2]) and (ml[-1] < sl[-1])

        buy_sc  = sum([std_val==1, eb or e9>e21, av, 40<=cr<=65, mb or cm>sl[-1], vol_spike]) * 16
        sell_sc = sum([std_val==-1, ebs or e9<e21, not av, 35<=cr<=60, mbs or cm<sl[-1], vol_spike]) * 16

        if buy_sc >= 60:   sig = "🟢 BUY"; conf = buy_sc
        elif sell_sc >= 60: sig = "🔴 SELL"; conf = sell_sc
        else:               sig = "⚪ WAIT"; conf = max(buy_sc, sell_sc)

        sl_p = round(min(lows[-5:]) * 0.998, 2) if "BUY" in sig else round(max(highs[-5:]) * 1.002, 2)
        risk = max(abs(cp - sl_p), 1)
        t1   = round(cp + risk*1.5, 2) if "BUY" in sig else round(cp - risk*1.5, 2)
        t2   = round(cp + risk*2.5, 2) if "BUY" in sig else round(cp - risk*2.5, 2)

        today    = datetime.now().date()
        today_df = df5[pd.to_datetime(df5['date']).dt.date == today]
        d_open   = today_df.iloc[0]['open'] if len(today_df) > 0 else closes[-1]
        d_high   = today_df['high'].max()   if len(today_df) > 0 else highs[-1]
        d_low    = today_df['low'].min()    if len(today_df) > 0 else lows[-1]

        chg     = round(((cp - d_open) / d_open) * 100, 2) if d_open else 0
        chg_ico = "📈" if chg >= 0 else "📉"

        st_txt   = "🟢 Bullish" if std_val == 1 else "🔴 Bearish" if std_val == -1 else "⚪ Neutral"
        ema_txt  = "✅ Bullish Cross" if eb else "❌ Bearish Cross" if ebs else "📈 Above" if e9>e21 else "📉 Below"
        vwap_txt = f"{'✅ Above' if av else '❌ Below'} (₹{round(cv,2)})"
        rsi_txt  = f"{'🔥 Overbought' if cr>70 else '💚 Oversold' if cr<30 else '✅ Normal'} ({round(cr,1)})"
        macd_txt = f"{'✅ Bullish' if mb or cm>sl[-1] else '❌ Bearish'} ({round(cm,3)})"
        vol_txt  = f"🔥 Spike {vol_ratio}x" if vol_spike else f"😐 Normal ({vol_ratio}x)"
        pat_txt  = ", ".join([p[0] for p in patterns]) if patterns else "None"

        msg = f"""<b>📊 ANALYSIS: {symbol} [{exchange}]</b>
━━━━━━━━━━━━━━━━━━━━

<b>💰 PRICE</b>
LTP:  <b>₹{round(cp,2)}</b>  {chg_ico} {chg:+.2f}%
Open: ₹{round(d_open,2)} | H: ₹{round(d_high,2)} | L: ₹{round(d_low,2)}

<b>📐 INDICATORS (5min)</b>
Supertrend : {st_txt}
EMA 9/21   : {ema_txt} (₹{round(e9,2)} / ₹{round(e21,2)})
VWAP       : {vwap_txt}
RSI(14)    : {rsi_txt}
MACD       : {macd_txt}
Volume     : {vol_txt}
Patterns   : {pat_txt}

<b>🎯 SIGNAL: {sig}</b>
Confidence: {conf}/100

<b>📌 KEY LEVELS</b>
Entry  : ₹{round(cp,2)}
SL     : ₹{sl_p}
Target1: ₹{t1}
Target2: ₹{t2}
R:R = 1:1.5

<i>⏰ {datetime.now().strftime('%d-%b-%Y %H:%M')} | 5min + Supertrend</i>"""

        send_telegram(msg)

    except Exception as e:
        log.error(f"[ANALYZE] {e}")
        send_telegram(f"❌ Error: {str(e)}")

# ================================================================
#  TELEGRAM LISTENER
# ================================================================
def telegram_listener():
    log.info("[TG] Listener started!")
    send_telegram(
        f"🤖 <b>Trading Bot v4 Online!</b>\n\n"
        f"✅ Auto Login: 8:45 AM daily\n"
        f"✅ Supertrend + EMA + VWAP + RSI + MACD\n"
        f"✅ Candlestick Patterns\n"
        f"✅ Multi-timeframe (5min + 15min)\n"
        f"✅ Auto Position Sizing\n\n"
        f"/analyze RELIANCE\n"
        f"/analyze NIFTY NFO\n"
        f"/analyze GOLD MCX\n"
        f"/status — bot status\n"
        f"/login — manual login link\n"
        f"/help — all commands"
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
                        send_telegram("📊 Usage:\n/analyze RELIANCE\n/analyze NIFTY NFO\n/analyze BANKNIFTY NFO\n/analyze GOLD MCX")
                    else:
                        threading.Thread(target=cmd_analyze, args=(parts[1],), daemon=True).start()

                elif text.lower() == "/login":
                    send_telegram(f"🔐 Manual login:\n{CALLBACK_URL}")

                elif text.lower() == "/status":
                    token_ok = bool(access_token[0])
                    last_l   = last_login[0].strftime('%H:%M %d-%b') if last_login[0] else "Never"
                    send_telegram(
                        f"<b>📊 Bot Status</b>\n\n"
                        f"Token: {'✅ Active' if token_ok else '❌ Missing'}\n"
                        f"Last Login: {last_l}\n"
                        f"Next Auto Login: 8:45 AM\n"
                        f"Capital: ₹{CAPITAL:,}\n"
                        f"Max Daily Loss: ₹{MAX_DAILY_LOSS:,}\n"
                        f"Per Trade: ₹{PER_TRADE_CAPITAL:,}"
                    )

                elif text.lower() == "/help":
                    send_telegram(
                        "🤖 <b>Commands:</b>\n\n"
                        "/analyze SYMBOL — Analysis\n"
                        "/analyze SYMBOL EXCHANGE\n"
                        "/status — Bot status\n"
                        "/login — Manual login link\n\n"
                        "<b>Examples:</b>\n"
                        "/analyze RELIANCE\n"
                        "/analyze HDFCBANK\n"
                        "/analyze NIFTY NFO\n"
                        "/analyze BANKNIFTY NFO\n"
                        "/analyze GOLD MCX\n"
                        "/analyze CRUDE MCX"
                    )
        except Exception as e:
            log.error(f"[TG] {e}")
        time.sleep(1)

# ================================================================
#  ORDER EXECUTOR
# ================================================================
class OrderExecutor:
    def __init__(self):
        self.daily_pnl   = 0
        self.trade_count = 0
        self.positions   = {}  # symbol -> {entry, sl, trailing_sl}

    def get_ltp(self, exchange, symbol):
        try: return kite.ltp(f"{exchange}:{symbol}")[f"{exchange}:{symbol}"]["last_price"]
        except: return None

    def execute(self, sig):
        symbol   = sig['symbol']; exchange = sig['exchange']
        action   = sig['signal']; quantity = sig['quantity']
        product  = sig['product']; sl_price = sig['sl']

        try:
            tx    = KiteConnect.TRANSACTION_TYPE_BUY if action=="BUY" else KiteConnect.TRANSACTION_TYPE_SELL
            pt    = KiteConnect.PRODUCT_MIS if product=="MIS" else KiteConnect.PRODUCT_NRML
            ltp   = self.get_ltp(exchange, symbol)
            if not ltp: return False
            price = round(ltp * 1.002, 1) if action=="BUY" else round(ltp * 0.998, 1)

            oid = kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR, exchange=exchange,
                tradingsymbol=symbol, transaction_type=tx,
                quantity=quantity, product=pt,
                order_type=KiteConnect.ORDER_TYPE_LIMIT, price=price
            )
            self.trade_count += 1

            # SL order
            sl_tx = KiteConnect.TRANSACTION_TYPE_SELL if action=="BUY" else KiteConnect.TRANSACTION_TYPE_BUY
            kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR, exchange=exchange,
                tradingsymbol=symbol, transaction_type=sl_tx,
                quantity=quantity, product=pt,
                order_type=KiteConnect.ORDER_TYPE_SL_M, trigger_price=sl_price
            )

            # Track for trailing SL
            self.positions[symbol] = {
                "action": action, "entry": price,
                "sl": sl_price, "trailing_sl": sl_price,
                "exchange": exchange, "quantity": quantity, "product": product
            }

            send_telegram(
                f"✅ <b>ORDER EXECUTED!</b>\n\n"
                f"{action} {symbol}\n"
                f"Price: ₹{price}\n"
                f"Qty: {quantity}\n"
                f"SL: ₹{sl_price}\n"
                f"Target1: ₹{sig['t1']}\n"
                f"Target2: ₹{sig['t2']}\n"
                f"Order ID: {oid}"
            )
            return True

        except Exception as e:
            log.error(f"[EXECUTE] {e}")
            send_telegram(f"❌ Order failed: {e}")
            return False

    def update_trailing_sl(self):
        """Update trailing SL for open positions"""
        for symbol, pos in list(self.positions.items()):
            try:
                ltp = self.get_ltp(pos['exchange'], symbol)
                if not ltp: continue

                action = pos['action']
                entry  = pos['entry']
                curr_sl = pos['trailing_sl']

                if action == "BUY":
                    profit = ltp - entry
                    # Trail SL up by 50% of profit
                    new_sl = round(ltp - (ltp - entry) * 0.5, 2)
                    if new_sl > curr_sl:
                        pos['trailing_sl'] = new_sl
                        log.info(f"[TRAIL SL] {symbol} SL updated: {curr_sl} → {new_sl}")
                        send_telegram(f"🔄 <b>Trailing SL Updated</b>\n{symbol}\nNew SL: ₹{new_sl}")
                else:
                    new_sl = round(ltp + (entry - ltp) * 0.5, 2)
                    if new_sl < curr_sl:
                        pos['trailing_sl'] = new_sl
                        log.info(f"[TRAIL SL] {symbol} SL updated: {curr_sl} → {new_sl}")

            except Exception as e:
                log.debug(f"[TRAIL SL] {symbol}: {e}")

    def update_pnl(self):
        try:
            self.daily_pnl = sum(p.get('pnl', 0) for p in kite.positions().get('net', []))
            return self.daily_pnl
        except: return 0

    def square_off_all(self):
        log.info("[SQUAREOFF] Closing all positions...")
        try:
            positions = kite.positions()
            for pos in positions.get('net', []):
                if pos['quantity'] != 0:
                    action = "SELL" if pos['quantity'] > 0 else "BUY"
                    pt     = KiteConnect.PRODUCT_MIS if pos['product'] == "MIS" else KiteConnect.PRODUCT_NRML
                    tx     = KiteConnect.TRANSACTION_TYPE_BUY if action == "BUY" else KiteConnect.TRANSACTION_TYPE_SELL
                    ltp    = self.get_ltp(pos['exchange'], pos['tradingsymbol'])
                    if ltp:
                        price = round(ltp * 1.002, 1) if action == "BUY" else round(ltp * 0.998, 1)
                        kite.place_order(
                            variety=KiteConnect.VARIETY_REGULAR, exchange=pos['exchange'],
                            tradingsymbol=pos['tradingsymbol'], transaction_type=tx,
                            quantity=abs(pos['quantity']), product=pt,
                            order_type=KiteConnect.ORDER_TYPE_LIMIT, price=price
                        )
            self.positions.clear()
            send_telegram("✅ All positions squared off!")
        except Exception as e:
            log.error(f"[SQUAREOFF] {e}")

# ================================================================
#  AUTO EXPIRY HELPERS
# ================================================================
def get_fut_symbol(base, exchange="NFO"):
    months = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]
    yr     = str(datetime.now().year)[2:]
    for delta in [0, 1]:
        mi  = (datetime.now().month - 1 + delta) % 12
        yri = yr if (datetime.now().month - 1 + delta) < 12 else str(int(yr)+1)
        sym = f"{base}{yri}{months[mi]}FUT"
        try:
            kite.ltp(f"{exchange}:{sym}")
            return sym
        except: pass
    return f"{base}{yr}{months[datetime.now().month-1]}FUT"

def get_mcx_sym(base):
    months = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]
    yr     = str(datetime.now().year)[2:]
    return f"{base}{yr}{months[datetime.now().month-1]}FUT"

# ================================================================
#  MAIN TRADING SYSTEM
# ================================================================
class TradingSystem:
    def __init__(self):
        self.executor      = OrderExecutor()
        self.scanned_today = set()
        self.squared_off   = False

        log.info("=" * 60)
        log.info("  KITE AUTO TRADING SYSTEM v4")
        log.info("  Multi-Strategy | Auto Login | Trailing SL")
        log.info("=" * 60)

        # Register executor for API
        _executor_ref[0] = self.executor

        # Start callback server
        threading.Thread(target=start_callback_server, daemon=True).start()

        # Start telegram listener
        threading.Thread(target=telegram_listener, daemon=True).start()

        # Try auto login immediately if no token
        if not access_token[0]:
            log.info("[AUTH] No token — trying auto login...")
            threading.Thread(target=auto_login, daemon=True).start()
        else:
            kite.set_access_token(access_token[0])
            log.info(f"[AUTH] Token loaded from env")

        # Schedule daily auto login at 8:45 AM
        threading.Thread(target=schedule_daily_login, daemon=True).start()

    def get_instruments(self):
        """Get all instruments to scan"""
        instruments = []

        # Nifty 50 stocks
        for stock in NIFTY50_STOCKS:
            instruments.append({"symbol": stock, "exchange": "NSE", "lots": 1, "lot_size": 1, "product": "MIS"})

        # BankNifty stocks (avoid duplicates)
        for stock in BANKNIFTY_STOCKS:
            if stock not in NIFTY50_STOCKS:
                instruments.append({"symbol": stock, "exchange": "NSE", "lots": 1, "lot_size": 1, "product": "MIS"})

        # F&O Futures
        instruments.append({"symbol": get_fut_symbol("NIFTY"),     "exchange": "NFO", "lots": 1, "lot_size": 25,  "product": "MIS"})
        instruments.append({"symbol": get_fut_symbol("BANKNIFTY"), "exchange": "NFO", "lots": 1, "lot_size": 15,  "product": "MIS"})
        instruments.append({"symbol": get_fut_symbol("FINNIFTY"),  "exchange": "NFO", "lots": 1, "lot_size": 40,  "product": "MIS"})

        # MCX
        instruments.append({"symbol": get_mcx_sym("GOLD"),        "exchange": "MCX", "lots": 1, "lot_size": 100,  "product": "NRML"})
        instruments.append({"symbol": get_mcx_sym("SILVERM"),      "exchange": "MCX", "lots": 1, "lot_size": 30,   "product": "NRML"})
        instruments.append({"symbol": get_mcx_sym("CRUDEOIL"),     "exchange": "MCX", "lots": 1, "lot_size": 100,  "product": "NRML"})
        instruments.append({"symbol": get_mcx_sym("NATURALGAS"),   "exchange": "MCX", "lots": 1, "lot_size": 1250, "product": "NRML"})

        return instruments

    def run(self):
        log.info("[BOT] Running...")

        while True:
            try:
                # Wait for token
                if not access_token[0]:
                    log.info(f"[WAIT] No token. Login: {CALLBACK_URL}")
                    time.sleep(30)
                    continue

                now = datetime.now().strftime("%H:%M")
                pnl = self.executor.update_pnl()

                # Reset daily at midnight
                if now == "00:01":
                    self.scanned_today.clear()
                    self.executor.trade_count = 0
                    self.squared_off = False
                    log.info("[RESET] Daily reset done!")

                # Square off time
                if now >= SQUAREOFF_TIME and not self.squared_off:
                    log.info("[SQUAREOFF] Time to close all positions!")
                    self.executor.square_off_all()
                    self.squared_off = True
                    send_telegram(f"🏁 <b>Market Closed!</b>\nFinal P&L: ₹{pnl:.2f}\nAll positions closed.")
                    time.sleep(3600)
                    continue

                # Max loss check
                if pnl <= -MAX_DAILY_LOSS:
                    log.warning(f"[STOP] Max loss hit! P&L: ₹{pnl:.2f}")
                    send_telegram(f"🚨 <b>MAX LOSS HIT!</b>\nP&L: ₹{pnl:.2f}\nBot stopped!")
                    self.executor.square_off_all()
                    time.sleep(3600)
                    continue

                # Max trades check
                if self.executor.trade_count >= MAX_TRADES_PER_DAY:
                    log.info(f"[STOP] Max {MAX_TRADES_PER_DAY} trades done!")
                    time.sleep(3600)
                    continue

                # Before market hours
                if now < TRADE_START_TIME:
                    log.info(f"[WAIT] Market opens at {TRADE_START_TIME}. Now: {now}")
                    time.sleep(60)
                    continue

                # After trade end
                if now > TRADE_END_TIME:
                    time.sleep(300)
                    continue

                # Update trailing SL
                self.executor.update_trailing_sl()

                # SCAN ALL INSTRUMENTS
                log.info(f"[SCAN] Starting scan... P&L: ₹{pnl:.2f} | Trades: {self.executor.trade_count}/{MAX_TRADES_PER_DAY}")
                signals = []

                for inst in self.get_instruments():
                    sym = inst['symbol']
                    if sym in self.scanned_today: continue
                    try:
                        result = get_signal(sym, inst['exchange'], inst['lots'], inst['lot_size'], inst['product'])
                        if result:
                            signals.append(result)
                            log.info(f"  ✅ {sym}: {result['signal']} | Score: {result['confidence']}")
                        time.sleep(0.4)
                    except Exception as e:
                        log.debug(f"  ❌ {sym}: {e}")

                # Top 3 by confidence
                signals.sort(key=lambda x: x['confidence'], reverse=True)
                signals = signals[:3]

                if not signals:
                    log.info("[SCAN] No signals found. Next scan in 5 min.")
                    time.sleep(300)
                    continue

                log.info(f"[SCAN] {len(signals)} signals found!")

                # Send signals to Telegram one by one
                for sig in signals:
                    if self.executor.trade_count >= MAX_TRADES_PER_DAY: break
                    sym = sig['symbol']
                    if sym in self.scanned_today: continue

                    icon = "🟢" if sig['signal'] == "BUY" else "🔴"
                    msg  = f"""{icon} <b>SIGNAL: {sig['signal']}</b>
━━━━━━━━━━━━━━━━━━

<b>{sym}</b> [{sig['exchange']}] | {sig['product']}

<b>Entry:</b>   ₹{sig['entry']}
<b>SL:</b>      ₹{sig['sl']} (Risk: ₹{sig['risk']}/share)
<b>Target 1:</b> ₹{sig['t1']}
<b>Target 2:</b> ₹{sig['t2']}
<b>Target 3:</b> ₹{sig['t3']}

<b>Confidence:</b> {sig['confidence']}/100
<b>R:R = 1:{sig['rr']}</b>
<b>Qty:</b> {sig['quantity']} shares

<b>📐 Reasons:</b>
{sig['reason']}

<b>RSI:</b> {sig['rsi']} | <b>VWAP:</b> ₹{sig['vwap']}

Reply <b>YES</b> ✅ — Execute trade
Reply <b>NO</b> ❌ — Skip
<i>⏰ Auto-cancel in 2 minutes</i>"""

                    send_telegram(msg)

                    # Wait for YES/NO
                    start   = time.time()
                    reply   = None
                    last_id = None
                    while time.time() - start < 120:
                        updates = tg_get_updates(last_id)
                        for u in updates:
                            last_id = u['update_id'] + 1
                            txt = u.get('message', {}).get('text', '').strip().upper()
                            if txt in ['YES', 'Y', 'HAN', 'HAAN', '1', 'OK']:
                                reply = True; break
                            elif txt in ['NO', 'N', 'NAI', 'NAHI', '0', 'SKIP']:
                                reply = False; break
                        if reply is not None: break
                        time.sleep(2)

                    if reply is True:
                        log.info(f"[APPROVED] Executing {sym}")
                        self.executor.execute(sig)
                        self.scanned_today.add(sym)
                    elif reply is False:
                        send_telegram(f"⏭️ <b>{sym}</b> skipped.")
                        self.scanned_today.add(sym)
                    else:
                        send_telegram(f"⏰ No reply — <b>{sym}</b> auto-cancelled.")
                        self.scanned_today.add(sym)

                    time.sleep(2)

                log.info("[SCAN] Done. Next scan in 5 min.")
                time.sleep(300)

            except KeyboardInterrupt:
                self.executor.square_off_all()
                break
            except Exception as e:
                log.error(f"[ERROR] {e}")
                time.sleep(30)

# ================================================================
#  START
# ================================================================
if __name__ == "__main__":
    log.info("KITE AUTO TRADING SYSTEM v4 STARTING...")
    system = TradingSystem()
    system.run()
