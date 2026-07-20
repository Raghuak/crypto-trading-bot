import os
import sys

# Set up paths
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import Database

def analyze_trades():
    db = Database()
    trades = db.get_all_trades(limit=100)
    
    print("="*80)
    print(" [ANALYSIS] DETAILED HISTORICAL TRADES LOG ANALYSIS ")
    print("="*80)
    print(f"Total trades logged in DB: {len(trades)}")
    print("-"*80)
    print(f"{'ID':<4} | {'Symbol':<10} | {'Side':<5} | {'Status':<7} | {'Entry':<8} | {'Exit':<8} | {'PnL %':<7} | {'PnL USDT':<8} | {'Exit Reason'}")
    print("-"*80)
    
    for t in reversed(trades):
        pnl = t['pnl'] if t['pnl'] is not None else 0.0
        pnl_pct = t['pnl_pct'] if t['pnl_pct'] is not None else 0.0
        entry = t['entry_price']
        exit_p = t['exit_price'] if t['exit_price'] is not None else 0.0
        reason = t['exit_order_id'] if t['exit_order_id'] else 'OPEN'
        
        print(f"{t['id']:<4} | {t['symbol']:<10} | {t['side']:<5} | {t['status']:<7} | {entry:<8.4f} | {exit_p:<8.4f} | {pnl_pct:<7.2f} | {pnl:<8.2f} | {reason}")
        
    print("="*80)

if __name__ == "__main__":
    analyze_trades()
