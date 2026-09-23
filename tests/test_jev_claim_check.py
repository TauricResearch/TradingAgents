"""Portfolio Manager claim check with TypeSafe Jev (docs/jev-use-cases.md, fit 4).

The Investment Thesis is split into claims in code; Jev says which are
checkable facts and which report would state them, then how each section of
those reports bears on each claim. Verdicts, the figures check and whether the
decision goes to REVIEW are code. Without Jev, or when a request fails, the
decision is kept as the Portfolio Manager wrote it.

A fake client stands in for the service: it answers from markers in the claim
and section text, so the tests pin the policy and the plumbing, not the model.
Claim markers: ``[fact]`` (checkable), ``[src:<report>]`` (routing), and
``[key:<name>]``; a section marks its relation to a claim with
``[supports:<name>]`` or ``[contra:<name>]``, and says nothing about the rest;
``[numeric:<name>]`` marks a relation that would take comparing numbers.
"""

from __future__ import annotations

import logging
import re
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating, render_pm_decision
from tradingagents.agents.utils import claim_check as cc
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.rating import RATING_REVIEW, extract_rating
from tradingagents.dataflows.config import set_config
from tradingagents.graph.signal_processing import SignalProcessor

# ---------------------------------------------------------------------------
# A fake Jev client
# ---------------------------------------------------------------------------


def _noul(p):
    return SimpleNamespace(noul=p)


def _choice(probabilities):
    best = max(probabilities, key=probabilities.get)
    return SimpleNamespace(choice=best, confidence=probabilities[best], probabilities=probabilities)


def _claim_answers(state, questions):
    claim = state["claim"]
    answers = {"checkable": _noul(0.9 if "[fact]" in claim else 0.1)}
    if "source" in questions:
        options = list(questions["source"].criteria)
        marked = [o for o in options if f"[src:{o}]" in claim]
        rest = [o for o in options if o not in marked]
        if marked:
            probabilities = {o: (0.9 if rest else 1.0) / len(marked) for o in marked}
            probabilities.update({o: 0.1 / len(rest) for o in rest})
        else:
            probabilities = {o: 1 / len(options) for o in options}
        answers["source"] = _choice(probabilities)
    return answers


_RELATIONS = {
    "supports": {"supports": 0.9, "contradicts": 0.02, "says_nothing": 0.08},
    "contra": {"supports": 0.05, "contradicts": 0.9, "says_nothing": 0.05},
}
_NOTHING = {"supports": 0.05, "contradicts": 0.05, "says_nothing": 0.9}


def _relation_answers(state):
    key = re.search(r"\[key:(\w+)\]", state["claim"])
    text = state["section"]["text"]
    relation = next(
        (r for r in _RELATIONS if key and f"[{r}:{key.group(1)}]" in text), None
    )
    numeric = bool(key) and f"[numeric:{key.group(1)}]" in text
    return {"relation": _choice(dict(_RELATIONS[relation] if relation else _NOTHING)),
            "needs_numbers": _noul(0.9 if numeric else 0.1)}


class FakeJev:
    """Answers from markers in the claim and section text; records every request."""

    def __init__(self, fail_on=None):
        self.fail_on = fail_on  # "checkable" or "relation": fail requests asking it
        self.requests = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True

    def system_one(self, state, questions):
        self.requests.append((state, questions))
        if self.fail_on in questions:
            raise RuntimeError("jev is down")
        if "relation" in questions:
            return SimpleNamespace(answers=_relation_answers(state))
        return SimpleNamespace(answers=_claim_answers(state, questions))

    def asked(self, question):
        return [state for state, questions in self.requests if question in questions]


INSTRUMENT = {"ticker": "NVDA", "name": "NVIDIA Corporation"}

REPORTS = {
    "market": (
        "## Price action\nThe stock closed at $118.40, above its 200-day average. "
        "RSI(14) is 68.2. [supports:trend]"
    ),
    "news": (
        "## Company news\nNvidia announced a new supply deal with a cloud provider. "
        "[supports:deal]\n\n## Macro\nThe Fed held rates at 5.25%."
    ),
    "fundamentals": (
        "## Revenue\nData-center revenue grew 22.4% to $30.77 billion. [supports:revenue]\n\n"
        "## Margins\nGross margin fell to 71.2% from 75% a year earlier. [contra:margin]"
    ),
}


