"""Self-contained institutional report: PNG charts + one HTML file + a PDF.

Opt-in (``emit_report``) because it's heavy: it renders the matplotlib chart
suite (``backtest.charts``), inlines every PNG as base64 into a single
``report.html`` (no external files to serve), and assembles the same charts
plus a metrics table into ``report.pdf`` via matplotlib's ``PdfPages`` — so no
new dependency beyond the existing ``backtest-report`` extra (matplotlib).

Everything is derived from one backtest's recorded outputs (equity curve,
closed trades, the ExtendedReport bundle). No LLM, no fabricated numbers; empty
panels degrade to the ``charts._placeholder`` rather than raising, so a run
with no votes (deterministic strategies) still produces an honest report.
"""

from __future__ import annotations

import base64
import html
import logging
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# charts rendered in order; (filename stem, human title). Equity/drawdown/
# monthly are equity-only; the rest are trade/regime/agent level.
_CHART_ORDER = [
    ("equity", "Equity curve"),
    ("drawdown", "Drawdown"),
    ("monthly_heatmap", "Monthly returns"),
    ("pnl_histogram", "P&L histogram"),
    ("trade_distribution", "Net P&L per trade"),
    ("win_loss", "Win / loss"),
    ("holding_time", "Holding time"),
    ("trade_timeline", "Trade timeline"),
    ("performance_by_regime", "Performance by regime"),
    ("agent_leaderboard", "Agent leaderboard"),
]

# report record keys → display label + formatter kind
_PERF_ROWS = [
    ("total_return", "Total return", "pct"),
    ("max_drawdown", "Max drawdown", "pct"),
    ("sharpe", "Sharpe", "num"),
    ("sortino", "Sortino", "num"),
    ("win_rate", "Win rate", "pct"),
    ("profit_factor", "Profit factor", "num"),
    ("expectancy_r", "Expectancy (R)", "num"),
]
_EXT_ROWS = [
    ("cagr", "CAGR", "pct"),
    ("calmar", "Calmar", "num"),
    ("recovery_factor", "Recovery factor", "num"),
    ("risk_of_ruin", "Risk of ruin", "pct"),
    ("alpha", "Alpha (ann.)", "pct"),
    ("beta", "Beta", "num"),
    ("benchmark_total_return", "Buy & hold return", "pct"),
    ("max_consecutive_losses", "Max consec. losses", "int"),
]


def _fmt(value: Any, kind: str) -> str:
    if value is None:
        return "—"
    try:
        if kind == "pct":
            return f"{float(value) * 100:.2f}%"
        if kind == "int":
            return f"{int(value)}"
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value)


