"""Batch multi-ticker analysis helpers.

This module keeps file parsing and cross-ticker summary generation separate
from the interactive CLI so the behavior is easy to test without running LLMs.
"""

from __future__ import annotations

import csv
import datetime
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Literal, Sequence

from markdown_it import MarkdownIt

from cli.llm_config import LLMConfigOverrides
from cli.models import AnalystType
from cli.utils import normalize_ticker_symbol
from tradingagents.agents.utils.rating import parse_rating

if TYPE_CHECKING:
    from tradingagents.allocation import AllocationPlan, AllocationPolicy


RATING_RANK = {
    "Buy": 5,
    "Overweight": 4,
    "Hold": 3,
    "Underweight": 2,
    "Sell": 1,
}


@dataclass(frozen=True)
class PortfolioHolding:
    ticker: str
    quantity: float | None = None
    average_cost: float | None = None
    market_value: float | None = None
    target_weight: float | None = None
    notes: str | None = None


@dataclass(frozen=True)
class BatchTickerResult:
    ticker: str
    status: Literal["success", "failed"]
    rating: str | None = None
    trader_action: str | None = None
    executive_summary: str | None = None
    report_path: Path | None = None
    holding: PortfolioHolding | None = None
    elapsed_seconds: float | None = None
    error: str | None = None


def parse_ticker_list(value: str) -> list[PortfolioHolding]:
    holdings: list[PortfolioHolding] = []
    for raw in value.split(","):
        ticker = raw.strip()
        if not ticker:
            continue
        try:
            holdings.append(PortfolioHolding(ticker=normalize_ticker_symbol(ticker)))
        except ValueError as exc:
            raise ValueError(f"Invalid ticker {ticker!r}: {exc}") from exc
    if not holdings:
        raise ValueError("At least one ticker is required.")
    return holdings


def load_batch_inputs(
    *, input_path: Path | None, tickers: str | None
) -> list[PortfolioHolding]:
    if input_path and tickers:
        raise ValueError("--input and --tickers are mutually exclusive.")
    if tickers:
        return parse_ticker_list(tickers)
    if input_path is None:
        raise ValueError("Provide either --input or --tickers.")

    suffix = input_path.suffix.lower()
    if suffix == ".csv":
        return _load_csv(input_path)
    if suffix == ".json":
        return _load_json(input_path)
    raise ValueError("Batch input must be a CSV or JSON file.")


def _load_csv(path: Path) -> list[PortfolioHolding]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "ticker" not in {name.strip() for name in reader.fieldnames}:
            raise ValueError("Batch CSV input must include a ticker column.")
        return [_holding_from_row(row, row_number=i) for i, row in enumerate(reader, start=2)]


def _load_json(path: Path) -> list[PortfolioHolding]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Batch JSON input must be a list of objects.")
    return [_holding_from_row(row, row_number=i) for i, row in enumerate(data, start=1)]


