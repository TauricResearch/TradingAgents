"""Portfolio Tracker page -- view holdings and alignment with recommendations.

Displays current positions alongside system recommendations, highlighting
alignment (holding what the system says to hold) and misalignment
(holding what it says to sell, or not holding what it says to buy).

See also: PLAN-desktop.md, Phase 4.
"""

from __future__ import annotations

from nicegui import ui

from desktop.services.price_service import PriceResult, PriceService
from desktop.state.database import (
    HistoryDB,
    PositionRow,
    RecommendationRow,
)

# ── Alignment helpers ────────────────────────────────────────────────────

_ALIGNED = "aligned"
_MISALIGNED = "misaligned"
_NEUTRAL = "neutral"


def _alignment_status(
    *, holding: bool, verdict: str | None,
) -> str:
    """Determine alignment between a position and the system verdict.

    Returns 'aligned', 'misaligned', or 'neutral'.
    """
    if verdict is None:
        return _NEUTRAL
    v = verdict.upper()
    if holding and v in ("HOLD", "BUY", "OVERWEIGHT"):
        return _ALIGNED
    if holding and v in ("SELL", "UNDERWEIGHT"):
        return _MISALIGNED
    if not holding and v in ("BUY", "OVERWEIGHT"):
        return _MISALIGNED
    return _NEUTRAL


def _alignment_icon(status: str) -> tuple[str, str]:
    """Return (icon_name, css_color_class) for an alignment status."""
    if status == _ALIGNED:
        return "check_circle", "text-green"
    if status == _MISALIGNED:
        return "warning", "text-orange"
    return "remove_circle_outline", "text-grey"


def _pnl_color(value: float) -> str:
    """CSS class for profit/loss coloring."""
    if value > 0:
        return "text-green"
    if value < 0:
        return "text-red"
    return "text-grey"


# ── Public entry point ───────────────────────────────────────────────────


def render_portfolio_page(*, db: HistoryDB) -> None:
    """Render the Portfolio Tracker page."""
    page = _PortfolioPage(db=db)
    page.build()


# ── Page implementation ──────────────────────────────────────────────────


