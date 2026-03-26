import pytest
from tradingagents.portfolio.candidate_prioritizer import prioritize_candidates
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.portfolio.models import Portfolio, Holding

@pytest.fixture
def empty_portfolio():
    return Portfolio(
        portfolio_id="test_port",
        name="test",
        initial_cash=100000.0,
        cash=100000.0,
        total_value=100000.0,
        created_at="2025-01-01"
    )

@pytest.fixture
def test_candidate():
    return {
        "ticker": "AAPL",
        "sector": "technology",
        "thesis_angle": "growth",
        "rationale": "High earnings potential",
        "conviction": "high"
    }

def test_no_memory_backward_compat(empty_portfolio, test_candidate):
    enriched = prioritize_candidates(
        [test_candidate], empty_portfolio, [], {"max_sector_pct": 0.35}, selection_memory=None
    )
    assert len(enriched) == 1
    assert enriched[0]["priority_score"] > 0
    assert "skip_reason" not in enriched[0]

def test_negative_match_zeroes_score(empty_portfolio, test_candidate):
    memory = FinancialSituationMemory("test_mem")
    # Matches the candidate description well
    memory.add_situations([
        ("AAPL technology growth High earnings potential high", "Avoid tech growth stocks in this macro"),
        ("MSFT another", "Another lesson") # Add second situation to ensure BM25 idf is positive or normalized properly, or mock it
    ])

    # Mocking get_memories directly because BM25 scores can be tricky to predict with tiny corpora
    original_get = memory.get_memories
    memory.get_memories = lambda *args, **kwargs: [{"similarity_score": 0.9, "recommendation": "Avoid tech growth stocks in this macro"}]

    enriched = prioritize_candidates(
        [test_candidate], empty_portfolio, [], {"max_sector_pct": 0.35}, selection_memory=memory
    )
    assert len(enriched) == 1
    assert enriched[0]["priority_score"] == 0.0
    assert "Memory lesson" in enriched[0]["skip_reason"]
    assert "Avoid tech growth stocks" in enriched[0]["skip_reason"]

    memory.get_memories = original_get

def test_positive_lessons_not_loaded(empty_portfolio, test_candidate):
    memory = FinancialSituationMemory("test_mem")

    enriched = prioritize_candidates(
        [test_candidate], empty_portfolio, [], {"max_sector_pct": 0.35}, selection_memory=memory
    )
    assert enriched[0]["priority_score"] > 0

def test_score_threshold_boundary(empty_portfolio, test_candidate):
    # If the score is exactly 0.5 (or less), it should not trigger rejection
    memory = FinancialSituationMemory("test_mem")
    memory.add_situations([("completely unrelated stuff that barely matches maybe one token aapl", "lesson text")])

    # Manually overwrite the get_memories to return a score exactly 0.5
    original_get = memory.get_memories
    memory.get_memories = lambda *args, **kwargs: [{"similarity_score": 0.5, "recommendation": "lesson text"}]

    enriched = prioritize_candidates(
        [test_candidate], empty_portfolio, [], {"max_sector_pct": 0.35}, selection_memory=memory
    )
    assert len(enriched) == 1
    assert enriched[0]["priority_score"] > 0
    assert "skip_reason" not in enriched[0]

def test_skip_reason_contains_advice(empty_portfolio, test_candidate):
    memory = FinancialSituationMemory("test_mem")
    advice_text = "Specific unique advice string 12345"
    memory.add_situations([("AAPL technology growth High earnings potential high", advice_text)])

    original_get = memory.get_memories
    memory.get_memories = lambda *args, **kwargs: [{"similarity_score": 0.9, "recommendation": advice_text}]

    enriched = prioritize_candidates(
        [test_candidate], empty_portfolio, [], {"max_sector_pct": 0.35}, selection_memory=memory
    )
    assert enriched[0]["priority_score"] == 0.0
    assert advice_text in enriched[0]["skip_reason"]

    memory.get_memories = original_get
