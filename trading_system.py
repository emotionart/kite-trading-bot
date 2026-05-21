# -*- coding: utf-8 -*-
"""
COMPLETE KITE TRADING SYSTEM v3
- Railway callback se auto token generate
- /analyze command
- No input() required
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os
import time
import logging
import threading
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from kiteconnect import KiteConnect
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

# ================================================================
#  CONFIG — Railway Variables se
# ================================================================
API_KEY        = os.environ.get("API_KEY",        "zhve1lfpjxtie9rv")
API_SECRET     = os.environ.get("API_SECRET",     "wr1cwi6ijdpa2phztvhbtm48z79a9jsu")
ACCESS_TOKEN   = os.environ.get("ACCESS_TOKEN",   "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8701616355:AAGvetI7MfI2f6vJh7LkeujpxHmmtB0OtXE")
CHAT_ID        = os.environ.get("CHAT_ID",        "8757681357")

MAX_DAILY_LOSS     = 10000
MAX_TRADES_PER_DAY = 5
TRADE_START_TIME   = "09:30"
TRADE_END_TIME     = "15:00"
SQUAREOFF_TIME     = "15:15"

NIFTY50_STOCKS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
    "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "TITAN",
    "SUNPHARMA", "ULTRACEMCO", "BAJFINANCE", "WIPRO", "NESTLEIND",
    "ADANIENT", "ONGC", "NTPC", "POWERGRID", "COALINDIA",
    "TATAMOTORS", "TATASTEEL", "JSWSTEEL", "HCLTECH", "TECHM"
]

MCX_INSTRUMENTS = [
    {"symbol": "SILVERM26JUNFUT",    "exchange": "MCX", "lots": 1, "lot_size": 30,   "product": "NRML"},
    {"symbol": "CRUDEOIL26JUNFUT",   "exchange": "MCX", "lots": 1, "lot_size": 100,  "product": "NRML"},
    {"symbol": "GOLD26JUNFUT",       "exchange": "MCX", "lots": 1, "lot_size": 100,  "product": "NRML"},
    {"symbol": "NATURALGAS26JUNFUT", "exchange": "MCX", "lots": 1, "lot_size": 1250, "product": "NRML"},
]

EMA_FAST = 9; EMA_SLOW = 21; RSI_PERIOD = 14
MACD_FAST = 12; MACD_SLOW = 26; MACD_SIGNAL = 9
CANDLE_INTERVAL = "5minute"

# Global kite instance
kite = KiteConnect(api_key=API_KEY)
if ACCESS_TOKEN:
    kite.set_access_token(ACCESS_TOKEN)

# ================================================================
#  LOGGING
# ================================================================
class SafeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            self.stream.write(msg + self.terminator)
            self.flush()
        except: pass

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
#  CALLBACK SERVER — Railway pe /callback handle karta hai
# ================================================================
class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global ACCESS_TOKEN, kite
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if '/callback' in self.path or '/auth' in self.path:
            request_token = params.get('request_token', [None])[0]
            if request_token:
                try:
                    session       = kite.generate_session(request_token, api_secret=API_SECRET)
                    ACCESS_TOKEN  = session['access_token']
                    kite.set_access_token(ACCESS_TOKEN)

                    log.info(f"[AUTH] New token: {ACCESS_TOKEN[:10]}...")
                    send_telegram(f"✅ <b>Auth Successful!</b>\nNew token set!\n/analyze RELIANCE try karo!")

                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(f"""<html><body style='background:#000;color:#0f0;font-family:monospace;padding:40px;text-align:center'>
<h1>✅ Authentication Successful!</h1>
<h2>Token Set! Bot chal raha hai!</h2>
<p>Telegram pe /analyze RELIANCE bhejo!</p>
<div style='background:#111;padding:15px;border:1px solid #0f0;margin:20px;font-size:12px'>
Token: {ACCESS_TOKEN[:20]}...
</div>
</body></html>""".encode())

                except Exception as e:
                    log.error(f"[AUTH ERROR] {e}")
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(f"<h1 style='color:red'>Error: {e}</h1>".encode())
            else:
                # Show login link
                login_url = kite.login_url()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(f"""<html><body style='background:#000;color:#0f0;font-family:monospace;padding:40px;text-align:center'>
