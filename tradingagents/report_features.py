"""Jev features from a run's reports, for learning from resolved decisions.

Fit 5 in docs/jev-use-cases.md. A backtest leaves, for every cell, the decision
in its log (settled later with the alpha it earned) and the run's full state on
disk. This asks a fixed set of Jev questions about each report, debate and
decision in that state, turns the answers into numeric columns, and hands them
with the outcomes to ``outcome_model`` to learn whether they predict alpha
better than the rating alone.

- A Score becomes two columns, its expected level and the spread of its level
  distribution; a Noul becomes one, its probability (the encoding of the
  Autoresearch Feature Discovery cookbook).
- One request per document asks all of that document's questions, so each
  request holds one report rather than the whole run.
- Answers are cached on disk by model, question and state, so a new or reworded
  question is the only one asked again when the set changes.

Jev is not asked to compare numbers or dates: the rating, the claim-check flag,
the outcome and every statistic are code.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import math
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from typesafe_sdk import Noul, NoulCriteria, Score

from tradingagents.agents.jev import ask_each, jev_client
from tradingagents.agents.rating import RATING_REVIEW, extract_rating
from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.symbols import safe_ticker_component
from tradingagents.decision_log import TradingMemoryLog
from tradingagents.outcome_model import (
    Dataset,
    Evaluation,
    NotEnoughData,
    check_size,
    evaluate,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Document:
    key: str    # the state key its questions refer to
    title: str


DOCUMENTS = {
    "market": Document("report", "Market Analyst report"),
    "sentiment": Document("report", "Sentiment Analyst report"),
    "news": Document("report", "News Analyst report"),
    "fundamentals": Document("report", "Fundamentals Analyst report"),
    "research_debate": Document("debate", "Debate between the bull and bear researchers"),
    "risk_debate": Document(
        "debate", "Debate between the aggressive, conservative and neutral risk analysts"
    ),
    "decision": Document("decision", "Portfolio Manager's final decision"),
}

# Far below the 32k-token state budget of jev-1.13; a report this long is a
# runaway, and its opening holds the summary.
MAX_DOCUMENT_CHARS = 60_000

_CLAIM_CHECK = re.compile(r"\n\s*\*\*Claim Check\*\*:")


def pm_decision(text: str) -> str:
    """The Portfolio Manager's decision without the claim-check block (fit 4).

    The block's verdict reaches the model as its own column, and a quoted
    contradicted claim would otherwise colour the conviction question.
    """
    return _CLAIM_CHECK.split(text, maxsplit=1)[0].strip()


def document_texts(state: Mapping[str, Any]) -> dict[str, str]:
    """The run's documents by name, leaving out any that are missing or empty."""
    debate = state.get("investment_debate_state") or {}
    risk = state.get("risk_debate_state") or {}
    texts = {
        "market": state.get("market_report"),
        "sentiment": state.get("sentiment_report"),
        "news": state.get("news_report"),
        "fundamentals": state.get("fundamentals_report"),
        "research_debate": debate.get("history"),
        "risk_debate": risk.get("history"),
        "decision": pm_decision(state.get("final_trade_decision") or ""),
    }
    return {name: text.strip()[:MAX_DOCUMENT_CHARS]
            for name, text in texts.items() if isinstance(text, str) and text.strip()}


def document_state(ticker: str, name: str, text: str) -> dict:
    doc = DOCUMENTS[name]
    return {"instrument": {"ticker": ticker}, doc.key: {"kind": doc.title, "text": text}}


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeatureQuestion:
    id: str
    document: str
    question: Any  # a typesafe_sdk Score or Noul

    @property
    def columns(self) -> tuple[str, ...]:
        if isinstance(self.question, Score):
            return (self.id, f"{self.id}_sd")
        return (self.id,)


def _noul(instructions: str, true: str, false: str) -> Noul:
    return Noul(instructions=instructions, criteria=NoulCriteria(true=true, false=false))


