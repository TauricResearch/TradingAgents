"""The run summary has to be able to say how many agents skipped the schema.

Every fallback is already logged one line at a time. What was missing is the
total: a run that dropped three agents to free text looked exactly like one that
kept the schema throughout, so nobody could tell how much of the output was
actually validated without watching stderr.
"""

import logging

import pytest

from tradingagents.agents.utils.structured import (
    FallbackCounter,
    invoke_structured_or_freetext,
)


class _Boom:
    """A structured LLM whose call always fails."""

    def invoke(self, prompt):
        raise ValueError("malformed JSON")


class _NoParse:
    """A thinking model that answers in prose instead of calling the tool."""

    def invoke(self, prompt):
        return None


class _Plain:
    def invoke(self, prompt):
        return type("R", (), {"content": "free text answer"})()


@pytest.fixture
def counter():
    c = FallbackCounter()
    log = logging.getLogger("tradingagents")
    log.addHandler(c)
    yield c
    log.removeHandler(c)


@pytest.mark.unit
class TestFallbackCounter:
    def test_counts_a_failed_structured_call(self, counter):
        invoke_structured_or_freetext(_Boom(), _Plain(), "p", str, "Trader")
        assert counter.total == 1
        assert counter.counts == {"Trader": 1}

    def test_counts_an_unparsed_thinking_model_answer(self, counter):
        """The DeepSeek-style miss: no exception, just nothing parsed."""
        invoke_structured_or_freetext(_NoParse(), _Plain(), "p", str, "Research Manager")
        assert counter.counts == {"Research Manager": 1}

    def test_tallies_per_agent(self, counter):
        for _ in range(2):
            invoke_structured_or_freetext(_Boom(), _Plain(), "p", str, "Trader")
        invoke_structured_or_freetext(_NoParse(), _Plain(), "p", str, "Portfolio Manager")
        assert counter.total == 3
        summary = counter.summary()
        assert "3" in summary
        assert "Trader x2" in summary
        assert "Portfolio Manager x1" in summary

    def test_a_clean_run_reports_nothing(self, counter):
        """No fallback means no line in the summary, not a line reading zero."""
        assert counter.total == 0
        assert counter.summary() == ""

    def test_ignores_unrelated_warnings(self, counter):
        logging.getLogger("tradingagents.somewhere").warning("unrelated")
        assert counter.total == 0

    def test_successful_structured_call_is_not_counted(self, counter):
        class Ok:
            def invoke(self, prompt):
                return "parsed"

        out = invoke_structured_or_freetext(Ok(), _Plain(), "p", lambda r: r, "Trader")
        assert out == "parsed"
        assert counter.total == 0
