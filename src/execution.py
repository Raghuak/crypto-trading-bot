import logging
import uuid
from datetime import datetime
from src.config import Config
from src.exchange import ExchangeClient
from src.database import Database

logger = logging.getLogger(__name__)

class ExecutionEngine:
    def __init__(self, exchange_client: ExchangeClient, db: Database):
        self.exchange = exchange_client
        self.db = db
        # Check if we should run local paper trading simulation
        self.local_simulation = self.exchange.paper_trading and not self.exchange.use_testnet
        if self.local_simulation:
            logger.info("Execution Engine running in Local Simulation mode (no API keys required).")

    def _generate_mock_order(self, symbol: str, side: str, order_type: str, qty: float, price: float) -> dict:
        """Generates a mock filled order dictionary for paper trading."""
        order_id = f"mock_{uuid.uuid4().hex[:12]}"
        timestamp = datetime.utcnow().isoformat()
        return {
            'id': order_id,
            'symbol': symbol,
            'side': side,
            'type': order_type,
            'price': price,
            'amount': qty,
            'filled': qty,
            'remaining': 0.0,
            'status': 'closed',
            'timestamp': timestamp,
            'datetime': timestamp,
            'cost': qty * price
        }

    def execute_buy(self, symbol: str, qty: float, entry_price: float, stop_loss: float, take_profit: float) -> int:
        """
        Executes a buy (long entry) order.
        Saves the order and trade records to the database.
        Returns the trade ID if successful, or None.
        """
        logger.info(f"Initiating BUY order for {qty:.6f} {symbol} at {entry_price:.4f} USDT...")
        
        try:
            if self.local_simulation:
                # Local paper trading simulation
                order = self._generate_mock_order(symbol, 'buy', 'market', qty, entry_price)
            else:
                # CCXT order placement (sandbox or live)
                order = self.exchange.create_order(symbol, 'market', 'buy', qty)
                # Wait for CCXT order details to be populated
                if order.get('status') != 'closed':
                    # If market order is not instantly filled, we fetch it or assume it is filled at current price
                    order_id = order['id']
                    order = self.exchange.fetch_order(order_id, symbol)

            # Extract details
            order_id = order['id']
            fill_price = order.get('price') or entry_price
            filled_qty = order.get('filled') or qty
            status = order.get('status', 'closed')
            timestamp = order.get('datetime') or datetime.utcnow().isoformat()

            # 1. Log order to DB
            self.db.insert_order(
                order_id=order_id,
                symbol=symbol,
                side='buy',
                order_type='market',
                price=fill_price,
                qty=qty,
                filled_qty=filled_qty,
                status=status,
                timestamp=timestamp
            )

            if status.lower() in ('closed', 'filled', 'open'):
                # 2. Create trade record
                trade_id = self.db.create_trade(
                    symbol=symbol,
                    side='long',
                    entry_price=fill_price,
                    entry_qty=filled_qty,
                    entry_time=timestamp,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    entry_order_id=order_id
                )
                logger.info(f"[TRADE ENTERED] Success! Trade ID: {trade_id}. Symbol: {symbol}, Qty: {filled_qty:.6f}, Price: {fill_price:.4f}, SL: {stop_loss:.4f}, TP: {take_profit:.4f}")
                return trade_id
            else:
                logger.error(f"Buy order status was {status}, not filled. Trade not opened.")
                
        except Exception as e:
            logger.error(f"Failed to execute buy order for {symbol}: {e}")
            
        return None

    def execute_sell(self, trade_id: int, symbol: str, qty: float, exit_price: float) -> bool:
        """
        Executes a sell (long exit) order to close an open trade.
        Updates order and closes trade in the database.
        Returns True if successful, or False.
        """
        try:
            if not self.local_simulation:
                # Fetch free balance of the base currency (e.g. 'ADA' from 'ADA/USDT') to account for trading fees
                base_currency = symbol.split('/')[0]
                try:
                    balance = self.exchange.fetch_balance()
                    free_bal = balance['free'].get(base_currency, 0.0)
                    # If free balance is less than requested qty, use the free balance instead
                    if free_bal < qty:
                        logger.warning(f"Requested sell qty {qty} exceeds free balance {free_bal} of {base_currency} (due to trading fees). Adjusting sell qty to {free_bal}.")
                        qty = free_bal
                except Exception as balance_err:
                    logger.warning(f"Could not fetch base asset balance for adjustments: {balance_err}")
                
                # Format quantity to the exchange's precision requirement to avoid decimal precision rejection errors
                try:
                    qty = float(self.exchange.client.amount_to_precision(symbol, qty))
                except Exception as prec_err:
                    logger.warning(f"Could not apply precision to sell amount: {prec_err}")
        except Exception as preprocess_err:
            logger.error(f"Error preprocessing sell order quantity: {preprocess_err}")

        logger.info(f"Initiating SELL order to close Trade {trade_id} for {qty:.6f} {symbol} at {exit_price:.4f} USDT...")
        
        try:
            if self.local_simulation:
                # Local paper trading simulation
                order = self._generate_mock_order(symbol, 'sell', 'market', qty, exit_price)
            else:
                # CCXT order placement (sandbox or live)
                order = self.exchange.create_order(symbol, 'market', 'sell', qty)
                if order.get('status') != 'closed':
                    order_id = order['id']
                    order = self.exchange.fetch_order(order_id, symbol)

            # Extract details
            order_id = order['id']
            fill_price = order.get('price') or exit_price
            filled_qty = order.get('filled') or qty
            status = order.get('status', 'closed')
            timestamp = order.get('datetime') or datetime.utcnow().isoformat()

            # 1. Log order to DB
            self.db.insert_order(
                order_id=order_id,
                symbol=symbol,
                side='sell',
                order_type='market',
                price=fill_price,
                qty=qty,
                filled_qty=filled_qty,
                status=status,
                timestamp=timestamp
            )

            if status.lower() in ('closed', 'filled', 'open'):
                # 2. Close trade in DB
                self.db.close_trade(
                    trade_id=trade_id,
                    exit_price=fill_price,
                    exit_qty=filled_qty,
                    exit_time=timestamp,
                    exit_order_id=order_id
                )
                logger.info(f"[TRADE CLOSED] Success! Trade ID: {trade_id}. Closed {symbol} at {fill_price:.4f}. PnL logged.")
                return True
            else:
                logger.error(f"Sell order status was {status}, not filled. Trade remains open.")
                
        except Exception as e:
            logger.error(f"Failed to execute sell order to close Trade {trade_id}: {e}")
            
        return False
