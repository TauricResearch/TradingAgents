"""A decision is recorded as the call that was made, or as needing review.

Two readers used to disagree about the same text: the signal said REVIEW while
the memory log wrote a fabricated Hold. Worse, prose that argued against a Buy
before concluding Underweight was read as Buy, because the parser took the first
rating word anywhere in the document. A wrong direction is worse than no
direction, so an unclear decision is REVIEW everywhere.
"""

from __future__ import annotations

import pytest

from tradingagents.agents.utils.rating import RATING_REVIEW, extract_rating, parse_rating

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
def test_prose_naming_one_rating_is_taken_as_the_call():
    assert extract_rating("On balance we stay Underweight until margins recover.") == "Underweight"


@pytest.mark.unit
def test_a_refusal_has_no_rating_and_is_not_defaulted():
    assert extract_rating(REFUSAL) is None
    assert parse_rating(REFUSAL) == RATING_REVIEW


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
    from tradingagents.agents.utils.memory import TradingMemoryLog

    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "m.md")})
    log.store_decision("NVDA", "2026-01-05", REFUSAL)

    entry = log.load_entries()[0]
    assert entry["rating"] == RATING_REVIEW


@pytest.mark.unit
def test_the_signal_and_the_log_agree_on_the_same_decision(tmp_path):
    from tradingagents.agents.utils.memory import TradingMemoryLog
    from tradingagents.graph.signal_processing import SignalProcessor

    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "m.md")})
    for text in (INVERTED, REFUSAL, "**Rating**: Buy\n\nAccumulate."):
        log.store_decision("NVDA", f"2026-01-0{len(log.load_entries()) + 1}", text)

    signals = [SignalProcessor.process_signal(None, text)
               for text in (INVERTED, REFUSAL, "**Rating**: Buy\n\nAccumulate.")]
    assert [e["rating"] for e in log.load_entries()] == signals


@pytest.mark.unit
def test_an_unscored_decision_is_left_out_of_the_backtest_figures(tmp_path):
    """REVIEW has no direction, so it cannot count for or against the system."""
    from tradingagents.agents.utils.memory import TradingMemoryLog
    from tradingagents.backtest import summarize

    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "m.md")})
    log.store_decision("NVDA", "2026-01-05", "**Rating**: Buy\n\nx")
    log.update_with_outcome("NVDA", "2026-01-05", 0.1, 0.04, 5, "note", "2026-02-01")
    log.store_decision("AAPL", "2026-01-05", REFUSAL)
    log.update_with_outcome("AAPL", "2026-01-05", 0.1, 0.04, 5, "note", "2026-02-01")

    summary = summarize(log)
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

        def process_signal(self, text):
            from tradingagents.graph.signal_processing import SignalProcessor
            return SignalProcessor.process_signal(None, text)

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

        def stream(self, *a, **k):
            yield {"messages": [], "final_trade_decision": REFUSAL}

    fake = _Graph()
    fake.graph = fake
    fake.propagator = fake
    monkeypatch.setattr(m, "TradingAgentsGraph", lambda *a, **k: fake)
    monkeypatch.setattr(m, "create_layout", lambda: None)
    monkeypatch.setattr(m, "update_display", lambda *a, **k: None)
    monkeypatch.setattr(m, "Live", type("L", (), {"__init__": lambda s, *a, **k: None,
                                                  "__enter__": lambda s: s,
                                                  "__exit__": lambda s, *a: False}))
    monkeypatch.setattr(m.console, "print", lambda *a, **k: printed.append(" ".join(str(x) for x in a)))
    monkeypatch.setattr(m, "display_complete_report", lambda *a, **k: None)
    monkeypatch.setattr(m.typer, "prompt", lambda *a, **k: "N")
    monkeypatch.setattr(m, "get_user_selections", lambda: {
        "ticker": "NVDA", "analysis_date": "2026-01-10",
        "analysts": [AnalystType.MARKET], "asset_type": "stock",
    })
    monkeypatch.setattr(m, "_build_run_config", lambda s, c: {
        "data_cache_dir": str(tmp_path / "c"), "results_dir": str(tmp_path / "r")})

    m.run_analysis()

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
                                    "current_response": "", "judge_decision": "", "count": 2},
        "risk_debate_state": {"history": "h", "latest_speaker": "", "count": 3,
                              "aggressive_history": "", "conservative_history": "", "neutral_history": "",
                              "current_aggressive_response": "", "current_conservative_response": "",
                              "current_neutral_response": "", "judge_decision": ""},
    }
    getattr(mod, factory)(_LLM())(state)

    prompt = " ".join(seen)
    assert "## Output" in prompt, "no output-format section in the prompt"
    section = prompt.split("## Output", 1)[1]
    assert f"**{must_name}**" in section, section[:300]
