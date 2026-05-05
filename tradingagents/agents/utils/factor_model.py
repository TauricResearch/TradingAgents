from __future__ import annotations

from typing import Any
import re

MODEL_VERSION = "deterministic-factor-model-v1"

TECHNICAL_TREND_POSITIVE_TERMS = ("uptrend", "breakout", "higher high", "bullish trend", "above resistance")
TECHNICAL_TREND_NEGATIVE_TERMS = ("downtrend", "breakdown", "lower low", "bearish trend", "below support")
MOMENTUM_POSITIVE_TERMS = ("momentum", "strength", "acceleration", "outperform", "gaining")
MOMENTUM_NEGATIVE_TERMS = ("weak momentum", "deceleration", "overbought", "underperform", "losing")
VOLATILITY_POSITIVE_TERMS = ("stable", "low volatility", "controlled volatility", "tight range", "calm")
VOLATILITY_NEGATIVE_TERMS = ("volatile", "elevated volatility", "atr", "wide range", "elevated risk", "drawdown")
NEWS_SENTIMENT_POSITIVE_TERMS = ("upgrade", "beat", "beats", "positive", "strong", "growth", "approval", "partnership")
NEWS_SENTIMENT_NEGATIVE_TERMS = ("downgrade", "miss", "lawsuit", "probe", "negative", "decline", "warning", "headwind")
FUNDAMENTALS_POSITIVE_TERMS = ("revenue growth", "margin expansion", "profit", "cash flow", "earnings", "healthy balance sheet")
FUNDAMENTALS_NEGATIVE_TERMS = ("debt", "loss", "margin pressure", "cash burn", "weak fundamentals", "impairment")
RISK_POSTURE_POSITIVE_TERMS = ("manageable risk", "balanced", "hedge", "risk-controlled", "diversified", "disciplined")
RISK_POSTURE_NEGATIVE_TERMS = ("uncertain", "bearish", "conservative", "downside", "fragile", "risk-off")
MACRO_REGIME_POSITIVE_TERMS = ("stable rates", "easing inflation", "soft landing", "liquidity improving", "risk-on", "favorable macro")
MACRO_REGIME_NEGATIVE_TERMS = ("tightening", "inflation", "recession", "liquidity squeeze", "risk-off", "rate hike", "credit stress")


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _summarize(text: str, limit: int = 240) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3].rstrip() + "..."


def _term_matches(text: str, terms: tuple[str, ...]) -> list[str]:
    lower = text.lower()
    return [term for term in terms if term in lower]


def _score_text(text: str, *, positive_terms: tuple[str, ...], negative_terms: tuple[str, ...]) -> dict[str, Any]:
    matched_positive_terms = _term_matches(text, positive_terms)
    matched_negative_terms = _term_matches(text, negative_terms)
    raw_score = len(matched_positive_terms) - len(matched_negative_terms)
    score = max(-3, min(3, raw_score))
    return {
        "score": score,
        "available": bool(text.strip()),
        "inputs": {
            "text_excerpt": _summarize(text),
            "matched_positive_terms": matched_positive_terms,
            "matched_negative_terms": matched_negative_terms,
            "positive_term_count": len(matched_positive_terms),
            "negative_term_count": len(matched_negative_terms),
        },
    }


def _factor(
    *,
    factor: str,
    label: str,
    source_keys: list[str],
    text: str,
    positive_terms: tuple[str, ...],
    negative_terms: tuple[str, ...],
) -> dict[str, Any]:
    scored = _score_text(text, positive_terms=positive_terms, negative_terms=negative_terms)
    score = int(scored["score"])
    return {
        "factor": factor,
        "label": label,
        "score": score,
        "available": scored["available"],
        "direction": _direction_from_score(score),
        "inputs": {
            "source_keys": source_keys,
            **scored["inputs"],
        },
        "rationale": _rationale_for_factor(label, score, scored["inputs"]),
    }


def _direction_from_score(score: int) -> str:
    if score > 0:
        return "bullish"
    if score < 0:
        return "bearish"
    return "neutral"


