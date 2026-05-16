"""Active Recommendations Dashboard — live prices, status, and portfolio heat.

Displays all active recommendations with current market prices fetched
via ``PriceService``, color-coded verdicts, stop/target breach indicators,
and an auto-refresh timer.

See also: PLAN-desktop.md.
"""

from __future__ import annotations

import logging
from datetime import datetime

from nicegui import ui

from desktop.services.price_service import PriceResult, PriceService
from desktop.state.database import HistoryDB, RecommendationRow

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Verdict → color mapping (Quasar classes)
# ---------------------------------------------------------------------------

_VERDICT_COLORS: dict[str, str] = {
    "BUY": "bg-green text-white",
    "OVERWEIGHT": "bg-green text-white",
    "HOLD": "bg-orange text-white",
    "SELL": "bg-red text-white",
    "UNDERWEIGHT": "bg-red text-white",
}
_VERDICT_DEFAULT = "bg-grey text-white"

_BULLISH_VERDICTS = frozenset({"BUY", "OVERWEIGHT"})
_BEARISH_VERDICTS = frozenset({"SELL", "UNDERWEIGHT"})

_AUTO_REFRESH_SECONDS = 60


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def render_dashboard_page(*, db: HistoryDB) -> None:
    """Render the active recommendations dashboard."""
    page = _DashboardPage(db=db)
    page.build()


# ---------------------------------------------------------------------------
# Internal page controller
# ---------------------------------------------------------------------------


