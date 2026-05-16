"""Interactive candlestick + volume chart for analysis reports.

Uses plotly via NiceGUI's ``ui.plotly()`` for zero-JS charting.
Fetches OHLCV data from yfinance at render time — the ticker and
date are already known from ``AnalysisRow`` or the running config.

See also: PLAN-features-v2.md, Feature 1.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from nicegui import ui

logger = logging.getLogger(__name__)

# ── Defaults ──────────────────────────────────────────────────────────────

_LOOKBACK_DAYS = 90  # calendar days → ~60 trading days
_CHART_HEIGHT = 340
_SMA_PERIOD = 20


# ── Data fetching ─────────────────────────────────────────────────────────


def _fetch_ohlcv(
    ticker: str,
    end_date: str,
    lookback_days: int = _LOOKBACK_DAYS,
) -> Any | None:
    """Fetch OHLCV DataFrame via yfinance, returning None on failure."""
    try:
        import yfinance as yf

        end = datetime.date.fromisoformat(end_date)
        start = end - datetime.timedelta(days=lookback_days)
        df = yf.Ticker(ticker).history(
            start=start.isoformat(),
            end=(end + datetime.timedelta(days=1)).isoformat(),
        )
        if df.empty:
            logger.warning("No price data for %s (%s → %s)", ticker, start, end)
            return None
        return df
    except Exception:
        logger.exception("Failed to fetch price data for %s", ticker)
        return None


# ── Chart figure builder ──────────────────────────────────────────────────


def _build_figure(
    df: Any,
    ticker: str,
    analysis_date: str,
) -> go.Figure:
    """Build a dark-themed candlestick + volume plotly figure."""
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.7, 0.3],
    )

    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Price",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ),
        row=1,
        col=1,
    )

    # 20-day SMA overlay
    if len(df) >= _SMA_PERIOD:
        sma = df["Close"].rolling(window=_SMA_PERIOD).mean()
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=sma,
                name=f"SMA {_SMA_PERIOD}",
                line={"color": "#ffa726", "width": 1.5},
            ),
            row=1,
            col=1,
        )

    # Volume bars
    colors = [
        "#26a69a" if c >= o else "#ef5350"
        for o, c in zip(df["Open"], df["Close"], strict=False)
    ]
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["Volume"],
            name="Volume",
            marker_color=colors,
            opacity=0.5,
        ),
        row=2,
        col=1,
    )

    # Vertical line at analysis date (shape + annotation for plotly 6.x compat)
    try:
        analysis_dt = datetime.date.fromisoformat(analysis_date)
        dt_val = datetime.datetime(analysis_dt.year, analysis_dt.month, analysis_dt.day)
        fig.add_shape(
            type="line",
            x0=dt_val, x1=dt_val,
            y0=0, y1=1,
            yref="paper",
            line={"color": "#7e57c2", "dash": "dash", "width": 1},
        )
        fig.add_annotation(
            x=dt_val, y=1, yref="paper",
            text="Analysis",
            showarrow=False,
            font={"color": "#7e57c2", "size": 11},
            yshift=10,
        )
    except ValueError:
        pass

    # Dark theme layout
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(30,30,30,0.8)",
        height=_CHART_HEIGHT,
        margin={"l": 50, "r": 20, "t": 30, "b": 20},
        showlegend=False,
        xaxis_rangeslider_visible=False,
        title={
            "text": f"{ticker} Price Action",
            "font": {"size": 14, "color": "#bbb"},
            "x": 0.01,
            "xanchor": "left",
        },
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.05)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)")
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Vol", row=2, col=1)

    return fig


# ── Public component ──────────────────────────────────────────────────────


class PriceChart:
    """Reusable price chart component.

    Usage::

        chart = PriceChart(ticker="AAPL", analysis_date="2025-05-14")
        chart.build()          # renders immediately (fetches data inline)
    """

    def __init__(self, ticker: str, analysis_date: str) -> None:
        self._ticker = ticker.upper().strip()
        self._date = analysis_date

    def build(self) -> None:
        """Render a spinner, then fetch data off the event loop and show chart.

        PERF-01: Uses NiceGUI's run.io_bound to avoid blocking the ASGI
        event loop during yfinance HTTP requests (1-5s per chart).
        """
        # Placeholder while data loads
        container = ui.column().classes("w-full")
        with container:
            spinner = ui.row().classes("w-full justify-center q-pa-sm")
            with spinner:
                ui.spinner("dots", size="lg", color="grey")
                ui.label("Loading chart...").classes("text-caption text-grey q-ml-sm")

        async def _load_chart() -> None:
            from nicegui import run
            df = await run.io_bound(_fetch_ohlcv, self._ticker, self._date)
            container.clear()
            with container:
                if df is None:
                    with ui.card().classes("w-full ta-chart-fallback"):
                        ui.label(
                            f"Price chart unavailable for {self._ticker}"
                        ).classes("text-caption text-grey")
                    return
                fig = _build_figure(df, self._ticker, self._date)
                ui.plotly(fig).classes("w-full")

        ui.timer(0.01, _load_chart, once=True)