def _b64_png(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def generate_report(
    run_dir: Path,
    *,
    meta: dict,
    report: dict,
    extended: dict | None,
    equity_curve: Sequence[float],
    timestamps: Sequence[datetime],
    benchmark_closes: Sequence[float],
    initial_equity: float,
    trades: Sequence[Any],
    states_by_rec_id: dict[str, dict],
) -> list[str]:
    """Render charts + report.html + report.pdf into ``run_dir``.

    Returns the generated file names (relative to ``run_dir``). Raises
    ``ImportError`` when matplotlib is absent — the caller guards and skips.
    """
    from tradingagents.pro.backtest import charts
    from tradingagents.pro.backtest.agent_attribution import agent_attribution
    from tradingagents.pro.backtest.regime_breakdown import regime_breakdown
    from tradingagents.pro.backtest.report import buy_hold_curve, drawdown_curve
    from tradingagents.pro.backtest.trade_log import enrich_trades

    run_dir.mkdir(parents=True, exist_ok=True)
    chart_dir = run_dir / "charts"

    enriched = enrich_trades(list(trades), states_by_rec_id, initial_equity)
    regimes = regime_breakdown(enriched)
    agents = agent_attribution(enriched)
    benchmark = buy_hold_curve(list(benchmark_closes), initial_equity)
    dd = (extended or {}).get("drawdown_curve") or drawdown_curve(list(equity_curve))
    monthly = (extended or {}).get("monthly_returns") or []

    # align lengths defensively (benchmark/timestamps map 1:1 to the curve)
    n = min(len(equity_curve), len(timestamps))
    ts = list(timestamps[:n])
    eq = list(equity_curve[:n])
    bench = benchmark[:n] if len(benchmark) >= n else None

    charts.equity_curve(chart_dir / "equity.png", ts, eq, bench)
    charts.drawdown(chart_dir / "drawdown.png", ts, list(dd[:n]))
    charts.monthly_heatmap(chart_dir / "monthly_heatmap.png", monthly)
    charts.pnl_histogram(chart_dir / "pnl_histogram.png", enriched)
    charts.trade_distribution(chart_dir / "trade_distribution.png", enriched)
    charts.win_loss_distribution(chart_dir / "win_loss.png", enriched)
    charts.holding_time(chart_dir / "holding_time.png", enriched)
    charts.trade_timeline(chart_dir / "trade_timeline.png", enriched)
    charts.performance_by_regime(chart_dir / "performance_by_regime.png", regimes)
    charts.agent_leaderboard(chart_dir / "agent_leaderboard.png", agents)

    chart_files = [f"charts/{stem}.png" for stem, _ in _CHART_ORDER
                   if (chart_dir / f"{stem}.png").is_file()]

    _write_html(run_dir / "report.html", meta, report, extended, chart_dir)
    _write_pdf(run_dir / "report.pdf", meta, report, extended, chart_dir)

    return ["report.html", "report.pdf", *chart_files]


def _metric_rows(report: dict, extended: dict | None) -> list[tuple[str, str]]:
    rows = [(label, _fmt(report.get(key), kind)) for key, label, kind in _PERF_ROWS]
    if extended:
        rows += [(label, _fmt(extended.get(key), kind))
                 for key, label, kind in _EXT_ROWS]
    return rows


def _write_html(path: Path, meta: dict, report: dict, extended: dict | None,
                chart_dir: Path) -> None:
    esc = html.escape
    title = esc(str(meta.get("title", "Backtest report")))
    subtitle = " · ".join(
        esc(str(meta.get(k))) for k in ("symbol", "timeframe", "duration", "window")
        if meta.get(k))
    rows_html = "\n".join(
        f"<tr><td>{esc(label)}</td><td class='v'>{esc(value)}</td></tr>"
        for label, value in _metric_rows(report, extended))
    imgs_html = "\n".join(
        f"<figure><figcaption>{esc(caption)}</figcaption>"
        f"<img alt='{esc(caption)}' src='data:image/png;base64,{_b64_png(p)}'></figure>"
        for stem, caption in _CHART_ORDER
        if (p := chart_dir / f"{stem}.png").is_file())
    path.write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ font: 14px/1.5 -apple-system, system-ui, sans-serif; margin: 2rem auto;
          max-width: 960px; color: #1a1d24; }}
  h1 {{ margin-bottom: .2rem; }} .sub {{ color: #6b7280; margin-bottom: 1.5rem; }}
  table {{ border-collapse: collapse; margin-bottom: 2rem; min-width: 320px; }}
  td {{ padding: .35rem .8rem; border-bottom: 1px solid #eef0f3; }}
  td.v {{ text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }}
  figure {{ margin: 0 0 1.5rem; }} img {{ width: 100%; border: 1px solid #eef0f3; }}
  figcaption {{ font-weight: 600; margin-bottom: .4rem; }}
</style></head><body>
<h1>{title}</h1><div class="sub">{subtitle}</div>
<table>{rows_html}</table>
{imgs_html}
</body></html>""", encoding="utf-8")


def _write_pdf(path: Path, meta: dict, report: dict, extended: dict | None,
               chart_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    with PdfPages(path) as pdf:
        # cover page: title + the metrics table
        fig, ax = plt.subplots(figsize=(8.27, 11.69))  # A4 portrait
        ax.axis("off")
        ax.text(0.5, 0.96, str(meta.get("title", "Backtest report")),
                ha="center", va="top", fontsize=18, weight="bold")
        sub = " · ".join(str(meta.get(k)) for k in
                         ("symbol", "timeframe", "duration", "window") if meta.get(k))
        ax.text(0.5, 0.92, sub, ha="center", va="top", fontsize=10, color="#6b7280")
        rows = _metric_rows(report, extended)
        table = ax.table(cellText=rows, colWidths=[0.5, 0.3],
                         cellLoc="left", loc="center", bbox=[0.15, 0.1, 0.7, 0.75])
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        pdf.savefig(fig)
        plt.close(fig)
        # one page per chart
        for stem, caption in _CHART_ORDER:
            p = chart_dir / f"{stem}.png"
            if not p.is_file():
                continue
            img = plt.imread(str(p))
            fig, ax = plt.subplots(figsize=(11, 6))
            ax.imshow(img)
            ax.axis("off")
            ax.set_title(caption)
            pdf.savefig(fig)
            plt.close(fig)