class _DashboardPage:
    """Builds and manages the Active Recommendations Dashboard."""

    def __init__(self, *, db: HistoryDB) -> None:
        self._db = db
        self._price_svc = PriceService()

        # UI refs
        self._table: ui.table | None = None
        self._last_updated_label: ui.label | None = None
        self._loading_spinner: ui.spinner | None = None
        self._timer: ui.timer | None = None

        # Stat card labels
        self._total_label: ui.label | None = None
        self._buy_label: ui.label | None = None
        self._hold_label: ui.label | None = None
        self._sell_label: ui.label | None = None

        # Footer labels
        self._heat_label: ui.label | None = None
        self._dist_label: ui.label | None = None

    # ── Build ──────────────────────────────────────────────────────────

    def build(self) -> None:
        """Render the full dashboard layout."""
        recs = self._db.list_active_recommendations()

        if not recs:
            self._build_empty_state()
            return

        with ui.column().classes("w-full q-pa-md gap-md"):
            self._build_header()
            self._build_summary_stats(recs)
            self._build_table()
            self._build_footer()

        # Initial data load
        self._refresh_data()

        # Auto-refresh timer
        self._timer = ui.timer(_AUTO_REFRESH_SECONDS, self._refresh_data)

    # ── Empty state ────────────────────────────────────────────────────

    def _build_empty_state(self) -> None:
        """Show a friendly empty state when no active recommendations exist."""
        with ui.column().classes(
            "w-full items-center justify-center q-pa-xl gap-md"
        ).style("min-height: 60vh"):
            ui.icon("analytics").classes("text-grey-6").style("font-size: 72px")
            ui.label("No recommendations yet").classes(
                "text-h5 text-grey-4"
            )
            ui.label(
                "Run your first analysis to see recommendations here"
            ).classes("text-body1 text-grey-6")
            ui.button(
                "Go to Analysis",
                icon="arrow_forward",
                on_click=lambda: ui.navigate.to("/"),
            ).props("color=green size=lg")

    # ── Header ─────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        with ui.row().classes("items-center w-full"):
            ui.label("Active Recommendations").classes("text-h5 text-white")
            ui.space()
            self._loading_spinner = ui.spinner("dots", size="sm")
            self._loading_spinner.set_visibility(False)
            ui.button(
                "Refresh",
                icon="refresh",
                on_click=self._on_manual_refresh,
            ).props("flat dense")
            self._last_updated_label = ui.label("").classes(
                "text-caption text-grey-5"
            )

    # ── Summary stat cards ─────────────────────────────────────────────

    def _build_summary_stats(self, recs: list[RecommendationRow]) -> None:
        with ui.row().classes("w-full gap-md flex-wrap"):
            self._total_label = self._stat_card(
                "Total Active", str(len(recs)), "list_alt", "text-blue"
            )
            buy_count = sum(
                1 for r in recs if r.verdict in _BULLISH_VERDICTS
            )
            self._buy_label = self._stat_card(
                "BUY / Overweight", str(buy_count), "trending_up", "text-green"
            )
            hold_count = sum(1 for r in recs if r.verdict == "HOLD")
            self._hold_label = self._stat_card(
                "HOLD", str(hold_count), "pause_circle", "text-orange"
            )
            sell_count = sum(
                1 for r in recs if r.verdict in _BEARISH_VERDICTS
            )
            self._sell_label = self._stat_card(
                "SELL / Underweight", str(sell_count), "trending_down", "text-red"
            )

    @staticmethod
    def _stat_card(
        title: str, value: str, icon_name: str, icon_color: str,
    ) -> ui.label:
        """Build a single summary-stat card and return the value label."""
        with ui.card().classes("bg-dark-page q-pa-md min-w-[140px]"):
            with ui.row().classes("items-center gap-sm"):
                ui.icon(icon_name).classes(f"{icon_color} text-h6")
                ui.label(title).classes("text-caption text-grey-5")
            value_label = ui.label(value).classes("text-h4 text-white q-mt-xs")
        return value_label

    # ── Main table ─────────────────────────────────────────────────────

    def _build_table(self) -> None:
        columns = [
            {"name": "ticker", "label": "Ticker", "field": "ticker", "sortable": True},
            {"name": "verdict", "label": "Verdict", "field": "verdict", "sortable": True},
            {"name": "entry_price", "label": "Entry Price", "field": "entry_price", "sortable": True},
            {"name": "current_price", "label": "Current Price", "field": "current_price", "sortable": True},
            {"name": "delta_pct", "label": "Delta %", "field": "delta_pct", "sortable": True},
            {"name": "stop_loss", "label": "Stop Loss", "field": "stop_loss"},
            {"name": "target", "label": "Target", "field": "target"},
            {"name": "status", "label": "Status", "field": "status"},
            {"name": "actions", "label": "", "field": "actions"},
        ]

        self._table = ui.table(
            columns=columns,
            rows=[],
            row_key="id",
            pagination={"rowsPerPage": 20},
        ).classes("w-full").props("flat bordered dense")

        # Ticker column — bold
        self._table.add_slot(
            "body-cell-ticker",
            """
            <q-td :props="props">
                <span class="text-bold text-white">{{ props.row.ticker }}</span>
            </q-td>
            """,
        )

        # Verdict column — color-coded badge
        self._table.add_slot(
            "body-cell-verdict",
            """
            <q-td :props="props">
                <q-badge :class="props.row.verdict_class" :label="props.row.verdict" />
            </q-td>
            """,
        )

        # Delta % column — green/red coloring
        self._table.add_slot(
            "body-cell-delta_pct",
            """
            <q-td :props="props">
                <span :class="props.row.delta_color">{{ props.row.delta_pct }}</span>
            </q-td>
            """,
        )

        # Status column — icons
        self._table.add_slot(
            "body-cell-status",
            """
            <q-td :props="props">
                <span>{{ props.row.status }}</span>
            </q-td>
            """,
        )

        # Actions column — View button
        self._table.add_slot(
            "body-cell-actions",
            """
            <q-td :props="props">
                <q-btn flat dense color="green" icon="visibility" label="View"
                       @click="$parent.$emit('view', props.row)" />
            </q-td>
            """,
        )

        def _on_view(e) -> None:
            try:
                aid = int(e.args["analysis_id"])
            except (KeyError, TypeError, ValueError):
                ui.notify("Invalid analysis ID", type="warning")
                return
            ui.navigate.to(f"/analysis/{aid}")

        self._table.on("view", _on_view)

    # ── Footer ─────────────────────────────────────────────────────────

    def _build_footer(self) -> None:
        with ui.row().classes("items-center w-full q-mt-sm gap-lg"):
            ui.icon("local_fire_department").classes("text-orange text-h6")
            self._heat_label = ui.label("Portfolio Heat: --").classes(
                "text-body2 text-grey-4"
            )
            ui.space()
            self._dist_label = ui.label("").classes(
                "text-caption text-grey-5"
            )

    # ── Refresh logic ──────────────────────────────────────────────────

    def _on_manual_refresh(self) -> None:
        """Invalidate cache then refresh."""
        self._price_svc.invalidate()
        self._refresh_data()

    def _refresh_data(self) -> None:
        """Fetch active recs + live prices, then update all UI components."""
        if self._loading_spinner:
            self._loading_spinner.set_visibility(True)

        try:
            recs = self._db.list_active_recommendations()
            if not recs:
                self._update_table([])
                self._update_stats([])
                self._update_footer([])
                return

            tickers = list({r.ticker for r in recs})
            prices = self._price_svc.get_prices(tickers)

            rows = self._build_rows(recs, prices)
            self._update_table(rows)
            self._update_stats(recs)
            self._update_footer(recs)

            now_str = datetime.now().strftime("%H:%M:%S")
            if self._last_updated_label:
                self._last_updated_label.set_text(f"Last updated: {now_str}")

        except Exception:
            logger.exception("Dashboard refresh failed")
            ui.notify("Failed to refresh dashboard", type="negative")
        finally:
            if self._loading_spinner:
                self._loading_spinner.set_visibility(False)

    # ── Row building ───────────────────────────────────────────────────

    @staticmethod
    def _build_rows(
        recs: list[RecommendationRow],
        prices: dict[str, PriceResult],
    ) -> list[dict]:
        """Convert recommendation rows + price data into table row dicts."""
        rows: list[dict] = []

        for rec in recs:
            price_data = prices.get(rec.ticker)
            current_price = price_data.price if price_data else None
            entry_price = rec.price_at_analysis

            # Delta % calculation
            delta_pct_val: float | None = None
            if current_price is not None and entry_price and entry_price != 0:
                delta_pct_val = ((current_price - entry_price) / entry_price) * 100

            # Format delta display
            if delta_pct_val is not None:
                sign = "+" if delta_pct_val >= 0 else ""
                delta_display = f"{sign}{delta_pct_val:.1f}%"
            else:
                delta_display = "--"

            # Delta color logic (invert for SELL verdicts)
            is_bearish = rec.verdict in _BEARISH_VERDICTS
            if delta_pct_val is not None:
                positive_is_good = not is_bearish
                if (delta_pct_val >= 0) == positive_is_good:
                    delta_color = "text-green"
                else:
                    delta_color = "text-red"
            else:
                delta_color = "text-grey"

            # Status indicators
            status_parts: list[str] = []
            if (
                rec.stop_loss is not None
                and current_price is not None
                and not is_bearish
                and current_price <= rec.stop_loss
            ):
                status_parts.append("⚠️ Stop")
            if (
                rec.profit_target is not None
                and current_price is not None
                and not is_bearish
                and current_price >= rec.profit_target
            ):
                status_parts.append("\U0001f3af Target")
            if (
                rec.stop_loss is not None
                and current_price is not None
                and is_bearish
                and current_price >= rec.stop_loss
            ):
                status_parts.append("⚠️ Stop")
            if (
                rec.profit_target is not None
                and current_price is not None
                and is_bearish
                and current_price <= rec.profit_target
            ):
                status_parts.append("\U0001f3af Target")
            if price_data and price_data.is_stale:
                status_parts.append("\U0001f4ca Stale")
            if price_data and price_data.error and current_price is None:
                status_parts.append("❌ Error")

            verdict_class = _VERDICT_COLORS.get(rec.verdict, _VERDICT_DEFAULT)

            rows.append(
                {
                    "id": rec.id,
                    "analysis_id": rec.analysis_id,
                    "ticker": rec.ticker,
                    "verdict": rec.verdict,
                    "verdict_class": verdict_class,
                    "entry_price": f"${entry_price:.2f}" if entry_price else "--",
                    "current_price": f"${current_price:.2f}" if current_price else "--",
                    "delta_pct": delta_display,
                    "delta_color": delta_color,
                    "stop_loss": f"${rec.stop_loss:.2f}" if rec.stop_loss else "--",
                    "target": f"${rec.profit_target:.2f}" if rec.profit_target else "--",
                    "status": " ".join(status_parts) if status_parts else "--",
                }
            )

        return rows

    # ── UI update helpers ──────────────────────────────────────────────

    def _update_table(self, rows: list[dict]) -> None:
        if self._table:
            self._table.rows = rows
            self._table.update()

    def _update_stats(self, recs: list[RecommendationRow]) -> None:
        total = len(recs)
        buy_count = sum(1 for r in recs if r.verdict in _BULLISH_VERDICTS)
        hold_count = sum(1 for r in recs if r.verdict == "HOLD")
        sell_count = sum(1 for r in recs if r.verdict in _BEARISH_VERDICTS)

        if self._total_label:
            self._total_label.set_text(str(total))
        if self._buy_label:
            self._buy_label.set_text(str(buy_count))
        if self._hold_label:
            self._hold_label.set_text(str(hold_count))
        if self._sell_label:
            self._sell_label.set_text(str(sell_count))

    def _update_footer(self, recs: list[RecommendationRow]) -> None:
        if not recs:
            if self._heat_label:
                self._heat_label.set_text("Portfolio Heat: --")
            if self._dist_label:
                self._dist_label.set_text("")
            return

        # Average confidence (portfolio heat)
        confidences = [r.confidence for r in recs if r.confidence is not None]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0
        if self._heat_label:
            self._heat_label.set_text(f"Portfolio Heat: {avg_conf:.0f}% avg confidence")

        # Verdict distribution summary
        buy_count = sum(1 for r in recs if r.verdict in _BULLISH_VERDICTS)
        hold_count = sum(1 for r in recs if r.verdict == "HOLD")
        sell_count = sum(1 for r in recs if r.verdict in _BEARISH_VERDICTS)
        parts = []
        if buy_count:
            parts.append(f"{buy_count} BUY")
        if hold_count:
            parts.append(f"{hold_count} HOLD")
        if sell_count:
            parts.append(f"{sell_count} SELL")
        if self._dist_label:
            self._dist_label.set_text(" | ".join(parts))