class _PortfolioPage:
    def __init__(self, *, db: HistoryDB) -> None:
        self._db = db
        self._price_service = PriceService()
        self._content_area: ui.column | None = None

    def build(self) -> None:
        with ui.column().classes("w-full q-pa-md gap-md"):
            # Header
            with ui.row().classes("items-center w-full"):
                ui.icon("work").classes("text-green text-h5")
                ui.label("Portfolio").classes("text-h5 text-white q-ml-sm")
                ui.space()
                ui.button(
                    "Add Position", icon="add",
                    on_click=self._open_add_dialog,
                ).props("color=green")
                ui.button(
                    "Refresh", icon="refresh",
                    on_click=self._refresh,
                ).props("flat dense")

            # Content area (rebuilt on refresh)
            self._content_area = ui.column().classes("w-full gap-md")

            self._refresh()

    # ── Refresh / rebuild ─────────────────────────────────────────────

    def _refresh(self) -> None:
        """Reload positions and recommendations, then rebuild the table."""
        if self._content_area is None:
            return

        positions = self._db.list_positions()
        recs = self._db.list_active_recommendations()
        rec_by_ticker: dict[str, RecommendationRow] = {
            r.ticker: r for r in recs
        }

        # Fetch current prices for all held tickers.
        tickers = [p.ticker for p in positions]
        prices: dict[str, PriceResult] = (
            self._price_service.get_prices(tickers) if tickers else {}
        )

        self._content_area.clear()
        with self._content_area:
            if not positions:
                self._build_empty_state()
                return

            self._build_summary(positions, prices, rec_by_ticker)
            self._build_table(positions, prices, rec_by_ticker)

    # ── Empty state ───────────────────────────────────────────────────

    @staticmethod
    def _build_empty_state() -> None:
        with ui.card().classes("w-full q-pa-lg"):
            with ui.column().classes("items-center gap-md"):
                ui.icon("account_balance_wallet").classes(
                    "text-grey-6 text-h2"
                )
                ui.label(
                    "No positions yet. Add your holdings to see how they "
                    "align with the system's recommendations."
                ).classes("text-body1 text-grey-5 text-center")

    # ── Summary row ───────────────────────────────────────────────────

    def _build_summary(
        self,
        positions: list[PositionRow],
        prices: dict[str, PriceResult],
        rec_by_ticker: dict[str, RecommendationRow],
    ) -> None:
        total_value = 0.0
        total_cost = 0.0
        aligned_count = 0
        total_count = len(positions)

        for pos in positions:
            pr = prices.get(pos.ticker)
            current = pr.price if pr and pr.price else pos.avg_price
            total_value += current * pos.quantity
            total_cost += pos.avg_price * pos.quantity

            rec = rec_by_ticker.get(pos.ticker)
            verdict = rec.verdict if rec else None
            if _alignment_status(holding=True, verdict=verdict) == _ALIGNED:
                aligned_count += 1

        total_pnl = total_value - total_cost
        total_pnl_pct = (
            ((total_value - total_cost) / total_cost * 100) if total_cost else 0.0
        )
        alignment_score = (
            (aligned_count / total_count * 100) if total_count else 0.0
        )

        with ui.row().classes("w-full gap-md"):
            # Total value card
            with ui.card().classes("q-pa-md"):
                ui.label("Portfolio Value").classes("text-caption text-grey-5")
                ui.label(f"${total_value:,.2f}").classes("text-h6 text-white")

            # Total P&L card
            with ui.card().classes("q-pa-md"):
                ui.label("Total P&L").classes("text-caption text-grey-5")
                pnl_cls = _pnl_color(total_pnl)
                ui.label(
                    f"${total_pnl:+,.2f} ({total_pnl_pct:+.1f}%)"
                ).classes(f"text-h6 {pnl_cls}")

            # Alignment card
            with ui.card().classes("q-pa-md"):
                ui.label("System Alignment").classes("text-caption text-grey-5")
                align_cls = "text-green" if alignment_score >= 70 else "text-orange"
                ui.label(
                    f"{alignment_score:.0f}% ({aligned_count}/{total_count})"
                ).classes(f"text-h6 {align_cls}")

    # ── Positions table ───────────────────────────────────────────────

    def _build_table(
        self,
        positions: list[PositionRow],
        prices: dict[str, PriceResult],
        rec_by_ticker: dict[str, RecommendationRow],
    ) -> None:
        with ui.card().classes("w-full"):
            ui.label("Positions").classes("text-subtitle1 text-white q-mb-sm")

            columns = [
                {"name": "ticker", "label": "Ticker", "field": "ticker", "sortable": True},
                {"name": "shares", "label": "Shares", "field": "shares", "sortable": True},
                {"name": "avg_price", "label": "Avg Price", "field": "avg_price", "sortable": True},
                {"name": "current", "label": "Current Price", "field": "current", "sortable": True},
                {"name": "pnl_dollar", "label": "P&L ($)", "field": "pnl_dollar", "sortable": True},
                {"name": "pnl_pct", "label": "P&L (%)", "field": "pnl_pct", "sortable": True},
                {"name": "verdict", "label": "System Verdict", "field": "verdict"},
                {"name": "alignment", "label": "Alignment", "field": "alignment"},
                {"name": "actions", "label": "", "field": "actions"},
            ]

            rows = []
            for pos in positions:
                pr = prices.get(pos.ticker)
                current = pr.price if pr and pr.price else None
                pnl_dollar = (
                    (current - pos.avg_price) * pos.quantity
                    if current else 0.0
                )
                pnl_pct = (
                    ((current - pos.avg_price) / pos.avg_price * 100)
                    if current and pos.avg_price else 0.0
                )

                rec = rec_by_ticker.get(pos.ticker)
                verdict = rec.verdict if rec else "N/A"
                align = _alignment_status(
                    holding=True, verdict=rec.verdict if rec else None,
                )

                rows.append({
                    "ticker": pos.ticker,
                    "shares": pos.quantity,
                    "avg_price": f"${pos.avg_price:.2f}",
                    "current": f"${current:.2f}" if current else "N/A",
                    "pnl_dollar": f"${pnl_dollar:+,.2f}",
                    "pnl_pct": f"{pnl_pct:+.1f}%",
                    "verdict": verdict,
                    "alignment": align,
                })

            table = ui.table(
                columns=columns,
                rows=rows,
                row_key="ticker",
                pagination={"rowsPerPage": 25},
            ).classes("w-full").props("flat bordered dense")

            # Custom cell renderers via slots

            # P&L dollar coloring
            table.add_slot(
                "body-cell-pnl_dollar",
                """
                <q-td :props="props">
                    <span :class="parseFloat(props.value) >= 0 ? 'text-green' : 'text-red'">
                        {{ props.value }}
                    </span>
                </q-td>
                """,
            )

            # P&L percent coloring
            table.add_slot(
                "body-cell-pnl_pct",
                """
                <q-td :props="props">
                    <span :class="parseFloat(props.value) >= 0 ? 'text-green' : 'text-red'">
                        {{ props.value }}
                    </span>
                </q-td>
                """,
            )

            # Alignment icon
            table.add_slot(
                "body-cell-alignment",
                """
                <q-td :props="props">
                    <q-icon v-if="props.value === 'aligned'"
                            name="check_circle" color="green" size="sm" />
                    <q-icon v-else-if="props.value === 'misaligned'"
                            name="warning" color="orange" size="sm" />
                    <q-icon v-else name="remove_circle_outline" color="grey" size="sm" />
                    <span class="q-ml-xs text-caption">{{ props.value }}</span>
                </q-td>
                """,
            )

            # Action buttons
            table.add_slot(
                "body-cell-actions",
                """
                <q-td :props="props">
                    <q-btn flat dense color="blue" icon="edit"
                           @click="$parent.$emit('edit', props.row)" />
                    <q-btn flat dense color="red" icon="delete"
                           @click="$parent.$emit('delete', props.row)" />
                </q-td>
                """,
            )

            table.on("edit", lambda e: self._open_edit_dialog(e.args))
            table.on("delete", lambda e: self._confirm_delete(e.args))

    # ── Add position dialog ───────────────────────────────────────────

    def _open_add_dialog(self) -> None:
        """Open a dialog to add a new portfolio position."""
        form_data: dict = {
            "ticker": "",
            "quantity": "",
            "avg_price": "",
            "date_opened": "",
            "notes": "",
        }

        with ui.dialog() as dialog, ui.card().classes("w-96"):
            ui.label("Add Position").classes("text-h6 text-white q-mb-md")

            ticker_input = ui.input(
                "Ticker (e.g., AAPL)",
                on_change=lambda e: form_data.update(ticker=e.value),
            ).props("outlined dense")

            qty_input = ui.number(
                "Quantity (shares)",
                on_change=lambda e: form_data.update(quantity=e.value),
            ).props("outlined dense")

            price_input = ui.number(
                "Average Price ($)",
                on_change=lambda e: form_data.update(avg_price=e.value),
            ).props("outlined dense")

            ui.input(
                "Date Opened (optional, YYYY-MM-DD)",
                on_change=lambda e: form_data.update(date_opened=e.value),
            ).props("outlined dense")

            ui.textarea(
                "Notes (optional)",
                on_change=lambda e: form_data.update(notes=e.value),
            ).props("outlined dense").classes("w-full")

            with ui.row().classes("w-full justify-end gap-sm q-mt-md"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button(
                    "Add",
                    on_click=lambda: self._save_position(form_data, dialog),
                ).props("color=green")

        dialog.open()

    def _save_position(self, data: dict, dialog: ui.dialog) -> None:
        """Validate and save a new position."""
        ticker = (data.get("ticker") or "").strip().upper()
        if not ticker or not ticker.isalpha():
            ui.notify("Ticker must be uppercase letters only", type="warning")
            return

        try:
            quantity = float(data.get("quantity") or 0)
        except (TypeError, ValueError):
            ui.notify("Quantity must be a positive number", type="warning")
            return
        if quantity <= 0:
            ui.notify("Quantity must be greater than 0", type="warning")
            return

        try:
            avg_price = float(data.get("avg_price") or 0)
        except (TypeError, ValueError):
            ui.notify("Price must be a positive number", type="warning")
            return
        if avg_price <= 0:
            ui.notify("Price must be greater than 0", type="warning")
            return

        date_opened = (data.get("date_opened") or "").strip() or None
        notes = (data.get("notes") or "").strip() or None

        self._db.upsert_position(
            ticker=ticker,
            quantity=quantity,
            avg_price=avg_price,
            date_opened=date_opened,
            notes=notes,
        )

        ui.notify(f"Added {ticker}", type="positive")
        dialog.close()
        self._refresh()

    # ── Edit position dialog ──────────────────────────────────────────

    def _open_edit_dialog(self, row: dict) -> None:
        """Open a dialog to edit an existing position."""
        ticker = row.get("ticker", "")
        positions = self._db.list_positions()
        existing = next((p for p in positions if p.ticker == ticker), None)
        if existing is None:
            ui.notify(f"Position {ticker} not found", type="warning")
            return

        form_data: dict = {
            "ticker": existing.ticker,
            "quantity": existing.quantity,
            "avg_price": existing.avg_price,
            "date_opened": existing.date_opened or "",
            "notes": existing.notes or "",
        }

        with ui.dialog() as dialog, ui.card().classes("w-96"):
            ui.label(f"Edit {ticker}").classes("text-h6 text-white q-mb-md")

            ui.input("Ticker").props("outlined dense readonly").bind_value(
                form_data, "ticker"
            )

            ui.number(
                "Quantity",
                value=existing.quantity,
                on_change=lambda e: form_data.update(quantity=e.value),
            ).props("outlined dense")

            ui.number(
                "Average Price ($)",
                value=existing.avg_price,
                on_change=lambda e: form_data.update(avg_price=e.value),
            ).props("outlined dense")

            ui.input(
                "Date Opened",
                value=existing.date_opened or "",
                on_change=lambda e: form_data.update(date_opened=e.value),
            ).props("outlined dense")

            ui.textarea(
                "Notes",
                value=existing.notes or "",
                on_change=lambda e: form_data.update(notes=e.value),
            ).props("outlined dense").classes("w-full")

            with ui.row().classes("w-full justify-end gap-sm q-mt-md"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button(
                    "Save",
                    on_click=lambda: self._save_position(form_data, dialog),
                ).props("color=green")

        dialog.open()

    # ── Delete confirmation ───────────────────────────────────────────

    def _confirm_delete(self, row: dict) -> None:
        """Show a confirmation dialog before deleting a position."""
        ticker = row.get("ticker", "")

        with ui.dialog() as dialog, ui.card().classes("w-80"):
            ui.label(f"Delete {ticker}?").classes("text-h6 text-white")
            ui.label(
                f"Remove {ticker} from your portfolio? This cannot be undone."
            ).classes("text-body2 text-grey-4 q-my-md")

            with ui.row().classes("w-full justify-end gap-sm"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button(
                    "Delete",
                    on_click=lambda: self._do_delete(ticker, dialog),
                ).props("color=red")

        dialog.open()

    def _do_delete(self, ticker: str, dialog: ui.dialog) -> None:
        """Execute the position deletion."""
        self._db.delete_position(ticker)
        ui.notify(f"Deleted {ticker}", type="positive")
        dialog.close()
        self._refresh()
