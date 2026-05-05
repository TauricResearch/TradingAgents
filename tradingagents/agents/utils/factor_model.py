from __future__ import annotations

import re
from typing import Any

MODEL_VERSION = "deterministic-factor-model-v2"

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

CLAIM_FACTOR_SPECS = (
    {
        "factor": "technical_trend",
        "label": "Technical trend",
        "source_keys": ["market_report"],
        "claim_types": {"market", "macro"},
        "positive_terms": TECHNICAL_TREND_POSITIVE_TERMS,
        "negative_terms": TECHNICAL_TREND_NEGATIVE_TERMS,
    },
    {
        "factor": "momentum",
        "label": "Momentum",
        "source_keys": ["market_report"],
        "claim_types": {"market", "macro"},
        "positive_terms": MOMENTUM_POSITIVE_TERMS,
        "negative_terms": MOMENTUM_NEGATIVE_TERMS,
    },
    {
        "factor": "volatility",
        "label": "Volatility",
        "source_keys": ["market_report"],
        "claim_types": {"market", "raw_tool_output"},
        "positive_terms": VOLATILITY_POSITIVE_TERMS,
        "negative_terms": VOLATILITY_NEGATIVE_TERMS,
    },
    {
        "factor": "news_sentiment",
        "label": "News sentiment",
        "source_keys": ["news_report", "sentiment_report"],
        "claim_types": {"news", "sentiment"},
        "positive_terms": NEWS_SENTIMENT_POSITIVE_TERMS,
        "negative_terms": NEWS_SENTIMENT_NEGATIVE_TERMS,
    },
    {
        "factor": "fundamentals",
        "label": "Fundamentals",
        "source_keys": ["fundamentals_report"],
        "claim_types": {"fundamentals"},
        "positive_terms": FUNDAMENTALS_POSITIVE_TERMS,
        "negative_terms": FUNDAMENTALS_NEGATIVE_TERMS,
    },
    {
        "factor": "risk_posture",
        "label": "Risk posture",
        "source_keys": ["risk_debate_state.history"],
        "claim_types": set(),
        "positive_terms": RISK_POSTURE_POSITIVE_TERMS,
        "negative_terms": RISK_POSTURE_NEGATIVE_TERMS,
    },
    {
        "factor": "macro_regime",
        "label": "Macro regime",
        "source_keys": ["market_report", "news_report", "macro_report"],
        "claim_types": {"macro", "market", "news"},
        "positive_terms": MACRO_REGIME_POSITIVE_TERMS,
        "negative_terms": MACRO_REGIME_NEGATIVE_TERMS,
    },
)


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


def _claim_graph(final_state: dict[str, Any]) -> dict[str, Any]:
    value = final_state.get("claim_graph")
    return value if isinstance(value, dict) else {}


def _source_registry(final_state: dict[str, Any]) -> dict[str, Any]:
    value = final_state.get("source_registry")
    return value if isinstance(value, dict) else {}


def _claim_objects(final_state: dict[str, Any]) -> list[dict[str, Any]]:
    graph = _claim_graph(final_state)
    claims = graph.get("claim_objects")
    if not isinstance(claims, list):
        return []
    return [claim for claim in claims if isinstance(claim, dict)]


def _claims_for_factor(final_state: dict[str, Any], claim_types: set[str]) -> list[dict[str, Any]]:
    claims = _claim_objects(final_state)
    if not claim_types:
        return []
    matched = [
        claim
        for claim in claims
        if str(claim.get("claim_type")) in claim_types
        or str(claim.get("evidence_type")) in claim_types
        or str(claim.get("state_key")) in claim_types
    ]
    return matched