# The first set, from the examples in the roadmap: fundamentals trend, valuation
# stretch, sentiment extremity, catalyst proximity, risk-debate asymmetry, and a
# few more of each report's main judgments. They are candidates, kept only while
# they lower the held-out error (outcome_model.evaluate reports which do).
QUESTIONS: tuple[FeatureQuestion, ...] = (
    FeatureQuestion("price_trend", "market", Score(
        instructions="What price trend does `report` describe for `instrument`?",
        criteria=[
            "A strong downtrend: the price is falling steeply or making new lows, below "
            "its main moving averages, and the report calls the trend clearly bearish.",
            "A mild downtrend: the price is drifting lower or weakening, with mostly "
            "bearish signals.",
            "No clear trend: the price is range-bound, or the signals are mixed.",
            "A mild uptrend: the price is rising or recovering, with mostly bullish signals.",
            "A strong uptrend: the price is rising steeply or making new highs, above its "
            "main moving averages, and the report calls the trend clearly bullish.",
        ],
    )),
    FeatureQuestion("overbought", "market", _noul(
        "Does `report` describe `instrument` as overbought or stretched to the upside?",
        true="It says the stock is overbought, extended far above its averages, or due "
             "for a pullback after a sharp rise.",
        false="It does not, or it describes the stock as oversold or fairly placed.",
    )),
    FeatureQuestion("oversold", "market", _noul(
        "Does `report` describe `instrument` as oversold or stretched to the downside?",
        true="It says the stock is oversold, far below its averages, or due for a "
             "rebound after a sharp fall.",
        false="It does not, or it describes the stock as overbought or fairly placed.",
    )),
    FeatureQuestion("fundamentals_trend", "fundamentals", Score(
        instructions="How are `instrument`'s business fundamentals changing, as `report` "
                     "describes them?",
        criteria=[
            "Deteriorating sharply: revenue or earnings are falling fast, margins are "
            "collapsing, or losses or cash burn are widening.",
            "Weakening: growth is slowing or turning negative, or margins or cash flow "
            "are under some pressure.",
            "Stable or mixed: little change, or improvements and declines that offset.",
            "Improving: growth is steady or picking up, and margins or cash flow are "
            "getting better.",
            "Improving strongly: rapid revenue or earnings growth, with expanding margins "
            "and strong cash generation.",
        ],
    )),
    FeatureQuestion("valuation_stretch", "fundamentals", Score(
        instructions="How does `report` judge `instrument`'s valuation?",
        criteria=[
            "Clearly cheap: the report calls the stock undervalued, or says it trades "
            "well below its own history or its peers.",
            "Somewhat cheap: the report says it trades modestly below its history or "
            "peers, or calls it attractively priced.",
            "Fair, or not judged: the report says it is priced in line with its history "
            "and peers, or gives no view on the valuation.",
            "Somewhat expensive: the report says it trades at a premium to its history "
            "or peers, but finds the premium defensible.",
            "Stretched: the report calls the valuation rich, demanding or bubble-like, "
            "pricing in a great deal of future growth.",
        ],
    )),
    FeatureQuestion("balance_sheet_risk", "fundamentals", _noul(
        "Does `report` flag a serious financial risk for `instrument`, such as heavy "
        "debt, weak liquidity, cash burn or heavy dilution?",
        true="It names such a risk as a real concern for the company.",
        false="It does not, or it describes the balance sheet and cash position as sound.",
    )),
    FeatureQuestion("sentiment_tone", "sentiment", Score(
        instructions="How bullish or bearish is the sentiment toward `instrument` that "
                     "`report` describes?",
        criteria=[
            "Strongly bearish: the news and posts are dominated by selling, fear or bad news.",
            "Mildly bearish: negative voices outweigh positive ones.",
            "Neutral: little sentiment either way, or positive and negative voices balance.",
            "Mildly bullish: positive voices outweigh negative ones.",
            "Strongly bullish: the news and posts are dominated by buying, excitement or "
            "good news.",
        ],
    )),
    FeatureQuestion("sentiment_extremity", "sentiment", Score(
        instructions="How one-sided and intense is the sentiment toward `instrument` that "
                     "`report` describes, whichever direction it points?",
        criteria=[
            "Quiet: little discussion, or views evenly mixed with no strong feeling.",
            "A mild lean in one direction, stated calmly.",
            "A clear lean in one direction, with some strong opinions.",
            "Strongly one-sided: most voices agree, in heated or emphatic language.",
            "Extreme: euphoria or panic, a crowded consensus, or talk of a squeeze, "
            "capitulation or mania.",
        ],
    )),
    FeatureQuestion("news_tone", "news", Score(
        instructions="Taken together, how good or bad for `instrument`'s stock is the "
                     "news that `report` describes?",
        criteria=[
            "Clearly bad: major negative developments, such as a big earnings miss, a "
            "lost lawsuit, a wave of downgrades or the loss of a key customer.",
            "Somewhat bad: concerns or modestly negative news, with no major blow.",
            "Neutral or mixed: no important news, or good and bad news that balance.",
            "Somewhat good: encouraging or modestly positive news, with no major win.",
            "Clearly good: major positive developments, such as a big earnings beat, a "
            "large contract or a breakthrough product.",
        ],
    )),
    # Timing is read as the report words it; Jev is not given the date to count from.
    FeatureQuestion("catalyst_proximity", "news", Score(
        instructions="How soon does `report` expect the next specific event that could "
                     "move `instrument`'s stock?",
        criteria=[
            "The report names no specific upcoming event for the company.",
            "The report names an upcoming event but gives no timing, or places it months away.",
            "The report expects an event within the next several weeks.",
            "The report says an event is imminent: due in the coming days, this week or next.",
        ],
    )),
    FeatureQuestion("macro_headwind", "news", _noul(
        "Does `report` describe economic, interest-rate, policy or sector conditions as "
        "a headwind for `instrument`?",
        true="It says the macro or sector backdrop is likely to hurt the company or its stock.",
        false="It describes the backdrop as neutral or supportive, or does not discuss it.",
    )),
    FeatureQuestion("bull_bear_balance", "research_debate", Score(
        instructions="On the evidence each side cites in `debate`, whose case on "
                     "`instrument` is stronger: the bull's or the bear's?",
        criteria=[
            "The bear case is much stronger: the bull's points are rebutted or rest on "
            "hope rather than evidence.",
            "The bear case is somewhat stronger.",
            "The two cases are evenly matched.",
            "The bull case is somewhat stronger.",
            "The bull case is much stronger: the bear's points are rebutted or rest on "
            "speculation rather than evidence.",
        ],
    )),
    FeatureQuestion("risk_debate_asymmetry", "risk_debate", Score(
        instructions="In `debate`, which way does the argument over `instrument` lean: "
                     "toward caution or toward taking the risk?",
        criteria=[
            "Strongly toward caution: the risks raised are serious and go unanswered, "
            "and even the aggressive side concedes ground.",
            "Somewhat toward caution: the risks get the better of the argument.",
            "Balanced: the risks and the upside are argued to a standstill.",
            "Somewhat toward taking the risk: the upside gets the better of the argument.",
            "Strongly toward taking the risk: the upside is well supported, and the "
            "risks raised are answered or small.",
        ],
    )),
    FeatureQuestion("conviction", "decision", Score(
        instructions="How much conviction does `decision` express in its call on `instrument`?",
        criteria=[
            "Very low: the call is heavily hedged, framed as a close judgment, or "
            "contingent on many conditions.",
            "Low: noticeable hedging and several caveats.",
            "Moderate: a clear call with some caveats.",
            "High: a firm call backed by several reasons, with few caveats.",
            "Very high: an emphatic call, with the case presented as clear-cut.",
        ],
    )),
)

