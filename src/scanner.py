import logging
import pandas as pd
import numpy as np
from src.config import Config
from src.exchange import ExchangeClient

logger = logging.getLogger(__name__)

class MarketScanner:
    def __init__(self, exchange_client: ExchangeClient):
        self.exchange = exchange_client

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculates Average True Range (ATR) in pure pandas/numpy."""
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1/period, adjust=False).mean()
        return atr

    def scan_markets(self) -> list[dict]:
        """
        Scans Config.SCAN_SYMBOLS for liquidity, volatility, and trend strength.
        Returns a sorted list of dictionaries representing the selected symbols.
        """
        scan_results = []
        logger.info(f"Scanning market for {len(Config.SCAN_SYMBOLS)} symbols...")

        for symbol in Config.SCAN_SYMBOLS:
            try:
                # Fetch 100 OHLCV candles (needed for EMA 50 and RSI 14 and ATR 14)
                ohlcv = self.exchange.fetch_ohlcv(symbol, Config.TIMEFRAME, limit=100)
                if not ohlcv or len(ohlcv) < 60:
                    logger.warning(f"Insufficient historical data for {symbol}.")
                    continue
                
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                
                # Calculations
                close = df['close']
                volume = df['volume']
                
                # Check basic liquidity (e.g. volume * price is the 24h/recent volume in quote asset)
                recent_close = close.iloc[-1]
                avg_volume_quote = (volume * close).tail(24).mean() # Approximate recent volume
                
                # Trend detection (EMA 20 & 50)
                ema_20 = close.ewm(span=Config.EMA_FAST_PERIOD, adjust=False).mean()
                ema_50 = close.ewm(span=Config.EMA_SLOW_PERIOD, adjust=False).mean()
                
                recent_ema_20 = ema_20.iloc[-1]
                recent_ema_50 = ema_50.iloc[-1]
                
                # Volatility (ATR %)
                atr = self.calculate_atr(df, Config.ATR_PERIOD)
                recent_atr = atr.iloc[-1]
                atr_pct = (recent_atr / recent_close) * 100
                
                # Build Scan Item
                scan_results.append({
                    'symbol': symbol,
                    'close': recent_close,
                    'ema_20': recent_ema_20,
                    'ema_50': recent_ema_50,
                    'atr': recent_atr,
                    'atr_pct': atr_pct,
                    'avg_volume_quote': avg_volume_quote,
                    'is_bullish': recent_close > recent_ema_50 and recent_ema_20 > recent_ema_50
                })
                
            except Exception as e:
                logger.error(f"Error scanning symbol {symbol}: {e}")
        
        # Filter: Must have minimum volume. Trend filter is only required for the EMA strategy.
        filtered_results = []
        for item in scan_results:
            if item['avg_volume_quote'] >= 10000:
                if Config.STRATEGY_TYPE == 'ema' and not item['is_bullish']:
                    continue
                filtered_results.append(item)
        
        # Sort results: Rank by volatility (ATR %) to prioritize active coins
        filtered_results.sort(key=lambda x: x['atr_pct'], reverse=True)
        
        logger.info(f"Scan complete. Selected {len(filtered_results)} of {len(scan_results)} symbols based on trend & volume.")
        return filtered_results
