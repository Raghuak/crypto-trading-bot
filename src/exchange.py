import logging
import ccxt
from src.config import Config

logger = logging.getLogger(__name__)

class ExchangeClient:
    def __init__(self):
        self.paper_trading = Config.PAPER_TRADING
        self.exchange_id = "binance"
        
        # Initialize CCXT Binance client
        options = {
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True,
                'recvWindow': 10000,
                'defaultType': 'spot',
                'fetchMarkets': ['spot']
            }
        }
        
        has_keys = (
            Config.BINANCE_API_KEY and 
            Config.BINANCE_SECRET_KEY and 
            not Config.BINANCE_API_KEY.startswith("dummy")
        )
        
        if has_keys:
            options['apiKey'] = Config.BINANCE_API_KEY
            options['secret'] = Config.BINANCE_SECRET_KEY
            
        self.client = ccxt.binance(options)
        
        self.use_testnet = Config.BINANCE_USE_TESTNET
        
        if self.use_testnet:
            if has_keys:
                try:
                    self.client.set_sandbox_mode(True)
                    logger.info("CCXT Binance Client initialized in Sandbox/Testnet Mode.")
                except Exception as e:
                    logger.warning(f"Failed to enable CCXT sandbox mode: {e}. Defaulting to live endpoints.")
            else:
                logger.error("BINANCE_USE_TESTNET is True but valid API keys are missing. Cannot connect to Sandbox.")
        else:
            if self.paper_trading:
                logger.info("CCXT Binance Client initialized in Live Read-Only mode for local Paper Trading Simulation.")
            else:
                logger.info("CCXT Binance Client initialized in LIVE Trading Mode! Exercise caution.")
                
        # Load time difference after client setup is complete (handles sandbox endpoint correctly)
        if has_keys:
            try:
                self.client.load_time_difference()
            except Exception as e:
                logger.warning(f"Failed to synchronize CCXT time difference during startup: {e}")

    def _execute_request(self, func, *args, **kwargs):
        """Helper to execute CCXT client calls with auto time-drift adjustment on -1021 error."""
        try:
            return func(*args, **kwargs)
        except ccxt.ExchangeError as e:
            err_msg = str(e)
            if "-1021" in err_msg or "Timestamp for this request was 1000ms ahead" in err_msg:
                logger.warning("Binance time drift (-1021) detected. Re-syncing CCXT time offset...")
                try:
                    self.client.load_time_difference()
                    # Retry the call once with the new time offset
                    return func(*args, **kwargs)
                except Exception as sync_err:
                    logger.error(f"Failed to synchronize CCXT time difference: {sync_err}")
            raise e

    def fetch_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 100) -> list:
        """Fetches historical candlestick data (OHLCV)."""
        try:
            ohlcv = self.client.fetch_ohlcv(symbol, timeframe, limit=limit)
            return ohlcv
        except ccxt.NetworkError as e:
            logger.warning(f"Network error fetching OHLCV for {symbol}: {e}")
        except ccxt.ExchangeError as e:
            logger.error(f"Exchange error fetching OHLCV for {symbol}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching OHLCV for {symbol}: {e}")
        return []

    def fetch_ticker(self, symbol: str) -> dict:
        """Fetches the current ticker (last price, bid, ask)."""
        try:
            ticker = self.client.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            return {}

    def fetch_balance(self) -> dict:
        """Fetches the account balances."""
        if self.paper_trading and (not Config.BINANCE_API_KEY or Config.BINANCE_API_KEY.startswith("dummy")):
            # If using local paper trading, return dummy virtual balance (handled in orchestrator)
            return {"free": {"USDT": 10000.0}, "total": {"USDT": 10000.0}}
        try:
            balance = self._execute_request(self.client.fetch_balance)
            return balance
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            raise e

    def create_order(self, symbol: str, order_type: str, side: str, amount: float, price: float = None, params: dict = None) -> dict:
        """Places an order. Intercepted if in local paper trading mode."""
        params = params or {}
        try:
            if order_type.lower() == 'limit':
                order = self._execute_request(self.client.create_order, symbol, order_type, side, amount, price, params)
            else:
                order = self._execute_request(self.client.create_order, symbol, order_type, side, amount, None, params)
            return order
        except ccxt.InsufficientFunds as e:
            logger.error(f"Insufficient funds placing {side} order for {symbol}: {e}")
            raise e
        except Exception as e:
            logger.error(f"Error placing {side} order for {symbol}: {e}")
            raise e

    def cancel_order(self, order_id: str, symbol: str) -> dict:
        """Cancels an existing open order."""
        try:
            return self._execute_request(self.client.cancel_order, order_id, symbol)
        except Exception as e:
            logger.error(f"Error canceling order {order_id} for {symbol}: {e}")
            raise e

    def fetch_order(self, order_id: str, symbol: str) -> dict:
        """Fetches status of a specific order."""
        try:
            return self._execute_request(self.client.fetch_order, order_id, symbol)
        except Exception as e:
            logger.error(f"Error fetching order {order_id} for {symbol}: {e}")
            raise e
            
    def get_load_markets(self) -> dict:
        """Loads all exchange markets."""
        try:
            return self.client.load_markets()
        except Exception as e:
            logger.error(f"Error loading markets: {e}")
            return {}
