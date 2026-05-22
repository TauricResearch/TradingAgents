"""
dashboard/simple.py — Simple mode layout for the trading dashboard.

Returns a dash.html.Div containing:
  1. KPI stats row (Win Rate, Total Trades, Realised P&L, Account Heat)
  2. Equity curve line chart
  3. Open positions card grid
  4. Recent trades table (last 10 closed)
  5. System status indicator (bottom-right)
"""

from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
from dash import dash_table, dcc, html

from .queries import (
    get_equity_curve,
    get_open_positions,
    get_recent_trades,
    get_stats_summary,
)

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
BG = "#0d1117"
CARD_BG = "#161b22"
TEXT = "#c9d1d9"
ACCENT = "#58a6ff"
WIN_GREEN = "#3fb950"
LOSS_RED = "#f85149"
MUTED = "#8b949e"
BORDER = "#30363d"

_CARD_STYLE = {
    "backgroundColor": CARD_BG,
    "borderRadius": "8px",
    "padding": "20px",
    "border": f"1px solid {BORDER}",
}


def _fmt_pnl(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}${value:,.2f}"


def _pnl_colour(value: float) -> str:
    return WIN_GREEN if value >= 0 else LOSS_RED


# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------
def _kpi_card(label: str, value: str, colour: str = TEXT) -> html.Div:
    return html.Div(
        [
            html.Div(label, style={"fontSize": "12px", "color": MUTED, "marginBottom": "6px"}),
            html.Div(value, style={"fontSize": "28px", "fontWeight": "700", "color": colour}),
        ],
        style={**_CARD_STYLE, "flex": "1", "minWidth": "180px"},
    )


def _stats_row(stats: dict) -> html.Div:
    win_colour = WIN_GREEN if stats["win_rate"] >= 50 else LOSS_RED
    pnl_colour = _pnl_colour(stats["total_pnl_dollars"])
    heat_colour = LOSS_RED if stats["account_heat"] > 10 else (
        "#e3b341" if stats["account_heat"] > 5 else WIN_GREEN
    )
    return html.Div(
        [
            _kpi_card("Win Rate", f"{stats['win_rate']:.1f}%", win_colour),
            _kpi_card("Total Trades", str(stats["total_trades"])),
            _kpi_card("Realised P&L", _fmt_pnl(stats["total_pnl_dollars"]), pnl_colour),
            _kpi_card("Account Heat", f"{stats['account_heat']:.1f}%", heat_colour),
        ],
        style={"display": "flex", "gap": "16px", "flexWrap": "wrap"},
    )


# ---------------------------------------------------------------------------
# Equity curve
# ---------------------------------------------------------------------------
def _equity_chart(df: pd.DataFrame) -> dcc.Graph:
    if df.empty:
        fig = go.Figure()
        fig.update_layout(
            title="Equity Curve — No Data",
            paper_bgcolor=CARD_BG,
            plot_bgcolor=CARD_BG,
            font={"color": TEXT},
        )
        return dcc.Graph(figure=fig, config={"displayModeBar": False})

    fig = go.Figure(
        go.Scatter(
            x=df["date"],
            y=df["account_equity"],
            mode="lines",
            line={"color": ACCENT, "width": 2},
            fill="tozeroy",
            fillcolor="rgba(88,166,255,0.08)",
            hovertemplate="<b>%{x}</b><br>Equity: $%{y:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        title={"text": "Equity Curve", "font": {"color": TEXT, "size": 14}},
        paper_bgcolor=CARD_BG,
        plot_bgcolor=CARD_BG,
        font={"color": TEXT},
        xaxis={
            "gridcolor": BORDER,
            "showgrid": True,
            "zeroline": False,
            "tickfont": {"color": MUTED},
        },
        yaxis={
            "gridcolor": BORDER,
            "showgrid": True,
            "zeroline": False,
            "tickprefix": "$",
            "tickfont": {"color": MUTED},
        },
        margin={"l": 60, "r": 20, "t": 40, "b": 40},
        hovermode="x unified",
    )
    return dcc.Graph(
        figure=fig,
        config={"displayModeBar": False},
        style={"height": "300px"},
    )


# ---------------------------------------------------------------------------
# Open positions
# ---------------------------------------------------------------------------
def _days_open(date_open_str: str) -> int:
    try:
        opened = datetime.fromisoformat(date_open_str)
        now = datetime.now(timezone.utc)
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=timezone.utc)
        return max(0, (now - opened).days)
    except Exception:
        return 0


def _position_card(pos: dict) -> html.Div:
    days = _days_open(pos.get("date_open", ""))
    direction = pos.get("signal", "—")
    entry = pos.get("entry_price")
    stop = pos.get("stop_price")
    entry_str = f"${entry:,.2f}" if entry is not None else "—"
    stop_str = f"${stop:,.2f}" if stop is not None else "—"

    return html.Div(
        [
            html.Div(
                [
                    html.Span(
                        pos.get("ticker", "?"),
                        style={"fontWeight": "700", "fontSize": "18px", "color": ACCENT},
                    ),
                    html.Span(
                        direction,
                        style={
                            "fontSize": "11px",
                            "color": CARD_BG,
                            "backgroundColor": ACCENT,
                            "borderRadius": "4px",
                            "padding": "2px 6px",
                            "marginLeft": "8px",
                        },
                    ),
                ],
                style={"marginBottom": "10px"},
            ),
            html.Div(f"Entry: {entry_str}", style={"fontSize": "13px", "color": MUTED}),
            html.Div(f"Stop: {stop_str}", style={"fontSize": "13px", "color": MUTED}),
            html.Div(
                f"{days}d open",
                style={"fontSize": "12px", "color": MUTED, "marginTop": "8px"},
            ),
        ],
        style={**_CARD_STYLE, "width": "200px", "flexShrink": "0"},
    )


