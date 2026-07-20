import os
import sys
from datetime import datetime
import ccxt

# Set up paths
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import Database
from src.exchange import ExchangeClient

def trigger_test_trade():
    print("="*60)
    print(" 🛠️ TRADING BOT TEST TRADE INJECTOR ")
    print("="*60)
    
    db = Database()
    exchange = ExchangeClient()
    
    symbol = "BTC/USDT"
    print(f"Fetching current price for {symbol}...")
    
    try:
        ticker = exchange.fetch_ticker(symbol)
        last_price = ticker.get('last')
        if not last_price:
            print("Error: Could not retrieve current price.")
            return
            
        print(f"Current BTC Price: {last_price:.2f} USDT")
        
        # Check if already in trade
        existing = db.get_trade_by_symbol(symbol, 'OPEN')
        if existing:
            print(f"You already have an active open position for {symbol}. Close it first using the Web UI.")
            print("="*60)
            return

        # Setup test parameters
        qty = 0.15 # Virtual quantity
        entry_cost = qty * last_price
        stop_loss = last_price * 0.985 # 1.5% below entry
        take_profit = last_price * 1.03 # 3% above entry
        
        print(f"\nInjecting mock trade into SQLite database:")
        print(f"  * Symbol:         {symbol}")
        print(f"  * Entry Price:    {last_price:.2f} USDT")
        print(f"  * Quantity:       {qty:.4f}")
        print(f"  * Position Cost:  {entry_cost:.2f} USDT")
        print(f"  * Stop Loss:      {stop_loss:.2f} USDT")
        print(f"  * Take Profit:    {take_profit:.2f} USDT")
        
        # Insert mock order
        order_id = "test_order_injected"
        db.insert_order(
            order_id=order_id,
            symbol=symbol,
            side='buy',
            order_type='market',
            price=last_price,
            qty=qty,
            filled_qty=qty,
            status='closed',
            timestamp=datetime.utcnow().isoformat()
        )
        
        # Insert trade
        trade_id = db.create_trade(
            symbol=symbol,
            side='long',
            entry_price=last_price,
            entry_qty=qty,
            entry_time=datetime.utcnow().isoformat(),
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_order_id=order_id
        )
        
        # Adjust simulated balance: deduct the cost from paper trading equity
        latest_eq = db.get_latest_equity(True)
        current_avail = latest_eq['available_balance'] if latest_eq else 10000.0
        current_total = latest_eq['total_balance'] if latest_eq else 10000.0
        db.log_equity(current_total, current_avail - entry_cost, True)
        
        print(f"\n[OK] Mock Trade injected successfully (Trade ID: {trade_id})!")
        print("1. Keep your bot running (`python src/main.py`).")
        print("2. Open http://localhost:9090 in your browser.")
        print("3. You should see BTC/USDT appear instantly in the 'Active Open Positions' table!")
        print("4. Watch the Unrealized P&L fluctuate live.")
        print("5. Test clicking the 'Force Close All' button in the browser to close the position.")
        
    except Exception as e:
        print(f"[ERROR] Failed to inject mock trade: {e}")
        
    print("="*60)

if __name__ == "__main__":
    trigger_test_trade()