<h1>🔐 Kite Auth</h1>
<a href='{login_url}' style='background:#0f0;color:#000;padding:15px 30px;font-size:18px;text-decoration:none;border-radius:5px'>
👉 Zerodha Login Karo
</a>
<p style='margin-top:20px'>Click karke login karo — token auto set ho jayega!</p>
</body></html>""".encode())
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot running!")

    def log_message(self, *args): pass

def start_callback_server():
    port   = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), CallbackHandler)
    log.info(f"[AUTH SERVER] Running on port {port}")
    server.serve_forever()

# ================================================================
#  INDICATORS
# ================================================================
def calculate_ema(prices, period):
    return pd.Series(prices).ewm(span=period, adjust=False).mean().values

def calculate_rsi(prices, period=14):
    prices = pd.Series(prices)
    delta  = prices.diff()
    gain   = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss   = -delta.where(delta < 0, 0).rolling(window=period).mean()
    return (100 - (100 / (1 + gain/loss))).values

def calculate_macd(prices, fast=12, slow=26, signal=9):
    prices      = pd.Series(prices)
    macd_line   = prices.ewm(span=fast, adjust=False).mean() - prices.ewm(span=slow, adjust=False).mean()
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line.values, signal_line.values

def calculate_vwap(df):
    typical = (df['high'] + df['low'] + df['close']) / 3
    return (typical * df['volume']).cumsum() / df['volume'].cumsum()

# ================================================================
#  /analyze COMMAND
# ================================================================
def get_current_expiry_symbol(base):
    """Auto detect current/next month futures symbol"""
    now   = datetime.now()
    # Months short codes
    months = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]
    yr     = str(now.year)[2:]  # 26
    m      = now.month - 1      # 0-indexed

    # Try current month first, then next
    for delta in [0, 1]:
        mi  = (m + delta) % 12
        yri = yr if (m + delta) < 12 else str(int(yr)+1)
        sym = f"{base}{yri}{months[mi]}FUT"
        try:
            kite.ltp(f"NFO:{sym}")
            return sym
        except:
            pass
    return f"{base}{yr}{months[m]}FUT"

# Short aliases
ALIASES = {
    "NIFTY":     ("NFO", "NIFTY"),
    "BANKNIFTY": ("NFO", "BANKNIFTY"),
    "FINNIFTY":  ("NFO", "FINNIFTY"),
    "MIDCAP":    ("NFO", "MIDCPNIFTY"),
    "GOLD":      ("MCX", "GOLD"),
    "SILVER":    ("MCX", "SILVERM"),
    "CRUDE":     ("MCX", "CRUDEOIL"),
    "NATURALGAS":("MCX", "NATURALGAS"),
}

def cmd_analyze(symbol_input):
    parts  = symbol_input.strip().upper().split()
    symbol = parts[0]
    exchange = parts[1] if len(parts) >= 2 else None

    # Auto-detect alias
    if symbol in ALIASES and "FUT" not in symbol:
        exch, base = ALIASES[symbol]
        exchange   = exch
        if exch == "NFO":
            symbol = get_current_expiry_symbol(base)
        elif exch == "MCX":
            now    = datetime.now()
            months = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]
            yr     = str(now.year)[2:]
            symbol = f"{base}{yr}{months[now.month-1]}FUT"
        send_telegram(f"ℹ️ Auto-detected: <b>{symbol} [{exchange}]</b>")
    elif not exchange:
        exchange = (
            "NFO" if any(x in symbol for x in ["NIFTY","BANKNIFTY","FINNIFTY"]) and any(x in symbol for x in ["FUT","CE","PE"]) else
            "MCX" if any(x in symbol for x in ["GOLD","SILVER","CRUDE","NATURALGAS","SILVERM"]) and "FUT" in symbol else
            "NSE"
        )

    send_telegram(f"🔍 <b>Analyzing {symbol} [{exchange}]...</b>")

    try:
        ltp_data = kite.ltp(f"{exchange}:{symbol}")
        info     = ltp_data[f"{exchange}:{symbol}"]
        token    = info["instrument_token"]

        to_date   = datetime.now()
        from_date = to_date - timedelta(days=5)
        candles   = kite.historical_data(token, from_date.strftime("%Y-%m-%d"), to_date.strftime("%Y-%m-%d"), "5minute")

        if not candles or len(candles) < 30:
            send_telegram(f"❌ {symbol} ka data nahi mila.")
            return

        df         = pd.DataFrame(candles)
        df.columns = ['date','open','high','low','close','volume']
        closes     = df['close'].values
        highs      = df['high'].values
        lows       = df['low'].values
        volumes    = df['volume'].values

        ema9        = pd.Series(closes).ewm(span=9, adjust=False).mean().values
        ema21       = pd.Series(closes).ewm(span=21, adjust=False).mean().values
        delta       = pd.Series(closes).diff()
        rsi         = (100-(100/(1+delta.where(delta>0,0).rolling(14).mean()/-delta.where(delta<0,0).rolling(14).mean()))).values
        macd_line   = (pd.Series(closes).ewm(span=12,adjust=False).mean()-pd.Series(closes).ewm(span=26,adjust=False).mean()).values
        signal_line = pd.Series(macd_line).ewm(span=9,adjust=False).mean().values
        typical     = (df['high']+df['low']+df['close'])/3
        vwap        = ((typical*df['volume']).cumsum()/df['volume'].cumsum()).values
        sma20       = pd.Series(closes).rolling(20).mean().values
        std20       = pd.Series(closes).rolling(20).std().values
        bb_upper    = sma20+2*std20
        bb_lower    = sma20-2*std20
        avg_vol     = np.mean(volumes[-20:])
        vol_spike   = volumes[-1] > avg_vol*1.5
        vol_ratio   = round(volumes[-1]/avg_vol,1)

        today    = datetime.now().date()
        today_df = df[pd.to_datetime(df['date']).dt.date == today]
        day_open = today_df.iloc[0]['open'] if len(today_df)>0 else closes[-1]
        day_high = today_df['high'].max()   if len(today_df)>0 else highs[-1]
        day_low  = today_df['low'].min()    if len(today_df)>0 else lows[-1]

        cp   = closes[-1]; cv = vwap[-1]; cr = rsi[-1]; cm = macd_line[-1]; cs = signal_line[-1]
        e9   = ema9[-1];   e21 = ema21[-1]

        eb   = (ema9[-2]<=ema21[-2]) and (ema9[-1]>ema21[-1])
        ebs  = (ema9[-2]>=ema21[-2]) and (ema9[-1]<ema21[-1])
        mb   = (macd_line[-2]<=signal_line[-2]) and (macd_line[-1]>signal_line[-1])
        mbs  = (macd_line[-2]>=signal_line[-2]) and (macd_line[-1]<signal_line[-1])
        av   = cp > cv

        bsc  = sum([av, eb or e9>e21, 40<=cr<=65, mb or cm>cs, vol_spike])*20
        ssc  = sum([not av, ebs or e9<e21, 35<=cr<=60, mbs or cm<cs, vol_spike])*20

        if bsc>=60:
            sig="🟢 BUY"; sl=round(min(lows[-3:])*0.998,2); risk=max(cp-sl,1)
            t1=round(cp+risk*1.5,2); t2=round(cp+risk*2.5,2); conf=bsc
        elif ssc>=60:
            sig="🔴 SELL"; sl=round(max(highs[-3:])*1.002,2); risk=max(sl-cp,1)
            t1=round(cp-risk*1.5,2); t2=round(cp-risk*2.5,2); conf=ssc
        else:
            sig="⚪ WAIT"; sl=round(min(lows[-3:])*0.998,2); risk=max(cp-sl,1)
            t1=round(cp+risk*1.5,2); t2=round(cp+risk*2.5,2); conf=max(bsc,ssc)

        chg     = round(((cp-day_open)/day_open)*100,2) if day_open else 0
        chg_ico = "📈" if chg>=0 else "📉"
        ema_txt = "✅ Bullish cross" if eb else "❌ Bearish cross" if ebs else "📈 EMA9>EMA21" if e9>e21 else "📉 EMA9<EMA21"
        vwap_txt= f"{'✅ Above' if av else '❌ Below'} (₹{round(cv,2)})"
        rsi_txt = f"{'🔥 Overbought' if cr>70 else '💚 Oversold' if cr<30 else '✅ Normal'} ({round(cr,1)})"
        macd_txt= f"{'✅ Bullish' if mb or cm>cs else '❌ Bearish'} ({round(cm,3)})"
        vol_txt = f"🔥 Spike! {vol_ratio}x" if vol_spike else f"😐 Normal ({vol_ratio}x)"
        bb_txt  = "⚠️ Near Upper" if cp>bb_upper[-1]*0.998 else "⚠️ Near Lower" if cp<bb_lower[-1]*1.002 else "✅ Inside Bands"

        msg = f"""<b>📊 ANALYSIS: {symbol} [{exchange}]</b>
