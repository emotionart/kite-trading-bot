# execution.py - Order execution
from kiteconnect import KiteConnect
from broker import broker
from risk import risk
from config import *
import logging

log = logging.getLogger(__name__)

class Executor:
    def execute(self, signal_data, quantity=None):
        symbol   = signal_data["symbol"]
        exchange = signal_data["exchange"]
        action   = signal_data["signal"]
        product  = signal_data["product"]
        sl_price = signal_data["sl"]
        entry    = signal_data["entry"]

        # Calculate quantity
        if quantity is None:
            quantity = risk.calculate_quantity(symbol, exchange, entry, product)
        else:
            quantity = int(quantity) * signal_data.get("lot_size", 1)

        try:
            transaction  = KiteConnect.TRANSACTION_TYPE_BUY if action == "BUY" else KiteConnect.TRANSACTION_TYPE_SELL
            product_type = KiteConnect.PRODUCT_MIS if product == "MIS" else KiteConnect.PRODUCT_NRML

            # Get current price
            ltp = broker.get_ltp(exchange, symbol)
            if not ltp or ltp == 0:
                log.error(f"[EXEC] Cannot get LTP for {symbol}")
                return None, "LTP not available"

            price = round(ltp * 1.002, 1) if action == "BUY" else round(ltp * 0.998, 1)

            # Place main order
            order_id = broker.place_order(
                exchange, symbol,
                transaction, quantity,
                product_type, KiteConnect.ORDER_TYPE_LIMIT,
                price=price
            )

            risk.trade_count += 1
            risk.open_positions[symbol] = {
                "action": action,
                "entry": price,
                "sl": sl_price,
                "t1": signal_data["t1"],
                "t2": signal_data["t2"],
                "quantity": quantity,
                "order_id": order_id
            }

            # Place Stop Loss
            sl_transaction = KiteConnect.TRANSACTION_TYPE_SELL if action == "BUY" else KiteConnect.TRANSACTION_TYPE_BUY
            try:
                broker.place_order(
                    exchange, symbol,
                    sl_transaction, quantity,
                    product_type, KiteConnect.ORDER_TYPE_SL_M,
                    trigger_price=sl_price
                )
                log.info(f"[EXEC] SL set at {sl_price}")
            except Exception as e:
                log.error(f"[EXEC] SL failed: {e}")

            log.info(f"[EXEC] Order placed! {action} {symbol} x{quantity} @ {price}")
            return order_id, price

        except Exception as e:
            log.error(f"[EXEC] Execution failed: {e}")
            return None, str(e)

    def exit_position(self, symbol):
        """Exit a specific position"""
        if symbol not in risk.open_positions:
            return False, "No open position"

        pos = risk.open_positions[symbol]
        exit_action = "SELL" if pos["action"] == "BUY" else "BUY"

        try:
            ltp = broker.get_ltp(
                next(p["exchange"] for p in broker.get_positions().get("net", []) if p["tradingsymbol"] == symbol),
                symbol
            )
            if ltp:
                price = round(ltp * 1.002, 1) if exit_action == "BUY" else round(ltp * 0.998, 1)
                transaction = KiteConnect.TRANSACTION_TYPE_BUY if exit_action == "BUY" else KiteConnect.TRANSACTION_TYPE_SELL
                broker.place_order(
                    "NSE", symbol, transaction,
                    pos["quantity"], KiteConnect.PRODUCT_MIS,
                    KiteConnect.ORDER_TYPE_LIMIT, price=price
                )
                del risk.open_positions[symbol]
                return True, price
        except Exception as e:
            return False, str(e)

# Global executor
executor = Executor()
