import os
import sys
import ccxt
from pathlib import Path
from dotenv import load_dotenv

# Set up paths
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

def verify_binance_connection():
    api_key = os.getenv("BINANCE_API_KEY", "")
    secret_key = os.getenv("BINANCE_SECRET_KEY", "")
    paper_trading = os.getenv("PAPER_TRADING", "True").lower() in ("true", "1", "yes")

    print("="*60)
    print(" [SEARCH] BINANCE API CONNECTION VERIFIER ")
    print("="*60)
    print(f"Paper Trading Mode:  {paper_trading}")
    print(f"API Key Found:       {'Yes (Censored)' if api_key and not api_key.startswith('dummy') else 'No (or Dummy)'}")
    print(f"API Secret Found:    {'Yes (Censored)' if secret_key and not secret_key.startswith('dummy') else 'No (or Dummy)'}")
    print("-"*60)

    if not api_key or api_key.startswith("dummy") or not secret_key or secret_key.startswith("dummy"):
        print("[ERROR] Valid Binance API credentials not found in .env file.")
        print("Please replace the dummy key and secret with your actual keys.")
        print("="*60)
        return

    # Initialize CCXT Binance client
    options = {
        'apiKey': api_key,
        'secret': secret_key,
        'enableRateLimit': True,
        'options': {
            'adjustForTimeDifference': True,
            'defaultType': 'spot',
            'fetchMarkets': ['spot']
        }
    }
    
    exchange = ccxt.binance(options)
    
    use_testnet = os.getenv("BINANCE_USE_TESTNET", "False").lower() in ("true", "1", "yes")
    
    if use_testnet:
        try:
            exchange.set_sandbox_mode(True)
            print("Mode: CCXT Sandbox/Testnet API")
        except Exception as e:
            print(f"[WARNING] Could not enable sandbox mode on CCXT: {e}")
            print("Will attempt connection to live exchange endpoint.")
    else:
        if paper_trading:
            print("Mode: LIVE Exchange API (Local Paper Trading Simulation)")
        else:
            print("Mode: LIVE Exchange API (LIVE Real Trades - Exercise extreme caution!)")

    print("\nAttempting connection to Binance API...")
    
    try:
        # 1. Test public market data fetch
        ticker = exchange.fetch_ticker('BTC/USDT')
        print(f"[SUCCESS] Fetched BTC/USDT price from Binance: {ticker['last']:.2f} USDT")
        
        # 2. Test private account data fetch (verifies API key signatures)
        balance = exchange.fetch_balance()
        print("[SUCCESS] Authenticated with private account API keys.")
        
        print("\nAccount Balances:")
        has_assets = False
        if 'total' in balance:
            for asset, total in balance['total'].items():
                if total > 0:
                    free = balance['free'].get(asset, 0.0)
                    # Clean asset name of any Unicode characters to prevent CP1252 print crashes
                    asset_clean = str(asset).encode('ascii', 'ignore').decode('ascii')
                    if not asset_clean:
                        asset_clean = "UNKNOWN"
                    print(f"  * {asset_clean}: Total = {total:.6f} | Available = {free:.6f}")
                    has_assets = True
        
        if not has_assets:
            print("  (Account balance is empty or 0 for all assets)")
            if use_testnet:
                print("  [TIP] You can get free virtual USDT/BTC for paper trading on the Binance Spot Testnet page.")
                
        print("\n[OK] Connection Verification SUCCESSFUL! You are ready to start the bot.")
        
    except ccxt.AuthenticationError as e:
        print(f"[ERROR] Authentication Error: Invalid API keys or signature: {e}")
        print("Double-check that your keys are copied correctly and have proper permissions.")
    except ccxt.PermissionDenied as e:
        print(f"[ERROR] Permission Denied: Your API key does not have permission to access this resource: {e}")
        print("Make sure Spot trading permissions are enabled on your API key.")
    except Exception as e:
        print(f"[ERROR] Connection Failed: {e}")
        
    print("="*60)

if __name__ == "__main__":
    verify_binance_connection()