def _score_from_claims(claims: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    bullish = [claim for claim in claims if claim.get("direction") == "bullish"]
    bearish = [claim for claim in claims if claim.get("direction") == "bearish"]
    neutral = [claim for claim in claims if claim.get("direction") == "neutral"]
    bullish_weight = sum(float(claim.get("confidence") or 0.0) for claim in bullish)
    bearish_weight = sum(float(claim.get("confidence") or 0.0) for claim in bearish)
    raw_score = round(bullish_weight - bearish_weight)
    score = max(-3, min(3, int(raw_score)))
    return score, {
        "claim_count": len(claims),
        "bullish_claim_ids": [claim.get("claim_id") for claim in bullish if claim.get("claim_id")],
        "bearish_claim_ids": [claim.get("claim_id") for claim in bearish if claim.get("claim_id")],
        "neutral_claim_ids": [claim.get("claim_id") for claim in neutral if claim.get("claim_id")],
        "source_ids": sorted({
            source_id
            for claim in claims
            for source_id in (claim.get("source_ids") or [])
            if isinstance(source_id, str) and source_id.strip()
        }),
        "evidence_types": sorted({
            str(claim.get("evidence_type"))
            for claim in claims
            if claim.get("evidence_type")
        }),
        "claim_texts": [_summarize(str(claim.get("text") or "")) for claim in claims[:5]],
        "counterevidence_claim_ids": sorted({
            counter_id
            for claim in claims
            for counter_id in (claim.get("counterevidence_claim_ids") or [])
            if isinstance(counter_id, str) and counter_id.strip()
        }),
    }


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


def _direction_from_score(score: int) -> str:
    if score > 0:
        return "bullish"
    if score < 0:
        return "bearish"
    return "neutral"


def _rationale_for_factor(label: str, score: int, inputs: dict[str, Any], *, claim_backed: bool) -> str:
    positives = inputs.get("matched_positive_terms") or []
    negatives = inputs.get("matched_negative_terms") or []
    claim_ids = inputs.get("bullish_claim_ids", []) + inputs.get("bearish_claim_ids", []) + inputs.get("neutral_claim_ids", [])
    if claim_backed and claim_ids:
        return (
            f"{label}: score={score}; "
            f"claims={claim_ids}; counterevidence={inputs.get('counterevidence_claim_ids') or []}."
        )
    if positives or negatives:
        return (
            f"{label}: score={score}; "
            f"positive_terms={positives or []}; negative_terms={negatives or []}."
        )
    return f"{label}: score={score}; no explicit signal terms matched."


def _factor(
    *,
    factor: str,
    label: str,
    source_keys: list[str],
    text: str,
    positive_terms: tuple[str, ...],
    negative_terms: tuple[str, ...],
    claims: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    claims = claims or []
    if claims:
        score, claim_inputs = _score_from_claims(claims)
        claim_inputs.update(
            {
                "source_keys": source_keys,
                "text_excerpt": _summarize(text),
                "positive_term_count": len(_term_matches(text, positive_terms)),
                "negative_term_count": len(_term_matches(text, negative_terms)),
            }
        )
        return {
            "factor": factor,
            "label": label,
            "score": score,
            "available": True,
            "direction": _direction_from_score(score),
            "inputs": claim_inputs,
            "rationale": _rationale_for_factor(label, score, claim_inputs, claim_backed=True),
        }

    scored = _score_text(text, positive_terms=positive_terms, negative_terms=negative_terms)
    score = int(scored["score"])
    inputs = {
        "source_keys": source_keys,
        **scored["inputs"],
        "claim_count": 0,
        "bullish_claim_ids": [],
        "bearish_claim_ids": [],
        "neutral_claim_ids": [],
        "source_ids": [],
        "evidence_types": [],
        "counterevidence_claim_ids": [],
    }
    return {
        "factor": factor,
        "label": label,
        "score": score,
        "available": scored["available"],
        "direction": _direction_from_score(score),
        "inputs": inputs,
        "rationale": _rationale_for_factor(label, score, inputs, claim_backed=False),
    }


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
    macro_report = _text(final_state.get("macro_report"))
    risk_state = final_state.get("risk_debate_state") if isinstance(final_state.get("risk_debate_state"), dict) else {}
    risk_text = _text(risk_state.get("history"))
    macro_text = " ".join(part for part in (market_report, news_report, macro_report) if part).strip()
    claim_graph = _claim_graph(final_state)
    source_registry = _source_registry(final_state)
    claims = _claim_objects(final_state)

    def _claims_for(*claim_types: str) -> list[dict[str, Any]]:
        return _claims_for_factor(final_state, set(claim_types))

    factors = [
        _factor(
            factor="technical_trend",
            label="Technical trend",
            source_keys=["market_report"],
            text=market_report,
            positive_terms=TECHNICAL_TREND_POSITIVE_TERMS,
            negative_terms=TECHNICAL_TREND_NEGATIVE_TERMS,
            claims=_claims_for("market", "macro"),
        ),
        _factor(
            factor="momentum",
            label="Momentum",
            source_keys=["market_report"],
            text=market_report,
            positive_terms=MOMENTUM_POSITIVE_TERMS,
            negative_terms=MOMENTUM_NEGATIVE_TERMS,
            claims=_claims_for("market", "macro"),
        ),
        _factor(
            factor="volatility",
            label="Volatility",
            source_keys=["market_report"],
            text=market_report,
            positive_terms=VOLATILITY_POSITIVE_TERMS,
            negative_terms=VOLATILITY_NEGATIVE_TERMS,
            claims=_claims_for("market", "raw_tool_output"),
        ),
        _factor(
            factor="news_sentiment",
            label="News sentiment",
            source_keys=["news_report", "sentiment_report"],
            text="\n".join(part for part in (news_report, sentiment_report) if part).strip(),
            positive_terms=NEWS_SENTIMENT_POSITIVE_TERMS,
            negative_terms=NEWS_SENTIMENT_NEGATIVE_TERMS,
            claims=_claims_for("news", "sentiment"),
        ),
        _factor(
            factor="fundamentals",
            label="Fundamentals",
            source_keys=["fundamentals_report"],
            text=fundamentals_report,
            positive_terms=FUNDAMENTALS_POSITIVE_TERMS,
            negative_terms=FUNDAMENTALS_NEGATIVE_TERMS,
            claims=_claims_for("fundamentals"),
        ),
        _factor(
            factor="risk_posture",
            label="Risk posture",
            source_keys=["risk_debate_state.history"],
            text=risk_text,
            positive_terms=RISK_POSTURE_POSITIVE_TERMS,
            negative_terms=RISK_POSTURE_NEGATIVE_TERMS,
            claims=[],
        ),
        _factor(
            factor="macro_regime",
            label="Macro regime",
            source_keys=["market_report", "news_report", "macro_report"],
            text=macro_text,
            positive_terms=MACRO_REGIME_POSITIVE_TERMS,
            negative_terms=MACRO_REGIME_NEGATIVE_TERMS,
            claims=_claims_for("macro", "market", "news"),
        ),
    ]

    total_score = sum(factor["score"] for factor in factors)
    suggested_rating = _rating_from_score(total_score)
    suggested_direction = _direction_from_score(total_score)
    claim_backed_factor_count = sum(1 for factor in factors if factor["inputs"].get("claim_count", 0) > 0)
    return {
        "model_version": MODEL_VERSION,
        "method": "claim-backed deterministic audit model over technical trend, momentum, volatility, news sentiment, fundamentals, risk posture, and macro regime",
        "factors": factors,
        "total_score": total_score,
        "suggested_rating": suggested_rating,
        "suggested_direction": suggested_direction,
        "claim_backed_factor_count": claim_backed_factor_count,
        "claim_graph_summary": {
            "claim_count": len(claims),
            "claim_source_count": len(claim_graph.get("claim_source_ids") or []),
            "source_count": len(source_registry.get("source_objects") or []),
        },
    }


def build_recommendation_scorecard(final_state: dict[str, Any]) -> dict[str, Any]:
    """Compatibility wrapper for the existing portfolio-manager contract."""
    return build_factor_model(final_state)