def _state(reports=REPORTS, **extra):
    state = {f"{name}_report": text for name, text in reports.items()}
    state.update({"company_of_interest": "NVDA", "asset_type": "stock"})
    state.update(extra)
    return state


def _decision(thesis, rating=PortfolioRating.BUY):
    return render_pm_decision(PortfolioDecision(
        rating=rating, executive_summary="Accumulate over two weeks.",
        investment_thesis=thesis, price_target=140.0, time_horizon="3-6 months",
    ))


THESIS = "\n".join([
    "The bull case carried the debate over the bears on valuation.",
    "- Data-center revenue grew 22% to $30.8B last quarter [fact] [src:fundamentals] [key:revenue]",
    "- Gross margin expanded to 75% on pricing power [fact] [src:fundamentals] [key:margin]",
    "- The stock trades above its 200-day average at $118 [fact] [src:market] [key:trend]",
    "- We recommend accumulating on dips toward $110 over the next month.",
])


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestThesis:
    def test_the_rendered_thesis_stops_at_the_price_target(self):
        text = cc.thesis_text(_decision("Revenue grew 22% on data-center demand."))
        assert text.strip() == "Revenue grew 22% on data-center demand."

    def test_a_free_text_heading_runs_to_the_next_heading_of_its_level(self):
        decision = (
            "## Executive Summary\nBuy now.\n\n## Investment Thesis\nRevenue grew 22%.\n\n"
            "### Detail\nMargins expanded.\n\n## Risks\nChina export limits."
        )
        text = cc.thesis_text(decision)
        assert "Revenue grew" in text and "Margins expanded" in text
        assert "Buy now" not in text and "China export" not in text

    def test_without_a_thesis_the_whole_text_minus_the_rating_line_is_read(self):
        text = cc.thesis_text("**Rating**: Buy\n\nRevenue grew 22% on data-center demand.")
        assert "Rating" not in text and "Revenue grew" in text


@pytest.mark.unit
class TestSplitClaims:
    def test_bullets_and_sentences_are_claims(self):
        claims = cc.split_claims(
            "Revenue grew 22% on data-center demand. Margins expanded to 75% last quarter.\n"
            "- Hyperscaler capex guidance was raised again\n"
            "* The stock trades above its 200-day average"
        )
        assert claims == [
            "Revenue grew 22% on data-center demand.",
            "Margins expanded to 75% last quarter.",
            "Hyperscaler capex guidance was raised again",
            "The stock trades above its 200-day average",
        ]

    def test_abbreviations_do_not_end_a_sentence(self):
        claims = cc.split_claims(
            "NVIDIA Corp. vs. AMD: forward P/E of 32x against 28x. U.S. export rules "
            "tightened in the quarter, e.g. for H20 chips."
        )
        assert claims == [
            "NVIDIA Corp. vs. AMD: forward P/E of 32x against 28x.",
            "U.S. export rules tightened in the quarter, e.g. for H20 chips.",
        ]

    def test_markdown_is_stripped_and_fragments_and_repeats_dropped(self):
        claims = cc.split_claims(
            "**Key drivers:**\n"
            "- **Margins:** gross margin reached `75%` per the [10-K](http://x)\n"
            "- **Margins:** gross margin reached `75%` per the [10-K](http://x)\n"
            "- Too short.\n"
            "| Metric | Value |\n|---|---|\n| Gross margin reported | 75% |"
        )
        assert claims == [
            "Margins: gross margin reached 75% per the 10-K",
            "Gross margin reported, 75%",
        ]

    def test_a_long_thesis_is_capped(self):
        thesis = " ".join(f"Claim number {i} is a checkable fact [fact]." for i in range(25))
        client = FakeJev()
        check = cc.run_check(client, f"**Investment Thesis**: {thesis}", {"news": "x"}, INSTRUMENT)
        assert len(client.asked("checkable")) == cc.MAX_CLAIMS
        assert check.candidates == 25
        assert "(the first 20 checked)" in cc.render_claim_check(check, "Buy")


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

_PARA = "Revenue rose strongly this quarter on data-center demand and new customers. " * 13