def _holding_from_row(row: dict, row_number: int) -> PortfolioHolding:
    if not isinstance(row, dict):
        raise ValueError(f"Row {row_number} must be an object.")
    raw_ticker = _optional_str(row.get("ticker"))
    if not raw_ticker:
        raise ValueError(f"Row {row_number} is missing ticker.")
    try:
        ticker = normalize_ticker_symbol(raw_ticker)
    except ValueError as exc:
        raise ValueError(f"Invalid ticker on row {row_number}: {exc}") from exc

    quantity = _optional_float(row.get("quantity"), "quantity", row_number)
    average_cost = _optional_float(row.get("average_cost"), "average_cost", row_number)
    market_value = _optional_float(row.get("market_value"), "market_value", row_number)
    if market_value is None and quantity is not None and average_cost is not None:
        market_value = quantity * average_cost

    return PortfolioHolding(
        ticker=ticker,
        quantity=quantity,
        average_cost=average_cost,
        market_value=market_value,
        target_weight=_optional_float(row.get("target_weight"), "target_weight", row_number),
        notes=_optional_str(row.get("notes")),
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: object, field_name: str, row_number: int) -> float | None:
    text = _optional_str(value)
    if text is None:
        return None
    try:
        return float(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Row {row_number} has invalid {field_name}: {value!r}") from exc


def extract_ticker_result(
    *,
    ticker: str,
    final_state: dict,
    report_path: Path | None,
    holding: PortfolioHolding,
    elapsed_seconds: float,
) -> BatchTickerResult:
    final_decision = str(final_state.get("final_trade_decision") or "")
    trader_plan = str(final_state.get("trader_investment_plan") or "")
    return BatchTickerResult(
        ticker=ticker,
        status="success",
        rating=parse_rating(final_decision),
        trader_action=parse_trader_action(trader_plan),
        executive_summary=parse_executive_summary(final_decision),
        report_path=report_path,
        holding=holding,
        elapsed_seconds=elapsed_seconds,
    )


def parse_trader_action(text: str) -> str:
    match = re.search(
        r"FINAL TRANSACTION PROPOSAL:\s*\**(BUY|HOLD|SELL)\**",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).title()
    match = re.search(r"\*\*Action\*\*:\s*(Buy|Hold|Sell)", text, flags=re.IGNORECASE)
    return match.group(1).title() if match else "Hold"


def parse_executive_summary(text: str) -> str | None:
    match = re.search(
        r"\*\*Executive Summary\*\*:\s*(.*?)(?:\n\s*\n|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    return " ".join(match.group(1).split())


def build_batch_summary_markdown(
    results: Sequence[BatchTickerResult],
    analysis_date: str,
    *,
    narrative: str | None = None,
    base_path: Path | None = None,
) -> str:
    generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# Batch Trading Analysis Summary",
        "",
        f"Generated: {generated}",
        "",
        f"Analysis Date: {analysis_date}",
        "",
        "## Ranked Tickers",
        "",
        "| Ticker | Status | Rating | Trader Action | Market Value | Current Weight | Target Weight | Report | Summary |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for result in _ranked_results(results):
        holding = result.holding
        market_value = holding.market_value if holding else None
        current_weight = _current_weight(result, results)
        target_weight = holding.target_weight if holding else None
        report = _relative_report_link(result.report_path, base_path)
        lines.append(
            "| {ticker} | {status} | {rating} | {action} | {market_value} | {current_weight} | {target_weight} | {report} | {summary} |".format(
                ticker=result.ticker,
                status=result.status,
                rating=result.rating or "",
                action=result.trader_action or "",
                market_value=_format_number(market_value),
                current_weight=_format_percent(current_weight),
                target_weight=_format_percent(target_weight),
                report=report,
                summary=_table_text(result.executive_summary or result.error or ""),
            )
        )

    lines.extend(_holdings_section(results))
    failures = [result for result in results if result.status == "failed"]
    if failures:
        lines.extend([
            "",
            "## Failures",
            "",
            "| Ticker | Error |",
            "| --- | --- |",
        ])
        for result in failures:
            lines.append(f"| {result.ticker} | {_table_text(result.error or '')} |")

    if narrative:
        lines.extend(["", "## Cross-Ticker Narrative", "", narrative.strip()])
    return "\n".join(lines) + "\n"


def write_batch_outputs(
    save_path: Path,
    results: Sequence[BatchTickerResult],
    analysis_date: str,
    *,
    narrative: str | None = None,
    allocation_plan: "AllocationPlan | None" = None,
) -> Path:
    save_path.mkdir(parents=True, exist_ok=True)
    markdown = build_batch_summary_markdown(
        results,
        analysis_date,
        narrative=narrative,
        base_path=save_path,
    )
    markdown_path = save_path / "batch_summary.md"
    markdown_path.write_text(markdown, encoding="utf-8")
    html = _render_markdown_html(markdown, "Batch Trading Analysis Summary")
    (save_path / "batch_summary.html").write_text(html, encoding="utf-8")
    json_data = [_jsonable_result(result, save_path) for result in results]
    (save_path / "batch_results.json").write_text(
        json.dumps(json_data, indent=2),
        encoding="utf-8",
    )
    if allocation_plan is not None:
        from tradingagents.allocation import allocation_plan_to_json, build_allocation_markdown

        allocation_markdown = build_allocation_markdown(allocation_plan, analysis_date)
        (save_path / "allocation_plan.md").write_text(
            allocation_markdown,
            encoding="utf-8",
        )
        allocation_html = _render_markdown_html(
            allocation_markdown,
            "Portfolio Allocation Plan",
        )
        (save_path / "allocation_plan.html").write_text(
            allocation_html,
            encoding="utf-8",
        )
        (save_path / "allocation_plan.json").write_text(
            json.dumps(allocation_plan_to_json(allocation_plan), indent=2),
            encoding="utf-8",
        )
    return markdown_path


def run_batch_analysis(
    *,
    holdings: Sequence[PortfolioHolding],
    analysis_date: str,
    output_language: str,
    analysts: list[AnalystType],
    research_depth: int,
    checkpoint: bool,
    llm_overrides: LLMConfigOverrides,
    save_path: Path,
    display_report: bool,
    continue_on_error: bool,
    available_cash: float,
    allocate: bool,
    dry_run: bool,
    allocation_policy: "AllocationPolicy | None",
    prices: dict[str, float] | None = None,
) -> list[BatchTickerResult]:
    from cli.main import SelectionOverrides, console, run_analysis

    results: list[BatchTickerResult] = []
    save_path.mkdir(parents=True, exist_ok=True)
    for holding in holdings:
        started = time.time()
        try:
            console.print(f"[bold cyan]Batch analyzing {holding.ticker}[/bold cyan]")
            analysis_result = run_analysis(
                checkpoint=checkpoint,
                llm_overrides=llm_overrides,
                selection_overrides=SelectionOverrides(
                    ticker=holding.ticker,
                    analysis_date=analysis_date,
                    output_language=output_language,
                    analysts=analysts,
                    research_depth=research_depth,
                    save_report=True,
                    save_path=save_path / holding.ticker,
                    display_report=display_report,
                ),
            )
            results.append(
                extract_ticker_result(
                    ticker=holding.ticker,
                    final_state=analysis_result.final_state,
                    report_path=analysis_result.report_path,
                    holding=holding,
                    elapsed_seconds=time.time() - started,
                )
            )
        except Exception as exc:
            results.append(
                BatchTickerResult(
                    ticker=holding.ticker,
                    status="failed",
                    holding=holding,
                    elapsed_seconds=time.time() - started,
                    error=str(exc),
                )
            )
            if not continue_on_error:
                break

    narrative = build_llm_narrative(results, llm_overrides)
    allocation_plan = None
    if allocate or dry_run:
        from tradingagents.allocation import build_allocation_plan

        allocation_plan = build_allocation_plan(
            results,
            available_cash=available_cash,
            prices=prices or _derive_prices_from_holdings(results),
            policy=allocation_policy,
        )
    summary_path = write_batch_outputs(
        save_path,
        results,
        analysis_date,
        narrative=narrative,
        allocation_plan=allocation_plan,
    )
    console.print(f"[green]Batch summary saved to:[/green] {summary_path.resolve()}")
    if allocation_plan is not None:
        allocation_path = save_path / "allocation_plan.md"
        console.print(
            f"[green]Allocation plan saved to:[/green] {allocation_path.resolve()}"
        )
    if dry_run and allocation_plan is not None:
        _print_dry_run_table(console, allocation_plan)
    return results


def _derive_prices_from_holdings(results: Sequence[BatchTickerResult]) -> dict[str, float]:
    derived: dict[str, float] = {}
    for result in results:
        holding = result.holding
        if (
            holding is None
            or holding.quantity is None
            or holding.quantity <= 0
            or holding.market_value is None
        ):
            continue
        derived[result.ticker] = float(holding.market_value) / float(holding.quantity)
    return derived


def _print_dry_run_table(console: object, allocation_plan: "AllocationPlan") -> None:
    from rich.table import Table

    table = Table(title="Allocation Dry Run")
    table.add_column("Ticker")
    table.add_column("Action")
    table.add_column("Quantity Delta", justify="right")
    table.add_column("Leftover Cash", justify="right")

    for row in allocation_plan.rows:
        quantity = (
            ""
            if row.quantity_delta is None
            else _format_quantity(row.quantity_delta)
        )
        table.add_row(
            row.ticker,
            row.recommended_action,
            quantity,
            _format_number(allocation_plan.leftover_cash),
        )
    console.print(table)


def build_llm_narrative(
    results: Sequence[BatchTickerResult],
    llm_overrides: LLMConfigOverrides,
    llm_factory: Callable[[LLMConfigOverrides], object] | None = None,
) -> str | None:
    successes = [r for r in results if r.status == "success"]
    if not successes:
        return None
    try:
        if llm_factory is None:
            from tradingagents.llm_clients import create_llm_client

            if not (llm_overrides.provider and llm_overrides.deep_model):
                return None
            client = create_llm_client(
                provider=llm_overrides.provider,
                model=llm_overrides.deep_model,
                base_url=llm_overrides.backend_url,
            )
            llm = client.get_llm()
        else:
            llm = llm_factory(llm_overrides)

        rows = "\n".join(
            f"- {r.ticker}: rating={r.rating}, action={r.trader_action}, market_value={r.holding.market_value if r.holding else None}, summary={r.executive_summary}"
            for r in successes
        )
        prompt = (
            "Summarize this batch trading analysis in one concise portfolio-aware section. "
            "Compare conviction, common risks, and any holdings concentration concerns. "
            "Do not invent prices or orders.\n\n"
            f"{rows}"
        )
        response = llm.invoke(prompt)
        return str(getattr(response, "content", response)).strip() or None
    except Exception:
        return None


def _ranked_results(results: Sequence[BatchTickerResult]) -> list[BatchTickerResult]:
    return sorted(
        results,
        key=lambda r: (
            r.status != "success",
            -RATING_RANK.get(r.rating or "Hold", 0),
            -((r.holding.market_value if r.holding and r.holding.market_value is not None else 0.0)),
            r.ticker,
        ),
    )


def _holdings_section(results: Sequence[BatchTickerResult]) -> list[str]:
    total = _total_market_value(results)
    if total <= 0:
        return []
    lines = [
        "",
        "## Holdings Exposure",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Total Provided Market Value | {total:.2f} |",
        "",
        "| Ticker | Market Value | Current Weight | Target Weight | Weight Gap |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for result in sorted(results, key=lambda r: r.ticker):
        holding = result.holding
        market_value = holding.market_value if holding else None
        current_weight = _current_weight(result, results)
        target_weight = holding.target_weight if holding else None
        gap = target_weight - current_weight if target_weight is not None and current_weight is not None else None
        lines.append(
            f"| {result.ticker} | {_format_number(market_value)} | {_format_percent(current_weight)} | {_format_percent(target_weight)} | {_format_percent(gap)} |"
        )
    return lines


def _total_market_value(results: Sequence[BatchTickerResult]) -> float:
    return sum(
        result.holding.market_value
        for result in results
        if result.holding and result.holding.market_value is not None
    )


def _current_weight(
    result: BatchTickerResult,
    results: Sequence[BatchTickerResult],
) -> float | None:
    if not result.holding or result.holding.market_value is None:
        return None
    total = _total_market_value(results)
    if total <= 0:
        return None
    return result.holding.market_value / total


def _format_number(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}"


def _format_percent(value: float | None) -> str:
    return "" if value is None else f"{value * 100:.2f}%"


def _relative_report_link(path: Path | None, base_path: Path | None = None) -> str:
    if path is None:
        return ""
    link_path = path
    if base_path is not None:
        try:
            link_path = path.relative_to(base_path)
        except ValueError:
            link_path = path
    return f"[report]({link_path.as_posix()})"


def _table_text(value: str) -> str:
    return " ".join(value.replace("|", "\\|").split())


def _jsonable_result(result: BatchTickerResult, base_path: Path) -> dict:
    data = asdict(result)
    if result.report_path is not None:
        try:
            data["report_path"] = result.report_path.relative_to(base_path).as_posix()
        except ValueError:
            data["report_path"] = result.report_path.as_posix()
    return data


def _render_markdown_html(markdown_text: str, title: str) -> str:
    body = MarkdownIt("commonmark", {"html": False}).enable("table").render(markdown_text)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
</head>
<body>
{body}
</body>
</html>
"""
