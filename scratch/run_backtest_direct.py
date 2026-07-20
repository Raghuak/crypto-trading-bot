import os
import sys
import traceback
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtest import HistoricalBacktester

try:
    print("Direct Diagnostic: Initializing HistoricalBacktester...", flush=True)
    tester = HistoricalBacktester()
    
    print("Direct Diagnostic: Running backtest for SOL/USDT (5m, 30 days)...", flush=True)
    
    # We call run directly and inline the printing to see where it hangs or stops
    res = tester.run("SOL/USDT", "5m", 30)
    
    print("Direct Diagnostic: Backtest run completed successfully!", flush=True)
    print("Direct Diagnostic: Result:", res, flush=True)
except Exception as e:
    print("Direct Diagnostic: CRASHED WITH EXCEPTION!", flush=True)
    traceback.print_exc(file=sys.stdout)
    sys.exit(1)