@pytest.mark.unit
class TestSplitSections:
    def test_reports_split_at_headings(self):
        report = f"## Revenue\n{_PARA}\n\n## Margins\n{_PARA}"
        sections = cc.split_sections("fundamentals", report)
        assert [s.heading for s in sections] == ["Revenue", "Margins"]
        assert sections[1].text.startswith("## Margins")

    def test_a_bold_line_is_a_heading(self):
        sections = cc.split_sections("news", f"**Company news**\n{_PARA}\n\n**Macro**:\n{_PARA}")
        assert [s.heading for s in sections] == ["Company news", "Macro"]

    def test_long_parts_split_at_paragraphs(self):
        report = "## Revenue\n" + "\n\n".join(f"Paragraph {i}. {_PARA}" for i in range(4))
        sections = cc.split_sections("fundamentals", report)
        assert len(sections) > 1
        assert all(len(s.text) <= cc.SECTION_CHARS for s in sections)
        assert all(s.heading == "Revenue" for s in sections)
        assert all(s.text.startswith(("## Revenue", "Paragraph")) for s in sections)

    def test_tables_stay_whole(self):
        table = "| Item | Value |\n|---|---|\n" + "\n".join(f"| Line item {i} | {i}.5% |" for i in range(150))
        assert len(table) > cc.SECTION_CHARS
        sections = cc.split_sections("fundamentals", f"## Key metrics\n{_PARA}\n\n{table}")
        assert any(table in s.text for s in sections)

    def test_small_parts_are_merged_and_named_by_headings_with_text(self):
        report = ("# NVDA Fundamentals\n\n## Summary\nShort intro.\n\n## Margins\nGross margin 75%."
                  "\n\n## Cash flow\nFree cash flow $13.5B.")
        sections = cc.split_sections("fundamentals", report)
        assert len(sections) == 1
        assert sections[0].heading == "Summary / Margins / Cash flow"
        assert sections[0].label == 'fundamentals report, "Summary / Margins / Cash flow"'
        assert sections[0].text == report

    def test_a_section_without_a_heading_is_cited_by_position(self):
        sections = cc.split_sections("market", f"{_PARA}\n\n{_PARA}\n\n{_PARA}")
        assert [s.label for s in sections][:2] == ["market report, part 1", "market report, part 2"]

    def test_only_written_reports_count(self):
        state = _state({"market": "M", "sentiment": "  ", "news": "", "fundamentals": "F"})
        assert cc.analyst_reports(state) == {"market": "M", "fundamentals": "F"}


# ---------------------------------------------------------------------------
# Routing (requests A and B)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRouting:
    def test_one_request_per_claim_asks_checkable_and_source_over_the_reports_present(self):
        client = FakeJev()
        cc.run_check(client, _decision(THESIS), REPORTS, INSTRUMENT)
        first = [(s, q) for s, q in client.requests if "checkable" in q]
        assert len(first) == 5
        assert all(set(q) == {"checkable", "source"} for _, q in first)
        assert list(first[0][1]["source"].criteria) == ["market", "news", "fundamentals"]
        assert first[0][0] == {"instrument": INSTRUMENT, "claim": first[0][0]["claim"]}

    def test_sections_below_the_source_floor_are_not_asked(self):
        client = FakeJev()
        cc.run_check(client, _decision(THESIS), REPORTS, INSTRUMENT)
        margin = [s for s in client.asked("relation") if "[key:margin]" in s["claim"]]
        assert {s["section"]["report"] for s in margin} == {"Fundamentals Analyst report"}
        # Only the three checkable claims are paired with sections.
        assert {s["claim"] for s in client.asked("relation")} == {
            c for c in cc.split_claims(THESIS) if "[fact]" in c
        }

    def test_an_unrouted_claim_is_asked_of_every_report(self):
        client = FakeJev()
        cc.run_check(client, "**Investment Thesis**: The Fed held rates steady this month [fact].",
                     REPORTS, INSTRUMENT)
        sections = sum(len(cc.split_sections(n, t)) for n, t in REPORTS.items())
        assert len(client.asked("relation")) == sections

    def test_with_one_report_there_is_no_source_question(self):
        client = FakeJev()
        cc.run_check(client, _decision(THESIS), {"fundamentals": REPORTS["fundamentals"]}, INSTRUMENT)
        assert all("source" not in q for _, q in client.requests)
        assert len(client.asked("relation")) == 3 * len(cc.split_sections("fundamentals", REPORTS["fundamentals"]))

    def test_the_section_state_names_its_report_and_heading(self):
        client = FakeJev()
        cc.run_check(client, _decision(THESIS), REPORTS, INSTRUMENT)
        state = next(s for s in client.asked("relation") if "[key:trend]" in s["claim"])
        assert set(state) == {"instrument", "claim", "section"}
        assert state["section"]["report"] == "Market Analyst report"
        assert state["section"]["heading"] == "Price action"
        assert "RSI(14) is 68.2" in state["section"]["text"]