def _open_positions_section(positions: list[dict]) -> html.Div:
    if not positions:
        content = html.Div(
            "No open positions",
            style={"color": MUTED, "padding": "20px"},
        )
    else:
        content = html.Div(
            [_position_card(p) for p in positions],
            style={"display": "flex", "gap": "12px", "flexWrap": "wrap"},
        )
    return html.Div(
        [
            html.H3(
                f"Open Positions ({len(positions)})",
                style={"color": TEXT, "marginBottom": "12px", "fontSize": "14px"},
            ),
            content,
        ],
        style={**_CARD_STYLE},
    )


# ---------------------------------------------------------------------------
# Recent trades table
# ---------------------------------------------------------------------------
_OUTCOME_STYLES = [
    {
        "if": {"filter_query": '{outcome} = "win"', "column_id": "outcome"},
        "backgroundColor": "rgba(63,185,80,0.15)",
        "color": WIN_GREEN,
    },
    {
        "if": {"filter_query": '{outcome} = "loss"', "column_id": "outcome"},
        "backgroundColor": "rgba(248,81,73,0.15)",
        "color": LOSS_RED,
    },
    {
        "if": {"filter_query": '{pnl_dollars} > 0', "column_id": "pnl_dollars"},
        "color": WIN_GREEN,
    },
    {
        "if": {"filter_query": '{pnl_dollars} < 0', "column_id": "pnl_dollars"},
        "color": LOSS_RED,
    },
    {
        "if": {"filter_query": '{pnl_pct} > 0', "column_id": "pnl_pct"},
        "color": WIN_GREEN,
    },
    {
        "if": {"filter_query": '{pnl_pct} < 0', "column_id": "pnl_pct"},
        "color": LOSS_RED,
    },
]


def _recent_trades_table(df: pd.DataFrame) -> html.Div:
    columns = ["ticker", "signal", "entry_price", "stop_price", "pnl_dollars", "pnl_pct", "outcome"]
    display_names = {
        "ticker": "Ticker",
        "signal": "Signal",
        "entry_price": "Entry",
        "stop_price": "Stop",
        "pnl_dollars": "P&L ($)",
        "pnl_pct": "P&L (%)",
        "outcome": "Outcome",
    }

    if df.empty:
        table_data = []
        for col in columns:
            if col not in df.columns:
                df[col] = None
    else:
        for col in columns:
            if col not in df.columns:
                df[col] = None
        # Round numeric columns for display
        if "pnl_dollars" in df.columns:
            df = df.copy()
            df["pnl_dollars"] = df["pnl_dollars"].apply(
                lambda x: round(x, 2) if pd.notna(x) else x
            )
        if "pnl_pct" in df.columns:
            df["pnl_pct"] = df["pnl_pct"].apply(
                lambda x: round(x, 2) if pd.notna(x) else x
            )
        table_data = df[columns].to_dict("records")

    return html.Div(
        [
            html.H3(
                "Recent Trades",
                style={"color": TEXT, "marginBottom": "12px", "fontSize": "14px"},
            ),
            dash_table.DataTable(
                data=table_data,
                columns=[{"name": display_names[c], "id": c} for c in columns],
                style_table={"overflowX": "auto"},
                style_header={
                    "backgroundColor": BG,
                    "color": MUTED,
                    "fontWeight": "600",
                    "border": f"1px solid {BORDER}",
                    "fontSize": "12px",
                },
                style_cell={
                    "backgroundColor": CARD_BG,
                    "color": TEXT,
                    "border": f"1px solid {BORDER}",
                    "padding": "10px 14px",
                    "fontSize": "13px",
                    "fontFamily": "inherit",
                },
                style_data_conditional=_OUTCOME_STYLES,
                page_size=10,
            ),
        ],
        style={**_CARD_STYLE},
    )


# ---------------------------------------------------------------------------
# System status
# ---------------------------------------------------------------------------
def _system_status() -> html.Div:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    conn_ok = True  # if we got here, DB was reachable
    dot_colour = WIN_GREEN if conn_ok else LOSS_RED
    label = "Healthy" if conn_ok else "DB Unavailable"
    return html.Div(
        [
            html.Span(
                "●",
                style={"color": dot_colour, "fontSize": "14px", "marginRight": "6px"},
            ),
            html.Span(label, style={"color": TEXT, "fontSize": "12px"}),
            html.Span(
                f"  Updated {now}",
                style={"color": MUTED, "fontSize": "11px", "marginLeft": "8px"},
            ),
        ],
        style={
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "flex-end",
            "padding": "8px 0",
        },
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def build_layout() -> html.Div:
    """Build and return the simple mode layout div."""
    stats = get_stats_summary()
    equity_df = get_equity_curve()
    positions = get_open_positions()
    trades_df = get_recent_trades(10)

    return html.Div(
        [
            _stats_row(stats),
            html.Div(
                html.Div(
                    _equity_chart(equity_df),
                    style={**_CARD_STYLE},
                ),
                style={"marginTop": "16px"},
            ),
            html.Div(
                _open_positions_section(positions),
                style={"marginTop": "16px"},
            ),
            html.Div(
                _recent_trades_table(trades_df),
                style={"marginTop": "16px"},
            ),
            html.Div(
                _system_status(),
                style={"marginTop": "8px"},
            ),
        ],
        style={"padding": "0"},
    )
