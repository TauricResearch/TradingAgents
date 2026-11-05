"""A decision is recorded as the call that was made, or as needing review.

Two readers used to disagree about the same text: the signal said REVIEW while
the memory log wrote a fabricated Hold. Worse, prose that argued against a Buy
before concluding Underweight was read as Buy, because the parser took the first
rating word anywhere in the document. A wrong direction is worse than no
direction, so an unclear decision is REVIEW everywhere.
"""

from __future__ import annotations

import pytest

import cli.run as cli_run
from tradingagents.agents.rating import RATING_REVIEW, extract_rating, parse_rating

INVERTED = ("The aggressive analyst pushed hard for a Buy on the AI backlog, but the "
            "conservative case on margin compression carried the debate. "
            "Final rating — Underweight. Trim to half weight over the next two weeks.")
REFUSAL = "I'm sorry, I can't provide a rating for this security."


@pytest.mark.unit
@pytest.mark.parametrize("separator", [":", "-", "—", "–", "：", ": **"])
def test_the_labelled_rating_wins_whatever_separates_it(separator):
    text = f"Buy arguments were raised and rejected.\n\nRating{separator}Underweight\n\nTrim."
    assert extract_rating(text) == "Underweight"


@pytest.mark.unit
def test_a_rating_argued_against_is_not_read_as_the_decision():
    assert extract_rating(INVERTED) == "Underweight"


@pytest.mark.unit
def test_prose_naming_several_ratings_without_a_label_needs_review():
    """Nothing in the text says which one is the call, so guessing risks
    reporting the opposite of the decision."""
    text = "The bull wants Buy, the bear wants Sell, and the committee was split."
    assert extract_rating(text) is None


@pytest.mark.unit
@pytest.mark.parametrize("prose", [
    "We would not Sell here; the dip is a chance to add.",
    "On balance we stay Underweight until margins recover.",
])
def test_a_rating_word_without_a_label_is_not_read_as_the_call(prose):
    """A rating word in prose may be one the text argues against (#1435)."""
    assert extract_rating(prose) is None
    assert parse_rating(prose) == RATING_REVIEW


@pytest.mark.unit
def test_a_refusal_has_no_rating_and_is_not_defaulted():
    assert extract_rating(REFUSAL) is None
    assert parse_rating(REFUSAL) == RATING_REVIEW


@pytest.mark.unit
@pytest.mark.parametrize(
    "alias,expected",
    [
        ("买入", "Buy"),
        ("增持", "Overweight"),
        ("持有", "Hold"),
        ("减持", "Underweight"),
        ("卖出", "Sell"),
    ],
)
def test_a_localized_labelled_rating_line_parses(alias, expected):
    """A non-English decision may spell the anchor line in its own language.
    The parser reads it rather than falling to REVIEW, which silently drops
    the decision from backtest scoring."""
    assert extract_rating(f"**评级**：{alias}") == expected


@pytest.mark.unit
def test_a_localized_label_takes_precedence_over_negated_english_prose():
    """The localized anchor line gets the same explicit-label precedence as an
    English one: the labelled call wins over a negated tier word in the prose
    below it."""
    assert extract_rating("**评级**：买入\n\n不建议卖出 (Sell)。") == "Buy"


@pytest.mark.unit
@pytest.mark.parametrize("qualified", ["最终评级：买入", "**最终评级**: 卖出"])
def test_a_localized_label_with_a_qualifier_parses(qualified):
    """Qualifiers before 评级 ("最终评级：买入") mirror the English
    "Final Rating:" shape and stay the decision's own line."""
    expected = "Buy" if "买入" in qualified else "Sell"
    assert extract_rating(qualified) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "mixed", ["Rating: 买入", "- **Rating**: 增持", "Final Rating: 卖出"]
)
def test_an_english_label_with_a_localized_value_parses(mixed):
    """The model kept the label English (as the instruction asks) but
    translated the value too; the label pass resolves the alias."""
    expected = {"买入": "Buy", "增持": "Overweight", "卖出": "Sell"}[
        next(w for w in ("买入", "增持", "卖出") if w in mixed)
    ]
    assert extract_rating(mixed) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "prose",
    [
        "建议不要买入，当前估值过高。",   # negated in a language without word boundaries
        "不减持当前仓位。",            # negated 减持
        "市场持续持有该仓位。",          # descriptive 持有, no label
    ],
)
def test_localized_tier_words_in_prose_without_a_label_are_not_calls(prose):
    """Chinese has no word boundaries: "不要买入" contains "买入", and
    "机构持有" is ordinary prose. Without a label line, localized tier words
    must not parse as positive calls — the direction-flip this parser exists
    to prevent (#1435)."""
    assert extract_rating(prose) is None
    assert parse_rating(prose) == RATING_REVIEW


