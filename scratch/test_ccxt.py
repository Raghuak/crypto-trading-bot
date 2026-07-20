import ccxt
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("BINANCE_API_KEY")
secret_key = os.getenv("BINANCE_SECRET_KEY")

print(f"API Key: {api_key[:10]}...")
print(f"Secret:  {secret_key[:10]}...")

exchange = ccxt.binance({
    'apiKey': api_key,
    'secret': secret_key,
    'enableRateLimit': True,
    'options': {
        'adjustForTimeDifference': True,
        'defaultType': 'spot'  # explicitly force spot
    }
})

exchange.set_sandbox_mode(True)

try:
    print("Testing fetch_ticker('BTC/USDT')...")
    ticker = exchange.fetch_ticker('BTC/USDT')
    print("Success:", ticker['last'])
except Exception as e:
    import traceback
    print("Error during fetch_ticker:")
    traceback.print_exc()
