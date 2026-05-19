# 🤖 KITE AUTO TRADING BOT

## Strategy: VWAP + EMA(9/21) + RSI + MACD Triple Confirmation

---

## ⚙️ SETUP (Ek baar karo)

### Step 1 — Libraries install karo:
```
pip install kiteconnect pandas numpy
```

### Step 2 — kite_trading_bot.py mein fill karo:
```python
API_KEY = "zhve1lfpjxtie9rv"       # Already filled
API_SECRET = "APNA_SECRET_YAHAN"   # KiteAutoBot ka secret dalo
ACCESS_TOKEN = "DAILY_TOKEN_YAHAN" # Har roz milega
```

---

## 📅 HAR ROZ SUBAH (Market se pehle)

### Step 1 — Auth karo:
```
python daily_auth.py
```
Browser khulega → Zerodha login → Authorize → Token mil jayega!

### Step 2 — Token copy karo:
`access_token.txt` file mein token hoga — use `kite_trading_bot.py` mein paste karo

### Step 3 — Bot start karo:
```
python kite_trading_bot.py
```

---

## 🎯 STRATEGY DETAILS

### BUY Signal (Sab sath hona chahiye):
- ✅ Price VWAP ke UPAR ho
- ✅ EMA 9 ne EMA 21 ko UPAR cross kiya ho
- ✅ RSI 40-65 ke beech ho
- ✅ MACD bullish crossover

### SELL Signal (Sab sath hona chahiye):
- ✅ Price VWAP ke NEECHE ho
- ✅ EMA 9 ne EMA 21 ko NEECHE cross kiya ho
- ✅ RSI 35-60 ke beech ho
- ✅ MACD bearish crossover

---

## 🛡️ RISK MANAGEMENT

| Setting | Value |
|---------|-------|
| Max Daily Loss | ₹5,000 |
| Max Trades/Day | 10 |
| Stop Loss | Previous candle high/low |
| Trade Time | 9:30 AM - 3:00 PM |
| Square Off | 3:15 PM |
| Lots | 1-2 only |

---

## ⚠️ IMPORTANT

1. **Pehle paper trade karo** — Bot ko simulate karo real money se pehle
2. **Token daily expire hota hai** — Har subah `daily_auth.py` run karo
3. **SEBI regulation** — Static IP register karo Kite Connect profile mein
4. **Bot band karna ho** — `Ctrl+C` dabao — automatically square off ho jayega

---

## 📊 INSTRUMENTS ADD KARNA

`kite_trading_bot.py` mein ye section edit karo:
```python
INSTRUMENTS = [
    {"symbol": "NIFTY26MAYFUT", "exchange": "NFO", "lots": 1, "lot_size": 25},
    {"symbol": "BANKNIFTY26MAYFUT", "exchange": "NFO", "lots": 1, "lot_size": 15},
    {"symbol": "SILVERM26JUNFUT", "exchange": "MCX", "lots": 1, "lot_size": 30},
]
```

---

Made with ❤️ by Claude for Jatin bhai 🚀
