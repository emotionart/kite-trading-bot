# broker.py - Kite API connection
import threading
import http.server
import urllib.parse
import webbrowser
from kiteconnect import KiteConnect
from config import KITE_API_KEY, KITE_API_SECRET, PORT, CALLBACK_URL
import logging

log = logging.getLogger(__name__)

class Broker:
    def __init__(self):
        self.kite = KiteConnect(api_key=KITE_API_KEY)
        self.access_token = None
        self.is_authenticated = False

    def get_login_url(self):
        return self.kite.login_url()

    def generate_session(self, request_token):
        try:
            session = self.kite.generate_session(request_token, api_secret=KITE_API_SECRET)
            self.access_token = session["access_token"]
            self.kite.set_access_token(self.access_token)
            self.is_authenticated = True
            log.info("[BROKER] Authentication successful!")
            return True
        except Exception as e:
            log.error(f"[BROKER] Auth failed: {e}")
            return False

    def get_ltp(self, exchange, symbol):
        try:
            data = self.kite.ltp(f"{exchange}:{symbol}")
            return data[f"{exchange}:{symbol}"]["last_price"]
        except Exception as e:
            log.error(f"[BROKER] LTP error {symbol}: {e}")
            return None

    def get_historical_data(self, exchange, symbol, interval, from_date, to_date):
        try:
            instrument = self.kite.ltp(f"{exchange}:{symbol}")
            token = list(instrument.values())[0].get("instrument_token")
            data = self.kite.historical_data(
                token,
                from_date.strftime("%Y-%m-%d"),
                to_date.strftime("%Y-%m-%d"),
                interval
            )
            return data
        except Exception as e:
            log.error(f"[BROKER] Historical data error {symbol}: {e}")
            return None

    def get_positions(self):
        try:
            return self.kite.positions()
        except Exception as e:
            log.error(f"[BROKER] Positions error: {e}")
            return {"net": []}

    def get_margins(self):
        try:
            return self.kite.margins()
        except Exception as e:
            log.error(f"[BROKER] Margins error: {e}")
            return {}

    def place_order(self, exchange, symbol, transaction_type, quantity, product, order_type, price=None, trigger_price=None):
        try:
            params = {
                "variety": KiteConnect.VARIETY_REGULAR,
                "exchange": exchange,
                "tradingsymbol": symbol,
                "transaction_type": transaction_type,
                "quantity": quantity,
                "product": product,
                "order_type": order_type,
            }
            if price:
                params["price"] = price
            if trigger_price:
                params["trigger_price"] = trigger_price

            order_id = self.kite.place_order(**params)
            log.info(f"[BROKER] Order placed: {order_id}")
            return order_id
        except Exception as e:
            log.error(f"[BROKER] Order failed: {e}")
            raise e

# Global broker instance
broker = Broker()
