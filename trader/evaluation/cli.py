"""python -m trader evaluate fetch | replay | rerun | signals: the offline evaluation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from trader.evaluation import report as md, signals as sq
from trader.evaluation.history import HOUR_MS, HistoryStore
from trader.evaluation.market import HistoricalOKX
from trader.evaluation.replay import (
    Signal,
    parse_grid,
    replay,
    signals_from_json,
    signals_from_ledger,
)
from trader.evaluation.rerun import cache_summary, rerun
from trader.intraday.settings import SIGNAL_BAR, SIGNAL_HOURS
from trader.intraday.signal import Signaler
from trader.ledger import Ledger
from trader.okx import OKX
from trader.settings import WATCHLIST, Settings

evaluate_app = typer.Typer(add_completion=False, no_args_is_help=True)

ATR_LOOKBACK_HOURS = 60   # covers any atr_bars a grid is likely to try, plus the engine's margin
FORWARD_HOURS = 24        # the longest horizon the signal study looks ahead


@evaluate_app.callback()
def evaluate_main() -> None:
    """Offline evaluation of the intraday rules: cached history, replays, signal quality."""


def store_path(settings: Settings) -> Path:
    return settings.home / "evaluation" / "history.sqlite"


def parse_time(text: str) -> int:
    """UTC milliseconds of "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM"."""
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(text, fmt).replace(tzinfo=UTC).timestamp() * 1000)
        except ValueError:
            continue
    raise typer.BadParameter(f"时间要写成 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM（UTC），不是 {text!r}")


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def _range(start: str, end: str | None) -> tuple[int, int]:
    start_ms = parse_time(start)
    end_ms = parse_time(end) if end else _now_ms() - _now_ms() % HOUR_MS
    if end_ms <= start_ms:
        raise typer.BadParameter("结束时间要晚于开始时间")
    return start_ms, end_ms


def fill(
    store: HistoryStore, start_ms: int, end_ms: int, bars: tuple[str, ...] = ("1m", "1H"),
    for_rerun: bool = False,
) -> None:
    """Fetch what the store lacks for a replay or signal study of ``[start_ms, end_ms)``;
    ``for_rerun`` adds what the signal's prompt reads (its bars, funding ahead, open
    interest)."""
    okx, now = OKX(), _now_ms()
    if for_rerun:
        bars = (*bars, SIGNAL_BAR)
    for coin in WATCHLIST:
        store.ensure_spec(okx, coin.swap)
        for bar in bars:
            lookback = ATR_LOOKBACK_HOURS * HOUR_MS if bar == "1H" else 2 * HOUR_MS
            if bar == SIGNAL_BAR:
                lookback = (SIGNAL_HOURS + 1) * HOUR_MS
            n = store.ensure_bars(okx, coin.swap, bar, start_ms - lookback, end_ms + FORWARD_HOURS * HOUR_MS, now)
            if n:
                typer.echo(f"{coin.swap} {bar}: 补了 {n} 根 K 线")
        ahead = 17 * HOUR_MS if for_rerun else HOUR_MS  # the prompt reads the settlement after the hour
        n = store.ensure_funding(okx, coin.swap, start_ms - HOUR_MS, end_ms + ahead, now)
        if n:
            typer.echo(f"{coin.swap} 资金费: 补了 {n} 次结算")
        if for_rerun:
            n = store.ensure_open_interest(okx, coin.swap, start_ms - 3 * HOUR_MS, end_ms, now)
            if n:
                typer.echo(f"{coin.swap} 持仓量: 补了 {n} 个小时点")


def _signals(settings: Settings, ledger: Path | None, signals_json: Path | None,
             start_ms: int, end_ms: int) -> list[Signal]:
    if signals_json is not None:
        return [s for s in signals_from_json(signals_json) if start_ms <= s.ts < end_ms]
    path = ledger or settings.intraday_ledger_path
    if not path.exists():
        raise typer.BadParameter(f"没有这个账本：{path}")
    return signals_from_ledger(path, start_ms, end_ms)


@evaluate_app.command("fetch")
def fetch_command(
    start: str = typer.Argument(..., help="开始（UTC），YYYY-MM-DD 或 YYYY-MM-DDTHH:MM"),
    end: str | None = typer.Argument(None, help="结束（UTC），缺省到当前整点"),
) -> None:
    """Cache the watchlist's 1m and 1H candles, funding and specs for a period."""
    settings = Settings.from_env()
    start_ms, end_ms = _range(start, end)
    store = HistoryStore(store_path(settings))
    fill(store, start_ms, end_ms)
    typer.echo(f"行情缓存在 {store.path}")