@pytest.mark.unit
def test_the_scale_quoted_in_a_prompt_does_not_become_the_rating():
    """A free-text answer that echoes the rating scale was read as the first
    tier listed in it."""
    text = ("**Rating Scale**: Buy, Overweight, Hold, Underweight, Sell.\n\n"
            "**Rating**: Sell\n\nExit the position.")
    assert extract_rating(text) == "Sell"


# --- the readers agree ------------------------------------------------------

@pytest.mark.unit
def test_the_memory_log_records_review_rather_than_a_tradeable_hold(tmp_path):
    from tradingagents.memory import TradingMemoryLog

    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "m.md")})
    log.store_decision("NVDA", "2026-01-05", REFUSAL)

    entry = log.load_entries()[0]
    assert entry["rating"] == RATING_REVIEW


@pytest.mark.unit
def test_the_signal_and_the_log_agree_on_the_same_decision(tmp_path):
    from tradingagents.agents.rating import parse_rating
    from tradingagents.memory import TradingMemoryLog

    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "m.md")})
    for text in (INVERTED, REFUSAL, "**Rating**: Buy\n\nAccumulate."):
        log.store_decision("NVDA", f"2026-01-0{len(log.load_entries()) + 1}", text)

    signals = [parse_rating(text)
               for text in (INVERTED, REFUSAL, "**Rating**: Buy\n\nAccumulate.")]
    assert [e["rating"] for e in log.load_entries()] == signals


@pytest.mark.unit
def test_an_unscored_decision_is_left_out_of_the_backtest_figures(tmp_path):
    """REVIEW has no direction, so it cannot count for or against the system."""
    from tradingagents.backtest import summarize
    from tradingagents.memory import TradingMemoryLog

    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "m.md")})
    log.store_decision("NVDA", "2026-01-05", "**Rating**: Buy\n\nx")
    log.update_with_outcome("NVDA", "2026-01-05", 0.1, 0.04, 5, "note", "2026-02-01")
    log.store_decision("AAPL", "2026-01-05", REFUSAL)
    log.update_with_outcome("AAPL", "2026-01-05", 0.1, 0.04, 5, "note", "2026-02-01")

    summary = summarize(tmp_path / "m.md")
    assert set(summary.by_rating) == {"Buy"}


@pytest.mark.unit
def test_the_cli_says_when_a_run_produced_no_usable_rating(monkeypatch, tmp_path, capsys):
    """The CLI is the primary entry point; an unreadable decision must be
    visible there, not only in the log."""
    import cli.main as m
    from cli.models import AnalystType

    printed = []

    class _Graph:
        graph = propagator = None

        def create_run_state(self, *a, **k):
            return {"messages": []}

        def record_decision(self, *a, **k):
            pass

        def get_graph_args(self, callbacks=None):
            return {}

        def begin_checkpoint(self, *a, **k):
            return None

        def checkpoint_input(self, state):
            return state

        def clear_checkpoint_on_success(self, *a, **k):
            pass

        def end_checkpoint(self):
            pass

        def stream_run(self, *a, **k):
            yield [], {"messages": [], "final_trade_decision": REFUSAL, "final_rating": RATING_REVIEW}

    fake = _Graph()
    fake.graph = fake
    fake.propagator = fake
    monkeypatch.setattr(cli_run, "TradingAgentsGraph", lambda *a, **k: fake)
    monkeypatch.setattr(cli_run, "create_layout", lambda: None)
    monkeypatch.setattr(cli_run, "update_display", lambda *a, **k: None)
    monkeypatch.setattr(cli_run, "Live", type("L", (), {"__init__": lambda s, *a, **k: None,
                                                  "__enter__": lambda s: s,
                                                  "__exit__": lambda s, *a: False}))
    monkeypatch.setattr(m.console, "print", lambda *a, **k: printed.append(" ".join(str(x) for x in a)))
    monkeypatch.setattr(cli_run, "display_complete_report", lambda *a, **k: None)
    monkeypatch.setattr(m.typer, "prompt", lambda *a, **k: "N")
    monkeypatch.setattr(cli_run, "get_user_selections", lambda flags=None: {
        "ticker": "NVDA", "analysis_date": "2026-01-10",
        "analysts": [AnalystType.MARKET], "asset_type": "stock",
    })
    monkeypatch.setattr(cli_run, "_build_run_config", lambda s, c: {
        "data_cache_dir": str(tmp_path / "c"), "results_dir": str(tmp_path / "r")})

    cli_run.run_analysis()

    assert any("review" in line.lower() for line in printed), printed[-5:]


