import ccxt
import traceback

print("Testing Option 1: fetchMarkets option...")
try:
    exchange = ccxt.binance({
        'options': {
            'defaultType': 'spot',
            'fetchMarkets': ['spot']  # Only fetch spot markets
        }
    })
    exchange.set_sandbox_mode(True)
    exchange.load_markets()
    print("Option 1 SUCCESSFUL! Spot markets loaded:", len(exchange.markets))
except Exception:
    traceback.print_exc()

print("\nTesting Option 2: adjust fetch_markets list manually...")
try:
    # If the default fetch_markets crashes, we can subclass or override fetch_markets,
    # or override the api calls list in exchange.options
    # Let's inspect CCXT options for fetching markets.
    pass
except Exception:
    traceback.print_exc()
