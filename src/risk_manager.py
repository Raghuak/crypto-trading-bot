import logging
from src.config import Config
from src.database import Database

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self, db: Database):
        self.db = db

    def calculate_stops(self, entry_price: float, atr: float) -> tuple[float, float]:
        """Calculates dynamic stop-loss and take-profit levels using ATR."""
        stop_loss = entry_price - (atr * Config.ATR_MULTIPLIER_SL)
        take_profit = entry_price + (atr * Config.ATR_MULTIPLIER_TP)
        return round(stop_loss, 4), round(take_profit, 4)

    def calculate_position_size(self, total_equity: float, available_balance: float, 
                                entry_price: float, stop_loss: float) -> float:
        """
        Calculates position size using the Fixed Fractional method:
        Risk = Equity * Risk%
        Position Size = Risk / (Entry Price - Stop Loss Price)
        """
        if entry_price <= stop_loss:
            logger.warning("Entry price is lower than or equal to stop loss. Position size cannot be calculated.")
            return 0.0

        risk_amount = total_equity * (Config.RISK_PER_TRADE_PCT / 100.0)
        risk_per_unit = entry_price - stop_loss
        
        position_qty = risk_amount / risk_per_unit
        position_cost = position_qty * entry_price
        
        # Risk control: do not allocate more than the available balance or 95% of it to account for trading fees.
        if position_cost > available_balance * 0.95:
            logger.warning(f"Calculated position cost ({position_cost:.2f} USDT) exceeds safe available balance limit. Capping to balance.")
            position_qty = (available_balance * 0.95) / entry_price
            
        # Ensure position qty is positive and non-zero
        if position_qty < 0:
            return 0.0
            
        return position_qty

    def check_portfolio_risk(self, total_equity: float) -> bool:
        """
        Checks broad portfolio safety limits:
        1. Maximum concurrent trades limit.
        2. Daily drawdown limit.
        Returns True if portfolio is safe to trade, False if blocked.
        """
        # 1. Check concurrent open trades
        open_trades = self.db.get_open_trades()
        if len(open_trades) >= Config.MAX_CONCURRENT_TRADES:
            logger.debug(f"Portfolio Risk: Max concurrent trades ({Config.MAX_CONCURRENT_TRADES}) reached. Blocking new trades.")
            return False

        # 2. Check daily drawdown
        daily_starting_equity = self.db.get_daily_starting_equity(Config.PAPER_TRADING)
        if daily_starting_equity > 0:
            drawdown_pct = ((daily_starting_equity - total_equity) / daily_starting_equity) * 100.0
            if drawdown_pct >= Config.DAILY_DRAWDOWN_LIMIT_PCT:
                logger.error(f"Portfolio Risk: Daily drawdown limit reached ({drawdown_pct:.2f}% / {Config.DAILY_DRAWDOWN_LIMIT_PCT}%). Blocked.")
                return False
                
        return True
