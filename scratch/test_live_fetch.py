import ccxt
import traceback
from datetime import datetime, timedelta

try:
    print("Initializing ccxt.binance...")
    exchange = ccxt.binance({'enableRateLimit': True})
    
    print("Fetching ohlcv...")
    start_time = datetime.utcnow() - timedelta(days=2)
    since = int(start_time.timestamp() * 1000)
    
    chunk = exchange.fetch_ohlcv("BTC/USDT", "5m", since=since, limit=10)
    print(f"Success! Fetched {len(chunk)} candles.")
    if chunk:
        print("Earliest timestamp:", chunk[0][0])
except Exception as e:
    print("Error:")
    traceback.print_exc()