━━━━━━━━━━━━━━━━━━━━

<b>💰 PRICE</b>
LTP:  <b>₹{round(cp,2)}</b>  {chg_ico} {chg:+.2f}%
Open: ₹{round(day_open,2)}
High: ₹{round(day_high,2)}  Low: ₹{round(day_low,2)}

<b>📐 INDICATORS (5min)</b>
EMA 9/21 : {ema_txt}
VWAP     : {vwap_txt}
RSI(14)  : {rsi_txt}
MACD     : {macd_txt}
Volume   : {vol_txt}
Bollinger: {bb_txt}

<b>🎯 SIGNAL: {sig}</b>
Confidence: {conf}/100

<b>📌 KEY LEVELS</b>
Entry  : ₹{round(cp,2)}
SL     : ₹{sl}
Target1: ₹{t1}
Target2: ₹{t2}
R:R = 1:1.5

<i>⏰ {datetime.now().strftime('%d-%b-%Y %H:%M')} | 5min</i>"""

        send_telegram(msg)

    except Exception as e:
        log.error(f"[ANALYZE] {e}")
        send_telegram(f"❌ Error: {str(e)}\n\nToken expire hua? Login karo:\nhttps://worker-production-5b28.up.railway.app/callback")

# ================================================================
#  TELEGRAM LISTENER
# ================================================================
def telegram_listener():
    log.info("[TG] Listener started!")
    railway_url = "https://worker-production-5b28.up.railway.app/callback"
    send_telegram(
        f"🤖 <b>Trading System Online! v3</b>\n\n"
        f"Token expire hone pe yahan click karo:\n{railway_url}\n\n"
        f"/analyze RELIANCE — analysis\n"
        f"/help — commands"
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
                        send_telegram("Usage:\n/analyze RELIANCE\n/analyze NIFTY26MAYFUT NFO\n/analyze GOLD26JUNFUT MCX")
                    else:
                        threading.Thread(target=cmd_analyze, args=(parts[1],), daemon=True).start()

                elif text.lower() == "/login":
                    send_telegram(f"🔐 Token refresh karne ke liye:\nhttps://worker-production-5b28.up.railway.app/callback")

                elif text.lower() == "/help":
                    send_telegram(
                        "🤖 <b>Commands:</b>\n\n"
                        "/analyze RELIANCE\n"
                        "/analyze NIFTY26MAYFUT NFO\n"
                        "/analyze GOLD26JUNFUT MCX\n"
                        "/login — token refresh link"
                    )
        except Exception as e:
            log.error(f"[TG LISTENER] {e}")
        time.sleep(1)

# ================================================================
#  INDICATORS + SIGNAL
# ================================================================
def analyze_instrument(symbol, exchange, lots=1, lot_size=1, product="MIS"):
    try:
        inst  = kite.ltp(f"{exchange}:{symbol}")
        token = list(inst.values())[0].get('instrument_token')
        to_date   = datetime.now()
        from_date = to_date - timedelta(days=5)
        data  = kite.historical_data(token, from_date.strftime("%Y-%m-%d"), to_date.strftime("%Y-%m-%d"), CANDLE_INTERVAL)
        if len(data) < 30: return None
        df         = pd.DataFrame(data)
        df.columns = ['date','open','high','low','close','volume']
        closes     = df['close'].values
        volumes    = df['volume'].values
        ema_fast   = calculate_ema(closes, EMA_FAST)
        ema_slow   = calculate_ema(closes, EMA_SLOW)
        rsi        = calculate_rsi(closes, RSI_PERIOD)
        macd_line, signal_line = calculate_macd(closes)
        vwap       = calculate_vwap(df)
        cp         = closes[-1]; cv = vwap.iloc[-1]; cr = rsi[-1]
        eb         = (ema_fast[-2]<=ema_slow[-2]) and (ema_fast[-1]>ema_slow[-1])
        ebs        = (ema_fast[-2]>=ema_slow[-2]) and (ema_fast[-1]<ema_slow[-1])
        mb         = (macd_line[-2]<=signal_line[-2]) and (macd_line[-1]>signal_line[-1])
        mbs        = (macd_line[-2]>=signal_line[-2]) and (macd_line[-1]<signal_line[-1])
        avg_vol    = np.mean(volumes[-20:])
        vol_spike  = volumes[-1] > avg_vol*1.5
        bc = {'vwap':cp>cv,'ema_cross':eb,'rsi':40<=cr<=65,'macd':mb,'volume':vol_spike}
        sc = {'vwap':cp<cv,'ema_cross':ebs,'rsi':35<=cr<=60,'macd':mbs,'volume':vol_spike}
        weights = {'vwap':25,'ema_cross':25,'rsi':20,'macd':20,'volume':10}
        bsc = sum(weights[k] for k,v in bc.items() if v)
        ssc = sum(weights[k] for k,v in sc.items() if v)
        if bsc>=70:
            sig='BUY'; sl=round(df.iloc[-2]['low']*0.998,2); risk=cp-sl
            t1=round(cp+risk*1.5,2); t2=round(cp+risk*2.5,2); conf=bsc; cond=bc
        elif ssc>=70:
            sig='SELL'; sl=round(df.iloc[-2]['high']*1.002,2); risk=sl-cp
            t1=round(cp-risk*1.5,2); t2=round(cp-risk*2.5,2); conf=ssc; cond=sc
        else: return None
        reasons = []
        if cond['vwap']:     reasons.append(f"VWAP {'above' if sig=='BUY' else 'below'} ({round(cv,2)})")
        if cond['ema_cross']: reasons.append(f"EMA {'bullish' if sig=='BUY' else 'bearish'} cross")
        if cond['rsi']:      reasons.append(f"RSI {round(cr,1)}")
        if cond['macd']:     reasons.append(f"MACD {'bullish' if sig=='BUY' else 'bearish'}")
        if cond['volume']:   reasons.append(f"Vol spike {round(volumes[-1]/avg_vol,1)}x")
        return {'symbol':symbol,'exchange':exchange,'signal':sig,'entry':round(cp,2),'sl':sl,'t1':t1,'t2':t2,
                'confidence':conf,'rr':1.5,'reason':'\n'.join([f'- {r}' for r in reasons]),
                'lots':lots,'lot_size':lot_size,'product':product,'type':'FUT'}
    except Exception as e:
        log.error(f"[ANALYZE] {symbol}: {e}")
        return None

# ================================================================
#  ORDER EXECUTOR
# ================================================================
class OrderExecutor:
    def __init__(self):
        self.daily_pnl   = 0
        self.trade_count = 0

    def get_ltp(self, exchange, symbol):
        try: return kite.ltp(f"{exchange}:{symbol}")[f"{exchange}:{symbol}"]["last_price"]
        except: return None

    def execute(self, signal_data):
        symbol=signal_data['symbol']; exchange=signal_data['exchange']
        action=signal_data['signal']; quantity=signal_data['lots']*signal_data['lot_size']
        product=signal_data['product']; sl_price=signal_data['sl']
        try:
            tx   = KiteConnect.TRANSACTION_TYPE_BUY if action=="BUY" else KiteConnect.TRANSACTION_TYPE_SELL
            pt   = KiteConnect.PRODUCT_MIS if product=="MIS" else KiteConnect.PRODUCT_NRML
            ltp  = self.get_ltp(exchange,symbol)
            if not ltp: return False
            price= round(ltp*1.002,1) if action=="BUY" else round(ltp*0.998,1)
            oid  = kite.place_order(variety=KiteConnect.VARIETY_REGULAR,exchange=exchange,
                       tradingsymbol=symbol,transaction_type=tx,quantity=quantity,
                       product=pt,order_type=KiteConnect.ORDER_TYPE_LIMIT,price=price)
            self.trade_count+=1
            sl_tx= KiteConnect.TRANSACTION_TYPE_SELL if action=="BUY" else KiteConnect.TRANSACTION_TYPE_BUY
            kite.place_order(variety=KiteConnect.VARIETY_REGULAR,exchange=exchange,
                tradingsymbol=symbol,transaction_type=sl_tx,quantity=quantity,
                product=pt,order_type=KiteConnect.ORDER_TYPE_SL_M,trigger_price=sl_price)
            send_telegram(f"✅ <b>ORDER DONE!</b>\n{action} {symbol}\nPrice:₹{price} SL:₹{sl_price}")
            return True
        except Exception as e:
            send_telegram(f"❌ Order failed: {e}")
            return False

    def square_off_all(self):
        try:
            positions=kite.positions()
            for pos in positions.get('net',[]):
                if pos['quantity']!=0:
                    action="SELL" if pos['quantity']>0 else "BUY"
                    pt=KiteConnect.PRODUCT_MIS if pos['product']=="MIS" else KiteConnect.PRODUCT_NRML
                    tx=KiteConnect.TRANSACTION_TYPE_BUY if action=="BUY" else KiteConnect.TRANSACTION_TYPE_SELL
                    ltp=self.get_ltp(pos['exchange'],pos['tradingsymbol'])
                    if ltp:
                        price=round(ltp*1.002,1) if action=="BUY" else round(ltp*0.998,1)
                        kite.place_order(variety=KiteConnect.VARIETY_REGULAR,exchange=pos['exchange'],
                            tradingsymbol=pos['tradingsymbol'],transaction_type=tx,
                            quantity=abs(pos['quantity']),product=pt,
                            order_type=KiteConnect.ORDER_TYPE_LIMIT,price=price)
            send_telegram("✅ All positions closed!")
        except Exception as e:
            log.error(f"[SQUAREOFF] {e}")

    def update_pnl(self):
        try:
            self.daily_pnl=sum(p.get('pnl',0) for p in kite.positions().get('net',[]))
            return self.daily_pnl
        except: return 0

# ================================================================
#  MAIN SYSTEM
# ================================================================
class TradingSystem:
    def __init__(self):
        self.executor      = OrderExecutor()
        self.scanned_today = set()
        log.info("="*55)
        log.info("TRADING SYSTEM v3 STARTED!")
        log.info("="*55)

        # Start callback server
        cb_thread = threading.Thread(target=start_callback_server, daemon=True)
        cb_thread.start()

        # Start telegram listener
        tg_thread = threading.Thread(target=telegram_listener, daemon=True)
        tg_thread.start()

    def run(self):
        squared_off = False
        while True:
            try:
                if not ACCESS_TOKEN:
                    log.info("[WAIT] No token — login karo: https://worker-production-5b28.up.railway.app/callback")
                    time.sleep(30)
                    continue

                now = datetime.now().strftime("%H:%M")
                pnl = self.executor.update_pnl()

                if now >= SQUAREOFF_TIME and not squared_off:
                    self.executor.square_off_all()
                    squared_off = True
                    time.sleep(3600)
                    continue

                if pnl <= -MAX_DAILY_LOSS:
                    send_telegram(f"🚨 Max loss! P&L:₹{pnl:.2f}")
                    self.executor.square_off_all()
                    break

                if self.executor.trade_count >= MAX_TRADES_PER_DAY:
                    time.sleep(3600)
                    continue

                if now < TRADE_START_TIME or now > TRADE_END_TIME:
                    time.sleep(60)
                    continue

                log.info(f"[SCAN] P&L:₹{pnl:.2f} Trades:{self.executor.trade_count}/{MAX_TRADES_PER_DAY}")
                signals = []
                for stock in NIFTY50_STOCKS:
                    if stock not in self.scanned_today:
                        r = analyze_instrument(stock,"NSE",1,1,"MIS")
                        if r: signals.append(r)
                        time.sleep(0.3)
                for inst in MCX_INSTRUMENTS:
                    r = analyze_instrument(inst['symbol'],inst['exchange'],inst['lots'],inst['lot_size'],inst['product'])
                    if r: signals.append(r)
                    time.sleep(0.3)

                signals.sort(key=lambda x:x['confidence'],reverse=True)
                signals = signals[:3]

                for signal in signals:
                    if self.executor.trade_count >= MAX_TRADES_PER_DAY: break
                    symbol = signal['symbol']
                    if symbol in self.scanned_today: continue
                    send_telegram(f"<b>SIGNAL: {signal['signal']}</b>\n{symbol}\nEntry:₹{signal['entry']}\nSL:₹{signal['sl']}\nT1:₹{signal['t1']}\nConfidence:{signal['confidence']}\n\nReply YES/NO (2 min)")
                    start = time.time(); reply = None; last_id = None
                    while time.time()-start < 120:
                        updates = tg_get_updates(last_id)
                        for u in updates:
                            last_id = u['update_id']+1
                            txt = u.get('message',{}).get('text','').upper()
                            if txt in ['YES','Y','HAN']: reply=True; break
                            elif txt in ['NO','N','NAHI']: reply=False; break
                        if reply is not None: break
                        time.sleep(2)
                    if reply is True: self.executor.execute(signal); self.scanned_today.add(symbol)
                    elif reply is False: send_telegram(f"Skipped {symbol}"); self.scanned_today.add(symbol)
                    else: send_telegram(f"Timeout — {symbol} cancelled"); self.scanned_today.add(symbol)

                time.sleep(300)

            except KeyboardInterrupt:
                self.executor.square_off_all()
                break
            except Exception as e:
                log.error(f"[ERROR] {e}")
                time.sleep(30)

if __name__ == "__main__":
    system = TradingSystem()
    system.run()
