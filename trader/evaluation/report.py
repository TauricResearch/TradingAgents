"""Markdown for what the evaluation found."""

from __future__ import annotations

from datetime import UTC, datetime

from trader.evaluation.replay import Policy, Result, describe
from trader.evaluation.signals import HORIZONS, Flips, Row
from trader.intraday.settings import Params


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d %H:%M")


def pct(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value * 100:+.{digits}f}%"


def num(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}" if isinstance(value, float) else f"{value:,}"


def table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(" --- " for _ in headers) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def replay_table(results: list[tuple[Params, Policy, Result]]) -> str:
    """One row per configuration, the live defaults first when present."""
    rows = []
    for params, policy, result in results:
        m = result.metrics()
        rows.append([
            describe(params, policy), pct(m["return"]), pct(-m["max_drawdown"]),
            num(m["sharpe"]), num(m["trades"]), num(m["stops"]), num(m["fees"]), num(m["funding"]),
            num(m["turnover"], 0), pct(m["avg_exposure"], 0), "是" if m["halted"] else "",
        ])
    return table(
        ["配置", "收益", "最大回撤", "Sharpe(日)", "成交", "止损", "手续费", "资金费", "换手(USDT)",
         "平均敞口", "触发熔断"],
        rows,
    )


def signal_table(title: str, rows: list[Row], horizons: tuple[int, ...] = HORIZONS) -> str:
    headers = [title, "样本"]
    for h in horizons:
        headers += [f"{h}h 命中", f"{h}h 均值(bp)", f"{h}h 中位(bp)"]
    body = []
    for r in rows:
        cells = [r.group, str(r.count)]
        for h in horizons:
            cells += [pct(r.hit_rate.get(h), 0), num(r.mean_bps.get(h), 1), num(r.median_bps.get(h), 1)]
        body.append(cells)
    return table(headers, body)


def flips_table(rows: list[Flips]) -> str:
    return table(
        ["币", "信号数", "Long", "Short", "Flat", "缺失", "换向", "任何变化", "平均连续长度"],
        [[r.coin, str(r.hours), str(r.long), str(r.short), str(r.flat), str(r.missing),
          str(r.reversals), str(r.changes), f"{r.mean_run:.1f}"] for r in rows],
    )


def fills_table(result: Result, limit: int = 60) -> str:
    rows = [
        [iso(f.ts), f.inst, f"{f.qty:+.4f}", num(f.price), num(f.fee), f.reason]
        for f in result.fills[-limit:]
    ]
    return table(["时间(UTC)", "合约", "数量", "价格", "手续费", "原因"], rows)


def document(title: str, sections: list[tuple[str, str]]) -> str:
    parts = [f"# {title}", ""]
    for heading, body in sections:
        parts += [f"## {heading}", "", body, ""]
    return "\n".join(parts)
