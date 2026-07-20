import os
from datetime import datetime
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.console import RenderableType
from src.config import Config
from src.database import Database

class CLIDashboard:
    def __init__(self, db: Database):
        self.db = db

    def _format_time(self, iso_str: str) -> str:
        if not iso_str:
            return "-"
        try:
            # Slices '2026-07-19T12:46:33.662000' -> '07-19 12:46'
            parts = iso_str.split('T')
            date_part = parts[0]
            time_part = parts[1]
            mm_dd = date_part[5:]
            hh_mm = time_part[:5]
            return f"{mm_dd} {hh_mm}"
        except Exception:
            return iso_str[:16]

    def generate_header(self, loop_count: int) -> Panel:
        """Creates the header panel with system status."""
        status_text = "[bold green]ACTIVE (PAPER TRADING)[/bold green]" if Config.PAPER_TRADING else "[bold red]ACTIVE (LIVE TRADING)[/bold red]"
        time_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        header_text = Text.from_markup(
            f"[bold cyan]🚀 AUTONOMOUS CRYPTO TRADING BOT v1.0[/bold cyan]\n"
            f"[dim]Status:[/dim] {status_text}  [dim]|  Time: {time_str}  |  Iteration: {loop_count}[/dim]"
        )
        
        return Panel(header_text, style="blue")

    def generate_metrics_panel(self, available_usdt: float, total_usdt: float) -> Panel:
        """Generates key performance metrics panel."""
        all_trades = self.db.get_all_trades()
        closed_trades = [t for t in all_trades if t['status'] == 'CLOSED']
        
        total_count = len(closed_trades)
        winning_trades = [t for t in closed_trades if (t['pnl'] or 0) > 0]
        win_rate = (len(winning_trades) / total_count * 100) if total_count > 0 else 0.0
        
        total_pnl = sum((t['pnl'] or 0) for t in closed_trades)
        
        # Calculate profit factor
        gross_profit = sum((t['pnl'] or 0) for t in winning_trades)
        gross_loss = abs(sum((t['pnl'] or 0) for t in closed_trades if (t['pnl'] or 0) <= 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0.0)

        # Build display text
        text = Text()
        text.append(f"💰 Account Summary\n", style="bold yellow")
        text.append(f"  • Total Equity:     {total_usdt:,.2f} USDT\n", style="white")
        text.append(f"  • Available USDT:   {available_usdt:,.2f} USDT\n\n", style="white")
        
        text.append(f"📈 Performance Metrics\n", style="bold yellow")
        text.append(f"  • Total Trades:     {total_count}\n", style="white")
        
        win_rate_style = "green" if win_rate >= 50 else "red"
        text.append(f"  • Win Rate:         ", style="white")
        text.append(f"{win_rate:.1f}%\n", style=win_rate_style)
        
        pnl_style = "bold green" if total_pnl >= 0 else "bold red"
        text.append(f"  • Total Net P&L:    ", style="white")
        text.append(f"{total_pnl:+.2f} USDT\n", style=pnl_style)
        
        pf_style = "green" if profit_factor >= 1.5 else "red"
        pf_str = f"{profit_factor:.2f}" if profit_factor != float('inf') else "∞"
        text.append(f"  • Profit Factor:    ", style="white")
        text.append(f"{pf_str}\n", style=pf_style)

        return Panel(text, title="Portfolio & Stats", style="cyan")

    def generate_positions_table(self, ticker_prices: dict) -> Panel:
        """Generates the table of currently open positions."""
        table = Table(expand=True)
        table.add_column("ID", justify="center", style="dim")
        table.add_column("Symbol", justify="center", style="bold")
        table.add_column("Side", justify="center", style="dim")
        table.add_column("Entry Price", justify="right")
        table.add_column("Last Price", justify="right")
        table.add_column("Unrealized P&L", justify="right")
        table.add_column("Stop Loss", justify="right", style="red")
        table.add_column("Take Profit", justify="right", style="green")
        table.add_column("Entry Time", justify="center", style="dim")

        open_trades = self.db.get_open_trades()
        
        for trade in open_trades:
            symbol = trade['symbol']
            entry_price = trade['entry_price']
            qty = trade['entry_qty']
            
            # Fetch latest real-time price
            last_price = ticker_prices.get(symbol, entry_price)
            
            # Calculate unrealized P&L
            unrealized_pnl = (last_price - entry_price) * qty
            unrealized_pct = ((last_price - entry_price) / entry_price) * 100
            
            pnl_style = "green" if unrealized_pnl >= 0 else "red"
            pnl_text = f"{unrealized_pnl:+.2f} ({unrealized_pct:+.2f}%)"
            
            table.add_row(
                str(trade['id']),
                symbol,
                trade['side'].upper(),
                f"{entry_price:.4f}",
                f"{last_price:.4f}",
                Text(pnl_text, style=pnl_style),
                f"{trade['stop_loss']:.4f}",
                f"{trade['take_profit']:.4f}",
                self._format_time(trade.get('entry_time', ''))
            )

        if not open_trades:
            return Panel(Text("\nNo active open positions.\n", style="dim italic", justify="center"), title="Open Positions", style="yellow")
            
        return Panel(table, title=f"Open Positions ({len(open_trades)})", style="green")

    def generate_trade_log_panel(self) -> Panel:
        """Generates the recent trade history log table."""
        table = Table(expand=True)
        table.add_column("Symbol", justify="center", style="bold")
        table.add_column("Entry Price", justify="right")
        table.add_column("Exit Price", justify="right")
        table.add_column("Quantity", justify="right")
        table.add_column("PnL %", justify="right")
        table.add_column("Net PnL", justify="right")
        table.add_column("Exit Reason", justify="center")
        table.add_column("Exit Time", justify="center", style="dim")

        all_trades = self.db.get_all_trades(limit=5)
        closed_trades = [t for t in all_trades if t['status'] == 'CLOSED']

        for trade in closed_trades:
            pnl_val = trade['pnl'] or 0.0
            pnl_pct_val = trade['pnl_pct'] or 0.0
            pnl_style = "green" if pnl_val >= 0 else "red"
            
            # Deduce exit reason dynamically
            entry_price = trade['entry_price'] or 0.0
            exit_price = trade['exit_price'] or 0.0
            stop_loss = trade['stop_loss'] or 0.0
            take_profit = trade['take_profit'] or 0.0
            
            if exit_price >= take_profit - 0.0001:
                reason = "TAKE_PROFIT"
                reason_style = "bold green"
            elif exit_price <= stop_loss + 0.0001:
                if abs(exit_price - entry_price) <= 0.0005:
                    reason = "BREAK_EVEN"
                    reason_style = "cyan"
                else:
                    reason = "STOP_LOSS"
                    reason_style = "red"
            else:
                reason = "STOP_LOSS"
                reason_style = "red"
            
            table.add_row(
                trade['symbol'],
                f"{trade['entry_price']:.4f}",
                f"{trade['exit_price']:.4f}" if trade['exit_price'] else "-",
                f"{trade['entry_qty']:.4f}",
                Text(f"{pnl_pct_val:+.2f}%", style=pnl_style),
                Text(f"{pnl_val:+.2f}", style=pnl_style),
                Text(reason, style=reason_style),
                self._format_time(trade.get('exit_time', ''))
            )

        if not closed_trades:
            return Panel(Text("No closed trades recorded yet.", style="dim italic", justify="center"), title="Recent Trade History", style="dim")

        return Panel(table, title="Recent Trade History (Last 5 Closed)", style="yellow")

    def draw(self, loop_count: int, available_usdt: float, total_usdt: float, ticker_prices: dict) -> Layout:
        """Draws the final dashboard Grid layout."""
        layout = Layout()
        
        # Split into Header, Body, and Footer
        layout.split_column(
            Layout(name="header", size=4),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=8)
        )
        
        # Split Body into columns (Stats / Metrics on Left, Active positions on Right)
        layout["body"].split_row(
            Layout(name="stats", ratio=1),
            Layout(name="positions", ratio=2)
        )
        
        # Fill sections
        layout["header"].update(self.generate_header(loop_count))
        layout["body"]["stats"].update(self.generate_metrics_panel(available_usdt, total_usdt))
        layout["body"]["positions"].update(self.generate_positions_table(ticker_prices))
        layout["footer"].update(self.generate_trade_log_panel())
        
        return layout
