import os
import sys
import pandas as pd
import numpy as np

# Set up paths
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config
from src.database import Database
from src.exchange import ExchangeClient
from src.cipher_strategy import CipherStrategy

def run_diagnose():
    print("="*80)
    print(" [DIAGNOSTIC] GATED CIPHER B STRATEGY STATE ANALYSIS ")
    print("="*80)
    
    exchange = ExchangeClient()
    strategy = CipherStrategy(exchange)
    
    # 1. Fetch BTC/USDT structure
    print("[1] Fetching BTC/USDT trend structure...")
    btc_ohlcv = exchange.fetch_ohlcv("BTC/USDT", Config.TIMEFRAME, limit=300)
    if not btc_ohlcv:
        print("[ERROR] Failed to fetch BTC/USDT data.")
        return
        
    btc_df = pd.DataFrame(btc_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    btc_close = btc_df['close'].iloc[-1]
    btc_ema_200 = btc_df['close'].ewm(span=200, adjust=False).mean().iloc[-1]
    btc_bullish = btc_close > btc_ema_200
    
    print(f"    * BTC Price: {btc_close:.2f}")
    print(f"    * BTC 200 EMA: {btc_ema_200:.2f}")
    print(f"    * BTC HTF Structure: {'BULLISH' if btc_bullish else 'BEARISH'} (Veto filter state: {'PASS' if btc_bullish else 'BLOCKED'})")
    print("-"*80)
    
    # 2. Scan all symbols
    symbols = Config.SCAN_SYMBOLS
    print(f"[2] Scanning {len(symbols)} coins on timeframe {Config.TIMEFRAME}...")
    
    print(f"{'Symbol':<10} | {'Regime':<6} | {'Price':<8} | {'200 EMA':<8} | {'WT2':<6} | {'WT X-over':<9} | {'Score':<5} | {'Decision':<5} | {'Veto/Filter Reason'}")
    print("-"*120)
    
    for symbol in symbols:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, Config.TIMEFRAME, limit=300)
            if not ohlcv:
                print(f"{symbol:<10} | Fetch failed.")
                continue
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Run indicator calculations
            wt1, wt2 = strategy.calculate_wavetrend(df)
            mfi = strategy.calculate_mfi(df)
            adx, plus_di, minus_di = strategy.calculate_adx(df)
            bb_width = strategy.calculate_bb_width(df)
            
            close = df['close'].iloc[-1]
            curr_wt1 = wt1.iloc[-1]
            curr_wt2 = wt2.iloc[-1]
            prev_wt1 = wt1.iloc[-2]
            prev_wt2 = wt2.iloc[-2]
            curr_mfi = mfi.iloc[-1]
            curr_adx = adx.iloc[-1]
            
            # Evaluate gates
            res = strategy.evaluate_gates(df, btc_df=btc_df)
            
            # Wt crossover details
            wt_crossover = (prev_wt2 <= prev_wt1) and (curr_wt2 > curr_wt1)
            
            # 200 EMA info
            ema_200 = df['close'].ewm(span=200, adjust=False).mean().iloc[-1]
            
            regime = 'TREND' if curr_adx > strategy.adx_threshold else 'RANGE'
            
            print(f"{symbol:<10} | {regime:<6} | {close:<8.4f} | {ema_200:<8.4f} | {curr_wt2:<6.1f} | {str(wt_crossover):<9} | {res['composite_score']:<5.1f} | {res['signal']:<5} | {res['reason']}")
            
        except Exception as e:
            print(f"{symbol:<10} | Error: {e}")
            
    print("="*80)

if __name__ == "__main__":
    run_diagnose()