@pytest.mark.unit
class TestInstrument:
    def test_identity_is_read_from_the_resolved_context(self):
        context = build_instrument_context("NVDA", "stock", {
            "company_name": "NVIDIA Corporation", "sector": "Technology", "industry": "Semiconductors",
        })
        instrument = cc.instrument_from_state({"company_of_interest": "NVDA", "instrument_context": context})
        assert instrument == {"ticker": "NVDA", "name": "NVIDIA Corporation",
                              "classification": "Technology / Semiconductors"}

    def test_crypto_and_bare_states(self):
        assert cc.instrument_from_state({"company_of_interest": "BTC-USD", "asset_type": "crypto"}) == {
            "ticker": "BTC-USD", "asset_type": "crypto asset"}


# ---------------------------------------------------------------------------
# Verdicts and policy
# ---------------------------------------------------------------------------

_A = cc.Section("fundamentals", "Revenue", "a")
_B = cc.Section("news", "Macro", "b")


def _rel(section, supports=0.05, contradicts=0.05, needs_numbers=0.1):
    return section, {"supports": supports, "contradicts": contradicts,
                     "says_nothing": 1 - supports - contradicts, "needs_numbers": needs_numbers}


@pytest.mark.unit
class TestVerdict:
    def test_the_best_supporting_section_decides(self):
        assert cc.claim_verdict([_rel(_A, supports=0.3), _rel(_B, supports=0.6)]) == ("supported", 0.6, _B)

    def test_support_wins_over_a_contradiction_elsewhere(self):
        verdict, _, section = cc.claim_verdict([_rel(_A, contradicts=0.9), _rel(_B, supports=0.7)])
        assert (verdict, section) == ("supported", _B)

    def test_a_confident_contradiction_without_support(self):
        assert cc.claim_verdict([_rel(_A, contradicts=0.85), _rel(_B, supports=0.5)]) == ("contradicted", 0.85, _A)

    def test_neither_is_unsupported_citing_the_closest_section(self):
        assert cc.claim_verdict([_rel(_A, supports=0.55, contradicts=0.4), _rel(_B, supports=0.2)]) == (
            "unsupported", 0.55, _A)
        assert cc.claim_verdict([]) == ("unsupported", 0.0, None)

    def test_thresholds_come_from_the_policy(self):
        strict = cc.ClaimCheckPolicy(supported_min=0.95)
        assert cc.claim_verdict([_rel(_A, supports=0.9)], strict)[0] == "unsupported"

    @pytest.mark.parametrize("relation", [{"contradicts": 0.95}, {"supports": 0.9}, {"supports": 0.58, "contradicts": 0.42}])
    def test_a_section_that_needs_numbers_compared_leaves_the_claim_unverified(self, relation):
        """Live, "trades below its five-year average" against 29.5x and 36x came
        out either way: Jev cannot compare numbers, so neither side counts."""
        assert cc.claim_verdict([_rel(_A, needs_numbers=0.93, **relation), _rel(_B)]) == ("unverified", 0.93, _A)

    def test_a_worded_section_still_decides_next_to_a_numeric_one(self):
        verdict, _, section = cc.claim_verdict([_rel(_A, contradicts=0.9, needs_numbers=0.9),
                                                _rel(_B, supports=0.8)])
        assert (verdict, section) == ("supported", _B)
        verdict, _, section = cc.claim_verdict([_rel(_A, supports=0.9, needs_numbers=0.9),
                                                _rel(_B, contradicts=0.9)])
        assert (verdict, section) == ("contradicted", _B)

    def test_a_numeric_section_that_says_nothing_is_not_a_verdict(self):
        assert cc.claim_verdict([_rel(_A, supports=0.2, contradicts=0.1, needs_numbers=0.9)])[0] == "unsupported"


def _result(verdict, figures=()):
    return cc.ClaimResult("c", 0.9, verdict, figures=figures)


