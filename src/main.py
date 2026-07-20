import os
import sys
import asyncio
import logging
from rich.live import Live

# Set up paths so we can import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config
from src.database import Database
from src.exchange import ExchangeClient
from src.scanner import MarketScanner
from src.strategy import StrategyEngine
from src.cipher_strategy import CipherStrategy
from src.risk_manager import RiskManager
from src.execution import ExecutionEngine
from src.paper_trader import PositionManager
import json
import uvicorn
from src.notifier import TelegramNotifier
from src.dashboard import CLIDashboard
from src.web_server import app, manager, get_recent_logs

# Configure logger
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, "bot.log")),
        logging.StreamHandler(sys.stdout)
    ]
)
# Suppress noisy ccxt logs
logging.getLogger("ccxt").setLevel(logging.WARNING)
logger = logging.getLogger("bot_orchestrator")

async def main():
    # 1. Initialize Core Components
    db = Database()
    exchange = ExchangeClient()
    scanner = MarketScanner(exchange)
    strategies = []
    if Config.STRATEGY_TYPE in ("ema", "both"):
        strategies.append(("EMA Crossover", StrategyEngine()))
    if Config.STRATEGY_TYPE in ("cipher", "both"):
        strategies.append(("Gated Cipher B", CipherStrategy(exchange)))
    
    logger.info(f"Loaded strategies: {[name for name, _ in strategies]}")
    risk_manager = RiskManager(db)
    execution = ExecutionEngine(exchange, db)
    position_manager = PositionManager(db, exchange, execution)
    notifier = TelegramNotifier()
    dashboard = CLIDashboard(db)

    # Attach instances to FastAPI state
    app.state.db = db
    app.state.exchange = exchange
    app.state.execution = execution

    # Start FastAPI / Uvicorn server asynchronously in the same event loop
    logger.info(f"Starting Web UI Server at http://{Config.WEB_HOST}:{Config.WEB_PORT}")
    web_config = uvicorn.Config(app, host=Config.WEB_HOST, port=Config.WEB_PORT, log_level="warning")
    web_server = uvicorn.Server(web_config)
    asyncio.create_task(web_server.serve())

    # Validate config
    if not Config.validate():
        logger.error("Configuration validation failed. Check your API credentials in .env.")
        notifier.notify_error("Configuration validation failed. API keys missing or invalid.")
        return

    # Seed initial balance log if DB is empty to construct the daily limit baselines
    initial_balance = 10000.0
    latest_eq = db.get_latest_equity(Config.PAPER_TRADING)
    if not latest_eq:
        if Config.PAPER_TRADING:
            db.log_equity(initial_balance, initial_balance, True)
        else:
            try:
                bal = exchange.fetch_balance()
                total_bal = bal['total'].get('USDT', 0.0)
                free_bal = bal['free'].get('USDT', 0.0)
                db.log_equity(total_bal, free_bal, False)
            except Exception as e:
                logger.error(f"Failed to log initial balance: {e}")

    logger.info("Trading bot orchestrator started successfully.")
    notifier.send_message("🚀 *Automated Trading Bot Started!* Monitoring market indicators and managing positions.")

    # Loop state variables
    loop_count = 0
    scan_interval_secs = 60  # Scan the market candidates every 60 seconds
    last_scan_time = 0
    watchlist = []

    # Start live terminal UI updating
    # We use rich Live console renderer
    with Live(dashboard.draw(0, 0, 0, {}), refresh_per_second=1, screen=True) as live:
        try:
            while True:
                loop_count += 1
                current_time = asyncio.get_event_loop().time()

                # A. Fetch Balances
                try:
                    balance = exchange.fetch_balance()
                    if Config.PAPER_TRADING and not exchange.use_testnet:
                        # For local simulation, calculate balance based on database trades
                        open_trades = db.get_open_trades()
                        all_trades = db.get_all_trades()
                        closed_trades = [t for t in all_trades if t['status'] == 'CLOSED']
                        
                        # Calculate closed P&L
                        closed_pnl = sum((t['pnl'] or 0.0) for t in closed_trades)
                        
                        # Fetch current prices for active symbols
                        ticker_prices = {}
                        active_symbols = list(set([t['symbol'] for t in open_trades] + Config.SCAN_SYMBOLS))
                        for sym in active_symbols:
                            try:
                                ticker = exchange.fetch_ticker(sym)
                                if ticker and 'last' in ticker:
                                    ticker_prices[sym] = ticker['last']
                            except Exception:
                                pass
                                
                        open_cost = 0.0
                        open_value = 0.0
                        for trade in open_trades:
                            sym = trade['symbol']
                            last_p = ticker_prices.get(sym, trade['entry_price'])
                            open_cost += trade['entry_price'] * trade['entry_qty']
                            open_value += last_p * trade['entry_qty']
                            
                        # Available margin: Initial Balance + Closed P&L - Cost of Open positions
                        available_balance = initial_balance + closed_pnl - open_cost
                        # Total equity: Available margin + Current value of Open positions
                        total_equity = available_balance + open_value
                    else:
                        usdt_total = balance['total'].get('USDT', 0.0)
                        bnb_total = balance['total'].get('BNB', 0.0)
                        available_balance = balance['free'].get('USDT', 0.0)
                        # Fetch price of symbols
                        ticker_prices = {}
                        open_trades = db.get_open_trades()
                        active_symbols = list(set([t['symbol'] for t in open_trades] + Config.SCAN_SYMBOLS + ['BNB/USDT']))
                        for sym in active_symbols:
                            try:
                                ticker = exchange.fetch_ticker(sym)
                                if ticker and 'last' in ticker:
                                    ticker_prices[sym] = ticker['last']
                            except Exception:
                                pass
                        
                        # Add market value of open positions to total_equity
                        open_value = 0.0
                        for trade in open_trades:
                            sym = trade['symbol']
                            last_p = ticker_prices.get(sym, trade['entry_price'])
                            open_value += last_p * trade['entry_qty']
                        
                        # Add value of BNB fee discount reserve to total_equity
                        bnb_price = ticker_prices.get('BNB/USDT', 570.0)
                        bnb_value = bnb_total * bnb_price
                        
                        total_equity = usdt_total + open_value + bnb_value
                except Exception as e:
                    logger.error(f"Error reading account balance: {e}")
                    total_equity = 10000.0
                    available_balance = 10000.0
                    ticker_prices = {}

                # B. Log equity curves periodically
                try:
                    db.log_equity(total_equity, available_balance, Config.PAPER_TRADING)
                except Exception as e:
                    logger.debug(f"Error logging equity: {e}")

                # C. Check exits and trailing stops (Real-time safety)
                position_manager.manage_positions()

                # D. Periodic Scanner Execution
                if Config.TRADING_ACTIVE and (current_time - last_scan_time >= scan_interval_secs):
                    logger.info("Executing market scanner run...")
                    watchlist = scanner.scan_markets()
                    last_scan_time = current_time

                # E. Evaluate entry signals on watch list
                for candidate in (watchlist if Config.TRADING_ACTIVE else []):
                    symbol = candidate['symbol']
                    
                    # Check if already in trade
                    existing_trade = db.get_trade_by_symbol(symbol, 'OPEN')
                    if existing_trade:
                        continue
                    
                    # Verify portfolio risk limits
                    if not risk_manager.check_portfolio_risk(total_equity):
                        break # Block further entries
                    
                    # Calculate Signal
                    try:
                        ohlcv = exchange.fetch_ohlcv(symbol, Config.TIMEFRAME, limit=100)
                        if not ohlcv:
                            continue
                        
                        import pandas as pd
                        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                        for strat_name, strat_engine in strategies:
                            signal_data = strat_engine.check_entry_signal(df)
                            
                            if signal_data['signal'] == 'BUY':
                                entry_price = signal_data['price']
                                atr_val = signal_data['atr']
                                rsi_val = signal_data['rsi']
                                
                                # Size position
                                stop_loss, take_profit = risk_manager.calculate_stops(entry_price, atr_val)
                                qty = risk_manager.calculate_position_size(total_equity, available_balance, entry_price, stop_loss)
                                
                                # Minimum cost filter (Binance minimum USDT is 10.0)
                                if qty > 0 and (qty * entry_price) >= 10.0:
                                    # Execute buy order
                                    trade_id = execution.execute_buy(symbol, qty, entry_price, stop_loss, take_profit)
                                    if trade_id:
                                        # Send notifications
                                        notifier.notify_entry(symbol, entry_price, qty, stop_loss, take_profit, rsi_val)
                                        logger.info(f"[{strat_name.upper()} TRIGGER] Entered trade for {symbol} at {entry_price:.4f}")
                                        break
                                else:
                                    logger.debug(f"[{strat_name}] Position sizing rejected entry for {symbol}: qty too small or cost below exchange minimum.")
                                
                    except Exception as e:
                        logger.error(f"Error evaluating entry for {symbol}: {e}")

                # F. Broadcast WebSocket update to browser clients
                try:
                    open_positions = []
                    for trade in db.get_open_trades():
                        sym = trade['symbol']
                        lp = ticker_prices.get(sym, trade['entry_price'])
                        upnl = (lp - trade['entry_price']) * trade['entry_qty']
                        upnl_pct = ((lp - trade['entry_price']) / trade['entry_price']) * 100
                        open_positions.append({
                            "id": trade["id"],
                            "symbol": sym,
                            "side": trade["side"],
                            "entry_price": trade["entry_price"],
                            "last_price": lp,
                            "qty": trade["entry_qty"],
                            "unrealized_pnl": round(upnl, 2),
                            "unrealized_pnl_pct": round(upnl_pct, 2),
                            "stop_loss": trade["stop_loss"],
                            "take_profit": trade["take_profit"]
                        })
                        
                    all_trades = db.get_all_trades()
                    closed_trades = [t for t in all_trades if t['status'] == 'CLOSED']
                    total_count = len(closed_trades)
                    winning_trades = [t for t in closed_trades if (t['pnl'] or 0) > 0]
                    win_rate = (len(winning_trades) / total_count * 100) if total_count > 0 else 0.0
                    total_pnl = sum((t['pnl'] or 0) for t in closed_trades)
                    
                    gross_profit = sum((t['pnl'] or 0) for t in winning_trades)
                    gross_loss = abs(sum((t['pnl'] or 0) for t in closed_trades if (t['pnl'] or 0) <= 0))
                    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0.0)
                    
                    state_update = {
                        "trading_active": Config.TRADING_ACTIVE,
                        "paper_trading": Config.PAPER_TRADING,
                        "total_equity": round(total_equity, 2),
                        "available_balance": round(available_balance, 2),
                        "metrics": {
                            "total_trades": total_count,
                            "win_rate": round(win_rate, 2),
                            "total_net_pnl": round(total_pnl, 2),
                            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else "∞"
                        },
                        "open_positions": open_positions,
                        "recent_closed_trades": [
                            {
                                "symbol": t["symbol"],
                                "entry_price": t["entry_price"],
                                "exit_price": t["exit_price"],
                                "entry_qty": t["entry_qty"],
                                "pnl": round(t["pnl"] or 0, 2),
                                "pnl_pct": round(t["pnl_pct"] or 0, 2),
                                "exit_order_id": t["exit_order_id"] or "MARKET",
                                "status": t["status"]
                            }
                        ],
                        "recent_logs": get_recent_logs(15)
                    }
                    asyncio.create_task(manager.broadcast(json.dumps(state_update)))
                except Exception as ws_err:
                    logger.debug(f"Error broadcasting state over websocket: {ws_err}")

                # G. Refresh CLI Dashboard Layout
                live.update(dashboard.draw(loop_count, available_balance, total_equity, ticker_prices))

                # G. Sleep interval
                await asyncio.sleep(5)  # 5 second tick rate

        except KeyboardInterrupt:
            logger.info("Bot execution halted by user (KeyboardInterrupt).")
            notifier.send_message("⚠️ *Trading Bot Halted*: Bot has been stopped manually.")
        except Exception as e:
            logger.critical(f"Bot execution crashed with error: {e}")
            notifier.notify_error(f"Bot crashed: {e}")
            raise e

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
