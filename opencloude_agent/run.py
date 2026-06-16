"""OpenClaude continuous paper-trading agent."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yfinance as yf


DEFAULT_WATCHLIST = ["AAPL", "MSFT", "NVDA", "TSLA", "SPY"]


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Opportunity:
    ticker: str
    score: float
    reason: str
    snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "score": self.score,
            "reason": self.reason,
            "snapshot": self.snapshot,
        }


@dataclass(slots=True)
class PaperPortfolio:
    cash_usd: float = 10_000.0
    positions: dict[str, float] = field(default_factory=dict)

    def to_dict(self, latest_prices: dict[str, float] | None = None) -> dict[str, Any]:
        latest_prices = latest_prices or {}
        equity = sum(
            quantity * latest_prices.get(ticker, 0.0)
            for ticker, quantity in self.positions.items()
        )
        return {
            "cash_usd": self.cash_usd,
            "positions": dict(self.positions),
            "equity_usd": equity,
            "total_value_usd": self.cash_usd + equity,
        }

    def simulate_buy(self, ticker: str, quantity: float, price: float) -> float:
        if price <= 0:
            return 0.0
        affordable = self.cash_usd // price
        quantity = min(quantity, affordable)
        if quantity <= 0:
            return 0.0
        cost = quantity * price
        self.cash_usd -= cost
        self.positions[ticker] = self.positions.get(ticker, 0.0) + quantity
        return cost

    def simulate_sell(self, ticker: str, quantity: float, price: float) -> float:
        quantity = min(quantity, self.positions.get(ticker, 0.0))
        if quantity <= 0:
            return 0.0
        proceeds = quantity * price
        self.cash_usd += proceeds
        self.positions[ticker] -= quantity
        if self.positions[ticker] <= 0:
            self.positions.pop(ticker, None)
        return proceeds


class MarketWatcher:
    def __init__(self, benchmark_ticker: str = "SPY"):
        self.benchmark_ticker = benchmark_ticker

    def snapshot(self, watchlist: Iterable[str]) -> dict[str, dict[str, Any]]:
        tickers = list(dict.fromkeys([*watchlist, self.benchmark_ticker]))
        data = yf.download(
            tickers=tickers,
            period="60d",
            interval="1d",
            group_by="ticker",
            progress=False,
            auto_adjust=False,
            threads=False,
        )
        return self.snapshot_from_dataframe(data, watchlist)

    def snapshot_from_dataframe(self, data: pd.DataFrame, watchlist: Iterable[str]) -> dict[str, dict[str, Any]]:
        benchmark_close = self._latest_close(self._ticker_frame(data, self.benchmark_ticker))
        benchmark_return_20d = None
        benchmark_frame = self._ticker_frame(data, self.benchmark_ticker)
        if benchmark_close is not None:
            benchmark_return_20d = self._returns(benchmark_frame, benchmark_close).get("return_20d")
        output: dict[str, dict[str, Any]] = {}

        for ticker in watchlist:
            frame = self._ticker_frame(data, ticker)
            close = self._latest_close(frame)
            volume = self._latest_volume(frame)
            returns = self._returns(frame, close)
            momentum_20d = returns.get("return_20d")
            relative_strength = None
            if momentum_20d is not None and benchmark_return_20d is not None:
                relative_strength = momentum_20d - benchmark_return_20d
            output[ticker] = {
                "ticker": ticker,
                "close": close,
                "volume": volume,
                "return_1d": returns.get("return_1d"),
                "return_5d": returns.get("return_5d"),
                "return_20d": momentum_20d,
                "benchmark_return_20d": benchmark_return_20d,
                "relative_strength_20d": relative_strength,
                "timestamp": utc_now().isoformat() + "Z",
            }
        return output

    @staticmethod
    def _ticker_frame(data: pd.DataFrame, ticker: str) -> pd.DataFrame:
        if not isinstance(data, pd.DataFrame) or data.empty:
            return pd.DataFrame()
        if isinstance(data.columns, pd.MultiIndex) and ticker in data.columns.get_level_values(0):
            return data[ticker].copy()
        if ticker in data.columns:
            return data[[ticker]].copy()
        return pd.DataFrame()

    @staticmethod
    def _latest_close(data: pd.DataFrame) -> float | None:
        if data.empty or "Close" not in data:
            return None
        close = data["Close"].dropna()
        return float(close.iloc[-1]) if not close.empty else None

    @staticmethod
    def _latest_volume(data: pd.DataFrame) -> float | None:
        if data.empty or "Volume" not in data:
            return None
        volume = data["Volume"].dropna()
        return float(volume.iloc[-1]) if not volume.empty else None

    @staticmethod
    def _returns(data: pd.DataFrame, latest_close: float | None) -> dict[str, float | None]:
        if data.empty or "Close" not in data or latest_close is None:
            return {"return_1d": None, "return_5d": None, "return_20d": None}
        close = data["Close"].dropna()
        if close.empty:
            return {"return_1d": None, "return_5d": None, "return_20d": None}

        def pct_back(days: int) -> float | None:
            if len(close) <= days:
                return None
            old_close = float(close.iloc[-days - 1])
            return latest_close / old_close - 1.0 if old_close else None

        return {
            "return_1d": pct_back(1),
            "return_5d": pct_back(5),
            "return_20d": pct_back(20),
        }


class OpportunityScanner:
    def __init__(self, max_candidates: int = 3):
        self.max_candidates = max_candidates

    def scan(self, market_snapshot: dict[str, dict[str, Any]]) -> list[Opportunity]:
        scored: list[Opportunity] = []
        for ticker, item in market_snapshot.items():
            if item.get("close") is None:
                continue
            score, reason = self._score(ticker, item)
            scored.append(Opportunity(ticker=ticker, score=score, reason=reason, snapshot=item))
        scored.sort(key=lambda opportunity: opportunity.score, reverse=True)
        return scored[: self.max_candidates]

    @staticmethod
    def _score(ticker: str, item: dict[str, Any]) -> tuple[float, str]:
        momentum_20d = item.get("return_20d") or 0.0
        relative_strength = item.get("relative_strength_20d") or 0.0
        volume = item.get("volume") or 0.0
        score = 50.0 + relative_strength * 100.0 + momentum_20d * 50.0
        if volume > 0:
            score += min(volume / 10_000_000.0, 5.0)
        reason = (
            f"{ticker}: 20d return {momentum_20d:.2%}; "
            f"relative strength {relative_strength:.2%}; volume {volume:,.0f}"
        )
        return score, reason


class RiskGuard:
    def evaluate(
        self,
        portfolio: dict[str, Any],
        opportunities: list[dict[str, Any]],
        max_single_position_ratio: float = 0.35,
    ) -> dict[str, Any]:
        total_value = portfolio.get("total_value_usd") or 0.0
        positions = portfolio.get("positions", {})
        risks: list[str] = []
        warnings: list[str] = []

        for ticker, quantity in positions.items():
            ratio = (quantity * 1.0) / total_value if total_value else 0.0
            if ratio > max_single_position_ratio:
                risks.append(f"{ticker} exceeds {max_single_position_ratio:.0%} portfolio weight")

        if len(positions) >= 5:
            warnings.append("Portfolio has 5 or more positions.")
        if not opportunities:
            warnings.append("No opportunities selected for this cycle.")

        if risks:
            overall = "blocked_by_risk"
        elif warnings:
            overall = "watch"
        else:
            overall = "safe"

        return {"overall_level": overall, "risks": risks, "warnings": warnings}


class ReportWriter:
    def __init__(self, results_dir: Path):
        self.results_dir = Path(results_dir)
        self.continuous_dir = self.results_dir / "continuous"
        self.continuous_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _to_jsonable(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: ReportWriter._to_jsonable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [ReportWriter._to_jsonable(item) for item in value]
        return value

    def append_text(self, filename: str, text: str) -> None:
        with (self.continuous_dir / filename).open("a", encoding="utf-8") as file:
            file.write(text)
            if not text.endswith("\n"):
                file.write("\n")

    def append_jsonl(self, filename: str, payload: dict[str, Any]) -> None:
        with (self.continuous_dir / filename).open("a", encoding="utf-8") as file:
            file.write(json.dumps(self._to_jsonable(payload), ensure_ascii=False) + "\n")

    def write_daily_summary(self, report: dict[str, Any]) -> None:
        lines = [
            f"# Continuous Trading Summary — {report['timestamp']}",
            "",
            f"Risk level: `{report.get('risk_summary', {}).get('overall_level', 'unknown')}`",
            "",
            "## Portfolio",
            "",
            f"Cash: `${report.get('portfolio', {}).get('cash_usd', 0):,.2f}`",
            f"Equity: `${report.get('portfolio', {}).get('equity_usd', 0):,.2f}`",
            f"Total value: `${report.get('portfolio', {}).get('total_value_usd', 0):,.2f}`",
            "",
            "## Opportunities",
            "",
        ]
        if report.get("opportunities"):
            for item in report["opportunities"]:
                lines.append(f"- `{item.get('ticker')}` score {item.get('score')}: {item.get('reason')}")
        else:
            lines.append("- No opportunities selected.")

        lines.extend(["", "## Decisions", ""])
        if report.get("decisions"):
            for item in report["decisions"]:
                lines.append(
                    f"- `{item.get('ticker')}` {item.get('action')} {item.get('quantity')} "
                    f"@ ${item.get('estimated_price', 0):,.2f} — {item.get('rationale')}"
                )
        else:
            lines.append("- No paper trades recommended.")
        (self.continuous_dir / "daily_summary.md").write_text("\n".join(lines), encoding="utf-8")


class OpenClaudeContinuousAgent:
    def __init__(
        self,
        results_dir: str | Path = "results",
        watchlist: list[str] | None = None,
        max_candidates: int = 3,
    ):
        self.results_dir = Path(results_dir)
        self.watchlist = watchlist or list(DEFAULT_WATCHLIST)
        self.portfolio = PaperPortfolio()
        self.market_watcher = MarketWatcher()
        self.scanner = OpportunityScanner(max_candidates=max_candidates)
        self.risk_guard = RiskGuard()
        self.report_writer = ReportWriter(self.results_dir)

    def run_once(self) -> dict[str, Any]:
        snapshot = self.market_watcher.snapshot(self.watchlist)
        opportunities = self.scanner.scan(snapshot)
        decisions = self._make_paper_decisions(opportunities, snapshot)
        risk_summary = self.risk_guard.evaluate(
            self.portfolio.to_dict(self._latest_prices(snapshot)),
            [opportunity.to_dict() for opportunity in opportunities],
        )
        portfolio_state = self.portfolio.to_dict(self._latest_prices(snapshot))
        report = {
            "cycle_id": utc_now().strftime("%Y%m%dT%H%M%SZ"),
            "timestamp": utc_now().isoformat() + "Z",
            "portfolio": portfolio_state,
            "opportunities": [opportunity.to_dict() for opportunity in opportunities],
            "decisions": decisions,
            "risk_summary": risk_summary,
        }
        self._persist_cycle(snapshot, opportunities, decisions, risk_summary, report)
        return report

    def run_watch_loop(self, interval_seconds: int = 3600) -> None:
        while True:
            self.run_once()
            time.sleep(interval_seconds)

    def _make_paper_decisions(
        self,
        opportunities: list[Opportunity],
        snapshot: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        decisions: list[dict[str, Any]] = []
        for opportunity in opportunities:
            ticker = opportunity.ticker
            price = snapshot[ticker].get("close")
            if not price:
                continue
            action = "buy" if opportunity.score >= 60 else "hold"
            quantity = 0
            value = 0.0
            if action == "buy":
                allocation = max(self.portfolio.cash_usd * 0.10, 1000.0)
                quantity = int(allocation // float(price))
                value = self.portfolio.simulate_buy(ticker, quantity, float(price))
            decisions.append(
                {
                    "ticker": ticker,
                    "action": action,
                    "quantity": quantity,
                    "estimated_price": float(price),
                    "estimated_value_usd": value,
                    "rationale": opportunity.reason,
                    "risk_level": "paper_only",
                    "timestamp": utc_now().isoformat() + "Z",
                }
            )
        return decisions

    def _persist_cycle(
        self,
        snapshot: dict[str, dict[str, Any]],
        opportunities: list[Opportunity],
        decisions: list[dict[str, Any]],
        risk_summary: dict[str, Any],
        report: dict[str, Any],
    ) -> None:
        self.report_writer.append_jsonl("watch_log.jsonl", {"timestamp": report["timestamp"], "snapshot": snapshot})
        self.report_writer.append_text(
            "log.txt",
            f"{report['timestamp']} cycle_id={report['cycle_id']} risk={risk_summary.get('overall_level')} "
            f"opportunities={len(opportunities)} decisions={len(decisions)}",
        )
        for opportunity in opportunities:
            self.report_writer.append_jsonl("opportunities.jsonl", opportunity.to_dict())
            self.report_writer.append_text("log.txt", f"Opportunity: {opportunity.ticker} score={opportunity.score} {opportunity.reason}")
        for decision in decisions:
            self.report_writer.append_jsonl("decisions.jsonl", decision)
            self.report_writer.append_text("log.txt", f"Decision: {decision['ticker']} {decision['action']} {decision['quantity']} @ ${decision['estimated_price']:.2f} - {decision['rationale']}")
        self.report_writer.write_daily_summary(report)

    @staticmethod
    def _latest_prices(snapshot: dict[str, dict[str, Any]]) -> dict[str, float]:
        return {
            ticker: item["close"]
            for ticker, item in snapshot.items()
            if item.get("close") is not None
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenClaude continuous paper-trading agent")
    parser.add_argument("--watchlist", default=",".join(DEFAULT_WATCHLIST))
    parser.add_argument("--max-candidates", type=int, default=3)
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=3600)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    agent = OpenClaudeContinuousAgent(
        watchlist=[item.strip() for item in args.watchlist.split(",") if item.strip()],
        max_candidates=args.max_candidates,
        results_dir=args.results_dir,
    )
    if args.watch:
        agent.run_watch_loop(interval_seconds=args.interval_seconds)
        return 0
    print(json.dumps(agent.run_once(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