@evaluate_app.command("replay")
def replay_command(
    start: str = typer.Argument(..., help="开始（UTC）"),
    end: str | None = typer.Argument(None, help="结束（UTC），缺省到当前整点"),
    ledger: Annotated[Path | None, typer.Option(help="取信号的日内账本，缺省为本机的")] = None,
    signals_json: Annotated[Path | None, typer.Option(help="或从 JSON 文件取信号")] = None,
    capital: float = typer.Option(10_000.0, help="起始资金 USDT"),
    param: Annotated[list[str] | None, typer.Option(help="引擎参数网格，如 stop_mult=2,2.5,3")] = None,
    policy: Annotated[list[str] | None, typer.Option(
        help="策略层网格，如 conviction_weights=0.5/1/1 flip_min_conviction=2"
    )] = None,
    out: Annotated[Path | None, typer.Option(help="把报告写到这个 Markdown 文件")] = None,
    no_fetch: bool = typer.Option(False, "--no-fetch", help="不补拉行情，只用缓存"),
) -> None:
    """Replay the intraday engine over recorded signals, for one or a grid of configurations."""
    settings = Settings.from_env()
    start_ms, end_ms = _range(start, end)
    store = HistoryStore(store_path(settings))
    if not no_fetch:
        fill(store, start_ms, end_ms)
    signals = _signals(settings, ledger, signals_json, start_ms, end_ms)
    if not signals:
        typer.echo("这段时间没有信号", err=True)
        raise typer.Exit(1)
    grid = parse_grid(param or [], policy or [])
    results = []
    for params, pol in grid:
        result = replay(store, signals, start_ms, end_ms, params=params, policy=pol, capital=capital)
        results.append((params, pol, result))
    results.sort(key=lambda r: r[2].metrics()["return"], reverse=True)
    body = md.replay_table(results)
    typer.echo(body)
    if out is not None:
        sections = [
            ("范围", f"{md.iso(start_ms)} → {md.iso(end_ms)} UTC，{len(signals)} 条信号，起始 {capital:,.0f} USDT，"
                   f"{len(results)} 个配置。"),
            ("配置对比", body),
        ]
        if len(results) == 1:
            sections.append(("成交", md.fills_table(results[0][2])))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md.document("日内规则层回放", sections))
        typer.echo(f"报告写到 {out}")


@evaluate_app.command("rerun")
def rerun_command(
    start: str = typer.Argument(..., help="开始（UTC）"),
    end: str | None = typer.Argument(None, help="结束（UTC），缺省到当前整点"),
    cache: Annotated[Path | None, typer.Option(
        help="存信号的账本文件，缺省为 TRADER_HOME/evaluation/rerun-<模型>-<提示词>.sqlite；"
             "可直接作为 replay/signals 的 --ledger"
    )] = None,
    budget: Annotated[float | None, typer.Option(help="本次最多花多少美元，花到即停（可续跑）")] = None,
    workers: int = typer.Option(3, help="同时问模型的币数"),
    capital: float = typer.Option(10_000.0, help="引擎起始资金 USDT"),
    no_fetch: bool = typer.Option(False, "--no-fetch", help="不补拉行情，只用缓存"),
) -> None:
    """Ask the live signal (same prompt, same model) what it would have said each hour
    of the period, with the engine trading its answers; cached, resumable, budgeted."""
    settings = Settings.from_env()
    start_ms, end_ms = _range(start, end)
    store = HistoryStore(store_path(settings))
    if not no_fetch:
        fill(store, start_ms, end_ms, for_rerun=True)
    market = HistoricalOKX(store, start_ms)
    signaler = Signaler(settings, market)
    print_ = signaler.fingerprint()
    path = cache or store_path(settings).with_name(f"rerun-{print_['model']}-{print_['prompt']}.sqlite")
    ledger = Ledger(path)
    before = cache_summary(ledger)
    typer.echo(f"模型 {print_['model']}，提示词 {print_['prompt']}；缓存 {path}："
               f"已有 {before['hours']} 小时 {before['signals']} 条信号，累计 {before['cost_usd']:.2f} 美元")
    result, stats, stopped = rerun(
        store, ledger, signaler, market, start_ms, end_ms, budget_usd=budget, workers=workers,
        watchlist=WATCHLIST, capital=capital, log=typer.echo,
    )
    typer.echo(
        f"本次：{stats.hours} 小时，{stats.calls} 次调用（{stats.failures} 次失败），"
        f"复用 {stats.cached} 条，花费 {stats.spent:.2f} 美元"
    )
    for line in stats.errors[-10:]:
        typer.echo(f"  失败：{line}", err=True)
    if stopped is not None:
        typer.echo(f"提前停止：{stopped}", err=True)
        raise typer.Exit(2)
    assert result is not None
    typer.echo(md.replay_table([(result.params, result.policy, result)]))


@evaluate_app.command("signals")
def signals_command(
    start: str = typer.Argument(..., help="开始（UTC）"),
    end: str | None = typer.Argument(None, help="结束（UTC），缺省到当前整点"),
    ledger: Annotated[Path | None, typer.Option(help="取信号的日内账本，缺省为本机的")] = None,
    signals_json: Annotated[Path | None, typer.Option(help="或从 JSON 文件取信号")] = None,
    out: Annotated[Path | None, typer.Option(help="把报告写到这个 Markdown 文件")] = None,
    no_fetch: bool = typer.Option(False, "--no-fetch", help="不补拉行情，只用缓存"),
) -> None:
    """Measure the signals on their own: forward returns by coin, conviction and direction."""
    settings = Settings.from_env()
    start_ms, end_ms = _range(start, end)
    store = HistoryStore(store_path(settings))
    if not no_fetch:
        fill(store, start_ms, end_ms, bars=("1m",))
    signals = _signals(settings, ledger, signals_json, start_ms, end_ms)
    swap_of = {c.research: c.swap for c in WATCHLIST}
    outcomes = sq.outcomes(store, signals, swap_of)
    directional = sq.directional(outcomes)
    sections = [
        ("范围", f"{md.iso(start_ms)} → {md.iso(end_ms)} UTC，{len(signals)} 条信号，其中有方向的 {len(directional)} 条。"
               " 收益按信号方向计（Short 在下跌时为正），单位基点；Flat 行的收益是它错过的原始涨跌。"),
        ("按方向", md.signal_table("方向", sq.summarize(outcomes, sq.by_direction))),
        ("按币（只算有方向的）", md.signal_table("币", sq.summarize(directional, sq.by_coin))),
        ("按信心（只算有方向的）", md.signal_table("信心", sq.summarize(directional, sq.by_conviction))),
        ("换向", md.flips_table(sq.flips(signals))),
    ]
    text = md.document("日内信号质量", sections)
    typer.echo(text)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
        typer.echo(f"报告写到 {out}")