@pytest.mark.unit
@pytest.mark.parametrize("module, factory, must_name", [
    ("tradingagents.agents.managers.portfolio_manager", "create_portfolio_manager", "Rating"),
    ("tradingagents.agents.managers.research_manager", "create_research_manager", "Recommendation"),
    ("tradingagents.agents.trader.trader", "create_trader", "Action"),
])
def test_a_decision_prompt_states_the_shape_of_its_answer(module, factory, must_name):
    """The field descriptions live in the schema, which a provider without
    structured output never sees. Without the format in the prompt body, the
    fallback answer is prose nobody can read a rating from."""
    import importlib

    from langchain_core.messages import AIMessage

    mod = importlib.import_module(module)
    seen = []

    class _LLM:
        def invoke(self, prompt, *a, **k):
            seen.append(prompt if isinstance(prompt, str) else str(prompt))
            return AIMessage("**Rating**: Hold\n\nnothing to do")

        def with_structured_output(self, *a, **k):
            raise NotImplementedError  # force the free-text path

    state = {
        "company_of_interest": "NVDA", "trade_date": "2026-08-14", "asset_type": "stock",
        "instrument_context": "", "market_report": "M", "sentiment_report": "S",
        "news_report": "N", "fundamentals_report": "F", "investment_plan": "P",
        "trader_investment_plan": "T", "past_context": "", "portfolio_context": "",
        "investment_debate_state": {"bull_history": "b", "bear_history": "r", "history": "h",
                                    "current_response": "", "count": 2},
        "risk_debate_state": {"history": "h", "latest_speaker": "", "count": 3,
                              "aggressive_history": "", "conservative_history": "", "neutral_history": "",
                              "current_aggressive_response": "", "current_conservative_response": "",
                              "current_neutral_response": ""},
    }
    getattr(mod, factory)(_LLM())(state)

    prompt = " ".join(seen)
    assert "## Output" in prompt, "no output-format section in the prompt"
    section = prompt.split("## Output", 1)[1]
    assert f"**{must_name}**" in section, section[:300]


@pytest.mark.unit
def test_a_state_without_the_typed_rating_reads_it_from_the_decision():
    """A run finished by an older version and resumed from its checkpoint has
    no final_rating; every reader falls back the same way instead of one
    raising and another reporting REVIEW."""
    from tradingagents.agents.rating import run_rating

    assert run_rating({"final_rating": "Hold", "final_trade_decision": "**Rating**: Buy"}) == "Hold"
    assert run_rating({"final_trade_decision": "**Rating**: Sell\n\nExit."}) == "Sell"
    assert run_rating({}) == RATING_REVIEW


@pytest.mark.unit
@pytest.mark.parametrize("quoted", [
    "Street consensus rating: Buy (28 of 35 analysts).",
    "Moody's affirmed the credit rating: Buy-side demand for the bonds stayed firm.",
    "Operating margin: Sell-side estimates sit below guidance.",
])
def test_a_rating_the_text_quotes_does_not_replace_the_decision(quoted):
    """A free-text decision opens with its own rating line; a rating it quotes
    as evidence, or a word merely ending in 'rating', is not the call."""
    text = f"**Rating**: Hold\n\n**Investment Thesis**: {quoted} We wait for margins."
    assert extract_rating(text) == "Hold"


