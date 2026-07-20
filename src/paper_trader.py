import logging
from datetime import datetime
from src.config import Config
from src.database import Database
from src.exchange import ExchangeClient
from src.execution import ExecutionEngine

logger = logging.getLogger(__name__)

class PositionManager:
    def __init__(self, db: Database, exchange_client: ExchangeClient, execution_engine: ExecutionEngine):
        self.db = db
        self.exchange = exchange_client
        self.execution = execution_engine

    def manage_positions(self):
        """
        Monitors open positions in real-time:
        1. Checks if current price has crossed Stop Loss or Take Profit triggers.
        2. Adjusts Trailing Stop Loss levels as the market moves in our favor.
        """
        open_trades = self.db.get_open_trades()
        if not open_trades:
            return

        logger.debug(f"Position Manager: Monitoring {len(open_trades)} open positions...")

        for trade in open_trades:
            symbol = trade['symbol']
            trade_id = trade['id']
            entry_price = trade['entry_price']
            qty = trade['entry_qty']
            current_sl = trade['stop_loss']
            current_tp = trade['take_profit']
            
            try:
                # 1. Fetch current ticker price
                ticker = self.exchange.fetch_ticker(symbol)
                if not ticker or 'last' not in ticker:
                    logger.warning(f"Could not fetch ticker for {symbol}. Skipping safety check.")
                    continue
                
                last_price = ticker['last']
                bid_price = ticker.get('bid', last_price)
                ask_price = ticker.get('ask', last_price)
                
                # Check exit conditions
                # Stop Loss trigger (exits at bid price since we are selling)
                if bid_price <= current_sl:
                    logger.warning(f"[STOP LOSS TRIGGERED] Symbol: {symbol}, Price: {bid_price:.4f} <= SL: {current_sl:.4f}")
                    # Close trade at SL price (or actual market bid price for realism)
                    self.execution.execute_sell(trade_id, symbol, qty, bid_price)
                    continue

                # Take Profit trigger (exits at bid price since we are selling)
                if bid_price >= current_tp:
                    logger.info(f"[TAKE PROFIT TRIGGERED] Symbol: {symbol}, Price: {bid_price:.4f} >= TP: {current_tp:.4f}")
                    self.execution.execute_sell(trade_id, symbol, qty, bid_price)
                    continue

                # 2. Check and update trailing stop loss
                # Fetch recent candles to get the ATR for trailing calculation
                ohlcv = self.exchange.fetch_ohlcv(symbol, Config.TIMEFRAME, limit=20)
                if ohlcv and len(ohlcv) >= 15:
                    import pandas as pd
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    
                    # Calculate ATR
                    high_low = df['high'] - df['low']
                    high_close = (df['high'] - df['close'].shift(1)).abs()
                    low_close = (df['low'] - df['close'].shift(1)).abs()
                    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                    atr = tr.ewm(alpha=1/Config.ATR_PERIOD, adjust=False).mean().iloc[-1]
                    
                    # Move to break-even if price reached entry_price + 1 * ATR
                    if last_price >= entry_price + atr and current_sl < entry_price:
                        new_sl = entry_price
                        self.db.update_trade_stops(trade_id, stop_loss=new_sl)
                        logger.info(f"[BREAK-EVEN ADJUSTED] Moved Stop Loss for {symbol} to Entry Price: {new_sl:.4f}")
                        current_sl = new_sl

                    # Trail stop loss: 1.5 * ATR below the current price
                    trail_sl = last_price - (1.5 * atr)
                    if trail_sl > current_sl:
                        new_sl = round(trail_sl, 4)
                        self.db.update_trade_stops(trade_id, stop_loss=new_sl)
                        logger.info(f"[TRAILING STOP UPDATED] Moved Stop Loss for {symbol} to: {new_sl:.4f}")

            except Exception as e:
                logger.error(f"Error managing position for {symbol} (Trade ID: {trade_id}): {e}")
