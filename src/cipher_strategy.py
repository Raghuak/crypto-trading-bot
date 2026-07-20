import logging
import numpy as np
import pandas as pd
from src.config import Config

logger = logging.getLogger(__name__)

class CipherStrategy:
    def __init__(self, exchange_client=None):
        self.exchange = exchange_client
        # WaveTrend Parameters
        self.wt_channel_len = 10
        self.wt_avg_len = 21
        self.wt_overbought = 53
        self.wt_oversold = -45
        
        # Confirmation Parameters
        self.adx_period = 14
        self.adx_threshold = 25
        self.bb_period = 20
        self.bb_std = 2.0

    def calculate_wavetrend(self, df: pd.DataFrame) -> tuple:
        """Calculates WT1 and WT2 WaveTrend lines matching VuManChu Cipher B."""
        high, low, close = df['high'], df['low'], df['close']
        
        # Typical Price
        ap = (high + low + close) / 3.0
        
        # EMA of Typical Price
        esa = ap.ewm(span=self.wt_channel_len, adjust=False).mean()
        
        # Mean Deviation
        d = (ap - esa).abs().ewm(span=self.wt_channel_len, adjust=False).mean()
        
        # Commodity Index
        ci = (ap - esa) / (0.015 * d + 1e-10) # Avoid divide by zero
        
        # WaveTrend WT1 and WT2
        wt1 = ci.ewm(span=self.wt_avg_len, adjust=False).mean()
        wt2 = wt1.rolling(window=4).mean()
        
        return wt1, wt2

    def calculate_mfi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculates standard Money Flow Index (MFI) to represent Money Flow wave."""
        tp = (df['high'] + df['low'] + df['close']) / 3.0
        money_flow = tp * df['volume']
        
        # Shift typical price to compare with previous
        tp_shifted = tp.shift(1)
        
        pos_flow = pd.Series(0.0, index=df.index)
        neg_flow = pd.Series(0.0, index=df.index)
        
        pos_flow[tp > tp_shifted] = money_flow
        neg_flow[tp < tp_shifted] = money_flow
        
        # Sum flows over period
        pos_mf = pos_flow.rolling(window=period).sum()
        neg_mf = neg_flow.rolling(window=period).sum()
        
        mfr = pos_mf / (neg_mf + 1e-10)
        mfi = 100.0 - (100.0 / (1.0 + mfr))
        
        return mfi

    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> tuple:
        """Calculates Average Directional Index (ADX) for regime classification."""
        high, low, close = df['high'], df['low'], df['close']
        
        # UpMove and DownMove
        up_move = high.diff()
        down_move = -low.diff()
        
        # DM+ and DM-
        plus_dm = pd.Series(0.0, index=df.index)
        minus_dm = pd.Series(0.0, index=df.index)
        
        plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
        minus_dm[(down_move > up_move) & (down_move > 0)] = down_move
        
        # True Range (TR)
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Smoothed TR, DM+, DM- using Wilder's smoothing (EMA span = 2*period - 1)
        atr_span = 2 * period - 1
        tr_smooth = tr.ewm(span=atr_span, adjust=False).mean()
        plus_dm_smooth = plus_dm.ewm(span=atr_span, adjust=False).mean()
        minus_dm_smooth = minus_dm.ewm(span=atr_span, adjust=False).mean()
        
        # DI+ and DI-
        plus_di = 100.0 * (plus_dm_smooth / (tr_smooth + 1e-10))
        minus_di = 100.0 * (minus_dm_smooth / (tr_smooth + 1e-10))
        
        # DX and ADX
        dx = 100.0 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10))
        adx = dx.ewm(span=atr_span, adjust=False).mean()
        
        return adx, plus_di, minus_di

    def calculate_bb_width(self, df: pd.DataFrame) -> pd.Series:
        """Calculates Bollinger Band Width for volatility coiling detection."""
        sma = df['close'].rolling(window=self.bb_period).mean()
        std = df['close'].rolling(window=self.bb_period).std()
        
        upper_bb = sma + (self.bb_std * std)
        lower_bb = sma - (self.bb_std * std)
        
        bb_width = (upper_bb - lower_bb) / (sma + 1e-10)
        return bb_width

    def check_divergence(self, df: pd.DataFrame, wt2: pd.Series, lookback: int = 15) -> bool:
        """Checks for a bullish divergence (price lower low, WT higher low) on recent bars."""
        if len(df) < lookback + 2:
            return False
            
        # Extract slices of last N bars
        price_slice = df['close'].iloc[-lookback:].values
        wt_slice = wt2.iloc[-lookback:].values
        
        # Find local minimum index in WT
        min_wt_idx = np.argmin(wt_slice)
        if min_wt_idx == 0 or min_wt_idx == lookback - 1:
            return False # Extreme boundary not a clean pivot
            
        # Check if it was a valid local pivot (trough)
        if wt_slice[min_wt_idx] < wt_slice[min_wt_idx - 1] and wt_slice[min_wt_idx] < wt_slice[min_wt_idx + 1]:
            # First trough located. Now look back for an earlier trough that is deeper in WT but higher in price
            earlier_price_slice = df['close'].iloc[-lookback*2:-lookback].values
            earlier_wt_slice = wt2.iloc[-lookback*2:-lookback].values
            
            earlier_min_wt_idx = np.argmin(earlier_wt_slice)
            
            # Verify bullish divergence:
            # Current price low is lower than earlier price low
            # Current WT low is HIGHER than earlier WT low
            if (price_slice[min_wt_idx] < earlier_price_slice[earlier_min_wt_idx] and
                wt_slice[min_wt_idx] > earlier_wt_slice[earlier_min_wt_idx] and
                wt_slice[min_wt_idx] < self.wt_oversold):
                return True
                
        return False

    def evaluate_gates(self, df: pd.DataFrame, btc_df: pd.DataFrame = None) -> dict:
        """Evaluates all 6 Gated Confirmation Stack layers and returns final signal dict."""
        # Dynamically fetch BTC/USDT bias if self.exchange is set and btc_df is not provided
        if btc_df is None and self.exchange is not None:
            try:
                # Fetch 200 bars of BTC/USDT on the 1-hour timeframe to evaluate bias
                btc_ohlcv = self.exchange.fetch_ohlcv("BTC/USDT", "1h", limit=200)
                if btc_ohlcv:
                    btc_df = pd.DataFrame(btc_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            except Exception as e:
                logger.debug(f"Failed to fetch BTC bias dynamically: {e}")

        result = {
            'signal': 'HOLD',
            'regime': 'RANGE',
            'composite_score': 0.0,
            'price': 0.0,
            'atr': 0.0,
            'wt1': 0.0,
            'wt2': 0.0,
            'rsi': 50.0, # fallback
            'reason': ''
        }
        
        if len(df) < 100:
            result['reason'] = 'Insufficient historical data'
            return result
            
        # Calculate Indicators
        wt1, wt2 = self.calculate_wavetrend(df)
        mfi = self.calculate_mfi(df)
        adx, plus_di, minus_di = self.calculate_adx(df)
        bb_width = self.calculate_bb_width(df)
        
        # ATR for stop calculation
        high, low, close = df['high'], df['low'], df['close']
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean().iloc[-1]
        
        # Current States (latest closed candle)
        curr_price = close.iloc[-1]
        curr_wt1 = wt1.iloc[-1]
        curr_wt2 = wt2.iloc[-1]
        prev_wt1 = wt1.iloc[-2]
        prev_wt2 = wt2.iloc[-2]
        curr_mfi = mfi.iloc[-1]
        curr_adx = adx.iloc[-1]
        curr_bbw = bb_width.iloc[-1]
        
        # Populate results basic metrics
        result['price'] = curr_price
        result['atr'] = atr
        result['wt1'] = curr_wt1
        result['wt2'] = curr_wt2
        result['rsi'] = curr_mfi # map MFI to UI's RSI card
        
        # --- LAYER 1: Regime Classification ---
        # If ADX is high, it is a trending market; if low, it is a ranging market
        is_trending = curr_adx > self.adx_threshold
        result['regime'] = 'TREND' if is_trending else 'RANGE'
        
        # --- LAYER 2: HTF Bias & BTC Filter ---
        # Fetch 200 EMA of closed prices for trend bias
        ema_200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
        is_htf_bullish = True if not Config.ENABLE_ALT_TREND_FILTER else (curr_price > ema_200)
        
        # Check BTC correlation
        btc_bullish = True
        if Config.ENABLE_BTC_TREND_FILTER and btc_df is not None and len(btc_df) >= 200:
            btc_close = btc_df['close']
            btc_ema_200 = btc_close.ewm(span=200, adjust=False).mean().iloc[-1]
            btc_bullish = btc_close.iloc[-1] > btc_ema_200
            
        # Alt-Long restriction: Cannot go long on alt if BTC bias is bearish
        if Config.ENABLE_BTC_TREND_FILTER and not btc_bullish:
            result['reason'] = 'Vetoed: BTC higher timeframe structure is bearish'
            return result
            
        # --- LAYER 3: Location (Structure Check) ---
        # For trend follow, price should be near local support or pull back to 21/50 EMA zone
        ema_21 = close.ewm(span=21, adjust=False).mean().iloc[-1]
        ema_55 = close.ewm(span=55, adjust=False).mean().iloc[-1]
        
        near_value_zone = False
        if is_trending:
            # Pulled back into value zone between EMA 21 and 55
            near_value_zone = (curr_price >= ema_55 * 0.99) and (curr_price <= ema_21 * 1.01)
        else:
            # Ranging: price should be near the lower Bollinger Band
            sma = close.rolling(window=self.bb_period).mean().iloc[-1]
            std = close.rolling(window=self.bb_period).std().iloc[-1]
            lower_bb = sma - (self.bb_std * std)
            near_value_zone = curr_price <= lower_bb * 1.015 # within 1.5% of lower band
            
        # --- LAYER 4: Cipher Trigger (WaveTrend Crossover) ---
        # WT2 crossed above WT1 in the oversold zone
        wt_crossover = (prev_wt2 <= prev_wt1) and (curr_wt2 > curr_wt1)
        wt_oversold = curr_wt2 <= self.wt_oversold
        
        has_bullish_div = self.check_divergence(df, wt2)
        
        # Calculate composite score (0-100)
        score = 0.0
        if wt_crossover:
            score += 30.0 # Base trigger points
        if wt_oversold:
            score += 20.0 # Extreme oversold bonus
        if curr_mfi > 50:
            score += 15.0 # Positive money flow bonus
        if near_value_zone:
            score += 15.0 # Value zone support bonus
        if has_bullish_div:
            score += 20.0 # Strong divergence signal
            
        result['composite_score'] = score
        
        # Evaluate Final Gates
        if is_trending:
            # TREND LONG: HTF bullish, price pulled back to value zone, WT crossovers OS, Money Flow turning green
            if is_htf_bullish and wt_crossover and wt_oversold and score >= 60:
                result['signal'] = 'BUY'
                result['reason'] = 'Trend pullback long entry confirmed'
        else:
            # RANGE LONG: WT Crossover in OS area + Bullish Divergence on boundary
            if wt_crossover and wt_oversold and (has_bullish_div or score >= 70):
                result['signal'] = 'BUY'
                result['reason'] = 'Range boundary reversal long entry confirmed'
                
        return result

    def check_entry_signal(self, df: pd.DataFrame, btc_df: pd.DataFrame = None) -> dict:
        """Alias method matching StrategyEngine check_entry_signal interface."""
        return self.evaluate_gates(df, btc_df)
