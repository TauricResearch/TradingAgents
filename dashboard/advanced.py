"""
dashboard/advanced.py — Advanced mode layout for the trading dashboard.

Returns a dash.html.Div containing:
  1. Equity curve with drawdown overlay (dual-axis)
  2. Rolling 30-day Sharpe ratio
  3. Per-analyst performance (horizontal bar chart)
  4. Trade scatter: pnl_pct vs regime, sized by shares, coloured by outcome
  5. P&L distribution histogram with normal curve overlay
  6. Win rate breakdowns by ticker, regime, signal (3 small bar charts)
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html
from plotly.subplots import make_subplots
from scipy import stats as scipy_stats

from .queries import (
    get_analyst_performance,
    get_equity_curve,
    get_pnl_distribution,
    get_recent_trades,
    get_stats_summary,
)

# ---------------------------------------------------------------------------
# Colour palette (shared with simple.py)
# ---------------------------------------------------------------------------
BG = "#0d1117"
CARD_BG = "#161b22"
TEXT = "#c9d1d9"
ACCENT = "#58a6ff"
WIN_GREEN = "#3fb950"
LOSS_RED = "#f85149"
MUTED = "#8b949e"
BORDER = "#30363d"
ORANGE = "#e3b341"

_BASE_LAYOUT = {
    "paper_bgcolor": CARD_BG,
    "plot_bgcolor": CARD_BG,
    "font": {"color": TEXT, "size": 12},
    "margin": {"l": 60, "r": 40, "t": 40, "b": 40},
}

_AXIS_STYLE = {
    "gridcolor": BORDER,
    "showgrid": True,
    "zeroline": False,
    "tickfont": {"color": MUTED},
    "linecolor": BORDER,
}

_CARD_STYLE = {
    "backgroundColor": CARD_BG,
    "borderRadius": "8px",
    "padding": "16px",
    "border": f"1px solid {BORDER}",
}


def _graph(fig: go.Figure, height: int = 320, graph_id: str = "") -> dcc.Graph:
    kwargs = {"figure": fig, "config": {"displayModeBar": False}, "style": {"height": f"{height}px"}}
    if graph_id:
        kwargs["id"] = graph_id
    return dcc.Graph(**kwargs)


# ---------------------------------------------------------------------------
# 1. Equity curve with drawdown overlay
# ---------------------------------------------------------------------------
def _equity_drawdown_chart(df: pd.DataFrame) -> html.Div:
    title = "Equity Curve & Drawdown"
    if df.empty:
        fig = go.Figure()
        fig.update_layout(title=title, **_BASE_LAYOUT)
        return html.Div(dcc.Graph(figure=fig, config={"displayModeBar": False}), style=_CARD_STYLE)

    equity = df["account_equity"].values
    # Compute drawdown series
    running_max = pd.Series(equity).cummax()
    drawdown_pct = (pd.Series(equity) - running_max) / running_max * 100

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=equity,
            mode="lines",
            line={"color": ACCENT, "width": 2},
            name="Equity",
            hovertemplate="Equity: $%{y:,.2f}<extra></extra>",
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=drawdown_pct,
            mode="lines",
            line={"color": LOSS_RED, "width": 1.5},
            fill="tozeroy",
            fillcolor="rgba(248,81,73,0.18)",
            name="Drawdown %",
            hovertemplate="Drawdown: %{y:.2f}%<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title={"text": title, "font": {"color": TEXT, "size": 13}},
        legend={"font": {"color": MUTED}, "bgcolor": "rgba(0,0,0,0)"},
        hovermode="x unified",
        **_BASE_LAYOUT,
    )
    fig.update_yaxes(title_text="Equity ($)", secondary_y=False, **_AXIS_STYLE)
    fig.update_yaxes(
        title_text="Drawdown (%)",
        secondary_y=True,
        ticksuffix="%",
        **_AXIS_STYLE,
    )
    fig.update_xaxes(**_AXIS_STYLE)

    return html.Div(_graph(fig, 320), style=_CARD_STYLE)


# ---------------------------------------------------------------------------
# 2. Rolling 30-day Sharpe ratio
# ---------------------------------------------------------------------------
def _sharpe_chart(df: pd.DataFrame) -> html.Div:
    title = "Rolling 30-Day Sharpe Ratio"
    if df.empty or len(df) < 2:
        fig = go.Figure()
        fig.update_layout(title=title, **_BASE_LAYOUT)
        return html.Div(dcc.Graph(figure=fig, config={"displayModeBar": False}), style=_CARD_STYLE)

    equity = df["account_equity"].ffill()
    daily_returns = equity.pct_change().dropna()

    # Annualised Sharpe (assume 252 trading days)
    sharpe = daily_returns.rolling(30).apply(
        lambda x: (x.mean() / x.std() * (252 ** 0.5)) if x.std() > 0 else 0.0,
        raw=True,
    )
    dates = df["date"].iloc[len(df) - len(sharpe):]

    # Use a single trace; we can't colour per-point easily in lines, so use bar
    fig = go.Figure(
        go.Bar(
            x=dates,
            y=sharpe,
            marker_color=[WIN_GREEN if v >= 1 else (ORANGE if v >= 0 else LOSS_RED) for v in sharpe],
            name="Sharpe",
            hovertemplate="<b>%{x}</b><br>Sharpe: %{y:.2f}<extra></extra>",
        )
    )
    fig.add_hline(y=1.0, line_dash="dot", line_color=WIN_GREEN, annotation_text="1.0")
    fig.add_hline(y=0.0, line_dash="solid", line_color=BORDER)

    fig.update_layout(
        title={"text": title, "font": {"color": TEXT, "size": 13}},
        **_BASE_LAYOUT,
    )
    fig.update_xaxes(**_AXIS_STYLE)
    fig.update_yaxes(**_AXIS_STYLE)

    return html.Div(_graph(fig, 280), style=_CARD_STYLE)


# ---------------------------------------------------------------------------
# 3. Per-analyst performance
# ---------------------------------------------------------------------------
def _analyst_bar(df: pd.DataFrame) -> html.Div:
    title = "Analyst Win Rate"
    if df.empty:
        fig = go.Figure()
        fig.update_layout(title=title, **_BASE_LAYOUT)
        return html.Div(dcc.Graph(figure=fig, config={"displayModeBar": False}), style=_CARD_STYLE)

    df = df.sort_values("win_rate", ascending=True)
    colours = [
        WIN_GREEN if r >= 55 else (ORANGE if r >= 45 else LOSS_RED)
        for r in df["win_rate"]
    ]

    fig = go.Figure(
        go.Bar(
            x=df["win_rate"],
            y=df["analyst_name"],
            orientation="h",
            marker_color=colours,
            text=[f"{r:.1f}% ({n})" for r, n in zip(df["win_rate"], df["total_signals"])],
            textposition="outside",
            textfont={"color": TEXT, "size": 11},
            hovertemplate="<b>%{y}</b><br>Win Rate: %{x:.1f}%<extra></extra>",
        )
    )
    fig.add_vline(x=50, line_dash="dot", line_color=MUTED)
    fig.update_layout(
        title={"text": title, "font": {"color": TEXT, "size": 13}},
        xaxis_ticksuffix="%",
        **_BASE_LAYOUT,
    )
    fig.update_xaxes(**_AXIS_STYLE)
    fig.update_yaxes(**_AXIS_STYLE)

    height = max(250, 40 * len(df) + 80)
    return html.Div(_graph(fig, height), style=_CARD_STYLE)


# ---------------------------------------------------------------------------
# 4. Trade scatter: pnl_pct vs regime
# ---------------------------------------------------------------------------
def _trade_scatter(df: pd.DataFrame) -> html.Div:
    title = "Trade Scatter — P&L % vs Regime"
    if df.empty:
        fig = go.Figure()
        fig.update_layout(title=title, **_BASE_LAYOUT)
        return html.Div(dcc.Graph(figure=fig, config={"displayModeBar": False}), style=_CARD_STYLE)

    needed = ["pnl_pct", "regime", "shares", "outcome", "ticker"]
    for col in needed:
        if col not in df.columns:
            df[col] = None

    df = df.dropna(subset=["pnl_pct"])
    df["regime"] = df["regime"].fillna("unknown")
    df["shares"] = df["shares"].fillna(1).clip(lower=1)
    df["outcome"] = df["outcome"].fillna("unknown")

    colours = df["outcome"].map(
        {"win": WIN_GREEN, "loss": LOSS_RED, "cancelled": MUTED}
    ).fillna(MUTED)

    max_shares = df["shares"].max() or 1
    sizes = (df["shares"] / max_shares * 20 + 5).clip(5, 25)

    fig = go.Figure(
        go.Scatter(
            x=df["pnl_pct"],
            y=df["regime"],
            mode="markers",
            marker={
                "color": colours.tolist(),
                "size": sizes.tolist(),
                "opacity": 0.8,
                "line": {"color": BORDER, "width": 1},
            },
            text=df["ticker"],
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Regime: %{y}<br>"
                "P&L: %{x:.2f}%<extra></extra>"
            ),
        )
    )
    fig.add_vline(x=0, line_dash="solid", line_color=BORDER)
    fig.update_layout(
        title={"text": title, "font": {"color": TEXT, "size": 13}},
        xaxis_ticksuffix="%",
        **_BASE_LAYOUT,
    )
    fig.update_xaxes(**_AXIS_STYLE)
    fig.update_yaxes(**_AXIS_STYLE)

    return html.Div(_graph(fig, 320), style=_CARD_STYLE)


# ---------------------------------------------------------------------------
# 5. P&L distribution histogram
# ---------------------------------------------------------------------------
def _pnl_histogram(series: pd.Series) -> html.Div:
    title = "P&L % Distribution"
    if series.empty:
        fig = go.Figure()
        fig.update_layout(title=title, **_BASE_LAYOUT)
        return html.Div(dcc.Graph(figure=fig, config={"displayModeBar": False}), style=_CARD_STYLE)

    values = series.dropna().values
    bins = min(30, max(10, len(values) // 3))

    counts, bin_edges = np.histogram(values, bins=bins)
    bin_centres = (bin_edges[:-1] + bin_edges[1:]) / 2

    bar_colours = [WIN_GREEN if c > 0 else LOSS_RED for c in bin_centres]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=bin_centres,
            y=counts,
            marker_color=bar_colours,
            opacity=0.7,
            name="Trades",
            hovertemplate="P&L: %{x:.2f}%<br>Count: %{y}<extra></extra>",
        )
    )

    # Normal curve overlay
    mu, sigma = values.mean(), values.std()
    if sigma > 0:
        x_range = np.linspace(values.min(), values.max(), 200)
        normal_y = scipy_stats.norm.pdf(x_range, mu, sigma)
        # Scale to histogram counts
        bin_width = bin_edges[1] - bin_edges[0]
        normal_y_scaled = normal_y * len(values) * bin_width
        fig.add_trace(
            go.Scatter(
                x=x_range,
                y=normal_y_scaled,
                mode="lines",
                line={"color": ACCENT, "width": 2},
                name="Normal fit",
                hoverinfo="skip",
            )
        )

    fig.add_vline(x=0, line_dash="solid", line_color=BORDER)
    fig.update_layout(
        title={"text": title, "font": {"color": TEXT, "size": 13}},
        bargap=0.05,
        legend={"font": {"color": MUTED}, "bgcolor": "rgba(0,0,0,0)"},
        **_BASE_LAYOUT,
    )
    fig.update_xaxes(ticksuffix="%", **_AXIS_STYLE)
    fig.update_yaxes(**_AXIS_STYLE)

    return html.Div(_graph(fig, 280), style=_CARD_STYLE)


# ---------------------------------------------------------------------------
# 6. Win rate breakdowns
# ---------------------------------------------------------------------------
def _small_winrate_bar(
    df: pd.DataFrame,
    group_col: str,
    title: str,
) -> go.Figure:
    if df.empty or group_col not in df.columns or "outcome" not in df.columns:
        fig = go.Figure()
        fig.update_layout(title=title, **_BASE_LAYOUT, margin={"l": 50, "r": 10, "t": 35, "b": 30})
        return fig

    grouped = (
        df[df["outcome"].isin(["win", "loss"])]
        .groupby(group_col)["outcome"]
        .agg(
            total="count",
            wins=lambda x: (x == "win").sum(),
        )
        .reset_index()
    )
    grouped["win_rate"] = (grouped["wins"] / grouped["total"] * 100).round(1)
    grouped = grouped.sort_values("win_rate", ascending=True).tail(10)

    colours = [
        WIN_GREEN if r >= 55 else (ORANGE if r >= 45 else LOSS_RED)
        for r in grouped["win_rate"]
    ]

    fig = go.Figure(
        go.Bar(
            x=grouped["win_rate"],
            y=grouped[group_col],
            orientation="h",
            marker_color=colours,
            text=[f"{r:.0f}%" for r in grouped["win_rate"]],
            textposition="outside",
            textfont={"color": MUTED, "size": 10},
            hovertemplate=f"<b>%{{y}}</b><br>Win Rate: %{{x:.1f}}%<extra></extra>",
        )
    )
    fig.add_vline(x=50, line_dash="dot", line_color=MUTED)
    fig.update_layout(
        title={"text": title, "font": {"color": TEXT, "size": 12}},
        xaxis_ticksuffix="%",
        xaxis_range=[0, 110],
        **{**_BASE_LAYOUT, "margin": {"l": 80, "r": 20, "t": 35, "b": 30}},
    )
    fig.update_xaxes(**_AXIS_STYLE)
    fig.update_yaxes(**{**_AXIS_STYLE, "tickfont": {"color": MUTED, "size": 10}})
    return fig


def _winrate_breakdowns(df: pd.DataFrame) -> html.Div:
    fig_ticker = _small_winrate_bar(df, "ticker", "By Ticker")
    fig_regime = _small_winrate_bar(df, "regime", "By Regime")
    fig_signal = _small_winrate_bar(df, "signal", "By Signal")

    return html.Div(
        [
            html.H3(
                "Win Rate Breakdowns",
                style={"color": TEXT, "marginBottom": "12px", "fontSize": "14px"},
            ),
            html.Div(
                [
                    dcc.Graph(
                        figure=fig_ticker,
                        config={"displayModeBar": False},
                        style={"height": "260px", "flex": "1"},
                    ),
                    dcc.Graph(
                        figure=fig_regime,
                        config={"displayModeBar": False},
                        style={"height": "260px", "flex": "1"},
                    ),
                    dcc.Graph(
                        figure=fig_signal,
                        config={"displayModeBar": False},
                        style={"height": "260px", "flex": "1"},
                    ),
                ],
                style={"display": "flex", "gap": "12px"},
            ),
        ],
        style={**_CARD_STYLE},
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def build_layout() -> html.Div:
    """Build and return the advanced mode layout div."""
    equity_df = get_equity_curve()
    analyst_df = get_analyst_performance()
    pnl_series = get_pnl_distribution()

    # Use all trades (not just recent 10) for scatter and breakdowns
    all_trades = get_recent_trades(n=500)

    return html.Div(
        [
            # Row 1: equity + drawdown | sharpe
            html.Div(
                [
                    html.Div(_equity_drawdown_chart(equity_df), style={"flex": "2"}),
                    html.Div(_sharpe_chart(equity_df), style={"flex": "1"}),
                ],
                style={"display": "flex", "gap": "16px"},
            ),
            # Row 2: analyst bar | trade scatter
            html.Div(
                [
                    html.Div(_analyst_bar(analyst_df), style={"flex": "1"}),
                    html.Div(_trade_scatter(all_trades), style={"flex": "2"}),
                ],
                style={"display": "flex", "gap": "16px", "marginTop": "16px"},
            ),
            # Row 3: P&L histogram
            html.Div(
                _pnl_histogram(pnl_series),
                style={"marginTop": "16px"},
            ),
            # Row 4: win rate breakdowns
            html.Div(
                _winrate_breakdowns(all_trades),
                style={"marginTop": "16px"},
            ),
        ],
        style={"padding": "0"},
    )
