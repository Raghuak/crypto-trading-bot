import logging
import requests
from src.config import Config

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self):
        self.enabled = Config.TELEGRAM_ENABLED
        self.token = Config.TELEGRAM_BOT_TOKEN
        self.chat_id = Config.TELEGRAM_CHAT_ID

        if self.enabled:
            if not self.token or not self.chat_id:
                logger.error("Telegram is enabled but TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing. Disabling notifications.")
                self.enabled = False
            else:
                logger.info("Telegram notification system initialized successfully.")

    def send_message(self, message: str):
        """Sends a markdown formatted message to the Telegram channel."""
        if not self.enabled:
            logger.debug(f"Telegram Notification (Disabled): {message}")
            return

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                logger.error(f"Failed to send Telegram message. Status code: {response.status_code}, Response: {response.text}")
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")

    def notify_entry(self, symbol: str, price: float, qty: float, sl: float, tp: float, rsi: float):
        """Format and send buy/entry alerts."""
        msg = (
            f"🟢 *[BUY ENTRY]*\n"
            f"**Symbol**: `{symbol}`\n"
            f"**Price**: `{price:.4f} USDT`\n"
            f"**Quantity**: `{qty:.6f}`\n"
            f"**Stop Loss**: `{sl:.4f} USDT`\n"
            f"**Take Profit**: `{tp:.4f} USDT`\n"
            f"**RSI**: `{rsi:.2f}`"
        )
        self.send_message(msg)

    def notify_exit(self, symbol: str, price: float, qty: float, pnl: float, pnl_pct: float, reason: str):
        """Format and send sell/exit alerts."""
        emoji = "🔴" if pnl < 0 else "🚀"
        msg = (
            f"{emoji} *[SELL EXIT - {reason}]*\n"
            f"**Symbol**: `{symbol}`\n"
            f"**Price**: `{price:.4f} USDT`\n"
            f"**Quantity**: `{qty:.6f}`\n"
            f"**PnL**: `{'+' if pnl >= 0 else ''}{pnl:.2f} USDT`\n"
            f"**Return**: `{'+' if pnl_pct >= 0 else ''}{pnl_pct:.2f}%`"
        )
        self.send_message(msg)

    def notify_error(self, error_msg: str):
        """Format and send error/system alert."""
        msg = (
            f"⚠️ *[SYSTEM ALERT - ERROR]*\n"
            f"**Details**: {error_msg}"
        )
        self.send_message(msg)
