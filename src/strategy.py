import logging
import pandas as pd
import numpy as np
from src.config import Config

logger = logging.getLogger(__name__)

class StrategyEngine:
    @staticmethod
    def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """Calculates indicators needed for strategy: EMA Fast, EMA Slow, RSI, ATR."""
        df = df.copy()
        
        # 1. EMA Calculations
        df['ema_fast'] = df['close'].ewm(span=Config.EMA_FAST_PERIOD, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=Config.EMA_SLOW_PERIOD, adjust=False).mean()
        
        # 2. RSI Calculation (TradingView/TA-Lib style)
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        # Use EWM for average gains and losses
        avg_gain = gain.ewm(com=Config.RSI_PERIOD - 1, adjust=False).mean()
        avg_loss = loss.ewm(com=Config.RSI_PERIOD - 1, adjust=False).mean()
        
        rs = avg_gain / (avg_loss + 1e-10) # Add tiny value to avoid division by zero
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 3. ATR Calculation
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        df['atr'] = tr.ewm(alpha=1 / Config.ATR_PERIOD, adjust=False).mean()
        return df

    def check_entry_signal(self, df: pd.DataFrame) -> dict:
        """
        Evaluates strategy conditions on the provided OHLCV DataFrame.
        Returns a signal dict: {'signal': 'BUY' | 'HOLD', 'price': float, 'atr': float, 'rsi': float}
        """
        if len(df) < max(Config.EMA_SLOW_PERIOD, Config.RSI_PERIOD, Config.ATR_PERIOD) + 5:
            return {'signal': 'HOLD', 'price': 0.0, 'atr': 0.0, 'rsi': 0.0}

        df_ind = self.calculate_indicators(df)
        
        # Latest values
        close = df_ind['close'].iloc[-1]
        ema_fast = df_ind['ema_fast'].iloc[-1]
        ema_slow = df_ind['ema_slow'].iloc[-1]
        rsi = df_ind['rsi'].iloc[-1]
        atr = df_ind['atr'].iloc[-1]
        
        # Previous values (for crossover detection)
        prev_ema_fast = df_ind['ema_fast'].iloc[-2]
        prev_ema_slow = df_ind['ema_slow'].iloc[-2]
        
        prev2_ema_fast = df_ind['ema_fast'].iloc[-3]
        prev2_ema_slow = df_ind['ema_slow'].iloc[-3]

        # Conditions
        # 1. Crossover: Fast EMA crossed above Slow EMA recently (current candle or last candle)
        crossover_current = (ema_fast > ema_slow) and (prev_ema_fast <= prev_ema_slow)
        crossover_previous = (prev_ema_fast > prev_ema_slow) and (prev2_ema_fast <= prev2_ema_slow)
        has_crossed = crossover_current or crossover_previous
        
        # 2. Momentum: RSI is between RSI_MIN_MOMENTUM and RSI_MAX_MOMENTUM (e.g. 50 and 65)
        # This filters out choppy markets and overbought conditions.
        rsi_valid = Config.RSI_MIN_MOMENTUM <= rsi <= Config.RSI_MAX_MOMENTUM
        
        # 3. Price confirmation: Close is above EMA Fast
        price_above_ema = close > ema_fast
        
        if has_crossed and rsi_valid and price_above_ema:
            return {
                'signal': 'BUY',
                'price': close,
                'atr': atr,
                'rsi': rsi
            }
            
        return {
            'signal': 'HOLD',
            'price': close,
            'atr': atr,
            'rsi': rsi
        }