@pytest.mark.unit
class TestReviewPolicy:
    def test_one_contradicted_claim_sends_the_decision_to_review(self):
        review, reasons = cc.review_decision([_result("supported")] * 5 + [_result("contradicted")])
        assert review and reasons == ("1 claim contradicted by the analyst reports",)

    @pytest.mark.parametrize(("unsupported", "supported", "review"), [
        (2, 2, True),    # 2 of 4: at least 2, and half
        (2, 3, False),   # 2 of 5: under half
        (1, 0, False),   # 1 of 1: fewer than 2
        (3, 1, True),
    ])
    def test_unsupported_claims_need_a_count_and_a_share(self, unsupported, supported, review):
        results = [_result("unsupported")] * unsupported + [_result("supported")] * supported
        assert cc.review_decision(results)[0] is review

    def test_claims_that_are_not_checkable_do_not_count(self):
        results = [_result("unsupported")] * 2 + [_result("supported")] * 3 + [_result("not_checkable")] * 9
        assert cc.review_decision(results)[0] is False

    def test_unstated_figures_alone_never_do(self):
        assert cc.review_decision([_result("supported", figures=("45%", "$9B"))])[0] is False

    def test_unverified_claims_never_do(self):
        assert cc.review_decision([_result("unverified")] * 3 + [_result("supported")])[0] is False


# ---------------------------------------------------------------------------
# Figures (in code)
# ---------------------------------------------------------------------------


def _written(text):
    return [f.written for f in cc.figures(text)]


@pytest.mark.unit
class TestFigures:
    @pytest.mark.parametrize("text", [
        "Revenue beat in Q3 2026", "as filed in the 10-K", "outperformed the S&P 500 index",
        "H100 and B200 shipments", "earnings on Sept 23", "as of 2026-09-23",
        "over the last 12 months", "2 analysts upgraded it", "above the 200-day average",
        "GPT-4 class models", "the 5G rollout", "a 3rd straight beat", "7203.T shares",
        "a Nasdaq-100 member", "over the next 3-6 months",
    ])
    def test_names_labels_dates_years_periods_and_counts_are_not_figures(self, text):
        assert _written(text) == []

    def test_units_and_scales(self):
        found = {f.written: (f.kind, f.value) for f in cc.figures(
            "grew 22% to $30.8B; $1.2 billion buyback; 450K units; $2.1T market cap; "
            "32.5x earnings; cut 50 bps; up 15 percent; trades at $5; S&P 500 at 5,800"
        )}
        assert found == {
            "22%": ("pct", 22.0), "$30.8B": ("num", 30.8e9), "$1.2 billion": ("num", 1.2e9),
            "450K": ("num", 450e3), "$2.1T": ("num", 2.1e12), "32.5x": ("mult", 32.5),
            "50 bps": ("bps", 50.0), "15 percent": ("pct", 15.0), "$5": ("num", 5.0),
            "5,800": ("num", 5800.0),
        }

    def test_the_low_end_of_a_range_takes_its_unit(self):
        assert [(f.written, f.kind) for f in cc.figures("margins of 10-15%")] == [("10", "pct"), ("15%", "pct")]

    def test_a_report_keeps_every_number(self):
        assert [f.written for f in cc.figures("in 2026, 3 new fabs", claim=False)] == ["2026", "3"]

    @pytest.mark.parametrize(("claim", "report", "stated"), [
        ("grew 22%", "grew 22.4%", True),              # rounded to the claim's precision
        ("grew 22.4%", "grew 22%", False),             # the claim is more precise than the report
        ("revenue of $31B", "revenue of $30.77 billion", True),
        ("revenue of $30.8B", "revenue of $30,770 million", True),
        ("revenue of $130.5B", "| Revenue ($B) | 130.5 |", True),  # unit in a table header
        ("grew 45%", "RSI at 45", False),              # a percentage is not a plain number
        ("P/E of 28x", "Trailing P/E: 28.3", True),     # a multiple may be written bare
        ("fell 3.2%", "change: -3.2%", True),           # the direction is Jev's question
        ("grew 45%", "grew 22.4%", False),
    ])
    def test_a_figure_is_stated_at_the_claims_precision(self, claim, report, stated):
        assert (cc.unstated_figures(claim, cc.figures(report, claim=False)) == []) is stated


# ---------------------------------------------------------------------------
# Output and the rating
# ---------------------------------------------------------------------------


def _check(thesis=THESIS, reports=REPORTS, rating=PortfolioRating.BUY):
    decision = _decision(thesis, rating)
    return decision, cc.run_check(FakeJev(), decision, reports, INSTRUMENT)


