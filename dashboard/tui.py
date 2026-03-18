"""
TUI Dashboard — Textual-based terminal interface with 4 panels:
  1. Markets table   2. Positions   3. Bot status   4. Logs
"""

from datetime import datetime
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, DataTable, RichLog, Label
from textual.reactive import reactive
from textual.timer import Timer
from rich.text import Text
from rich.table import Table


class StatusPanel(Static):
    """Bot status panel — last scan, RPC, wallet, active markets."""

    def compose(self) -> ComposeResult:
        yield Label("⚡ Bot Status", id="status-title")

    def update_status(self, data: dict):
        status_lines = []
        status_lines.append(f"  🕐 Last Scan:     {data.get('last_scan', 'Never')}")
        status_lines.append(f"  🌐 RPC:           {data.get('rpc_status', 'Unknown')}")
        status_lines.append(f"  📊 Active Markets: {data.get('active_markets', 0)}")
        status_lines.append(f"  💰 Balance:       ${data.get('balance', 0):.2f} USDC")
        status_lines.append(f"  📡 Mode:          {'🔸 DRY RUN' if data.get('dry_run', True) else '🟢 LIVE'}")

        content = "\n".join(status_lines)
        self.update(f"[bold cyan]⚡ Bot Status[/bold cyan]\n{content}")


class MarketsPanel(Static):
    """Markets table panel — active weather markets with prices and edge."""

    def compose(self) -> ComposeResult:
        yield Label("📈 Weather Markets", id="markets-title")

    def update_markets(self, markets: list[dict]):
        table = Table(
            title="📈 Weather Markets",
            show_header=True,
            header_style="bold magenta",
            border_style="dim",
            expand=True,
        )
        table.add_column("City", style="cyan", min_width=12)
        table.add_column("Threshold", justify="center", min_width=8)
        table.add_column("YES", justify="right", style="red", min_width=6)
        table.add_column("NO", justify="right", style="green", min_width=6)
        table.add_column("Forecast", justify="center", min_width=8)
        table.add_column("Edge", justify="right", min_width=7)
        table.add_column("Volume", justify="right", min_width=10)

        for m in markets:
            city = m.get("city", "?") or "?"
            threshold = f"{m.get('threshold_c', '?')}°C" if m.get("threshold_c") else "?"
            yes_p = f"{m.get('yes_price', 0):.2f}" if m.get("yes_price") is not None else "?"
            no_p = f"{m.get('no_price', 0):.2f}" if m.get("no_price") is not None else "?"
            forecast = f"{m.get('forecast_high_c', '?')}°C" if m.get("forecast_high_c") else "?"

            edge = m.get("edge")
            if edge is not None:
                edge_str = f"{edge:+.2%}"
                edge_style = "green" if edge > 0 else "red"
            else:
                edge_str = "—"
                edge_style = "dim"

            vol = m.get("volume", 0) or 0
            vol_str = f"${vol:,.0f}" if vol else "—"

            table.add_row(city, threshold, yes_p, no_p, forecast, f"[{edge_style}]{edge_str}[/{edge_style}]", vol_str)

        if not markets:
            table.add_row("—", "—", "—", "—", "—", "—", "—")

        self.update(table)


class PositionsPanel(Static):
    """Open positions panel."""

    def compose(self) -> ComposeResult:
        yield Label("📊 Positions", id="positions-title")

    def update_positions(self, positions: list[dict]):
        table = Table(
            title="📊 Open Positions",
            show_header=True,
            header_style="bold yellow",
            border_style="dim",
            expand=True,
        )
        table.add_column("Market", style="cyan", min_width=15)
        table.add_column("Side", justify="center", min_width=6)
        table.add_column("Entry", justify="right", min_width=7)
        table.add_column("Size", justify="right", min_width=8)
        table.add_column("PnL", justify="right", min_width=8)

        for p in positions:
            market_name = p.get("city", p.get("market", "?"))
            side = p.get("side", "NO")
            entry = f"{p.get('price', p.get('entry_price', 0)):.4f}"
            size = f"${p.get('amount', p.get('size', 0)):.2f}"
            pnl = p.get("pnl", 0)
            pnl_str = f"${pnl:+.2f}" if isinstance(pnl, (int, float)) else "—"
            pnl_style = "green" if isinstance(pnl, (int, float)) and pnl >= 0 else "red"

            table.add_row(market_name, side, entry, size, f"[{pnl_style}]{pnl_str}[/{pnl_style}]")

        if not positions:
            table.add_row("No open positions", "—", "—", "—", "—")

        self.update(table)


class WeatherBotApp(App):
    """Polymarket Weather Bot TUI Dashboard."""

    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 2;
        grid-gutter: 1;
        padding: 1;
        background: $surface;
    }

    StatusPanel {
        border: round $primary;
        padding: 1 2;
        height: 100%;
    }

    MarketsPanel {
        border: round $secondary;
        padding: 1;
        height: 100%;
        column-span: 1;
    }

    PositionsPanel {
        border: round $warning;
        padding: 1;
        height: 100%;
    }

    #log-panel {
        border: round $accent;
        padding: 1;
        height: 100%;
    }

    #log-panel RichLog {
        height: 100%;
    }
    """

    TITLE = "🌤️  Polymarket Weather Bot"
    SUB_TITLE = "Quantitative Weather Trading"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._status_data: dict = {}
        self._markets_data: list[dict] = []
        self._positions_data: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield MarketsPanel(id="markets-panel")
        yield StatusPanel(id="status-panel")
        yield PositionsPanel(id="positions-panel")
        yield Container(RichLog(id="bot-log", highlight=True, markup=True), id="log-panel")
        yield Footer()

    def on_mount(self):
        """Initialize dashboard with empty state."""
        self.update_all(
            status={"last_scan": "Starting...", "rpc_status": "Connecting...", "active_markets": 0, "balance": 0.0, "dry_run": True},
            markets=[],
            positions=[],
        )

    def update_all(self, status: dict = None, markets: list = None, positions: list = None):
        """Update all panels at once."""
        if status:
            self._status_data = status
            try:
                self.query_one(StatusPanel).update_status(status)
            except Exception:
                pass

        if markets is not None:
            self._markets_data = markets
            try:
                self.query_one(MarketsPanel).update_markets(markets)
            except Exception:
                pass

        if positions is not None:
            self._positions_data = positions
            try:
                self.query_one(PositionsPanel).update_positions(positions)
            except Exception:
                pass

    def add_log(self, message: str, style: str = ""):
        """Add a message to the log panel."""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_widget = self.query_one("#bot-log", RichLog)
            if style:
                log_widget.write(f"[dim]{timestamp}[/dim] [{style}]{message}[/{style}]")
            else:
                log_widget.write(f"[dim]{timestamp}[/dim] {message}")
        except Exception:
            pass


def create_app() -> WeatherBotApp:
    """Create and return the TUI application instance."""
    return WeatherBotApp()
