import os
import sqlite3
from datetime import datetime
from src.config import Config

class Database:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DB_PATH
        # Ensure parent directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initializes tables for trades, orders, and equity logs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Orders table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    type TEXT NOT NULL,
                    price REAL NOT NULL,
                    qty REAL NOT NULL,
                    filled_qty REAL DEFAULT 0,
                    status TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            # 2. Trades table (lifecycles of positions)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    entry_qty REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    exit_price REAL,
                    exit_qty REAL,
                    exit_time TEXT,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    pnl REAL,
                    pnl_pct REAL,
                    status TEXT NOT NULL, -- 'OPEN', 'CLOSED'
                    entry_order_id TEXT NOT NULL,
                    exit_order_id TEXT,
                    FOREIGN KEY (entry_order_id) REFERENCES orders (id),
                    FOREIGN KEY (exit_order_id) REFERENCES orders (id)
                )
            """)
            
            # 3. Equity logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS equity_logs (
                    timestamp TEXT PRIMARY KEY,
                    total_balance REAL NOT NULL,
                    available_balance REAL NOT NULL,
                    paper_trading INTEGER NOT NULL -- 1 for True, 0 for False
                )
            """)
            conn.commit()

    # --- Order DB Operations ---
    def insert_order(self, order_id: str, symbol: str, side: str, order_type: str, 
                     price: float, qty: float, status: str, timestamp: str, filled_qty: float = 0.0):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO orders (id, symbol, side, type, price, qty, filled_qty, status, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (order_id, symbol, side, order_type, price, qty, filled_qty, status, timestamp))
            conn.commit()

    def update_order_status(self, order_id: str, status: str, filled_qty: float = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if filled_qty is not None:
                cursor.execute("""
                    UPDATE orders SET status = ?, filled_qty = ? WHERE id = ?
                """, (status, filled_qty, order_id))
            else:
                cursor.execute("""
                    UPDATE orders SET status = ? WHERE id = ?
                """, (status, order_id))
            conn.commit()

    def get_order(self, order_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    # --- Trade DB Operations ---
    def create_trade(self, symbol: str, side: str, entry_price: float, entry_qty: float, 
                     entry_time: str, stop_loss: float, take_profit: float, entry_order_id: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trades (symbol, side, entry_price, entry_qty, entry_time, stop_loss, take_profit, status, entry_order_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
            """, (symbol, side, entry_price, entry_qty, entry_time, stop_loss, take_profit, entry_order_id))
            conn.commit()
            return cursor.lastrowid

    def close_trade(self, trade_id: int, exit_price: float, exit_qty: float, exit_time: str, exit_order_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Fetch trade entry details to calculate PnL
            cursor.execute("SELECT entry_price, entry_qty, side FROM trades WHERE id = ?", (trade_id,))
            row = cursor.fetchone()
            if not row:
                return
            
            entry_price = row['entry_price']
            side = row['side']
            
            # Compute PnL
            # PnL = (Exit Price - Entry Price) * Qty for Longs
            # For shorts, PnL = (Entry Price - Exit Price) * Qty (if support shorts later)
            if side.lower() == 'buy' or side.lower() == 'long':
                pnl = (exit_price - entry_price) * exit_qty
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100
            else: # short
                pnl = (entry_price - exit_price) * exit_qty
                pnl_pct = ((entry_price - exit_price) / entry_price) * 100
                
            cursor.execute("""
                UPDATE trades 
                SET exit_price = ?, exit_qty = ?, exit_time = ?, exit_order_id = ?, pnl = ?, pnl_pct = ?, status = 'CLOSED'
                WHERE id = ?
            """, (exit_price, exit_qty, exit_time, exit_order_id, pnl, pnl_pct, trade_id))
            conn.commit()

    def update_trade_stops(self, trade_id: int, stop_loss: float = None, take_profit: float = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if stop_loss is not None and take_profit is not None:
                cursor.execute("UPDATE trades SET stop_loss = ?, take_profit = ? WHERE id = ?", (stop_loss, take_profit, trade_id))
            elif stop_loss is not None:
                cursor.execute("UPDATE trades SET stop_loss = ? WHERE id = ?", (stop_loss, trade_id))
            elif take_profit is not None:
                cursor.execute("UPDATE trades SET take_profit = ? WHERE id = ?", (take_profit, trade_id))
            conn.commit()

    def get_open_trades(self) -> list[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE status = 'OPEN'")
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_trade_by_symbol(self, symbol: str, status: str = 'OPEN') -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE symbol = ? AND status = ? LIMIT 1", (symbol, status))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_trades(self, limit: int = 100) -> list[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades ORDER BY entry_time DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    # --- Equity DB Operations ---
    def log_equity(self, total_balance: float, available_balance: float, paper_trading: bool):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            timestamp = datetime.utcnow().isoformat()
            cursor.execute("""
                INSERT INTO equity_logs (timestamp, total_balance, available_balance, paper_trading)
                VALUES (?, ?, ?, ?)
            """, (timestamp, total_balance, available_balance, 1 if paper_trading else 0))
            conn.commit()

    def get_latest_equity(self, paper_trading: bool) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM equity_logs 
                WHERE paper_trading = ? 
                ORDER BY timestamp DESC LIMIT 1
            """, (1 if paper_trading else 0,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_daily_starting_equity(self, paper_trading: bool) -> float:
        """Gets the total equity logged at the start of the current day (UTC)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            today_start = datetime.utcnow().date().isoformat() + "T00:00:00"
            cursor.execute("""
                SELECT total_balance FROM equity_logs 
                WHERE paper_trading = ? AND timestamp >= ? 
                ORDER BY timestamp ASC LIMIT 1
            """, (1 if paper_trading else 0, today_start))
            row = cursor.fetchone()
            if row:
                return row['total_balance']
            
            # If no logs today yet, get the absolute latest logged balance
            latest = self.get_latest_equity(paper_trading)
            return latest['total_balance'] if latest else 0.0