# Columns computed in code: the Portfolio Manager's rating from -1 (Sell) to 1
# (Buy), and whether the claim check sent the decision to REVIEW. They are the
# baseline the Jev columns have to beat.
RATING_VALUES = {"Buy": 1.0, "Overweight": 0.5, "Hold": 0.0, "Underweight": -0.5, "Sell": -1.0}
CODE_COLUMNS = ("rating", "review")


def question_columns(questions: Sequence[FeatureQuestion]) -> dict[str, tuple[str, ...]]:
    return {q.id: q.columns for q in questions}


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------


def jev_model_name() -> str:
    """The model the client will ask, as configured (an alias until pinned)."""
    return (get_config().get("jev_model") or os.environ.get("TYPESAFE_DEFAULT_MODEL")
            or "jev-latest")


def raw_answer(answer: Any) -> dict:
    """The part of an answer the features are computed from, as plain JSON."""
    if hasattr(answer, "probabilities"):
        return {"probabilities": {str(k): float(v) for k, v in answer.probabilities.items()}}
    return {"noul": float(answer.noul)}


def encode(question: FeatureQuestion, raw: Mapping[str, Any]) -> dict[str, float]:
    """Columns for one answer: a Score's expected level and spread, a Noul's probability."""
    if "probabilities" in raw:
        probs = {int(level): p for level, p in raw["probabilities"].items()}
        total = sum(probs.values()) or 1.0
        mean = sum(level * p for level, p in probs.items()) / total
        variance = sum(level * level * p for level, p in probs.items()) / total - mean * mean
        return {question.id: mean, f"{question.id}_sd": math.sqrt(max(variance, 0.0))}
    return {question.id: raw["noul"]}


