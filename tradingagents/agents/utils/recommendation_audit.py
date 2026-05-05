from __future__ import annotations

import re
from typing import Any

from tradingagents.agents.utils.factor_model import build_factor_model


REPORT_SPECS = (
    ("market_report", "market", "Market analyst report"),
    ("news_report", "news", "News analyst report"),
    ("sentiment_report", "sentiment", "Sentiment analyst report"),
    ("fundamentals_report", "fundamentals", "Fundamentals analyst report"),
)

POSITIVE_TERMS = (
    "bullish",
    "breakout",
    "buy",
    "constructive",
    "growth",
    "improving",
    "outperform",
    "positive",
    "strong",
    "uptrend",
)

TECHNICAL_TREND_POSITIVE_TERMS = ("above", "uptrend", "breakout", "higher high", "bullish trend", "golden cross")
TECHNICAL_TREND_NEGATIVE_TERMS = ("below", "downtrend", "breakdown", "lower low", "bearish trend", "death cross")
MOMENTUM_POSITIVE_TERMS = ("momentum", "macd", "rsi", "strength", "acceleration", "outperform")
MOMENTUM_NEGATIVE_TERMS = ("overbought", "weak momentum", "deceleration", "divergence", "underperform")
VOLATILITY_POSITIVE_TERMS = ("stable", "low volatility", "controlled volatility", "tight range")
VOLATILITY_NEGATIVE_TERMS = ("volatile", "volatility", "atr", "wide range", "elevated risk", "drawdown")
NEWS_POSITIVE_TERMS = ("upgrade", "beat", "beats", "positive", "strong", "growth", "approval", "partnership")
NEWS_NEGATIVE_TERMS = ("downgrade", "miss", "lawsuit", "probe", "risk", "negative", "decline", "warning")
FUNDAMENTALS_POSITIVE_TERMS = ("revenue growth", "margin", "profit", "cash flow", "earnings", "balance sheet", "fundamentals")
FUNDAMENTALS_NEGATIVE_TERMS = ("debt", "loss", "margin pressure", "cash burn", "weak fundamentals", "impairment")
RISK_POSITIVE_TERMS = ("manageable risk", "balanced", "hedge", "risk-controlled", "diversified")
RISK_NEGATIVE_TERMS = ("risk", "uncertain", "volatility", "sell", "bearish", "conservative", "downside")

NEGATIVE_TERMS = (
    "bearish",
    "decline",
    "downtrend",
    "elevated risk",
    "negative",
    "risk",
    "sell",
    "uncertain",
    "underperform",
    "volatility",
    "weak",
)

_TICKER_RE = re.compile(r"\b[A-Z]{2,5}(?:\.[A-Z]{1,4})?\b")
_COMMON_NON_TICKERS = {
    "AI",
    "API",
    "ATR",
    "BUY",
    "CEO",
    "CFO",
    "CSV",
    "DB",
    "EMA",
    "ETF",
    "FINAL",
    "GDP",
    "JSON",
    "LLM",
    "MACD",
    "NASDAQ",
    "NYSE",
    "HOLD",
    "OVERWEIGHT",
    "PDF",
    "PE",
    "RAW",
    "RSI",
    "SMA",
    "SRC",
    "TOOL",
    "SELL",
    "UNDERWEIGHT",
    "US",
    "USD",
    "VWAP",
}

_ISSUER_ALIASES = {
    "AAPL": {"apple"},
    "AMZN": {"amazon"},
    "GOOGL": {"alphabet", "google"},
    "JPM": {"jpmorgan", "jp morgan", "jpmorgan chase"},
    "MSFT": {"microsoft"},
    "NVDA": {"nvidia"},
    "TSLA": {"tesla"},
}

_KNOWN_OTHER_ISSUERS = {
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "apple": "AAPL",
    "avalyn": "AVLN",
    "google": "GOOGL",
    "jpmorgan": "JPM",
    "marvell": "MRVL",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "tesla": "TSLA",
}


def _summary(text: str, limit: int = 360) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3].rstrip() + "..."


def build_source_objects(final_state: dict[str, Any]) -> list[dict[str, Any]]:
    """Create stable source objects from available final-state reports."""
    sources: list[dict[str, Any]] = []
    for key, source_type, label in REPORT_SPECS:
        content = final_state.get(key)
        if not isinstance(content, str) or not content.strip():
            continue
        source_id = f"SRC-{source_type.upper()}-1"
        sources.append(
            {
                "source_id": source_id,
                "source_type": source_type,
                "label": label,
                "state_key": key,
                "summary": _summary(content),
                "bytes": len(content.encode("utf-8")),
            }
        )
    return sources