@pytest.mark.unit
class TestOutput:
    def test_a_contradicted_claim_is_cited_and_the_decision_goes_to_review(self):
        decision, check = _check()
        block = cc.render_claim_check(check, "Buy")
        lines = block.splitlines()
        assert lines[0].startswith(
            "**Claim Check**: 5 statements read from the Investment Thesis, 3 checkable "
            "against the analyst reports: 2 supported, 1 contradicted."
        )
        assert lines[1].startswith('- Contradicted: "Gross margin expanded to 75% on pricing power')
        assert lines[1].endswith('(fundamentals report, "Revenue / Margins"; contradicts 0.90)')
        assert lines[-1] == (
            "**Rating after claim check**: REVIEW (the Portfolio Manager rated Buy; "
            "1 claim contradicted by the analyst reports)"
        )
        full = f"{decision}\n\n{block}"
        assert extract_rating(decision) == "Buy"
        assert extract_rating(full) is None
        assert SignalProcessor().process_signal(full) == RATING_REVIEW

    def test_invented_facts_and_figures_are_listed(self):
        thesis = THESIS + "\n".join([
            "",
            "- Hyperscaler capex rose 45% this year [fact] [key:capex]",
            "- A second hyperscaler signed a multi-year supply deal [fact] [key:hyper]",
            "- Inventory days fell sharply as supply caught up [fact] [key:inventory]",
        ])
        _, check = _check(thesis)
        block = cc.render_claim_check(check, "Buy")
        assert "3 not found. 1 figure in no report." in block
        assert '- Not found: "Hyperscaler capex rose 45% this year' in block
        assert "(closest: " in block and "supports 0.05)" in block
        assert '- Figure in no report: 45% in "Hyperscaler capex rose 45%' in block
        assert "REVIEW (the Portfolio Manager rated Buy; 1 claim contradicted by the analyst " \
               "reports; 3 of 6 checkable claims not found in the analyst reports)" in block

    def test_a_claim_that_needs_numbers_compared_is_listed_as_unverified(self):
        thesis = THESIS.replace("[key:margin]", "[key:revenue]") + (
            "\n- At 29.5x forward earnings it trades below its average multiple [fact] [src:fundamentals] [key:pe]")
        reports = dict(REPORTS, fundamentals=REPORTS["fundamentals"] + (
            "\n\n## Valuation\n29.5x forward earnings against a five-year average of 36x. [contra:pe] [numeric:pe]"))
        decision, check = _check(thesis, reports)
        block = cc.render_claim_check(check, "Buy")
        assert "4 checkable against the analyst reports: 3 supported, 1 unverified." in block
        assert '- Unverified: "At 29.5x forward earnings it trades below its average multiple' in block
        assert block.endswith("; needs a numeric comparison 0.90)")
        assert not check.review and extract_rating(f"{decision}\n\n{block}") == "Buy"

    def test_a_supported_thesis_keeps_its_rating(self):
        thesis = THESIS.replace("[key:margin]", "[key:revenue]")
        decision, check = _check(thesis)
        block = cc.render_claim_check(check, "Buy")
        assert block.splitlines() == [
            "**Claim Check**: 5 statements read from the Investment Thesis, 3 checkable against "
            "the analyst reports: 3 supported. (Claims judged by TypeSafe Jev; figures matched in code.)"
        ]
        assert extract_rating(f"{decision}\n\n{block}") == "Buy"

    def test_with_no_checkable_claims_only_a_note_is_added(self):
        _, check = _check("We recommend buying on dips.\nThe bulls argued more convincingly than the bears.")
        block = cc.render_claim_check(check, "Buy")
        assert block.startswith("**Claim Check**: 2 statements read")
        assert "none is a checkable fact" in block and "REVIEW" not in block

    def test_an_unreadable_rating_is_named_as_such(self):
        _, check = _check()
        assert "(no rating could be read from the Portfolio Manager's decision; " in cc.render_claim_check(check, None)

    def test_a_quoted_rating_does_not_become_the_decision(self):
        """rating.py takes the last labelled line, so a claim quoting another
        rating must not read as a label after the Portfolio Manager's own."""
        decision = ("## Investment Thesis\n"
                    "- Analysts' consensus rating: Sell, yet revenue beat [fact] [key:odd]\n\n"
                    "**Rating**: Buy")
        check = cc.run_check(FakeJev(), decision, REPORTS, INSTRUMENT)
        block = cc.render_claim_check(check, "Buy")
        assert not check.review and "consensus rating Sell" in block
        assert extract_rating(f"{decision}\n\n{block}") == "Buy"


