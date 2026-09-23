"""Checking the Portfolio Manager's claims against the analyst reports.

Fit 4 in docs/jev-use-cases.md, after the Double-Checking Citations cookbook.
The Portfolio Manager decides from the research plan, the trader's plan, the
risk debate and past lessons. It never reads the analyst reports, so a fact in
its Investment Thesis has passed through two or three LLM summaries on the way
and can arrive misread or invented. This check reads the thesis back against
the reports:

1. The thesis is split into claims in code: bullets and sentences.
2. One Jev request per claim asks whether it is a checkable fact about the
   instrument or its market (not a recommendation, a forecast, or a remark
   about the debate) and which report would state it.
3. One request per checkable claim and section of the reports it could come
   from asks whether the section supports it, contradicts it, or says nothing.
4. The verdicts, the figures check and whether the decision goes to REVIEW are
   decided in code, from the thresholds in ``ClaimCheckPolicy``.

Figures are matched as strings in code, not by Jev, which cannot compare
numbers: a number in a checkable claim that no report states, at the claim's
precision, is listed. It does not send the decision to REVIEW on its own,
because the Portfolio Manager legitimately derives figures such as the upside
to its target.

The typesafe SDK is imported only when questions are built, so the Portfolio
Manager can import this module without the ``jev`` extra installed.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from tradingagents.agents.utils.jev import ask_each, jev_client
from tradingagents.agents.utils.rating import extract_rating
from tradingagents.dataflows.config import get_config

logger = logging.getLogger(__name__)

# Report key -> short name used in the output and in the source question.
# Crypto runs use the same keys.
REPORTS = {
    "market_report": "market",
    "sentiment_report": "sentiment",
    "news_report": "news",
    "fundamentals_report": "fundamentals",
}
# What each report holds, as the options of the source question.
REPORT_CONTENTS = {
    "market": "Market Analyst report: the recent price action, trading volume, moving "
              "averages, momentum and volatility indicators (such as RSI, MACD, Bollinger "
              "Bands and ATR), and support and resistance levels.",
    "sentiment": "Sentiment Analyst report: the tone of recent news headlines and of "
                 "StockTwits and Reddit posts, and how bullish or bearish they are.",
    "news": "News Analyst report: recent news and events about the instrument, and the "
            "economy, interest rates, central banks, geopolitics and sector trends, with "
            "prediction-market odds.",
    "fundamentals": "Fundamentals Analyst report: the business profile, financial "
                    "statements (revenue, earnings, margins, cash flow, balance sheet), "
                    "valuation ratios and financial history.",
}


def report_title(name: str) -> str:
    return f"{name.capitalize()} Analyst report"


# Claims: shorter fragments are headings or labels, and the cap bounds the requests.
MAX_CLAIMS = 20
MIN_CLAIM_CHARS = 25
# Sections: long enough to hold a topic, small enough that the question is not
# lost in unrelated detail. Smaller parts are merged with a neighbour.
SECTION_CHARS = 2400
SMALL_SECTION_CHARS = 400
# Quoted claims and headings in the output are trimmed to keep the decision
# compact: past decisions are fed back into later prompts (memory.get_past_context).
_QUOTE_CHARS = 140


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


def claim_questions(sources: Sequence[str]) -> dict:
    """Request A: is the claim checkable, and which report would state it.

    ``source`` is asked only when there are at least two reports to choose from.
    """
    from typesafe_sdk import Choice, Noul, NoulCriteria

    questions = {
        # The Portfolio Manager's prompt holds the debate and past lessons, not the
        # reports, so its thesis mixes facts with remarks about the analysts and the
        # debate. Only the facts can be looked up in a report.
        "checkable": Noul(
            instructions=(
                "Is `claim` a statement of fact about `instrument`, its business, its "
                "stock, its industry or the market, of a kind an analyst report could "
                "confirm or refute?"
            ),
            criteria=NoulCriteria(
                true="It states a fact or assesses current conditions: results, margins, "
                     "growth, valuation, price action or indicators, news, products, "
                     "customers, competitors, the industry, the economy or the market "
                     "(for example 'margins are expanding' or 'the stock trades above its "
                     "200-day average'). Expectations reported as facts, such as company "
                     "guidance or consensus estimates, count.",
                false="It is a recommendation, a plan or an action to take; a price "
                      "target or an entry, stop or sizing level; the writer's own forecast "
                      "of what will happen; a statement about the debate, the analysts or "
                      "their arguments; a reference to past decisions or lessons; a "
                      "statement about the portfolio or the positions held; or a generic "
                      "caveat about risk.",
            ),
        ),
    }
    if len(sources) > 1:
        questions["source"] = Choice(
            instructions="Which analyst report would state the facts in `claim`?",
            criteria={name: REPORT_CONTENTS[name] for name in sources},
        )
    return questions


def relation_questions() -> dict:
    """Request B: how one report section bears on one claim."""
    from typesafe_sdk import Choice

    # "Supports" asks for one of the claim's points rather than all of them: a
    # compound claim often draws its parts from different sections, and would
    # otherwise never be supported by any single one.
    return {"relation": Choice(
        instructions="How does `section` relate to `claim`?",
        criteria={
            "supports": "`section` states or implies at least one of the points `claim` "
                        "makes, and contradicts none of them.",
            "contradicts": "`section` states the opposite of something `claim` asserts, "
                           "or a fact that cannot be true at the same time as it.",
            "says_nothing": "`section` does not address what `claim` asserts: it is about "
                            "something else, or mentions the topic without confirming or "
                            "denying the claim.",
        },
    )}


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClaimCheckPolicy:
    """Every threshold the check reads.

    Starting points from the Double-Checking Citations cookbook, not values tuned
    for this domain: tune them on backtest outcomes (``tradingagents/backtest.py``).
    """

    checkable_min: float = 0.50     # P(checkable) at or above: the claim is checked
    source_floor: float = 0.15      # sections of reports with P(source) below are not asked
    supported_min: float = 0.60     # best P(supports) at or above: supported
    contradicted_min: float = 0.80  # else best P(contradicts) at or above: contradicted
    # REVIEW when any claim is contradicted, or when at least this many checkable
    # claims are unsupported and they are at least this share of the checkable ones.
    review_unsupported_min: int = 2
    review_unsupported_share: float = 0.50


DEFAULT_POLICY = ClaimCheckPolicy()


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------

_THESIS_LABEL = re.compile(r"\*\*Investment Thesis\*\*\s*:|\*\*Investment Thesis:\*\*", re.I)
_THESIS_HEADING = re.compile(r"^(#{1,6})\s*Investment Thesis\b[^\n]*$", re.I | re.M)
_FIELD_AFTER_THESIS = r"\s*\*\*(?:Price Target|Time Horizon)\b"
_RATING_LINE = re.compile(r"^[\W_]*rating\b", re.I)


def thesis_text(decision: str) -> str:
    """The Investment Thesis of a rendered decision, or the text minus its rating line.

    The structured path renders ``**Investment Thesis**: ...`` followed by the
    price target and time horizon; a free-text answer may use a heading instead.
    """
    m = _THESIS_LABEL.search(decision)
    if m:
        body = decision[m.end():]
        end = re.search(f"^{_FIELD_AFTER_THESIS}", body, re.I | re.M)
        return body[: end.start()] if end else body
    m = _THESIS_HEADING.search(decision)
    if m:
        body = decision[m.end():]
        level = len(m.group(1))
        end = re.search(rf"^(?:#{{1,{level}}}\s|{_FIELD_AFTER_THESIS})", body, re.I | re.M)
        return body[: end.start()] if end else body
    return "\n".join(line for line in decision.splitlines() if not _RATING_LINE.match(line))


_BULLET = re.compile(r"^\s*(?:[-*+•]|\d{1,2}[.)])\s+")
_TABLE_RULE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")
_ABBREVIATION = re.compile(
    r"(?:\b(?:Inc|Corp|Co|Ltd|Plc|vs|etc|approx|est|incl|Mr|Ms|Dr|St|No|Jan|Feb|Mar|Apr|"
    r"Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)|\be\.g|\bi\.e|\b[A-Z](?:\.[A-Z])*)\.$"
)
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])([\"'”’)\]]*)\s+(?=[\"“(\[]?[A-Z0-9$])")


def strip_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links keep their text
    text = re.sub(r"^\s*(?:#{1,6}\s+|>\s*)", "", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"(?<!\w)\*(?=\S)|(?<=\S)\*(?!\w)", "", text)  # *emphasis*
    if text.count("|") >= 2:  # a table row: its cells, in order
        text = ", ".join(c.strip() for c in text.strip().strip("|").split("|") if c.strip())
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> list[str]:
    """Sentences of one paragraph or bullet, not breaking after abbreviations."""
    out, start = [], 0
    for m in _SENTENCE_BREAK.finditer(text):
        if _ABBREVIATION.search(text[start:m.start()]):
            continue
        out.append(text[start:m.start() + len(m.group(1))].strip())
        start = m.end()
    out.append(text[start:].strip())
    return [s for s in out if s]


def split_claims(thesis: str) -> list[str]:
    """Bullets and sentences of the thesis, without markdown, fragments or repeats.

    Every result is a candidate: Jev decides which are checkable facts.
    """
    units: list[str] = []
    paragraph: list[str] = []

    def flush():
        if paragraph:
            units.append(" ".join(paragraph))
            paragraph.clear()

    for line in thesis.splitlines():
        if not line.strip() or _TABLE_RULE.match(line):
            flush()
        elif _BULLET.match(line) or line.lstrip().startswith(("#", "|")):
            flush()
            units.append(_BULLET.sub("", line))
        else:
            paragraph.append(line.strip())
    flush()

    claims: list[str] = []
    for unit in units:
        for sentence in split_sentences(strip_markdown(unit)):
            if len(sentence) >= MIN_CLAIM_CHARS and sentence not in claims:
                claims.append(sentence)
    return claims


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Section:
    """One part of one analyst report, as Jev sees it and as the output cites it."""

    report: str  # short name, e.g. "fundamentals"
    heading: str  # its headings with text of their own, "" when it has none
    text: str
    part: int = 1  # position within the report, for citing a section without a heading

    @property
    def label(self) -> str:
        where = f'"{_quote(self.heading, 60)}"' if self.heading else f"part {self.part}"
        return f"{self.report} report, {where}"


_HEADING = re.compile(r"^\s{0,3}(?:#{1,6}\s+(.+?)\s*#*\s*|\*\*([^*\n]{2,80}?)\*\*:?\s*)$")


def _heading(line: str) -> str | None:
    m = _HEADING.match(line)
    if not m:
        return None
    return strip_markdown(m.group(1) or m.group(2)).rstrip(":")


def _blocks(text: str) -> list[str]:
    """Paragraph blocks, with each markdown table kept whole as its own block."""
    blocks: list[list[str]] = []
    for line in text.splitlines():
        if not line.strip():
            blocks.append([])
            continue
        is_table = line.lstrip().startswith("|")
        if not blocks or not blocks[-1] or blocks[-1][-1].lstrip().startswith("|") != is_table:
            blocks.append([])
        blocks[-1].append(line)
    return ["\n".join(b) for b in blocks if b]


def _pieces(block: str) -> list[str]:
    """``block`` in pieces of at most ``SECTION_CHARS``, cut at lines, then at
    sentences. A table stays whole whatever its length."""
    if len(block) <= SECTION_CHARS or block.lstrip().startswith("|"):
        return [block]
    pieces = []
    for line in block.splitlines():
        for sentence in split_sentences(line) if len(line) > SECTION_CHARS else [line]:
            while len(sentence) > SECTION_CHARS:  # one enormous sentence: a hard cut
                pieces.append(sentence[:SECTION_CHARS])
                sentence = sentence[SECTION_CHARS:]
            pieces.append(sentence)
    return _pack(pieces, "\n")


def _pack(pieces: Sequence[str], sep: str) -> list[str]:
    chunks: list[str] = []
    for piece in pieces:
        if chunks and len(chunks[-1]) + len(sep) + len(piece) <= SECTION_CHARS:
            chunks[-1] += sep + piece
        else:
            chunks.append(piece)
    return chunks


def split_sections(report: str, text: str) -> list[Section]:
    """Split a report at its headings, then long parts at paragraph blocks.

    Parts shorter than ``SMALL_SECTION_CHARS`` are merged into a neighbour, so a
    heading followed straight by a subheading does not become a question of its own.
    """
    parts: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        heading = _heading(line)
        if heading is not None:
            parts.append((heading, []))
        parts[-1][1].append(line)

    # (heading, text); the heading is "" for text before the first heading, and
    # for a heading line with no text of its own, which names nothing when merged.
    chunks: list[tuple[str, str]] = []
    for heading, lines in parts:
        body = "\n".join(lines).strip()
        if not body:
            continue
        own_text = any(line.strip() for line in lines[1 if heading else 0:])
        if len(body) <= SECTION_CHARS:
            chunks.append((heading if own_text else "", body))
            continue
        pieces = [p for block in _blocks(body) for p in _pieces(block)]
        chunks.extend((heading, chunk) for chunk in _pack(pieces, "\n\n"))

    merged: list[tuple[list[str], str]] = []
    for heading, body in chunks:
        if merged:
            headings, prev = merged[-1]
            small = len(prev) < SMALL_SECTION_CHARS or len(body) < SMALL_SECTION_CHARS
            if small and len(prev) + 2 + len(body) <= SECTION_CHARS:
                merged[-1] = (headings + [heading], f"{prev}\n\n{body}")
                continue
        merged.append(([heading], body))

    sections = []
    for i, (headings, body) in enumerate(merged, start=1):
        names = dict.fromkeys(h for h in headings if h)
        sections.append(Section(report, " / ".join(names), body, i))
    return sections


def analyst_reports(state: Mapping[str, Any]) -> dict[str, str]:
    """Non-empty analyst reports in the state, by short name."""
    return {
        name: text.strip()
        for key, name in REPORTS.items()
        if isinstance(text := state.get(key), str) and text.strip()
    }


# ---------------------------------------------------------------------------
# Figures (in code)
# ---------------------------------------------------------------------------

_SCALES = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mm": 1e6, "mn": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
    "t": 1e12, "tn": 1e12, "trillion": 1e12,
}
_NUMBER = re.compile(r"(?<![\w.'’])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?")
# The unit written after a number: a scale letter attached to it, or a word.
_UNIT = re.compile(
    r"(?P<scale>[kKmMbBtT]|mm|mn|bn|tn)(?![A-Za-z])"
    r"|\s?(?P<pct>%|percent\b|per cent\b|pct\b|percentage points?\b|pp\b|ppts?\b)"
    r"|\s?(?P<bps>bps\b|bp\b|basis points?\b)"
    r"|\s?(?P<mult>x\b|×|times\b)"
    r"|\s?(?P<word>thousand|million|billion|trillion|mm|mn|bn|tn)\b",
    re.I,
)
_RANGE = re.compile(r"\s?(?:-|–|—|to)\s?(?=\$?\d)")
_TIME_UNIT = re.compile(
    r"[\s-]*(?:trading\s+)?(?:days?|weeks?|months?|quarters?|years?|yrs?|sessions?|hours?)\b", re.I
)
_INDEX_NAME = re.compile(
    r"(?:S&P|Nasdaq|NASDAQ|Russell|FTSE|Nikkei|DAX|CAC|Stoxx|STOXX|ASX|TSX|Nifty|NIFTY|KOSPI)"
    r"[\s-]*$"
)
_CURRENCY = re.compile(r"[$€£¥₹]\s?$")
_INDEX_SIZES = {30, 40, 50, 60, 100, 200, 225, 250, 350, 400, 500, 600, 1000, 2000, 3000, 5000}
_MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
          r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b\.?")
_DATES = re.compile(
    rf"\b\d{{4}}-\d{{2}}-\d{{2}}\b|\b\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?\b"
    rf"|\b{_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?\b|\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH}"
)


@dataclass(frozen=True)
class Figure:
    """A number as written: its digits, scale and kind, for matching at its precision."""

    written: str
    mantissa: float  # absolute value as written, before the scale
    decimals: int
    scale: float  # 1 when no scale is written
    kind: str  # pct, bps, mult or num (plain numbers and currency amounts)

    @property
    def value(self) -> float:
        return self.mantissa * self.scale


def _kind(m: re.Match | None) -> tuple[str, float]:
    if m is None:
        return "num", 1.0
    if m.group("scale"):
        return "num", _SCALES[m.group("scale").lower()]
    if m.group("word"):
        return "num", _SCALES[m.group("word").lower()]
    for kind in ("pct", "bps", "mult"):
        if m.group(kind):
            return kind, 1.0
    return "num", 1.0


def figures(text: str, *, claim: bool = True) -> list[Figure]:
    """The figures written in ``text``.

    Numbers that are part of a name or a label are never figures: Q3, 10-K,
    H100, S&P 500, dates, a ticker's exchange code. In a claim (``claim=True``)
    years, periods such as "12 months", and bare counts below 10 are also
    skipped; in a report every number counts, since it can only confirm.
    """
    text = _DATES.sub(" ", text)
    found: list[Figure] = []
    matches = list(_NUMBER.finditer(text))
    for i, m in enumerate(matches):
        before, after = text[:m.start()], text[m.end():]
        if re.search(r"[A-Za-z][-/]$", before) or re.match(r"(?:[-.][A-Za-z])", after):
            continue  # GPT-4, COVID-19, 10-K, 200-day, 7203.T
        if re.match(r"[A-Za-z]", after) and not _UNIT.match(after):
            continue  # 5G, 3rd, 4Q
        digits, decimals = m.group(1).replace(",", ""), m.group(2) or ""
        mantissa = float(digits + decimals)
        if _INDEX_NAME.search(before) and not decimals and int(digits) in _INDEX_SIZES:
            continue
        own_unit = unit = _UNIT.match(after)
        if unit is None and (rng := _RANGE.match(after)):
            # The low end of a range takes the high end's unit: "10-15%".
            nxt = matches[i + 1] if i + 1 < len(matches) else None
            if nxt is not None and nxt.start() <= m.end() + rng.end() + 1:
                unit = _UNIT.match(text[nxt.end():])
        kind, scale = _kind(unit)
        currency = _CURRENCY.search(before)
        if claim and unit is None and not currency:
            if not decimals and "," not in m.group(1) and 1900 <= mantissa <= 2099:
                continue  # a year
            if _TIME_UNIT.match(after):
                continue  # a period: "12 months", "3 years"
            if not decimals and mantissa < 10:
                continue  # a count: "2 analysts", "3 quarters"
        written = (currency.group(0).strip() if currency else "") + m.group(0)
        if own_unit:
            written += own_unit.group(0)
        found.append(Figure(written.strip(), mantissa, len(decimals) - 1 if decimals else 0, scale, kind))
    return found


_COMPATIBLE = {"pct": {"pct"}, "bps": {"bps"}, "mult": {"mult", "num"}, "num": {"num", "mult"}}


def figure_stated(fig: Figure, stated: Sequence[Figure]) -> bool:
    """Whether a report states ``fig`` when rounded to the claim's precision.

    Signs are ignored (the direction is Jev's question). When either side has
    no scale, the digits alone are also compared, since a table often gives its
    unit in a header: "Revenue ($B) | 130.5".
    """
    step = 10.0 ** -fig.decimals
    for r in stated:
        if r.kind not in _COMPATIBLE[fig.kind]:
            continue
        tolerance = step * fig.scale / 2 * (1 + 1e-9)
        if abs(r.value - fig.value) <= tolerance:
            return True
        if (fig.scale == 1 or r.scale == 1) and abs(r.mantissa - fig.mantissa) <= step / 2 * (1 + 1e-9):
            return True
    return False


def unstated_figures(claim: str, stated: Sequence[Figure]) -> list[str]:
    return [f.written for f in figures(claim) if not figure_stated(f, stated)]


# ---------------------------------------------------------------------------
# Checking
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClaimResult:
    claim: str
    checkable: float
    verdict: str  # supported, contradicted, unsupported, not_checkable
    probability: float = 0.0  # P(supports) or P(contradicts) behind the verdict
    section: Section | None = None  # the section behind the verdict, or the closest one
    sources: Mapping[str, float] = field(default_factory=dict)
    figures: tuple[str, ...] = ()  # figures no report states


@dataclass(frozen=True)
class ClaimCheck:
    results: tuple[ClaimResult, ...]
    candidates: int  # claims read from the thesis, before the cap
    review: bool
    reasons: tuple[str, ...]

    def with_verdict(self, verdict: str) -> list[ClaimResult]:
        return [r for r in self.results if r.verdict == verdict]

    @property
    def checkable(self) -> list[ClaimResult]:
        return [r for r in self.results if r.verdict != "not_checkable"]


def instrument_from_state(state: Mapping[str, Any]) -> dict[str, str]:
    """Ticker, name and classification, read from the context resolved at run start.

    The Portfolio Manager runs mid-graph, so the identity is taken from the
    instrument context already on the state rather than looked up again.
    """
    instrument = {"ticker": str(state.get("company_of_interest", ""))}
    context = state.get("instrument_context") or ""
    m = re.search(r"Resolved identity: (.*?)\. Do not substitute", context)
    if m:
        for item in m.group(1).split("; "):
            key, _, value = item.partition(": ")
            if key in ("Company", "Name") and value:
                instrument["name"] = value
            elif key in ("Business classification", "Sector", "Industry") and value:
                instrument["classification"] = value
    if state.get("asset_type") == "crypto":
        instrument["asset_type"] = "crypto asset"
    return instrument


def run_check(
    client,
    decision: str,
    reports: Mapping[str, str],
    instrument: Mapping[str, str],
    policy: ClaimCheckPolicy = DEFAULT_POLICY,
) -> ClaimCheck:
    """Judge every claim of ``decision`` against ``reports``.

    Raises when a Jev request fails, so the caller keeps the decision as written
    rather than acting on a partial check.
    """
    candidates = split_claims(thesis_text(decision))
    claims = candidates[:MAX_CLAIMS]
    sources = list(reports)
    instrument = dict(instrument)

    responses = ask_each(
        client, [{"instrument": instrument, "claim": c} for c in claims], claim_questions(sources)
    )
    sections = {name: split_sections(name, text) for name, text in reports.items()}
    stated = [f for text in reports.values() for f in figures(text, claim=False)]

    # (claim index, section) for each request B.
    pairs: list[tuple[int, Section]] = []
    first_pass: list[ClaimResult] = []
    for i, (claim, response) in enumerate(zip(claims, responses, strict=True)):
        answers = response.answers
        p_checkable = answers["checkable"].noul
        # With one report there is nothing to route: all its sections are asked.
        p_source = dict(answers["source"].probabilities) if len(sources) > 1 else {sources[0]: 1.0}
        if p_checkable < policy.checkable_min:
            first_pass.append(ClaimResult(claim, p_checkable, "not_checkable", sources=p_source))
            continue
        first_pass.append(ClaimResult(
            claim, p_checkable, "unsupported", sources=p_source,
            figures=tuple(unstated_figures(claim, stated)),
        ))
        for name in sources:
            if p_source.get(name, 0.0) >= policy.source_floor:
                pairs.extend((i, s) for s in sections[name])

    relations = ask_each(
        client,
        [{"instrument": instrument, "claim": claims[i],
          "section": {"report": report_title(s.report), "heading": s.heading, "text": s.text}}
         for i, s in pairs],
        relation_questions(),
    )
    judged: dict[int, list[tuple[Section, Mapping[str, float]]]] = {}
    for (i, section), response in zip(pairs, relations, strict=True):
        judged.setdefault(i, []).append((section, response.answers["relation"].probabilities))

    results = []
    for i, result in enumerate(first_pass):
        if result.verdict == "not_checkable":
            results.append(result)
            continue
        verdict, p, section = claim_verdict(judged.get(i, []), policy)
        results.append(ClaimResult(
            result.claim, result.checkable, verdict, p, section, result.sources, result.figures,
        ))

    review, reasons = review_decision(results, policy)
    return ClaimCheck(tuple(results), len(candidates), review, reasons)


def claim_verdict(
    relations: Sequence[tuple[Section, Mapping[str, float]]],
    policy: ClaimCheckPolicy = DEFAULT_POLICY,
) -> tuple[str, float, Section | None]:
    """Supported by the best section, else contradicted by the worst, else unsupported.

    Returns the verdict, its probability, and the section behind it (for an
    unsupported claim, the closest one).
    """
    if not relations:
        return "unsupported", 0.0, None
    support = max(relations, key=lambda r: r[1].get("supports", 0.0))
    p_support = support[1].get("supports", 0.0)
    if p_support >= policy.supported_min:
        return "supported", p_support, support[0]
    against = max(relations, key=lambda r: r[1].get("contradicts", 0.0))
    p_against = against[1].get("contradicts", 0.0)
    if p_against >= policy.contradicted_min:
        return "contradicted", p_against, against[0]
    return "unsupported", p_support, support[0]


def review_decision(
    results: Sequence[ClaimResult], policy: ClaimCheckPolicy = DEFAULT_POLICY,
) -> tuple[bool, tuple[str, ...]]:
    """Whether the decision goes to REVIEW, and why. Unstated figures alone never do."""
    checkable = [r for r in results if r.verdict != "not_checkable"]
    contradicted = sum(r.verdict == "contradicted" for r in checkable)
    unsupported = sum(r.verdict == "unsupported" for r in checkable)
    reasons = []
    if contradicted:
        reasons.append(f"{_n(contradicted, 'claim')} contradicted by the analyst reports")
    if (unsupported >= policy.review_unsupported_min
            and unsupported >= policy.review_unsupported_share * len(checkable)):
        reasons.append(f"{unsupported} of {len(checkable)} checkable claims not found in the analyst reports")
    return bool(reasons), tuple(reasons)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

# A quoted "rating: X" must not read as the decision's rating label (rating.py
# takes the last labelled line), so its separator is dropped in quotes.
_LABEL_IN_QUOTE = re.compile(r"(\brating\b[^:\-\u2010-\u2015]*)[:\-\u2010-\u2015]+", re.I)


def _quote(text: str, limit: int = _QUOTE_CHARS) -> str:
    text = re.sub(r"\s+", " ", text).strip().replace('"', "'")
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return _LABEL_IN_QUOTE.sub(r"\1", text)


def _n(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def render_claim_check(check: ClaimCheck, pm_rating: str | None) -> str:
    """The block appended to the decision: a summary line, the failures, the rating."""
    checkable = check.checkable
    read = f"{_n(check.candidates, 'statement')} read from the Investment Thesis"
    if check.candidates > len(check.results):
        read += f" (the first {len(check.results)} checked)"
    if not checkable:
        return (f"**Claim Check**: {read}; none is a checkable fact about the instrument "
                f"or its market, so nothing was checked against the analyst reports.")

    counts = {v: len(check.with_verdict(v)) for v in ("supported", "contradicted", "unsupported")}
    tally = ", ".join(f"{n} {label}" for n, label in (
        (counts["supported"], "supported"),
        (counts["contradicted"], "contradicted"),
        (counts["unsupported"], "not found"),
    ) if n)
    unmatched = [(r, f) for r in checkable for f in r.figures]
    summary = f"**Claim Check**: {read}, {len(checkable)} checkable against the analyst reports: {tally}."
    if unmatched:
        summary += f" {_n(len(unmatched), 'figure')} in no report."
    summary += " (Claims judged by TypeSafe Jev; figures matched in code.)"

    lines = [summary]
    for r in check.with_verdict("contradicted"):
        lines.append(f'- Contradicted: "{_quote(r.claim)}" ({r.section.label}; '
                     f"contradicts {r.probability:.2f})")
    for r in check.with_verdict("unsupported"):
        where = (f"closest: {r.section.label}; supports {r.probability:.2f}"
                 if r.section else "no report section could hold it")
        lines.append(f'- Not found: "{_quote(r.claim)}" ({where})')
    for r, fig in unmatched:
        lines.append(f'- Figure in no report: {fig} in "{_quote(r.claim)}"')

    if check.review:
        called = f"the Portfolio Manager rated {pm_rating}" if pm_rating else \
            "no rating could be read from the Portfolio Manager's decision"
        lines.append("")
        lines.append(f"**Rating after claim check**: REVIEW ({called}; {'; '.join(check.reasons)})")
    return "\n".join(lines)


def check_claims(
    decision: str, state: Mapping[str, Any], policy: ClaimCheckPolicy = DEFAULT_POLICY,
) -> str:
    """The decision with its claim check appended, or unchanged without Jev.

    Unchanged when the check is switched off, no analyst report was written,
    Jev is unavailable, or any Jev request fails.
    """
    if not get_config().get("jev_claim_check", True):
        return decision
    reports = analyst_reports(state)
    if not reports or not decision.strip():
        return decision
    client = jev_client()
    if client is None:
        return decision
    try:
        with client:
            check = run_check(client, decision, reports, instrument_from_state(state), policy)
    except Exception as exc:  # noqa: BLE001 — keep the decision as the Portfolio Manager wrote it
        logger.warning(
            "Portfolio Manager: claim check failed (%s); keeping the decision unchecked", exc,
        )
        return decision
    pm_rating = extract_rating(decision)
    logger.info(
        "Portfolio Manager: claim check read %d claims, %d checkable, review=%s",
        len(check.results), len(check.checkable), check.review,
    )
    return f"{decision.rstrip()}\n\n{render_claim_check(check, pm_rating)}"
