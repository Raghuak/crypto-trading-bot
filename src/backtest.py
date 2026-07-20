import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

# Set up paths so we can import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config
from src.exchange import ExchangeClient
from src.strategy import StrategyEngine
from src.cipher_strategy import CipherStrategy

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

import ccxt

class HistoricalBacktester:
    def __init__(self, initial_balance: float = 10000.0):
        self.initial_balance = initial_balance
        # We use a live production client (read-only) to fetch full historical charts,
        # because the Binance Spot Testnet Sandbox database is limited to the last 3.5 days of history.
        self.exchange = ccxt.binance({'enableRateLimit': True})
        if Config.STRATEGY_TYPE == "cipher":
            self.strategy = CipherStrategy(self.exchange)
            logger.info("Backtest strategy loaded: Gated Cipher B Strategy (Running on Live Production data)")
        else:
            self.strategy = StrategyEngine()
            logger.info("Backtest strategy loaded: EMA Crossover Strategy (Running on Live Production data)")

    def run(self, symbol: str, timeframe: str = '1h', days: int = 30) -> dict:
        logger.info(f"Starting backtest for {symbol} ({timeframe}) over the last {days} days...")
        
        # Calculate limit based on days and timeframe
        # 5m: 288, 15m: 96, 1h: 24, 4h: 6
        candles_per_day = 288 if timeframe == '5m' else 96 if timeframe == '15m' else 24 if timeframe == '1h' else 6 if timeframe == '4h' else 1
        limit = candles_per_day * days
        
        # Add safety margin lookback for indicator calculation (e.g. 200 EMA needs 200 warm-up bars)
        fetch_limit = limit + 250
        
        # Fetch historical data paginated to support long backtests on small timeframes
        ohlcv = []
        # Calculate 'since' based on exchange server time to handle any local system clock drift/future offsets
        server_time = self.exchange.milliseconds()
        since = server_time - int((days + 3) * 24 * 60 * 60 * 1000)
        
        logger.info(f"Fetching historical market data for {symbol}...")
        prev_start = None
        while len(ohlcv) < fetch_limit:
            try:
                chunk = self.exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
                if not chunk:
                    break
                if prev_start is not None and chunk[0][0] == prev_start:
                    logger.warning("Exchange returned duplicate market historical chunk. Breaking fetch loop.")
                    break
                prev_start = chunk[0][0]
                ohlcv.extend(chunk)
                since = chunk[-1][0] + 1
                if len(chunk) < 1000:
                    break
            except Exception as e:
                logger.error(f"Error fetching historical chunk: {e}")
                break
        
        if not ohlcv or len(ohlcv) < 100:
            logger.error(f"Failed to fetch sufficient historical data for backtesting {symbol}.")
            return {}

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # Calculate ATR directly on the dataframe for trailing stops management
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.ewm(alpha=1 / Config.ATR_PERIOD, adjust=False).mean()
        
        # Fetch BTC/USDT 1h historical data for Gated Cipher filters (only if using CipherStrategy)
        btc_df = None
        if isinstance(self.strategy, CipherStrategy):
            logger.info("Fetching historical BTC/USDT 1h data for backtest veto filters...")
            # We fetch 1h candles covering the backtest period + safety lookback margin
            btc_candles_needed = 24 * days + 250
            # Calculate start time for BTC data based on exchange server time
            server_time = self.exchange.milliseconds()
            btc_since = server_time - int((days + 15) * 24 * 60 * 60 * 1000)
            
            btc_ohlcv = []
            btc_prev_start = None
            while len(btc_ohlcv) < btc_candles_needed:
                try:
                    chunk = self.exchange.fetch_ohlcv("BTC/USDT", "1h", since=btc_since, limit=1000)
                    if not chunk:
                        break
                    if btc_prev_start is not None and chunk[0][0] == btc_prev_start:
                        logger.warning("Exchange returned duplicate BTC historical chunk. Breaking fetch loop.")
                        break
                    btc_prev_start = chunk[0][0]
                    btc_ohlcv.extend(chunk)
                    btc_since = chunk[-1][0] + 1
                    if len(chunk) < 1000:
                        break
                except Exception as e:
                    logger.error(f"Error fetching BTC historical chunk: {e}")
                    break
            
            if btc_ohlcv:
                btc_df = pd.DataFrame(btc_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Slice to the requested backtesting period
        backtest_df = df.iloc[-limit:].reset_index(drop=True)
        
        # Simulation variables
        balance = self.initial_balance
        open_position = None # We track 1 active position per symbol for simplicity
        trades = []
        
        # Iterate candle by candle to simulate live trading environment
        for i in range(2, len(backtest_df)):
            current_row = backtest_df.iloc[i]
            prev_row = backtest_df.iloc[i-1]
            
            current_time = current_row['datetime']
            close = current_row['close']
            high = current_row['high']
            low = current_row['low']
            
            # 1. Manage active open position
            if open_position:
                # Check exit conditions inside the candle
                # Check Stop Loss first (conservative)
                if low <= open_position['stop_loss']:
                    exit_price = open_position['stop_loss']
                    pnl = (exit_price - open_position['entry_price']) * open_position['qty']
                    pnl_pct = ((exit_price - open_position['entry_price']) / open_position['entry_price']) * 100
                    balance += open_position['qty'] * exit_price
                    
                    trades.append({
                        'symbol': symbol,
                        'entry_time': open_position['entry_time'],
                        'exit_time': current_time,
                        'entry_price': open_position['entry_price'],
                        'exit_price': exit_price,
                        'qty': open_position['qty'],
                        'pnl': pnl,
                        'pnl_pct': pnl_pct,
                        'reason': 'STOP_LOSS'
                    })
                    open_position = None
                    continue
                
                # Check Take Profit
                if high >= open_position['take_profit']:
                    exit_price = open_position['take_profit']
                    pnl = (exit_price - open_position['entry_price']) * open_position['qty']
                    pnl_pct = ((exit_price - open_position['entry_price']) / open_position['entry_price']) * 100
                    balance += open_position['qty'] * exit_price
                    
                    trades.append({
                        'symbol': symbol,
                        'entry_time': open_position['entry_time'],
                        'exit_time': current_time,
                        'entry_price': open_position['entry_price'],
                        'exit_price': exit_price,
                        'qty': open_position['qty'],
                        'pnl': pnl,
                        'pnl_pct': pnl_pct,
                        'reason': 'TAKE_PROFIT'
                    })
                    open_position = None
                    continue
                
                # Dynamic trailing stop-loss implementation
                highest_since_entry = max(open_position['highest_high'], high)
                open_position['highest_high'] = highest_since_entry
                
                atr_val = current_row['atr']
                if highest_since_entry >= open_position['entry_price'] + atr_val and open_position['stop_loss'] < open_position['entry_price']:
                    open_position['stop_loss'] = open_position['entry_price']
                
                trail_sl = highest_since_entry - (1.5 * atr_val)
                if trail_sl > open_position['stop_loss']:
                    open_position['stop_loss'] = round(trail_sl, 4)
                    
            # 2. Check for entry signals if we don't have an open position
            else:
                current_df_idx = len(df) - limit + i
                sub_df = df.iloc[:current_df_idx + 1]
                
                # Sliced BTC historical data matching lookback (up to active 1h candle start)
                sliced_btc_df = None
                if btc_df is not None:
                    hour_ts = current_row['timestamp'] - (current_row['timestamp'] % 3600000)
                    sliced_btc_df = btc_df[btc_df['timestamp'] <= hour_ts].reset_index(drop=True)
                
                if isinstance(self.strategy, CipherStrategy):
                    signal_data = self.strategy.check_entry_signal(sub_df, sliced_btc_df)
                else:
                    signal_data = self.strategy.check_entry_signal(sub_df)
                
                if signal_data['signal'] == 'BUY':
                    entry_price = signal_data['price']
                    atr_val = signal_data['atr']
                    
                    # Risk calculations
                    stop_loss = entry_price - (atr_val * Config.ATR_MULTIPLIER_SL)
                    take_profit = entry_price + (atr_val * Config.ATR_MULTIPLIER_TP)
                    
                    risk_pct = Config.RISK_PER_TRADE_PCT / 100.0
                    risk_amount = balance * risk_pct
                    risk_per_unit = entry_price - stop_loss
                    
                    qty = risk_amount / risk_per_unit
                    position_cost = qty * entry_price
                    
                    # Ensure we have enough balance
                    if position_cost > balance * 0.95:
                        qty = (balance * 0.95) / entry_price
                        position_cost = qty * entry_price
                        
                    if qty > 0 and position_cost >= 10.0: # Minimum order value filter
                        balance -= position_cost
                        open_position = {
                            'symbol': symbol,
                            'entry_time': open_position['entry_time'] if open_position else current_time,
                            'entry_price': entry_price,
                            'qty': qty,
                            'stop_loss': round(stop_loss, 4),
                            'take_profit': round(take_profit, 4),
                            'highest_high': high
                        }
        
        # If position is still open at the end of backtest, force close it at the final price
        if open_position:
            final_row = backtest_df.iloc[-1]
            exit_price = final_row['close']
            pnl = (exit_price - open_position['entry_price']) * open_position['qty']
            pnl_pct = ((exit_price - open_position['entry_price']) / open_position['entry_price']) * 100
            balance += open_position['qty'] * exit_price
            trades.append({
                'symbol': symbol,
                'entry_time': open_position['entry_time'],
                'exit_time': final_row['datetime'],
                'entry_price': open_position['entry_price'],
                'exit_price': exit_price,
                'qty': open_position['qty'],
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'reason': 'FORCE_CLOSE'
            })
            
        # Calculate statistics
        pnl_df = pd.DataFrame(trades)
        stats = self.calculate_statistics(pnl_df, balance)
        
        return stats

    def calculate_statistics(self, pnl_df: pd.DataFrame, final_balance: float) -> dict:
        if pnl_df.empty:
            return {
                'total_trades': 0,
                'win_rate': 0.0,
                'net_profit': 0.0,
                'profit_factor': 0.0,
                'max_drawdown': 0.0,
                'final_balance': final_balance,
                'trades': []
            }
            
        total_trades = len(pnl_df)
        winning_trades = pnl_df[pnl_df['pnl'] > 0]
        losing_trades = pnl_df[pnl_df['pnl'] <= 0]
        
        win_rate = (len(winning_trades) / total_trades) * 100
        net_profit = final_balance - self.initial_balance
        
        gross_profit = winning_trades['pnl'].sum()
        gross_loss = abs(losing_trades['pnl'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Calculate Drawdown Curve
        equity_curve = [self.initial_balance]
        current_eq = self.initial_balance
        for _, row in pnl_df.iterrows():
            current_eq += row['pnl']
            equity_curve.append(current_eq)
            
        equity_series = pd.Series(equity_curve)
        peaks = equity_series.cummax()
        drawdowns = (equity_series - peaks) / peaks * 100
        max_drawdown = abs(drawdowns.min())
        
        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'net_profit': net_profit,
            'profit_factor': profit_factor,
            'max_drawdown': max_drawdown,
            'final_balance': final_balance,
            'trades': pnl_df.to_dict(orient='records')
        }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Backtest the Crypto Bot strategy.")
    parser.add_argument("--symbol", type=str, default="BTC/USDT", help="Crypto pair to backtest")
    parser.add_argument("--timeframe", type=str, default="5m", help="Timeframe (e.g. 5m, 15m, 1h)")
    parser.add_argument("--days", type=int, default=30, help="Number of days to backtest")
    args = parser.parse_args()

    backtester = HistoricalBacktester()
    results = backtester.run(args.symbol, args.timeframe, args.days)
    
    if results:
        print("\n" + "="*50)
        print(f" BACKTEST RESULTS: {args.symbol} ({args.timeframe}) ")
        print("="*50)
        print(f"Initial Balance:  10,000.00 USDT")
        print(f"Final Balance:    {results['final_balance']:.2f} USDT")
        print(f"Net Profit/Loss:  {results['net_profit']:.2f} USDT ({results['net_profit']/100:.2f}%)")
        print(f"Total Trades:     {results['total_trades']}")
        print(f"Win Rate:         {results['win_rate']:.2f}%")
        print(f"Profit Factor:    {results['profit_factor']:.2f}")
        print(f"Max Drawdown:     {results['max_drawdown']:.2f}%")
        print("="*50)
        
        # Display trades
        if results['trades']:
            print("\nAll Trades executed:")
            trades_df = pd.DataFrame(results['trades'])
            cols = ['entry_time', 'exit_time', 'entry_price', 'exit_price', 'pnl_pct', 'pnl', 'reason']
            print(trades_df[cols].to_string(index=False))
            print("="*50 + "\n")