class AnswerCache:
    """Jev answers on disk, keyed by model, question and state.

    A reworded question or a changed report is a new key, so only what changed
    is asked again. The model is the configured name: pin ``jev_model`` to a
    versioned id before collecting answers you mean to compare, since an alias
    such as jev-latest moves. Each entry records the model that answered.
    """

    def __init__(self, path: Path | None):
        self.path = Path(path) if path else None
        self._entries: dict[str, dict] = {}
        if self.path and self.path.exists():
            try:
                self._entries = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                logger.warning("Ignoring unreadable Jev feature cache %s: %s", self.path, exc)

    @staticmethod
    def key(model: str, question: FeatureQuestion, state: Mapping) -> str:
        payload = json.dumps(
            {"model": model, "question": question.question.model_dump(mode="json"), "state": state},
            sort_keys=True, ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> dict | None:
        return self._entries.get(key)

    def put(self, key: str, answer: dict, answered_by: str) -> None:
        self._entries[key] = {**answer, "model": answered_by}

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._entries, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)


@dataclass
class Extraction:
    rows: list[dict[str, float]]
    requests: int = 0             # sent to Jev in this call; the rest came from the cache
    models: set[str] = field(default_factory=set)  # every model behind the answers used


def extract_features(
    client: Any,
    decisions: Sequence[Decision],
    questions: Sequence[FeatureQuestion] = QUESTIONS,
    cache: AnswerCache | None = None,
) -> Extraction:
    """Feature columns for each decision, asking Jev only what the cache lacks.

    One request per decision and document, holding that document's uncached
    questions. A document the run did not write leaves its columns out, and the
    model fills them with the training mean. The cache is saved after each batch,
    so a failed request keeps what was already paid for; the failure itself is
    raised.
    """
    cache = cache or AnswerCache(None)
    model = jev_model_name()
    by_doc: dict[str, list[FeatureQuestion]] = {}
    for q in questions:
        by_doc.setdefault(q.document, []).append(q)

    # Group the (decision, document) pairs by which questions they still need,
    # since ask_each sends the same questions with every state.
    todo: dict[tuple[str, ...], list[tuple[dict, list[str]]]] = {}
    for d in decisions:
        for name, doc_questions in by_doc.items():
            if name not in d.documents:
                continue
            state = document_state(d.ticker, name, d.documents[name])
            keys = {q.id: AnswerCache.key(model, q, state) for q in doc_questions}
            missing = tuple(q.id for q in doc_questions if cache.get(keys[q.id]) is None)
            if missing:
                todo.setdefault(missing, []).append((state, [keys[i] for i in missing]))

    by_id = {q.id: q for q in questions}
    requests = 0
    try:
        for ids, jobs in todo.items():
            responses = ask_each(client, [state for state, _ in jobs], {i: by_id[i].question for i in ids})
            for (_, keys), response in zip(jobs, responses, strict=True):
                for qid, key in zip(ids, keys, strict=True):
                    cache.put(key, raw_answer(response.answers[qid]),
                              getattr(response, "model", None) or model)
            requests += len(jobs)
            cache.save()
    finally:
        cache.save()

    extraction = Extraction(rows=[], requests=requests)
    for d in decisions:
        row = {"rating": RATING_VALUES.get(d.pm_rating or "", 0.0),
               "review": 1.0 if d.rating == RATING_REVIEW else 0.0}
        for q in questions:
            if q.document not in d.documents:
                continue
            state = document_state(d.ticker, q.document, d.documents[q.document])
            entry = cache.get(AnswerCache.key(model, q, state))
            extraction.models.add(entry.get("model", model))
            row.update(encode(q, entry))
        extraction.rows.append(row)
    return extraction


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


@dataclass
class Decision:
    ticker: str
    date: str
    resolved: str            # when the outcome became known
    rating: str              # as logged; REVIEW when unreadable or sent to review
    pm_rating: str | None    # the Portfolio Manager's own rating
    alpha: float
    documents: dict[str, str]


@dataclass
class DecisionSet:
    decisions: list[Decision] = field(default_factory=list)
    pending: int = 0
    no_state: int = 0      # settled, but the run's saved state is missing
    unscorable: int = 0    # settled with no readable alpha or resolution date

    def describe(self) -> str:
        parts = [f"{len(self.decisions)} settled decisions with saved reports"]
        if self.pending:
            parts.append(f"{self.pending} pending")
        if self.no_state:
            parts.append(f"{self.no_state} settled without a saved state")
        if self.unscorable:
            parts.append(f"{self.unscorable} settled without a readable outcome")
        return ", ".join(parts)


def _percent(text: str | None) -> float | None:
    """A log percentage ("+1.3%") as a fraction; the log rounds it to 0.1 points."""
    try:
        return float((text or "").strip().rstrip("%")) / 100
    except ValueError:
        return None


