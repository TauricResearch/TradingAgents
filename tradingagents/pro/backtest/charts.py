"""Matplotlib renderers for the backtest visual dashboard (report-only).

Each function writes one PNG and is defensive: with no data it writes a small
"no data" placeholder rather than raising, so a single empty panel never sinks
the whole report. Import is lazy/guarded — matplotlib is an optional extra
(``tradingagents[backtest-report]``). Uses the headless Agg backend.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from tradingagents.pro.backtest.agent_attribution import AgentScore  # noqa: E402
from tradingagents.pro.backtest.regime_breakdown import RegimeStats  # noqa: E402
from tradingagents.pro.backtest.trade_log import EnrichedTrade  # noqa: E402

_BULL = "#16824a"
_BEAR = "#d33b35"
_ACCENT = "#3b5bdb"


def _save(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def _placeholder(path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.text(0.5, 0.5, f"{title}\n(no data)", ha="center", va="center")
    ax.axis("off")
    _save(fig, path)


def equity_curve(
    path: Path,
    timestamps: Sequence[datetime],
    equity: Sequence[float],
    benchmark: Sequence[float] | None = None,
) -> None:
    if len(equity) < 2:
        return _placeholder(path, "Equity curve")
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(timestamps, equity, color=_ACCENT, lw=1.4, label="Strategy")
    if benchmark and len(benchmark) == len(equity):
        ax.plot(timestamps, benchmark, color="#9aa5b1", lw=1.1, ls="--",
                label="Buy & hold")
        ax.legend(loc="best", fontsize=8)
    ax.set_title("Equity curve")
    ax.set_ylabel("Equity")
    ax.grid(alpha=0.2)
    _save(fig, path)


def drawdown(path: Path, timestamps: Sequence[datetime], dd: Sequence[float]) -> None:
    if len(dd) < 2:
        return _placeholder(path, "Drawdown")
    fig, ax = plt.subplots(figsize=(10, 3.2))
    pct = [-d * 100 for d in dd]
    ax.fill_between(timestamps, pct, 0, color=_BEAR, alpha=0.35)
    ax.plot(timestamps, pct, color=_BEAR, lw=1.0)
    ax.set_title("Drawdown (underwater)")
    ax.set_ylabel("% below peak")
    ax.grid(alpha=0.2)
    _save(fig, path)


def monthly_heatmap(path: Path, monthly: Sequence[tuple[str, float]]) -> None:
    if not monthly:
        return _placeholder(path, "Monthly returns")
    import numpy as np

    years = sorted({m[:4] for m, _ in monthly})
    grid = np.full((len(years), 12), np.nan)
    yr_idx = {y: i for i, y in enumerate(years)}
    for label, ret in monthly:
        y, mm = label[:4], int(label[5:7])
        grid[yr_idx[y], mm - 1] = ret * 100
    fig, ax = plt.subplots(figsize=(10, 0.7 * len(years) + 1.6))
    vmax = max(1.0, float(np.nanmax(np.abs(grid))))
    im = ax.imshow(grid, cmap="RdYlGn", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(12))
    ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul",
                        "Aug", "Sep", "Oct", "Nov", "Dec"], fontsize=8)
    ax.set_yticks(range(len(years)))
    ax.set_yticklabels(years)
    for i in range(len(years)):
        for j in range(12):
            if not np.isnan(grid[i, j]):
                ax.text(j, i, f"{grid[i, j]:.1f}", ha="center", va="center",
                        fontsize=7)
    ax.set_title("Monthly returns (%)")
    fig.colorbar(im, ax=ax, fraction=0.025)
    _save(fig, path)


def trade_distribution(path: Path, trades: Sequence[EnrichedTrade]) -> None:
    if not trades:
        return _placeholder(path, "Trade P&L over time")
    fig, ax = plt.subplots(figsize=(10, 3.6))
    xs = range(1, len(trades) + 1)
    colors = [_BULL if t.net_pnl >= 0 else _BEAR for t in trades]
    ax.bar(xs, [t.net_pnl for t in trades], color=colors)
    ax.axhline(0, color="#333", lw=0.6)
    ax.set_title("Net P&L per trade (chronological)")
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Net P&L")
    ax.grid(alpha=0.2)
    _save(fig, path)


def win_loss_distribution(path: Path, trades: Sequence[EnrichedTrade]) -> None:
    if not trades:
        return _placeholder(path, "Win / loss")
    wins = sum(1 for t in trades if t.outcome == "Win")
    losses = sum(1 for t in trades if t.outcome == "Loss")
    be = sum(1 for t in trades if t.outcome == "Breakeven")
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.bar(["Win", "Loss", "Breakeven"], [wins, losses, be],
           color=[_BULL, _BEAR, "#9aa5b1"])
    ax.set_title("Win / loss distribution")
    ax.set_ylabel("Trades")
    for i, v in enumerate((wins, losses, be)):
        ax.text(i, v, str(v), ha="center", va="bottom", fontsize=9)
    _save(fig, path)


def pnl_histogram(path: Path, trades: Sequence[EnrichedTrade]) -> None:
    if not trades:
        return _placeholder(path, "P&L histogram")
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist([t.net_pnl for t in trades], bins=min(30, max(5, len(trades))),
            color=_ACCENT, alpha=0.8)
    ax.axvline(0, color=_BEAR, lw=1.0, ls="--")
    ax.set_title("Net P&L histogram")
    ax.set_xlabel("Net P&L")
    ax.set_ylabel("Trades")
    ax.grid(alpha=0.2)
    _save(fig, path)


def holding_time(path: Path, trades: Sequence[EnrichedTrade]) -> None:
    if not trades:
        return _placeholder(path, "Holding time")
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist([t.holding_hours / 24 for t in trades],
            bins=min(30, max(5, len(trades))), color="#7048e8", alpha=0.8)
    ax.set_title("Holding-time distribution")
    ax.set_xlabel("Holding time (days)")
    ax.set_ylabel("Trades")
    ax.grid(alpha=0.2)
    _save(fig, path)


def trade_timeline(path: Path, trades: Sequence[EnrichedTrade]) -> None:
    if not trades:
        return _placeholder(path, "Trade timeline")
    fig, ax = plt.subplots(figsize=(10, 4))
    for i, t in enumerate(trades):
        try:
            o = datetime.fromisoformat(t.opened_at)
            c = datetime.fromisoformat(t.closed_at)
        except ValueError:
            continue
        color = _BULL if t.net_pnl >= 0 else _BEAR
        ax.plot([o, c], [i, i], color=color, lw=2, marker="|")
    ax.set_title("Trade timeline (green=win, red=loss)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Trade #")
    ax.grid(alpha=0.2)
    _save(fig, path)


def performance_by_regime(path: Path, regimes: Sequence[RegimeStats]) -> None:
    if not regimes:
        return _placeholder(path, "Performance by regime")
    fig, ax = plt.subplots(figsize=(8, 4))
    labels = [r.regime for r in regimes]
    pnls = [r.total_net_pnl for r in regimes]
    ax.bar(labels, pnls, color=[_BULL if p >= 0 else _BEAR for p in pnls])
    ax.axhline(0, color="#333", lw=0.6)
    ax.set_title("Total net P&L by market regime")
    ax.set_ylabel("Net P&L")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", fontsize=8)
    _save(fig, path)


def agent_leaderboard(path: Path, agents: Sequence[AgentScore]) -> None:
    if not agents:
        return _placeholder(path, "Agent leaderboard")
    top = sorted(agents, key=lambda a: a.hit_rate, reverse=True)
    fig, ax = plt.subplots(figsize=(8, 0.4 * len(top) + 1.5))
    labels = [a.agent_id for a in top]
    rates = [a.hit_rate * 100 for a in top]
    ax.barh(labels, rates, color=_ACCENT)
    ax.set_xlabel("Hit rate (%)")
    ax.set_title("Agent accuracy leaderboard")
    ax.invert_yaxis()
    ax.grid(alpha=0.2, axis="x")
    _save(fig, path)


def strategy_comparison(path: Path, regimes: Sequence[RegimeStats]) -> None:
    """The system runs one regime-adaptive multi-agent strategy, so 'strategy'
    performance is shown as win-rate across regimes."""
    if not regimes:
        return _placeholder(path, "Strategy comparison")
    fig, ax = plt.subplots(figsize=(8, 4))
    labels = [r.regime for r in regimes]
    wr = [r.win_rate * 100 for r in regimes]
    ax.bar(labels, wr, color="#0c8599")
    ax.set_title("Win rate by regime (the strategy is regime-adaptive)")
    ax.set_ylabel("Win rate (%)")
    ax.set_ylim(0, 100)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", fontsize=8)
    _save(fig, path)