# ---------------------------------------------------------------------------
# Degrading, and the switch
# ---------------------------------------------------------------------------


def _no_client():
    raise AssertionError("jev_client must not be called")


@pytest.mark.unit
class TestDegrade:
    def test_without_a_key_the_decision_is_unchanged(self):
        decision = _decision(THESIS)
        assert cc.check_claims(decision, _state()) == decision

    def test_the_switch_turns_the_check_off(self, monkeypatch):
        monkeypatch.setattr(cc, "jev_client", _no_client)
        set_config({"jev_claim_check": False})
        decision = _decision(THESIS)
        assert cc.check_claims(decision, _state()) == decision

    def test_the_switch_reads_its_environment_variable(self, monkeypatch):
        from tradingagents.default_config import _apply_env_overrides
        monkeypatch.setenv("TRADINGAGENTS_JEV_CLAIM_CHECK", "false")
        assert _apply_env_overrides({"jev_claim_check": True})["jev_claim_check"] is False

    def test_without_reports_there_is_nothing_to_check(self, monkeypatch):
        monkeypatch.setattr(cc, "jev_client", _no_client)
        decision = _decision(THESIS)
        empty = _state(dict.fromkeys(REPORTS, ""))
        assert cc.check_claims(decision, empty) == decision

    @pytest.mark.parametrize("fail_on", ["checkable", "relation"])
    def test_a_failed_request_keeps_the_decision_unchecked(self, monkeypatch, caplog, fail_on):
        client = FakeJev(fail_on=fail_on)
        monkeypatch.setattr(cc, "jev_client", lambda: client)
        decision = _decision(THESIS)
        with caplog.at_level(logging.WARNING):
            assert cc.check_claims(decision, _state()) == decision
        assert "claim check failed" in caplog.text
        assert client.closed

    def test_with_jev_the_check_is_appended(self, monkeypatch):
        client = FakeJev()
        monkeypatch.setattr(cc, "jev_client", lambda: client)
        decision = _decision(THESIS)
        out = cc.check_claims(decision, _state())
        assert out.startswith(decision) and "\n\n**Claim Check**: " in out
        assert client.closed


# ---------------------------------------------------------------------------
# The Portfolio Manager node
# ---------------------------------------------------------------------------


def _pm_state():
    return _state(
        past_context="", investment_plan="Research plan.", trader_investment_plan="Trader plan.",
        risk_debate_state={
            "history": "Risk debate history.", "aggressive_history": "", "conservative_history": "",
            "neutral_history": "", "judge_decision": "", "current_aggressive_response": "",
            "current_conservative_response": "", "current_neutral_response": "", "count": 1,
        },
    )


def _pm_llm(thesis):
    structured = MagicMock()
    structured.invoke.return_value = PortfolioDecision(
        rating=PortfolioRating.BUY, executive_summary="Accumulate.", investment_thesis=thesis,
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestPortfolioManagerNode:
    def test_the_checked_decision_is_both_the_judge_decision_and_the_final_one(self, monkeypatch):
        client = FakeJev()
        monkeypatch.setattr(cc, "jev_client", lambda: client)
        result = create_portfolio_manager(_pm_llm(THESIS))(_pm_state())

        final = result["final_trade_decision"]
        assert final == result["risk_debate_state"]["judge_decision"]
        assert final.startswith("**Rating**: Buy")
        assert "**Claim Check**: " in final
        assert final.rstrip().endswith("1 claim contradicted by the analyst reports)")
        assert SignalProcessor().process_signal(final) == RATING_REVIEW
        assert len(client.asked("checkable")) == 5 and client.closed

    def test_without_jev_the_node_returns_the_rendered_decision(self):
        result = create_portfolio_manager(_pm_llm(THESIS))(_pm_state())
        assert result["final_trade_decision"] == render_pm_decision(PortfolioDecision(
            rating=PortfolioRating.BUY, executive_summary="Accumulate.", investment_thesis=THESIS,
        ))
        assert SignalProcessor().process_signal(result["final_trade_decision"]) == "Buy"