def state_path(states_dir: Path, ticker: str, date: str) -> Path:
    """Where ``TradingAgentsGraph`` saved a run's full state."""
    return (Path(states_dir) / safe_ticker_component(ticker) / "TradingAgentsStrategy_logs"
            / f"full_states_log_{date}.json")


def load_decisions(log_path: Path, states_dir: Path) -> DecisionSet:
    """Settled decisions from a decision log, joined to the states the runs saved."""
    result = DecisionSet()
    if not Path(log_path).exists():
        return result
    for entry in TradingMemoryLog({"memory_log_path": str(log_path)}).load_entries():
        if entry["pending"]:
            result.pending += 1
            continue
        alpha = _percent(entry.get("alpha"))
        if alpha is None or not entry.get("resolved"):
            result.unscorable += 1
            continue
        try:
            path = state_path(states_dir, entry["ticker"], entry["date"])
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            result.no_state += 1
            continue
        decision_text = entry.get("decision") or state.get("final_trade_decision") or ""
        result.decisions.append(Decision(
            ticker=entry["ticker"],
            date=entry["date"],
            resolved=entry["resolved"],
            rating=entry["rating"],
            pm_rating=extract_rating(pm_decision(decision_text)),
            alpha=alpha,
            documents=document_texts(state),
        ))
    return result


def build_dataset(decisions: Sequence[Decision], rows: Sequence[Mapping[str, float]],
                  columns: Sequence[str]) -> Dataset:
    return Dataset.from_rows(
        rows=rows,
        columns=list(columns),
        alpha=[d.alpha for d in decisions],
        dates=[d.date for d in decisions],
        resolved=[d.resolved for d in decisions],
        labels=[f"{d.ticker} {d.date} {d.pm_rating or RATING_REVIEW}"
                + (" (REVIEW)" if d.rating == RATING_REVIEW and d.pm_rating else "")
                for d in decisions],
    )


def write_feature_table(path: Path, decisions: Sequence[Decision],
                        rows: Sequence[Mapping[str, float]], columns: Sequence[str]) -> Path:
    """One CSV row per decision: identity, outcome and every feature column."""
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "date", "resolved", "logged_rating", "pm_rating",
                         "alpha", *columns])
        for d, row in zip(decisions, rows, strict=True):
            writer.writerow([d.ticker, d.date, d.resolved, d.rating, d.pm_rating or "",
                             f"{d.alpha:.4f}",
                             *("" if c not in row else f"{row[c]:.4f}" for c in columns)])
    return path


# ---------------------------------------------------------------------------
# One call for the CLI
# ---------------------------------------------------------------------------


class JevUnavailable(RuntimeError):
    pass


@dataclass
class LearnResult:
    decisions: DecisionSet
    evaluation: Evaluation
    table_path: Path
    cache_path: Path
    requests: int
    models: set[str]


def learn_from_run(
    run_dir: Path,
    holdout: float = 0.25,
    questions: Sequence[FeatureQuestion] = QUESTIONS,
    client: Any = None,
) -> LearnResult:
    """Ask the feature questions about a backtest run and score them on its outcomes.

    Raises ``NotEnoughData`` before any Jev request when the run has too few
    settled decisions to hold any out, and ``JevUnavailable`` when Jev is off.
    """
    run_dir = Path(run_dir)
    decisions = load_decisions(run_dir / "trading_memory.md", run_dir)
    try:
        check_size([d.date for d in decisions.decisions])
    except NotEnoughData as exc:
        raise NotEnoughData(f"{exc} This run has {decisions.describe()}.") from None

    client = client or jev_client()
    if client is None:
        raise JevUnavailable(
            "Learning from reports needs TypeSafe Jev: set TYPESAFE_API_KEY and install "
            'the jev extra (pip install "tradingagents[jev]").'
        )
    cache_path = Path(get_config()["data_cache_dir"]) / "jev_report_features.json"
    with client:
        extraction = extract_features(client, decisions.decisions, questions, AnswerCache(cache_path))

    groups = question_columns(questions)
    columns = [*CODE_COLUMNS, *(c for cols in groups.values() for c in cols)]
    table = write_feature_table(run_dir / "report_features.csv", decisions.decisions,
                                extraction.rows, columns)
    dataset = build_dataset(decisions.decisions, extraction.rows, columns)
    evaluation = evaluate(dataset, groups, baseline=CODE_COLUMNS, holdout=holdout)
    return LearnResult(decisions, evaluation, table, cache_path,
                       extraction.requests, extraction.models)
