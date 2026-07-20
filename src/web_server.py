import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import json
import os
from pathlib import Path
from src.config import Config

logger = logging.getLogger(__name__)

def get_recent_logs(limit: int = 15) -> list[str]:
    import os
    log_file = "logs/bot.log"
    if not os.path.exists(log_file):
        return []
    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            return [line.strip() for line in lines if line.strip()][-limit:]
    except Exception:
        return []

# Initialize FastAPI App
app = FastAPI(title="Autonomous Crypto Bot API")

# Add CORS Middleware to prevent local development connection issues
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active WebSocket connections list
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.debug("WebSocket client connected.")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.debug("WebSocket client disconnected.")

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.debug(f"Failed to send websocket message to a client: {e}")

manager = ConnectionManager()

# Initialize global trading active flag in Config if not already present
if not hasattr(Config, "TRADING_ACTIVE"):
    Config.TRADING_ACTIVE = True

# --- API Endpoints ---

@app.get("/api/status")
async def get_status(request: Request):
    db = request.app.state.db
    exchange = request.app.state.exchange
    
    # Query Database for trade performance
    all_trades = db.get_all_trades()
    closed_trades = [t for t in all_trades if t['status'] == 'CLOSED']
    open_trades = db.get_open_trades()
    
    total_count = len(closed_trades)
    winning_trades = [t for t in closed_trades if (t['pnl'] or 0) > 0]
    win_rate = (len(winning_trades) / total_count * 100) if total_count > 0 else 0.0
    total_pnl = sum((t['pnl'] or 0) for t in closed_trades)
    
    gross_profit = sum((t['pnl'] or 0) for t in winning_trades)
    gross_loss = abs(sum((t['pnl'] or 0) for t in closed_trades if (t['pnl'] or 0) <= 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0.0)
    
    # Retrieve total equity and available balance dynamically or from exchange
    if Config.PAPER_TRADING and not (hasattr(exchange, 'use_testnet') and exchange.use_testnet):
        initial_balance = 10000.0
        closed_pnl = sum((t['pnl'] or 0.0) for t in closed_trades)
        
        # Calculate open positions cost and current value
        open_cost = 0.0
        open_value = 0.0
        for trade in open_trades:
            symbol = trade['symbol']
            try:
                ticker = exchange.fetch_ticker(symbol)
                last_price = ticker.get('last', trade['entry_price'])
            except Exception:
                last_price = trade['entry_price']
            open_cost += trade['entry_price'] * trade['entry_qty']
            open_value += last_price * trade['entry_qty']
            
        available_balance = initial_balance + closed_pnl - open_cost
        total_equity = available_balance + open_value
    else:
        try:
            balance = exchange.fetch_balance()
            usdt_total = balance['total'].get('USDT', 0.0)
            bnb_total = balance['total'].get('BNB', 0.0)
            available_balance = balance['free'].get('USDT', 0.0)
            
            # Add market value of open positions to total_equity
            open_value = 0.0
            for trade in open_trades:
                symbol = trade['symbol']
                try:
                    ticker = exchange.fetch_ticker(symbol)
                    last_price = ticker.get('last', trade['entry_price'])
                except Exception:
                    last_price = trade['entry_price']
                open_value += last_price * trade['entry_qty']
                
            # Add value of BNB fee discount reserve to total_equity
            try:
                bnb_ticker = exchange.fetch_ticker('BNB/USDT')
                bnb_price = bnb_ticker.get('last', 570.0)
            except Exception:
                bnb_price = 570.0
            bnb_value = bnb_total * bnb_price
                
            total_equity = usdt_total + open_value + bnb_value
        except Exception:
            latest_eq = db.get_latest_equity(Config.PAPER_TRADING)
            total_equity = latest_eq['total_balance'] if latest_eq else 0.0
            available_balance = latest_eq['available_balance'] if latest_eq else 0.0

    return {
        "trading_active": Config.TRADING_ACTIVE,
        "paper_trading": Config.PAPER_TRADING,
        "db_path": Config.DB_PATH,
        "total_equity": total_equity,
        "available_balance": available_balance,
        "metrics": {
            "total_trades": total_count,
            "win_rate": round(win_rate, 2),
            "total_net_pnl": round(total_pnl, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else "∞"
        },
        "open_positions_count": len(open_trades),
        "recent_logs": get_recent_logs(15)
    }

@app.get("/api/positions")
async def get_positions(request: Request):
    db = request.app.state.db
    exchange = request.app.state.exchange
    
    open_trades = db.get_open_trades()
    positions = []
    
    for trade in open_trades:
        symbol = trade['symbol']
        entry_price = trade['entry_price']
        qty = trade['entry_qty']
        
        try:
            ticker = exchange.fetch_ticker(symbol)
            last_price = ticker.get('last', entry_price)
        except Exception:
            last_price = entry_price
            
        unrealized_pnl = (last_price - entry_price) * qty
        unrealized_pct = ((last_price - entry_price) / entry_price) * 100
        
        positions.append({
            "id": trade["id"],
            "symbol": symbol,
            "side": trade["side"],
            "entry_price": entry_price,
            "last_price": last_price,
            "qty": qty,
            "unrealized_pnl": round(unrealized_pnl, 2),
            "unrealized_pnl_pct": round(unrealized_pct, 2),
            "stop_loss": trade["stop_loss"],
            "take_profit": trade["take_profit"],
            "entry_time": trade["entry_time"]
        })
        
    return positions

@app.get("/api/trades")
async def get_trades(request: Request):
    db = request.app.state.db
    # Return last 50 trades
    return db.get_all_trades(limit=50)

# --- Action Endpoints ---

@app.post("/api/actions/toggle_trading")
async def toggle_trading():
    Config.TRADING_ACTIVE = not Config.TRADING_ACTIVE
    action = "resumed" if Config.TRADING_ACTIVE else "paused"
    logger.info(f"Bot trading execution manually {action} via Web UI.")
    return {"status": "success", "trading_active": Config.TRADING_ACTIVE, "message": f"Trading bot {action} successfully."}

@app.post("/api/actions/close_all")
async def close_all_positions(request: Request):
    db = request.app.state.db
    execution = request.app.state.execution
    exchange = request.app.state.exchange
    
    open_trades = db.get_open_trades()
    if not open_trades:
        return {"status": "success", "message": "No open positions to close."}
        
    closed_count = 0
    for trade in open_trades:
        symbol = trade['symbol']
        trade_id = trade['id']
        qty = trade['entry_qty']
        
        try:
            # Fetch last price to fill order realistically
            ticker = exchange.fetch_ticker(symbol)
            exit_price = ticker.get('last', trade['entry_price'])
            
            # Execute market sell
            success = execution.execute_sell(trade_id, symbol, qty, exit_price)
            if success:
                closed_count += 1
        except Exception as e:
            logger.error(f"Failed to manually close Trade {trade_id} via Web UI: {e}")
            
    return {"status": "success", "message": f"Successfully closed {closed_count} open positions."}

# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, listen for client messages if needed
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# --- Serve Static UI Files ---

# Create static folder directory path
STATIC_DIR = Path(__file__).resolve().parent / "static"
os.makedirs(STATIC_DIR, exist_ok=True)

# Mount static directory for JS, CSS, and Assets
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def get_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse(content="<h1>Frontend UI index.html not built yet. Proceeding with frontend generation...</h1>", status_code=200)
    
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)
