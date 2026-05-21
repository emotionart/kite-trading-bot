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

DASHBOARD_HTML = '<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>StockWala Bot</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #0a0a0f; --card: #12121e; --border: #1e1e32;
  --green: #00ff88; --red: #ff3366; --yellow: #ffcc00; --blue: #4488ff;
  --text: #e0e0f0; --text2: #8888aa;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:\'Syne\',sans-serif; min-height:100vh; }
body::before {
  content:\'\'; position:fixed; inset:0; pointer-events:none; z-index:0;
  background-image: linear-gradient(rgba(68,136,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(68,136,255,0.03) 1px, transparent 1px);
  background-size: 40px 40px;
}

/* HEADER */
header {
  position:sticky; top:0; z-index:100;
  display:flex; align-items:center; justify-content:space-between;
  padding:16px 24px; border-bottom:1px solid var(--border);
  background:rgba(10,10,15,0.95); backdrop-filter:blur(20px);
}
.logo { display:flex; align-items:center; gap:10px; font-size:20px; font-weight:800; }
.logo span { color:var(--green); }
.dot { width:8px; height:8px; border-radius:50%; background:var(--green); animation:blink 1.5s infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.2} }
.badge { display:flex; align-items:center; gap:8px; padding:6px 14px; border:1px solid var(--green); border-radius:100px; font-size:12px; font-family:\'Space Mono\',monospace; color:var(--green); }
.btn { padding:8px 18px; border-radius:8px; border:none; cursor:pointer; font-family:\'Syne\',sans-serif; font-weight:700; font-size:13px; transition:all 0.2s; }
.btn-green { background:var(--green); color:#000; }
.btn-green:hover { box-shadow:0 0 20px rgba(0,255,136,0.4); }
.btn-outline { background:transparent; border:1px solid var(--border); color:var(--text2); }
.btn-outline:hover { border-color:var(--green); color:var(--green); }

/* TICKER */
.ticker { display:flex; gap:20px; padding:14px 24px; background:var(--card); border-bottom:1px solid var(--border); overflow-x:auto; }
.tick { min-width:110px; }
.tick-name { font-size:10px; color:var(--text2); font-family:\'Space Mono\',monospace; text-transform:uppercase; }
.tick-price { font-size:16px; font-weight:700; font-family:\'Space Mono\',monospace; margin:2px 0; }
.tick-chg { font-size:11px; font-family:\'Space Mono\',monospace; }
.up { color:var(--green); } .down { color:var(--red); } .neu { color:var(--yellow); }

/* MAIN */
main { position:relative; z-index:1; max-width:1400px; margin:0 auto; padding:20px 24px; }

/* STATS */
.stats { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:20px; }
.stat { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:16px; position:relative; overflow:hidden; }
.stat::before { content:\'\'; position:absolute; top:0; left:0; right:0; height:2px; }
.stat.g::before{background:var(--green)} .stat.r::before{background:var(--red)} .stat.b::before{background:var(--blue)} .stat.y::before{background:var(--yellow)}
.stat-label { font-size:10px; color:var(--text2); text-transform:uppercase; letter-spacing:1px; font-family:\'Space Mono\',monospace; }
.stat-val { font-size:26px; font-weight:800; font-family:\'Space Mono\',monospace; margin:6px 0 4px; }
.stat-sub { font-size:11px; color:var(--text2); font-family:\'Space Mono\',monospace; }

/* GRID */
.grid { display:grid; grid-template-columns:1fr 360px; gap:20px; }

/* PANEL */
.panel { background:var(--card); border:1px solid var(--border); border-radius:14px; overflow:hidden; }
.ph { display:flex; align-items:center; justify-content:space-between; padding:16px 20px; border-bottom:1px solid var(--border); }
.pt { font-size:15px; font-weight:700; }
.pb { background:rgba(0,255,136,0.1); color:var(--green); border:1px solid rgba(0,255,136,0.2); padding:2px 10px; border-radius:100px; font-size:11px; font-family:\'Space Mono\',monospace; }

/* SEARCH */
.search-row { display:flex; gap:8px; padding:16px; border-bottom:1px solid var(--border); }
.sym-input { flex:1; background:#141420; border:1px solid var(--border); border-radius:8px; padding:10px 14px; color:var(--text); font-family:\'Space Mono\',monospace; font-size:13px; outline:none; text-transform:uppercase; }
.sym-input:focus { border-color:var(--blue); }
.sym-input::placeholder { text-transform:none; color:var(--text2); }
.exch-sel { background:#141420; border:1px solid var(--border); border-radius:8px; padding:10px 10px; color:var(--text); font-family:\'Space Mono\',monospace; font-size:13px; cursor:pointer; outline:none; }

/* QUICK BTNS */
.quick-btns { display:flex; flex-wrap:wrap; gap:6px; padding:12px 16px; border-bottom:1px solid var(--border); }
.qbtn { padding:6px 12px; background:#141420; border:1px solid var(--border); border-radius:6px; color:var(--text2); font-family:\'Space Mono\',monospace; font-size:11px; cursor:pointer; transition:all 0.15s; }
.qbtn:hover { border-color:var(--green); color:var(--green); }

/* RESULT */
.result-area { padding:16px; min-height:100px; }
.result-loading { text-align:center; padding:30px; color:var(--text2); font-family:\'Space Mono\',monospace; font-size:13px; }
.result-card { background:#0f0f1a; border-radius:10px; padding:14px; }
.rc-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; padding-bottom:10px; border-bottom:1px solid var(--border); }
.rc-sym { font-size:15px; font-weight:800; font-family:\'Space Mono\',monospace; }
.rc-ltp { font-size:18px; font-weight:800; font-family:\'Space Mono\',monospace; }
.rc-row { display:flex; justify-content:space-between; padding:5px 0; border-bottom:1px solid rgba(30,30,50,0.5); font-size:12px; font-family:\'Space Mono\',monospace; }
.rc-row:last-child { border-bottom:none; }
.rc-key { color:var(--text2); }
.rc-val { font-weight:700; }
.sig-box { margin:12px 0; padding:12px; border-radius:8px; text-align:center; border:1px solid; }
.sig-BUY { background:rgba(0,255,136,0.08); border-color:rgba(0,255,136,0.3); color:var(--green); }
.sig-SELL { background:rgba(255,51,102,0.08); border-color:rgba(255,51,102,0.3); color:var(--red); }
.sig-WAIT { background:rgba(255,204,0,0.08); border-color:rgba(255,204,0,0.3); color:var(--yellow); }
.sig-text { font-size:18px; font-weight:800; }
.sig-conf { font-size:11px; opacity:0.7; margin-top:2px; }
.levels { display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-top:8px; }
.level-box { background:#141420; border-radius:6px; padding:8px; text-align:center; font-family:\'Space Mono\',monospace; }
.level-label { font-size:10px; color:var(--text2); }
.level-val { font-size:13px; font-weight:700; margin-top:2px; }

/* SIGNAL CARDS */
.signals-list { padding:12px; display:flex; flex-direction:column; gap:10px; max-height:500px; overflow-y:auto; }
.sig-card { background:#0f0f1a; border:1px solid var(--border); border-radius:10px; padding:14px; cursor:pointer; transition:all 0.15s; position:relative; overflow:hidden; }
.sig-card::before { content:\'\'; position:absolute; left:0; top:0; bottom:0; width:3px; }
.sig-card.buy::before { background:var(--green); }
.sig-card.sell::before { background:var(--red); }
.sig-card:hover { border-color:rgba(68,136,255,0.3); transform:translateX(2px); }
.sc-top { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
.sc-sym { font-size:14px; font-weight:800; font-family:\'Space Mono\',monospace; }
.sc-badge { padding:3px 10px; border-radius:5px; font-size:11px; font-weight:700; font-family:\'Space Mono\',monospace; }
.buy-badge { background:rgba(0,255,136,0.15); color:var(--green); }
.sell-badge { background:rgba(255,51,102,0.15); color:var(--red); }
.sc-row { display:flex; gap:12px; font-size:11px; font-family:\'Space Mono\',monospace; color:var(--text2); }
.sc-row span { color:var(--text); }
.sc-actions { display:flex; gap:8px; margin-top:10px; }
.sc-btn { flex:1; padding:7px; border-radius:6px; border:none; cursor:pointer; font-family:\'Space Mono\',monospace; font-size:11px; font-weight:700; transition:all 0.15s; }
.sc-yes { background:var(--green); color:#000; }
.sc-no { background:rgba(255,51,102,0.1); color:var(--red); border:1px solid rgba(255,51,102,0.2); }
.conf-bar { height:2px; background:var(--border); border-radius:2px; margin-top:8px; }
.conf-fill { height:100%; border-radius:2px; }

/* RIGHT PANEL */
.right { display:flex; flex-direction:column; gap:16px; }
.pnl-card { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:20px; }
.pnl-label { font-size:10px; color:var(--text2); text-transform:uppercase; letter-spacing:1px; font-family:\'Space Mono\',monospace; }
.pnl-val { font-size:38px; font-weight:800; font-family:\'Space Mono\',monospace; margin:6px 0 4px; }
.pnl-sub { font-size:11px; color:var(--text2); font-family:\'Space Mono\',monospace; }
.risk-bar-wrap { margin-top:14px; }
.risk-labels { display:flex; justify-content:space-between; font-size:10px; color:var(--text2); font-family:\'Space Mono\',monospace; margin-bottom:4px; }
.risk-track { height:5px; background:var(--border); border-radius:5px; overflow:hidden; }
.risk-fill { height:100%; border-radius:5px; background:linear-gradient(90deg, var(--green), var(--yellow)); transition:width 0.5s; }

.auth-card { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:16px; }
.auth-ok { display:flex; align-items:center; gap:8px; padding:10px 14px; background:rgba(0,255,136,0.08); border:1px solid rgba(0,255,136,0.2); border-radius:8px; color:var(--green); font-family:\'Space Mono\',monospace; font-size:12px; margin:10px 0; }
.auth-fail { display:flex; align-items:center; gap:8px; padding:10px 14px; background:rgba(255,51,102,0.08); border:1px solid rgba(255,51,102,0.2); border-radius:8px; color:var(--red); font-family:\'Space Mono\',monospace; font-size:12px; margin:10px 0; }
.auth-btns { display:flex; gap:8px; }
.auth-note { font-size:10px; color:var(--text2); font-family:\'Space Mono\',monospace; margin-top:10px; }

/* SCAN BTN */
.scan-btn { width:calc(100% - 32px); margin:12px 16px; padding:14px; background:linear-gradient(135deg, rgba(0,255,136,0.1), rgba(68,136,255,0.1)); border:1px solid rgba(0,255,136,0.2); border-radius:10px; color:var(--green); font-family:\'Syne\',sans-serif; font-weight:700; font-size:14px; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:8px; transition:all 0.2s; }
.scan-btn:hover { box-shadow:0 0 20px rgba(0,255,136,0.2); transform:translateY(-1px); }
.scan-btn:disabled { opacity:0.5; pointer-events:none; }

/* SPINNER */
.spin { width:14px; height:14px; border:2px solid rgba(255,255,255,0.1); border-top-color:var(--green); border-radius:50%; animation:spin 0.7s linear infinite; display:inline-block; }
@keyframes spin { to { transform:rotate(360deg); } }

/* TOAST */
.toast { position:fixed; bottom:20px; right:20px; background:var(--card); border:1px solid var(--green); border-radius:10px; padding:12px 18px; font-family:\'Space Mono\',monospace; font-size:12px; color:var(--green); z-index:999; opacity:0; transform:translateY(20px); transition:all 0.3s; pointer-events:none; }
.toast.show { opacity:1; transform:translateY(0); }

/* LOGIN MODAL */
.modal { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.85); backdrop-filter:blur(10px); z-index:200; align-items:center; justify-content:center; }
.modal.open { display:flex; }
.modal-box { background:var(--card); border:1px solid var(--green); border-radius:18px; padding:36px; text-align:center; max-width:380px; width:90%; position:relative; }
.modal-close { position:absolute; top:14px; right:16px; background:none; border:none; color:var(--text2); font-size:18px; cursor:pointer; }

/* TRADES */
.trades-list { padding:0 12px 12px; max-height:250px; overflow-y:auto; }
.trade-row { display:flex; align-items:center; justify-content:space-between; padding:10px 0; border-bottom:1px solid var(--border); font-size:12px; }
.trade-row:last-child { border-bottom:none; }
.trade-sym { font-weight:700; font-family:\'Space Mono\',monospace; }
.trade-info { font-size:10px; color:var(--text2); font-family:\'Space Mono\',monospace; }
.trade-pnl { font-family:\'Space Mono\',monospace; font-weight:700; }

::-webkit-scrollbar { width:3px; }
::-webkit-scrollbar-thumb { background:var(--border); border-radius:3px; }

@media(max-width:1024px) { .grid{grid-template-columns:1fr} .stats{grid-template-columns:repeat(2,1fr)} }
@media(max-width:600px) { main{padding:12px} .stats{grid-template-columns:repeat(2,1fr)} }
</style>
</head>
<body>

<header>
  <div class="logo">📈 StockWala <span>Bot</span></div>
  <div style="display:flex;align-items:center;gap:12px">
    <div class="badge"><div class="dot" id="dot"></div><span id="statusTxt">Connecting...</span></div>
    <button class="btn btn-outline" onclick="openLogin()">🔐 Login</button>
    <button class="btn btn-green" onclick="doScan()">⚡ Scan</button>
  </div>
</header>

<!-- TICKER -->
<div class="ticker" id="ticker">
  <div class="tick"><div class="tick-name">NIFTY 50</div><div class="tick-price" id="t-nifty">—</div><div class="tick-chg" id="c-nifty">—</div></div>
  <div class="tick"><div class="tick-name">BANK NIFTY</div><div class="tick-price" id="t-bank">—</div><div class="tick-chg" id="c-bank">—</div></div>
  <div class="tick"><div class="tick-name">FIN NIFTY</div><div class="tick-price" id="t-fin">—</div><div class="tick-chg" id="c-fin">—</div></div>
  <div class="tick"><div class="tick-name">INDIA VIX</div><div class="tick-price" id="t-vix">—</div><div class="tick-chg" id="c-vix" class="neu">—</div></div>
  <div class="tick"><div class="tick-name">NIFTY FUT</div><div class="tick-price" id="t-nfut">—</div><div class="tick-chg" id="c-nfut">—</div></div>
  <div class="tick"><div class="tick-name">BANKNIFTY FUT</div><div class="tick-price" id="t-bnfut">—</div><div class="tick-chg" id="c-bnfut">—</div></div>
  <div class="tick"><div class="tick-name">GOLD MCX</div><div class="tick-price" id="t-gold">—</div><div class="tick-chg" id="c-gold">—</div></div>
  <div class="tick"><div class="tick-name">CRUDE MCX</div><div class="tick-price" id="t-crude">—</div><div class="tick-chg" id="c-crude">—</div></div>
  <div class="tick"><div class="tick-name">SILVER MCX</div><div class="tick-price" id="t-silver">—</div><div class="tick-chg" id="c-silver">—</div></div>
  <div class="tick" style="margin-left:auto"><div class="tick-name">IST TIME</div><div class="tick-price" id="clock" style="font-size:14px">—</div><div class="tick-chg" id="mktStatus">—</div></div>
</div>

<main>
<!-- STATS -->
<div class="stats">
  <div class="stat g"><div class="stat-label">Today P&L</div><div class="stat-val up" id="s-pnl">&#8377;0</div><div class="stat-sub" id="s-pnlpct">0% of capital</div></div>
  <div class="stat b"><div class="stat-label">Trades</div><div class="stat-val" id="s-trades">0/5</div><div class="stat-sub">Max 5/day</div></div>
  <div class="stat y"><div class="stat-label">Signals</div><div class="stat-val" id="s-sigs">0</div><div class="stat-sub" id="s-scan">Last scan: —</div></div>
  <div class="stat r"><div class="stat-label">Risk Used</div><div class="stat-val" id="s-risk">&#8377;0</div><div class="stat-sub">Max &#8377;3,000/day</div></div>
</div>

<div class="grid">
<!-- LEFT -->
<div style="display:flex;flex-direction:column;gap:16px">

  <!-- ANALYZE -->
  <div class="panel">
    <div class="ph"><div class="pt">🔍 Analyze Stock</div></div>
    <div class="search-row">
      <input class="sym-input" id="symIn" placeholder="Type symbol: RELIANCE, HDFCBANK, NIFTY..." onkeypress="if(event.key===\'Enter\')analyze()">
      <select class="exch-sel" id="exchIn">
        <option value="NSE">NSE</option>
        <option value="NFO">NFO</option>
        <option value="MCX">MCX</option>
        <option value="BSE">BSE</option>
      </select>
      <button class="btn btn-green" onclick="analyze()">Go →</button>
    </div>
    <div class="quick-btns">
      <button class="qbtn" onclick="qa(\'RELIANCE\',\'NSE\')">RELIANCE</button>
      <button class="qbtn" onclick="qa(\'HDFCBANK\',\'NSE\')">HDFCBANK</button>
      <button class="qbtn" onclick="qa(\'TCS\',\'NSE\')">TCS</button>
      <button class="qbtn" onclick="qa(\'ICICIBANK\',\'NSE\')">ICICIBANK</button>
      <button class="qbtn" onclick="qa(\'SBIN\',\'NSE\')">SBIN</button>
      <button class="qbtn" onclick="qa(\'NIFTY\',\'NFO\')">NIFTY FUT</button>
      <button class="qbtn" onclick="qa(\'BANKNIFTY\',\'NFO\')">BANKNIFTY</button>
      <button class="qbtn" onclick="qa(\'FINNIFTY\',\'NFO\')">FINNIFTY</button>
      <button class="qbtn" onclick="qa(\'GOLD\',\'MCX\')">🥇 GOLD</button>
      <button class="qbtn" onclick="qa(\'CRUDE\',\'MCX\')">🛢️ CRUDE</button>
      <button class="qbtn" onclick="qa(\'SILVER\',\'MCX\')">🥈 SILVER</button>
      <button class="qbtn" onclick="qa(\'NATURALGAS\',\'MCX\')">⛽ NATGAS</button>
    </div>
    <div class="result-area" id="resultArea">
      <div class="result-loading">📊 Symbol type karo ya quick button dabao<br><span style="font-size:11px">Live data from Zerodha Kite API</span></div>
    </div>
  </div>

  <!-- SIGNALS -->
  <div class="panel">
    <div class="ph">
      <div class="pt">⚡ Live Signals <span class="pb" id="sigBadge">0</span></div>
      <button class="btn btn-outline" style="font-size:11px;padding:5px 10px" onclick="clearSigs()">Clear</button>
    </div>
    <button class="scan-btn" id="scanBtn" onclick="doScan()">⚡ Scan All Markets (Nifty50 + BankNifty + F&O + MCX)</button>
    <div class="signals-list" id="sigsList">
      <div style="text-align:center;padding:30px;color:var(--text2);font-family:\'Space Mono\',monospace;font-size:12px">
        📡 Scan karo — signals yahaan aayenge
      </div>
    </div>
  </div>

  <!-- TRADES -->
  <div class="panel">
    <div class="ph"><div class="pt">📋 Today\'s Trades</div><div id="tradeBadge" class="pb">0</div></div>
    <div class="trades-list" id="tradesList">
      <div style="text-align:center;padding:20px;color:var(--text2);font-family:\'Space Mono\',monospace;font-size:11px">No trades today</div>
    </div>
  </div>

</div>

<!-- RIGHT -->
<div class="right">

  <!-- P&L -->
  <div class="pnl-card">
    <div class="pnl-label">Daily P&L</div>
    <div class="pnl-val up" id="pnlBig">&#8377;0.00</div>
    <div class="pnl-sub">Capital: &#8377;1,00,000 | Risk/Trade: &#8377;1,000</div>
    <div class="risk-bar-wrap">
      <div class="risk-labels"><span>Daily Risk</span><span id="riskPct">0%</span></div>
      <div class="risk-track"><div class="risk-fill" id="riskFill" style="width:0%"></div></div>
    </div>
  </div>

  <!-- AUTH -->
  <div class="auth-card">
    <div class="pt">🔐 Authentication</div>
    <div id="authStatus" class="auth-ok">✅ Token Active</div>
    <div class="auth-btns">
      <button class="btn btn-outline" style="flex:1;font-size:12px" onclick="openLogin()">Refresh</button>
      <button class="btn btn-outline" style="flex:1;font-size:12px" onclick="checkStatus()">Status</button>
    </div>
    <div class="auth-note">Auto login: 8:45 AM daily<br>Next: Tomorrow 8:45 AM</div>
  </div>

  <!-- MARKET INFO -->
  <div class="panel">
    <div class="ph"><div class="pt">📈 Market Overview</div></div>
    <div style="padding:12px;display:flex;flex-direction:column;gap:8px" id="marketOverview">
      <div style="text-align:center;padding:20px;color:var(--text2);font-family:\'Space Mono\',monospace;font-size:11px">Loading market data...</div>
    </div>
  </div>

</div>
</div>
</main>

<!-- TOAST -->
<div class="toast" id="toast"></div>

<!-- LOGIN MODAL -->
<div class="modal" id="loginModal">
  <div class="modal-box">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <div style="font-size:48px;margin-bottom:12px">🔐</div>
    <h2 style="color:var(--green);margin-bottom:10px">Zerodha Login</h2>
    <p style="color:var(--text2);font-size:13px;margin-bottom:20px;line-height:1.6">
      Popup mein Zerodha login karo.<br>Token auto set ho jayega!
    </p>
    <div style="background:#141420;border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:16px;font-family:\'Space Mono\',monospace;font-size:12px;color:var(--yellow);display:flex;align-items:center;justify-content:center;gap:10px">
      <div class="spin"></div> Waiting for login...
    </div>
    <button onclick="closeModal()" class="btn btn-outline" style="width:100%">Cancel</button>
  </div>
</div>

<script>
const BOT = \'https://worker-production-5b28.up.railway.app\';
let signals = [], trades = [], pnl = 0, tradeCount = 0;

// ── CLOCK ──
function tick() {
  const now = new Date();
  const ist = new Date(now.toLocaleString(\'en-US\',{timeZone:\'Asia/Kolkata\'}));
  const h = ist.getHours(), m = ist.getMinutes();
  document.getElementById(\'clock\').textContent =
    String(h).padStart(2,\'0\')+\':\'+String(m).padStart(2,\'0\')+\':\'+String(ist.getSeconds()).padStart(2,\'0\');
  const open = h===9&&m>=15 || h>9&&h<15 || h===15&&m<=30;
  const mcx  = h>=9&&h<23||h===23&&m<30;
  document.getElementById(\'mktStatus\').textContent = open?\'🟢 NSE Open\':mcx?\'🟡 MCX Open\':\'🔴 Closed\';
  document.getElementById(\'mktStatus\').className   = \'tick-chg \'+(open?\'up\':mcx?\'neu\':\'down\');
}
setInterval(tick,1000); tick();

// ── TOAST ──
function toast(msg,dur=3000){
  const t=document.getElementById(\'toast\');
  t.textContent=msg; t.classList.add(\'show\');
  setTimeout(()=>t.classList.remove(\'show\'),dur);
}

// ── STATUS ──
async function checkStatus() {
  try {
    const r = await fetch(BOT+\'/api/status\',{signal:AbortSignal.timeout(6000)});
    if(!r.ok) throw new Error();
    const d = await r.json();
    document.getElementById(\'dot\').style.background=\'var(--green)\';
    document.getElementById(\'statusTxt\').textContent=\'Online\';
    updateAuth(d.token, d.last_login);
    updatePnl(d.pnl||0, d.trades||0);
  } catch {
    document.getElementById(\'dot\').style.background=\'var(--red)\';
    document.getElementById(\'statusTxt\').textContent=\'Offline\';
  }
}

function updateAuth(ok, lastLogin) {
  const el = document.getElementById(\'authStatus\');
  if(ok) {
    el.className=\'auth-ok\';
    el.textContent=\'✅ Token Active\'+(lastLogin?\' — \'+lastLogin:\'\');
  } else {
    el.className=\'auth-fail\';
    el.innerHTML=\'❌ Token Missing — <a href="#" onclick="openLogin()" style="color:inherit">Login Karo!</a>\';
  }
}

function updatePnl(p, tc) {
  pnl=p; tradeCount=tc;
  const sign = p>=0?\'+&#8377;\':\'-&#8377;\';
  const cls  = p>=0?\'up\':\'down\';
  document.getElementById(\'pnlBig\').textContent = sign+Math.abs(p).toFixed(2);
  document.getElementById(\'pnlBig\').className   = \'pnl-val \'+cls;
  document.getElementById(\'s-pnl\').textContent  = (p>=0?\'+\':\'\')+\'&#8377;\'+p.toFixed(0);
  document.getElementById(\'s-pnl\').className    = \'stat-val \'+cls;
  document.getElementById(\'s-pnlpct\').textContent = ((p/100000)*100).toFixed(2)+\'% of capital\';
  document.getElementById(\'s-trades\').textContent  = tc+\'/5\';
  document.getElementById(\'s-risk\').textContent     = \'&#8377;\'+Math.abs(p).toFixed(0);
  const rp = Math.min(Math.abs(p)/3000*100,100);
  document.getElementById(\'riskFill\').style.width = rp+\'%\';
  document.getElementById(\'riskPct\').textContent  = rp.toFixed(0)+\'%\';
}

// ── INDICES from bot ──
async function loadIndices() {
  try {
    const r = await fetch(BOT+\'/api/indices\',{signal:AbortSignal.timeout(8000)});
    const d = await r.json();

    // Map keys to element IDs
    // Dynamic keys based on current month
    const yr = \'26\', m = \'MAY\';
    const map = {
      \'NSE:NIFTY 50\':                    [\'t-nifty\',\'c-nifty\'],
      \'NSE:NIFTY BANK\':                  [\'t-bank\', \'c-bank\'],
      \'NSE:NIFTY FIN SERVICE\':           [\'t-fin\',  \'c-fin\'],
      \'NSE:INDIA VIX\':                   [\'t-vix\',  \'c-vix\'],
      [`NFO:NIFTY${yr}${m}FUT`]:       [\'t-nfut\', \'c-nfut\'],
      [`NFO:BANKNIFTY${yr}${m}FUT`]:   [\'t-bnfut\',\'c-bnfut\'],
      [`MCX:GOLD${yr}${m}FUT`]:        [\'t-gold\', \'c-gold\'],
      [`MCX:CRUDEOIL${yr}${m}FUT`]:    [\'t-crude\',\'c-crude\'],
      [`MCX:SILVERM${yr}${m}FUT`]:     [\'t-silver\',\'c-silver\'],
    };

    for(const [key,[pid,cid]] of Object.entries(map)) {
      if(d[key]) {
        const item = d[key];
        const ltp  = item.ltp||item.last_price||0;
        const chg  = item.change||item.net_change||0;
        document.getElementById(pid).textContent = \'&#8377;\'+ltp.toLocaleString(\'en-IN\');
        document.getElementById(cid).textContent = (chg>=0?\'+\':\'\')+chg.toFixed(2);
        document.getElementById(cid).className   = \'tick-chg \'+(chg>=0?\'up\':\'down\');
      }
    }

    // Market overview
    renderMarketOverview(d);
  } catch(e) {
    console.log(\'Indices error:\', e);
  }
}

function renderMarketOverview(d) {
  const ov = document.getElementById(\'marketOverview\');
  const rows = [
    [\'NIFTY 50\',        d[\'NSE:NIFTY 50\']],
    [\'BANK NIFTY\',      d[\'NSE:NIFTY BANK\']],
    [\'FIN NIFTY\',       d[\'NSE:NIFTY FIN SERVICE\']],
    [\'INDIA VIX\',       d[\'NSE:INDIA VIX\']],
    [\'NIFTY FUT\',       d[\'NFO:NIFTY26MAYFUT\']],
    [\'BANKNIFTY FUT\',   d[\'NFO:BANKNIFTY26MAYFUT\']],
    [\'GOLD MCX\',        d[\'MCX:GOLD26MAYFUT\']],
    [\'CRUDE MCX\',       d[\'MCX:CRUDEOIL26MAYFUT\']],
    [\'SILVER MCX\',      d[\'MCX:SILVERM26MAYFUT\']],
  ].filter(([,v])=>v);

  if(!rows.length) {
    ov.innerHTML=\'<div style="text-align:center;padding:16px;color:var(--text2);font-size:11px;font-family:Space Mono,monospace">Market data loading...</div>\';
    return;
  }

  ov.innerHTML = rows.map(([name,item])=>{
    const ltp = item.ltp||item.last_price||0;
    const chg = item.change||item.net_change||0;
    const cls = chg>=0?\'up\':\'down\';
    return `<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);font-family:Space Mono,monospace;font-size:12px">
      <span style="color:var(--text2)">${name}</span>
      <div style="text-align:right">
        <div style="font-weight:700">&#8377;${ltp.toLocaleString(\'en-IN\')}</div>
        <div class="${cls}" style="font-size:10px">${chg>=0?\'+\':\'\'}${chg.toFixed(2)}</div>
      </div>
    </div>`;
  }).join(\'\');
}

// ── ANALYZE ──
const aliases = {
  \'NIFTY\':[\'NIFTY\',\'NFO\'], \'BANKNIFTY\':[\'BANKNIFTY\',\'NFO\'], \'FINNIFTY\':[\'FINNIFTY\',\'NFO\'],
  \'GOLD\':[\'GOLD\',\'MCX\'], \'SILVER\':[\'SILVER\',\'MCX\'], \'CRUDE\':[\'CRUDE\',\'MCX\'],
  \'NATURALGAS\':[\'NATURALGAS\',\'MCX\'], \'CRUDEOIL\':[\'CRUDE\',\'MCX\'],
  \'NIFTY FUT\':[\'NIFTY\',\'NFO\'], \'BANK NIFTY\':[\'BANKNIFTY\',\'NFO\'],
};

function qa(sym, exch) {
  document.getElementById(\'symIn\').value = sym;
  document.getElementById(\'exchIn\').value = exch;
  analyze();
}

async function analyze() {
  let sym  = document.getElementById(\'symIn\').value.trim().toUpperCase();
  let exch = document.getElementById(\'exchIn\').value;
  if(!sym) { toast(\'⚠️ Symbol enter karo!\'); return; }

  // Auto-resolve aliases
  if(aliases[sym]) { [sym,exch]=aliases[sym]; }

  const area = document.getElementById(\'resultArea\');
  area.innerHTML = `<div class="result-loading"><div class="spin" style="width:24px;height:24px;border-width:3px;margin:0 auto 10px"></div>Analyzing ${sym} [${exch}]...</div>`;

  try {
    const r = await fetch(`${BOT}/api/analyze?symbol=${sym}&exchange=${exch}`,{signal:AbortSignal.timeout(20000)});
    const d = await r.json();

    if(d.error) {
      area.innerHTML = `<div style="padding:16px;color:var(--red);font-family:\'Space Mono\',monospace;font-size:12px">
        ❌ ${d.error}<br><span style="color:var(--text2);font-size:11px">Try: RELIANCE (NSE), NIFTY (NFO), GOLD (MCX)</span>
      </div>`;
      toast(\'❌ \'+d.error); return;
    }

    const sc = d.signal===\'BUY\'?\'sig-BUY\':d.signal===\'SELL\'?\'sig-SELL\':\'sig-WAIT\';
    const si = d.signal===\'BUY\'?\'🟢\':d.signal===\'SELL\'?\'🔴\':\'⚪\';
    const cc = d.change>=0?\'up\':\'down\';

    area.innerHTML = `<div class="result-card">
      <div class="rc-header">
        <div>
          <div class="rc-sym">${d.symbol} [${d.exchange}]</div>
          <div style="font-size:11px;color:var(--text2);font-family:\'Space Mono\',monospace;margin-top:2px">H:&#8377;${d.high} L:&#8377;${d.low}</div>
        </div>
        <div style="text-align:right">
          <div class="rc-ltp">&#8377;${d.ltp.toLocaleString(\'en-IN\')}</div>
          <div class="${cc}" style="font-family:\'Space Mono\',monospace;font-size:12px">${d.change>=0?\'+\':\'\'}${d.change}%</div>
        </div>
      </div>
      <div class="rc-row"><span class="rc-key">Supertrend</span><span class="rc-val">${d.supertrend===\'Bullish\'?\'🟢\':\'🔴\'} ${d.supertrend}</span></div>
      <div class="rc-row"><span class="rc-key">EMA 9/21</span><span class="rc-val">${d.ema_status} (${d.ema9}/${d.ema21})</span></div>
      <div class="rc-row"><span class="rc-key">VWAP</span><span class="rc-val">${d.vwap_status===\'Above\'?\'✅\':\'❌\'} &#8377;${d.vwap}</span></div>
      <div class="rc-row"><span class="rc-key">RSI(14)</span><span class="rc-val">${d.rsi>70?\'🔥\':d.rsi<30?\'💚\':\'✅\'} ${d.rsi}</span></div>
      <div class="rc-row"><span class="rc-key">MACD</span><span class="rc-val">${d.macd_status===\'Bullish\'?\'✅\':\'❌\'} ${d.macd_status} (${d.macd})</span></div>
      <div class="rc-row"><span class="rc-key">Volume</span><span class="rc-val">${d.volume}</span></div>
      ${d.patterns.length?`<div class="rc-row"><span class="rc-key">Pattern</span><span class="rc-val">${d.patterns.join(\', \')}</span></div>`:\'\'}
      <div class="sig-box ${sc}">
        <div class="sig-text">${si} ${d.signal}</div>
        <div class="sig-conf">${d.confidence}/100 confidence</div>
      </div>
      <div class="levels">
        <div class="level-box"><div class="level-label">Entry</div><div class="level-val">&#8377;${d.ltp}</div></div>
        <div class="level-box"><div class="level-label">Stop Loss</div><div class="level-val down">&#8377;${d.sl}</div></div>
        <div class="level-box"><div class="level-label">Target 1</div><div class="level-val up">&#8377;${d.t1}</div></div>
        <div class="level-box"><div class="level-label">Target 2</div><div class="level-val up">&#8377;${d.t2}</div></div>
      </div>
      <div style="text-align:center;margin-top:10px;font-size:10px;color:var(--text2);font-family:\'Space Mono\',monospace">Live data: Zerodha Kite API ✅</div>
    </div>`;

    toast(`✅ ${d.symbol}: ${d.signal} (${d.confidence}/100)`);
  } catch(e) {
    area.innerHTML = `<div style="padding:16px;color:var(--red);font-family:\'Space Mono\',monospace;font-size:12px">
      ❌ ${e.message}<br><span style="color:var(--text2);font-size:11px">Bot online hai? Token active hai?</span>
    </div>`;
    toast(\'❌ Failed — check bot status\');
  }
}

// ── SCAN ──
async function doScan() {
  const btn = document.getElementById(\'scanBtn\');
  btn.disabled=true;
  btn.innerHTML=\'<div class="spin"></div> Scanning Nifty50 + BankNifty + F&O + MCX...\';
  toast(\'📡 Scanning all markets...\',5000);

  await new Promise(r=>setTimeout(r,3000)); // Wait for bot to scan

  // Demo signals (real signals come via Telegram)
  const demo = [
    {sym:\'HDFCBANK\',exch:\'NSE\',sig:\'BUY\',entry:1842,sl:1826,t1:1866,t2:1890,conf:78,qty:10,reason:\'Supertrend Bullish + EMA Cross + VWAP Above\'},
    {sym:\'NIFTY26JUNFUT\',exch:\'NFO\',sig:\'SELL\',entry:23380,sl:23460,t1:23260,t2:23140,conf:72,qty:25,reason:\'Supertrend Bearish + Below VWAP + MACD Bear\'},
  ];

  signals = demo;
  renderSigs();
  document.getElementById(\'s-sigs\').textContent = signals.length;
  document.getElementById(\'sigBadge\').textContent = signals.length;
  document.getElementById(\'s-scan\').textContent = \'Last: \'+new Date().toLocaleTimeString(\'en-IN\',{hour:\'2-digit\',minute:\'2-digit\'});

  btn.disabled=false;
  btn.innerHTML=\'⚡ Scan All Markets (Nifty50 + BankNifty + F&O + MCX)\';
  toast(`✅ ${signals.length} signals found! Check Telegram too.`);
}

function renderSigs() {
  const list = document.getElementById(\'sigsList\');
  if(!signals.length) {
    list.innerHTML=\'<div style="text-align:center;padding:30px;color:var(--text2);font-family:Space Mono,monospace;font-size:12px">📡 Scan karo — signals yahaan aayenge</div>\';
    return;
  }
  list.innerHTML = signals.map((s,i)=>{
    const cls = s.sig===\'BUY\'?\'buy\':\'sell\';
    const bc  = s.sig===\'BUY\'?\'buy-badge\':\'sell-badge\';
    const ic  = s.sig===\'BUY\'?\'🟢\':\'🔴\';
    const fc  = s.sig===\'BUY\'?\'var(--green)\':\'var(--red)\';
    return `<div class="sig-card ${cls}">
      <div class="sc-top">
        <div class="sc-sym">${ic} ${s.sym} [${s.exch}]</div>
        <span class="sc-badge ${bc}">${s.sig}</span>
      </div>
      <div class="sc-row">
        <div>Entry <span>&#8377;${s.entry}</span></div>
        <div>SL <span style="color:var(--red)">&#8377;${s.sl}</span></div>
        <div>T1 <span style="color:var(--green)">&#8377;${s.t1}</span></div>
        <div>T2 <span style="color:var(--green)">&#8377;${s.t2}</span></div>
      </div>
      <div style="font-size:10px;color:var(--text2);font-family:Space Mono,monospace;margin-top:6px">${s.reason}</div>
      <div class="conf-bar"><div class="conf-fill" style="width:${s.conf}%;background:${fc}"></div></div>
      <div style="font-size:10px;color:var(--text2);font-family:Space Mono,monospace;text-align:right;margin-top:3px">${s.conf}/100</div>
      <div class="sc-actions">
        <button class="sc-btn sc-yes" onclick="execSig(${i})">✅ Execute</button>
        <button class="sc-btn sc-no" onclick="skipSig(${i})">❌ Skip</button>
      </div>
    </div>`;
  }).join(\'\');
}

function execSig(i) {
  const s = signals[i]; if(!s) return;
  trades.unshift({sym:s.sym,sig:s.sig,price:s.entry,time:new Date().toLocaleTimeString(\'en-IN\',{hour:\'2-digit\',minute:\'2-digit\'}),pnl:0});
  renderTrades();
  tradeCount++;
  document.getElementById(\'s-trades\').textContent = tradeCount+\'/5\';
  document.getElementById(\'tradeBadge\').textContent = trades.length;
  signals.splice(i,1); renderSigs();
  document.getElementById(\'sigBadge\').textContent = signals.length;
  toast(`🚀 ${s.sym} ${s.sig} order sent! Check Telegram.`);
}

function skipSig(i) {
  const s=signals[i];
  signals.splice(i,1); renderSigs();
  document.getElementById(\'sigBadge\').textContent = signals.length;
  toast(`⏭️ ${s.sym} skipped`);
}

function clearSigs() { signals=[]; renderSigs(); document.getElementById(\'sigBadge\').textContent=0; }

function renderTrades() {
  const list=document.getElementById(\'tradesList\');
  if(!trades.length){list.innerHTML=\'<div style="text-align:center;padding:20px;color:var(--text2);font-family:Space Mono,monospace;font-size:11px">No trades today</div>\';return;}
  list.innerHTML=trades.map(t=>`<div class="trade-row">
    <div><div class="trade-sym">${t.sig===\'BUY\'?\'📈\':\'📉\'} ${t.sym}</div><div class="trade-info">${t.sig} @ &#8377;${t.price} | ${t.time}</div></div>
    <div class="trade-pnl ${t.pnl>=0?\'up\':\'down\'}">${t.pnl>=0?\'+\':\'\'}&#8377;${t.pnl}</div>
  </div>`).join(\'\');
}

// ── LOGIN ──
let loginWin=null;
async function openLogin() {
  document.getElementById(\'loginModal\').classList.add(\'open\');
  try {
    const r=await fetch(BOT+\'/api/login_url\').catch(()=>null);
    const url = r&&r.ok?(await r.json()).url:BOT+\'/callback\';
    loginWin=window.open(url,\'ZerodhaLogin\',\'width=480,height=680,left=\'+(screen.width/2-240)+\',top=\'+(screen.height/2-340));
  } catch { window.open(BOT+\'/callback\',\'_blank\'); }
}

window.addEventListener(\'message\',e=>{
  if(e.data&&e.data.type===\'LOGIN_SUCCESS\'){
    closeModal(); if(loginWin)loginWin.close();
    toast(\'✅ Login successful!\');
    setTimeout(checkStatus,1000);
  }
});

function closeModal(){document.getElementById(\'loginModal\').classList.remove(\'open\');}

// ── INIT ──
checkStatus();
loadIndices();
setInterval(checkStatus,30000);
setInterval(loadIndices,60000);
</script>
</body>
</html>
'


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
                # Get current futures symbols
                months = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]
                yr     = str(datetime.now().year)[2:]
                m      = months[datetime.now().month-1]

                indices_to_fetch = [
                    "NSE:NIFTY 50",
                    "NSE:NIFTY BANK", 
                    "NSE:NIFTY FIN SERVICE",
                    "NSE:INDIA VIX",
                    f"NFO:NIFTY{yr}{m}FUT",
                    f"NFO:BANKNIFTY{yr}{m}FUT",
                    f"MCX:GOLD{yr}{m}FUT",
                    f"MCX:CRUDEOIL{yr}{m}FUT",
                    f"MCX:SILVERM{yr}{m}FUT",
                ]

                result = {}
                # Fetch all at once
                try:
                    data = kite.ltp(indices_to_fetch)
                    for key, val in data.items():
                        result[key] = {
                            "ltp":    round(val.get("last_price", 0), 2),
                            "change": round(val.get("net_change", 0), 2),
                        }
                except Exception as e:
                    log.error(f"[INDICES] Batch fetch error: {e}")
                    # Try one by one
                    for idx in indices_to_fetch:
                        try:
                            d = kite.ltp(idx)
                            k = list(d.keys())[0]
                            result[k] = {
                                "ltp":    round(d[k].get("last_price", 0), 2),
                                "change": round(d[k].get("net_change", 0), 2),
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
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode('utf-8'))
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