@pytest.mark.unit
@pytest.mark.parametrize("quoted", [
    "- Rating: Buy (Goldman Sachs, 12m target 180)",
    "| Rating: Buy | Morgan Stanley |",
    "> Rating: Buy, per the sell-side note",
    "Street consensus rating: Buy",
    "Consensus rating: Buy (28 of 35 analysts)",
])
def test_a_quoted_rating_in_a_list_table_or_quote_is_not_the_decision(quoted):
    text = f"Our rating: Hold\n\nWhat others say:\n{quoted}\n\nWe wait for margins."
    assert extract_rating(text) == "Hold"


@pytest.mark.unit
@pytest.mark.parametrize("text, expected", [
    ("Consensus rating: Buy\nRating: Sell", "Sell"),
    ("Analyst rating: Overweight\n**Rating**: Underweight", "Underweight"),
    ("Previous rating: Buy\n## Final Rating - Hold", "Hold"),
    ("Street rating: Sell\nOur rating: Buy", "Buy"),
    ("Credit rating: Sell\nRating: Buy", "Buy"),
    ("Sell-side consensus rating: Buy\n**Rating**: Hold", "Hold"),
    # the decision opens with its rating, as the prompt asks
    ("- **Rating**: Sell\n\nConsensus rating: Buy", "Sell"),
    ("- **Rating**: Sell\n- **Investment Thesis**: consensus rating: Buy, we disagree.", "Sell"),
    ("1. **Rating**: Underweight\n2. **Executive Summary**: Street rating: Buy.", "Underweight"),
    ("\u2022 **Rating**: Sell\nConsensus rating: Buy", "Sell"),
    ("## Decision\n\n- **Rating**: Hold\n- Rating: Buy (Goldman Sachs)", "Hold"),
    ("Recommended rating: Buy\n\nConsensus rating: Sell", "Buy"),
    ("Updated rating: Sell\nPrevious rating: Buy", "Sell"),
    ("Our final rating: Sell\nConsensus rating: Buy", "Sell"),
    ("**Overall Final Rating**: Sell\nConsensus rating: Buy", "Sell"),
    # ratings quoted as list items before the decision's own line
    ("Broker views:\n- Rating: Buy (Morgan Stanley)\n- Rating: Hold (Goldman)\n\n**Rating**: Sell", "Sell"),
    ("Previous decision recap:\n- **Rating**: Buy (2026-09-01)\n\n**Rating**: Sell", "Sell"),
    ("Lessons:\n- Rating: Buy was wrong last time\n\n**Rating**: Hold", "Hold"),
])
def test_a_rating_someone_else_gave_does_not_become_the_decision(text, expected):
    """The decision's own rating line is read as the call; another party's
    rating, even on a line of its own, is evidence, not the call (#1466)."""
    assert extract_rating(text) == expected


@pytest.mark.unit
@pytest.mark.parametrize("text", [
    "Trader's proposed rating: Buy\n\nPortfolio Manager's rating: Hold",
    "Research Manager rating: Buy\nPortfolio rating: Underweight",
    "Trader's rating: Buy\nRisk team rating: Sell\nPortfolio Manager's Final Rating: Hold",
    "Risk views:\n- Aggressive analyst rating: Buy\n- Conservative rating: Sell\n\nPM: Rating: Hold",
    "PM Rating: Sell\n- Rating: Buy (JPMorgan)",
    "Position rating: Underweight\n* Rating: Overweight per Citi",
    "Street views:\n- Goldman rating: Buy\n\nWeighing all of this, the Portfolio Manager's rating: Underweight.",
    "Analyst views:\n- Rating: Buy (Goldman)\n\nAfter the debate our final call is Sell (Rating: Sell).",
    "Lessons:\n- Rating: Buy was wrong last time\n\n- **Rating**: Hold",
    "Broker views:\n- Rating: Buy (MS)\n\n- **Rating**: Sell",
    "Investment rating: Underweight\nStreet rating: Buy",
    "## Street view\n1. Rating: Buy, target $250 (JPM)\n\n## Our call\n**Rating**: Underweight",
])
def test_ratings_that_disagree_with_no_line_of_the_decisions_own_need_review(text):
    """When the text never states its own rating in the decision's shape and the
    ratings it names disagree, nobody can tell which is the call (#1170)."""
    assert extract_rating(text) is None
