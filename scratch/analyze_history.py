import os
import sys
import pandas as pd
import numpy as np

# Set up paths
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config
from src.exchange import ExchangeClient
from src.cipher_strategy import CipherStrategy

def analyze_history():
    print("="*90)
    print(" [HISTORICAL DIAGNOSTIC] ANALYZING RECENT 300 BARS (25 HOURS) OF DATA ")
    print("="*90)
    
    exchange = ExchangeClient()
    strategy = CipherStrategy(exchange)
    
    # 1. Fetch BTC/USDT history for time-sync analysis
    print("Fetching BTC/USDT historical baseline...")
    btc_ohlcv = exchange.fetch_ohlcv("BTC/USDT", Config.TIMEFRAME, limit=300)
    if not btc_ohlcv:
        print("[ERROR] Failed to fetch BTC history.")
        return
    btc_df = pd.DataFrame(btc_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    # Pre-calculate BTC EMA 200 curve
    btc_df['ema_200'] = btc_df['close'].ewm(span=200, adjust=False).mean()
    btc_history_map = {row['timestamp']: (row['close'] > row['ema_200']) for _, row in btc_df.iterrows()}

    symbols = Config.SCAN_SYMBOLS
    print(f"Analyzing {len(symbols)} symbols over the last 300 candles (5m timeframe)...")
    print("-" * 120)
    
    for symbol in symbols:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, Config.TIMEFRAME, limit=300)
            if not ohlcv:
                print(f"{symbol:<10} | Failed to fetch history.")
                continue
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Calculate indicators
            wt1, wt2 = strategy.calculate_wavetrend(df)
            mfi = strategy.calculate_mfi(df)
            adx, plus_di, minus_di = strategy.calculate_adx(df)
            bb_width = strategy.calculate_bb_width(df)
            
            # Reconstruct evaluation for each candle (starting at index 50 to allow indicators to warm up)
            total_candles = len(df)
            crossover_count = 0
            oversold_crossover_count = 0
            buy_signals = 0
            
            # Track filter rejections
            veto_reasons = {
                "BTC Bearish": 0,
                "HTF Alt Bearish (Trend Mode)": 0,
                "Not in Value Zone": 0,
                "Low Composite Score": 0
            }
            
            for i in range(50, total_candles):
                # Slices up to i
                sub_df = df.iloc[:i+1]
                
                # Check WT crossover on index i
                p_wt1, p_wt2 = wt1.iloc[i-1], wt2.iloc[i-1]
                c_wt1, c_wt2 = wt1.iloc[i], wt2.iloc[i]
                
                wt_crossover = (p_wt2 <= p_wt1) and (c_wt2 > c_wt1)
                if not wt_crossover:
                    continue
                    
                crossover_count += 1
                
                # Check if oversold
                wt_oversold = c_wt2 <= strategy.wt_over_sold if hasattr(strategy, 'wt_over_sold') else c_wt2 <= strategy.wt_oversold
                if not wt_oversold:
                    continue
                    
                oversold_crossover_count += 1
                
                # We have an oversold crossover! Let's check which gates block it.
                # Re-evaluate logic for candle index i
                curr_price = df['close'].iloc[i]
                curr_adx = adx.iloc[i]
                
                is_trending = curr_adx > strategy.adx_threshold
                
                # BTC bias at timestamp
                ts = df['timestamp'].iloc[i]
                btc_bullish = btc_history_map.get(ts, True) # default to true if timestamp mismatches
                
                if not btc_bullish:
                    veto_reasons["BTC Bearish"] += 1
                    continue
                    
                # HTF Alt Bias
                ema_200_val = df['close'].iloc[:i+1].ewm(span=200, adjust=False).mean().iloc[-1]
                is_htf_bullish = curr_price > ema_200_val
                
                # Value zone Location check
                near_value_zone = False
                if is_trending:
                    ema_21 = df['close'].iloc[:i+1].ewm(span=21, adjust=False).mean().iloc[-1]
                    ema_55 = df['close'].iloc[:i+1].ewm(span=55, adjust=False).mean().iloc[-1]
                    near_value_zone = (curr_price >= ema_55 * 0.99) and (curr_price <= ema_21 * 1.01)
                else:
                    sma = df['close'].iloc[:i+1].rolling(window=strategy.bb_period).mean().iloc[-1]
                    std = df['close'].iloc[:i+1].rolling(window=strategy.bb_period).std().iloc[-1]
                    lower_bb = sma - (strategy.bb_std * std)
                    near_value_zone = curr_price <= lower_bb * 1.015
                    
                # Bullish Divergence
                has_bullish_div = strategy.check_divergence(sub_df, wt2.iloc[:i+1])
                
                # Score Calculation
                score = 30.0 # Base trigger points
                if wt_oversold:
                    score += 20.0 # Extreme oversold bonus
                if mfi.iloc[i] > 50:
                    score += 15.0 # Positive money flow bonus
                if near_value_zone:
                    score += 15.0 # Value zone support bonus
                if has_bullish_div:
                    score += 20.0 # Strong divergence signal
                
                # Check Veto gates
                if is_trending:
                    if not is_htf_bullish:
                        veto_reasons["HTF Alt Bearish (Trend Mode)"] += 1
                        continue
                    if score < 60:
                        veto_reasons["Low Composite Score"] += 1
                        continue
                    buy_signals += 1
                else:
                    # Ranging: WT Crossover in OS + (Bullish Divergence or Score >= 70)
                    if not (has_bullish_div or score >= 70):
                        if not near_value_zone:
                            veto_reasons["Not in Value Zone"] += 1
                        else:
                            veto_reasons["Low Composite Score"] += 1
                        continue
                    buy_signals += 1
            
            print(f"{symbol:<10} | WT Crossovers: {crossover_count:<3} | OS Crossovers (WT2 <= -53): {oversold_crossover_count:<3} | BUY Signals: {buy_signals:<3}")
            if oversold_crossover_count > 0:
                print(f"           -> Rejections: {dict(veto_reasons)}")
                
        except Exception as e:
            print(f"{symbol:<10} | Error: {e}")
            
    print("="*90)

if __name__ == "__main__":
    analyze_history()
