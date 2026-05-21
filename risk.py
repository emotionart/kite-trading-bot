# risk.py - Risk management
from broker import broker
from config import *
import logging

log = logging.getLogger(__name__)

class RiskManager:
    def __init__(self):
        self.daily_pnl   = 0
        self.trade_count = 0
        self.open_positions = {}

    def update_pnl(self):
        try:
            positions = broker.get_positions()
            self.daily_pnl = sum(pos.get("pnl", 0) for pos in positions.get("net", []))
            return self.daily_pnl
        except:
            return 0

    def is_max_loss_hit(self):
        return self.daily_pnl <= -MAX_DAILY_LOSS

    def is_max_trades_hit(self):
        return self.trade_count >= MAX_TRADES_PER_DAY

    def is_trading_time(self):
        from datetime import datetime
        now = datetime.now().strftime("%H:%M")
        return TRADE_START_TIME <= now <= TRADE_END_TIME

    def is_squareoff_time(self):
        from datetime import datetime
        now = datetime.now().strftime("%H:%M")
        return now >= SQUAREOFF_TIME

    def calculate_quantity(self, symbol, exchange, price, product="MIS"):
        """Calculate quantity based on position size"""
        if product == "NRML":
            return 1  # MCX - 1 lot
        
        # For stocks - based on STOCK_POSITION_SIZE
        if price > 0:
            qty = int(STOCK_POSITION_SIZE / price)
            return max(1, qty)
        return 1

    def squareoff_all(self):
        """Square off all open positions"""
        log.info("[RISK] Squaring off all positions...")
        try:
            from kiteconnect import KiteConnect
            positions = broker.get_positions()
            squared = 0
            for pos in positions.get("net", []):
                if pos["quantity"] != 0:
                    action = "SELL" if pos["quantity"] > 0 else "BUY"
                    product = pos["product"]
                    transaction = KiteConnect.TRANSACTION_TYPE_BUY if action == "BUY" else KiteConnect.TRANSACTION_TYPE_SELL
                    product_type = KiteConnect.PRODUCT_MIS if product == "MIS" else KiteConnect.PRODUCT_NRML

                    ltp = broker.get_ltp(pos["exchange"], pos["tradingsymbol"])
                    if ltp:
                        price = round(ltp * 1.002, 1) if action == "BUY" else round(ltp * 0.998, 1)
                        broker.place_order(
                            pos["exchange"], pos["tradingsymbol"],
                            transaction, abs(pos["quantity"]),
                            product_type, KiteConnect.ORDER_TYPE_LIMIT, price=price
                        )
                        squared += 1
            log.info(f"[RISK] Squared off {squared} positions")
            return squared
        except Exception as e:
            log.error(f"[RISK] Squareoff error: {e}")
            return 0

# Global risk manager
risk = RiskManager()
