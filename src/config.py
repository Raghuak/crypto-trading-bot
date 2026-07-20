import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

class Config:
    # Bot Mode
    PAPER_TRADING: bool = os.getenv("PAPER_TRADING", "True").lower() in ("true", "1", "yes")
    DB_PATH: str = os.getenv("DB_PATH", "data/trading_bot.db")
    WEB_PORT: int = int(os.getenv("WEB_PORT", "9090"))
    WEB_HOST: str = os.getenv("WEB_HOST", "127.0.0.1")
    
    # Binance API Keys
    BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
    BINANCE_SECRET_KEY: str = os.getenv("BINANCE_SECRET_KEY", "")
    BINANCE_USE_TESTNET: bool = os.getenv("BINANCE_USE_TESTNET", "False").lower() in ("true", "1", "yes")
    
    # Telegram Notifications
    TELEGRAM_ENABLED: bool = os.getenv("TELEGRAM_ENABLED", "False").lower() in ("true", "1", "yes")
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    
    # Risk Management
    RISK_PER_TRADE_PCT: float = float(os.getenv("RISK_PER_TRADE_PCT", "1.0"))
    MAX_CONCURRENT_TRADES: int = int(os.getenv("MAX_CONCURRENT_TRADES", "3"))
    DAILY_DRAWDOWN_LIMIT_PCT: float = float(os.getenv("DAILY_DRAWDOWN_LIMIT_PCT", "5.0"))
    DEFAULT_LEVERAGE: int = int(os.getenv("DEFAULT_LEVERAGE", "1"))
    
    # Strategy Configuration
    STRATEGY_TYPE: str = os.getenv("STRATEGY_TYPE", "ema")
    TIMEFRAME: str = os.getenv("TIMEFRAME", "1h")
    SCAN_SYMBOLS: list[str] = [s.strip() for s in os.getenv("SCAN_SYMBOLS", "BTC/USDT,ETH/USDT").split(",") if s.strip()]
    EMA_FAST_PERIOD: int = int(os.getenv("EMA_FAST_PERIOD", "20"))
    EMA_SLOW_PERIOD: int = int(os.getenv("EMA_SLOW_PERIOD", "50"))
    RSI_PERIOD: int = int(os.getenv("RSI_PERIOD", "14"))
    RSI_MIN_MOMENTUM: int = int(os.getenv("RSI_MIN_MOMENTUM", "50"))
    RSI_MAX_MOMENTUM: int = int(os.getenv("RSI_MAX_MOMENTUM", "65"))
    ATR_PERIOD: int = int(os.getenv("ATR_PERIOD", "14"))
    ATR_MULTIPLIER_SL: float = float(os.getenv("ATR_MULTIPLIER_SL", "1.5"))
    ATR_MULTIPLIER_TP: float = float(os.getenv("ATR_MULTIPLIER_TP", "3.0"))
    
    # Gated Cipher B Safety Filters (defaulted to False to increase trade frequency)
    ENABLE_BTC_TREND_FILTER: bool = os.getenv("ENABLE_BTC_TREND_FILTER", "False").lower() in ("true", "1", "yes")
    ENABLE_ALT_TREND_FILTER: bool = os.getenv("ENABLE_ALT_TREND_FILTER", "False").lower() in ("true", "1", "yes")

    @classmethod
    def validate(cls) -> bool:
        """Simple checks to ensure API credentials exist if paper trading is disabled."""
        if not cls.PAPER_TRADING:
            if not cls.BINANCE_API_KEY or cls.BINANCE_API_KEY.startswith("dummy"):
                return False
            if not cls.BINANCE_SECRET_KEY or cls.BINANCE_SECRET_KEY.startswith("dummy"):
                return False
        return True