def _rationale_for_factor(label: str, score: int, inputs: dict[str, Any]) -> str:
    positives = inputs.get("matched_positive_terms") or []
    negatives = inputs.get("matched_negative_terms") or []
    if positives or negatives:
        return (
            f"{label}: score={score}; "
            f"positive_terms={positives or []}; negative_terms={negatives or []}."
        )
    return f"{label}: score={score}; no explicit signal terms matched."


def _rating_from_score(score: int) -> str:
    if score >= 6:
        return "Buy"
    if score >= 2:
        return "Overweight"
    if score <= -6:
        return "Sell"
    if score <= -2:
        return "Underweight"
    return "Hold"


def build_factor_model(final_state: dict[str, Any]) -> dict[str, Any]:
    market_report = _text(final_state.get("market_report"))
    news_report = _text(final_state.get("news_report"))
    sentiment_report = _text(final_state.get("sentiment_report"))
    fundamentals_report = _text(final_state.get("fundamentals_report"))
    risk_state = final_state.get("risk_debate_state") if isinstance(final_state.get("risk_debate_state"), dict) else {}
    risk_text = _text(risk_state.get("history"))
    macro_report = _text(final_state.get("macro_report"))
    macro_text = " ".join(part for part in (market_report, news_report, macro_report) if part).strip()

    factors = [
        _factor(
            factor="technical_trend",
            label="Technical trend",
            source_keys=["market_report"],
            text=market_report,
            positive_terms=TECHNICAL_TREND_POSITIVE_TERMS,
            negative_terms=TECHNICAL_TREND_NEGATIVE_TERMS,
        ),
        _factor(
            factor="momentum",
            label="Momentum",
            source_keys=["market_report"],
            text=market_report,
            positive_terms=MOMENTUM_POSITIVE_TERMS,
            negative_terms=MOMENTUM_NEGATIVE_TERMS,
        ),
        _factor(
            factor="volatility",
            label="Volatility",
            source_keys=["market_report"],
            text=market_report,
            positive_terms=VOLATILITY_POSITIVE_TERMS,
            negative_terms=VOLATILITY_NEGATIVE_TERMS,
        ),
        _factor(
            factor="news_sentiment",
            label="News sentiment",
            source_keys=["news_report", "sentiment_report"],
            text="\n".join(part for part in (news_report, sentiment_report) if part).strip(),
            positive_terms=NEWS_SENTIMENT_POSITIVE_TERMS,
            negative_terms=NEWS_SENTIMENT_NEGATIVE_TERMS,
        ),
        _factor(
            factor="fundamentals",
            label="Fundamentals",
            source_keys=["fundamentals_report"],
            text=fundamentals_report,
            positive_terms=FUNDAMENTALS_POSITIVE_TERMS,
            negative_terms=FUNDAMENTALS_NEGATIVE_TERMS,
        ),
        _factor(
            factor="risk_posture",
            label="Risk posture",
            source_keys=["risk_debate_state.history"],
            text=risk_text,
            positive_terms=RISK_POSTURE_POSITIVE_TERMS,
            negative_terms=RISK_POSTURE_NEGATIVE_TERMS,
        ),
        _factor(
            factor="macro_regime",
            label="Macro regime",
            source_keys=["market_report", "news_report", "macro_report"],
            text=macro_text,
            positive_terms=MACRO_REGIME_POSITIVE_TERMS,
            negative_terms=MACRO_REGIME_NEGATIVE_TERMS,
        ),
    ]

    total_score = sum(factor["score"] for factor in factors)
    suggested_rating = _rating_from_score(total_score)
    suggested_direction = _direction_from_score(total_score)
    return {
        "model_version": MODEL_VERSION,
        "method": "seven-factor deterministic audit model over technical trend, momentum, volatility, news sentiment, fundamentals, risk posture, and macro regime",
        "factors": factors,
        "total_score": total_score,
        "suggested_rating": suggested_rating,
        "suggested_direction": suggested_direction,
    }


def build_recommendation_scorecard(final_state: dict[str, Any]) -> dict[str, Any]:
    """Compatibility wrapper for the existing portfolio-manager contract."""
    return build_factor_model(final_state)