def build_raw_tool_source_objects(final_state: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize captured graph tool outputs as citeable source objects."""
    raw_outputs = final_state.get("raw_tool_outputs")
    if not isinstance(raw_outputs, list):
        return []
    sources: list[dict[str, Any]] = []
    for item in raw_outputs:
        if not isinstance(item, dict):
            continue
        source_id = item.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            continue
        output = item.get("output")
        if output is None:
            output = item.get("content", "")
        output_text = output if isinstance(output, str) else repr(output)
        sources.append(
            {
                "source_id": source_id,
                "source_type": "raw_tool_output",
                "label": f"Raw tool output: {item.get('tool_name', 'unknown')}",
                "tool_name": item.get("tool_name", "unknown"),
                "summary": _summary(output_text, limit=260),
                "output_sha256": item.get("output_sha256"),
                "bytes": item.get("bytes") or len(output_text.encode("utf-8")),
            }
        )
    return sources


def _canonical_symbol(ticker: str) -> str:
    return ticker.split(".", 1)[0].upper()


def build_pre_synthesis_scope_audit(ticker: str, final_state: dict[str, Any]) -> dict[str, Any]:
    """Deterministically inspect available reports before Portfolio Manager synthesis."""
    symbol = _canonical_symbol(ticker)
    allowed_aliases = _ISSUER_ALIASES.get(symbol, {symbol.lower()})
    findings: list[dict[str, Any]] = []
    inspected: list[str] = []

    for key, _source_type, label in REPORT_SPECS:
        content = final_state.get(key)
        if not isinstance(content, str) or not content.strip():
            continue
        inspected.append(key)
        tickers = {
            match.group(0)
            for match in _TICKER_RE.finditer(content)
            if match.group(0) not in _COMMON_NON_TICKERS
        }
        unrelated_tickers = sorted(t for t in tickers if _canonical_symbol(t) != symbol)
        if unrelated_tickers:
            findings.append(
                {
                    "code": "pre_synthesis_unrelated_ticker",
                    "severity": "error",
                    "source": key,
                    "message": f"{label} mentions ticker(s) outside requested instrument {ticker}.",
                    "evidence": ", ".join(unrelated_tickers),
                }
            )

        lower_content = content.lower()
        other_issuers = []
        for issuer, issuer_symbol in _KNOWN_OTHER_ISSUERS.items():
            if issuer_symbol == symbol or issuer in allowed_aliases:
                continue
            if re.search(rf"\b{re.escape(issuer)}\b", lower_content):
                other_issuers.append(f"{issuer} ({issuer_symbol})")
        if other_issuers:
            findings.append(
                {
                    "code": "pre_synthesis_unrelated_entity",
                    "severity": "error",
                    "source": key,
                    "message": f"{label} mentions issuer(s) unrelated to requested instrument {ticker}.",
                    "evidence": ", ".join(sorted(other_issuers)),
                }
            )

    return {
        "requested_ticker": ticker,
        "status": "failed" if findings else "passed",
        "inspected_reports": inspected,
        "findings": findings,
    }


def render_sources_for_prompt(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "No structured source objects were available."
    return "\n".join(
        f"- {src['source_id']} ({src['source_type']}): {src['summary']}" for src in sources
    )


def render_raw_tool_sources_for_prompt(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "No raw tool output sources were captured."
    return "\n".join(
        (
            f"- {src['source_id']} ({src.get('tool_name', 'unknown')}): "
            f"sha256={src.get('output_sha256') or 'unknown'}; {src['summary']}"
        )
        for src in sources[:12]
    )


def render_scorecard_for_prompt(scorecard: dict[str, Any]) -> str:
    lines = [
        f"Total score: {scorecard['total_score']}",
        f"Suggested rating: {scorecard['suggested_rating']}",
        f"Suggested direction: {scorecard['suggested_direction']}",
    ]
    for factor in scorecard["factors"]:
        source_keys = factor.get("inputs", {}).get("source_keys") if isinstance(factor.get("inputs"), dict) else []
        claim_ids = factor.get("inputs", {}).get("bullish_claim_ids", []) + factor.get("inputs", {}).get("bearish_claim_ids", []) + factor.get("inputs", {}).get("neutral_claim_ids", []) if isinstance(factor.get("inputs"), dict) else []
        if isinstance(source_keys, list):
            source_text = ", ".join(str(source) for source in source_keys if source)
        else:
            source_text = "none"
        claim_text = ", ".join(str(claim_id) for claim_id in claim_ids if claim_id) or "none"
        lines.append(
            f"- {factor['factor']}: score={factor['score']} source={source_text or 'none'} claims={claim_text}"
        )
    return "\n".join(lines)


def build_recommendation_scorecard(final_state: dict[str, Any]) -> dict[str, Any]:
    return build_factor_model(final_state)


def render_scope_audit_for_prompt(scope_audit: dict[str, Any]) -> str:
    findings = scope_audit.get("findings") or []
    if not findings:
        return (
            f"Status: {scope_audit.get('status', 'unknown')}; "
            f"inspected reports: {', '.join(scope_audit.get('inspected_reports') or []) or 'none'}."
        )
    lines = [
        f"Status: {scope_audit.get('status', 'unknown')}; inspected reports: {', '.join(scope_audit.get('inspected_reports') or []) or 'none'}."
    ]
    for finding in findings:
        lines.append(
            f"- {finding.get('severity', 'unknown')} {finding.get('code', 'unknown')} in {finding.get('source', 'unknown')}: {finding.get('evidence', '')}"
        )
    return "\n".join(lines)
