"""Tests for LLMRunner._map_rating()."""
import tempfile
import pytest

from orchestrator.config import OrchestratorConfig
from orchestrator.llm_runner import LLMRunner


@pytest.fixture
def runner(tmp_path):
    cfg = OrchestratorConfig(cache_dir=str(tmp_path))
    return LLMRunner(cfg)


# All 5 known ratings
@pytest.mark.parametrize("rating,expected", [
    ("BUY",         (1,  0.9)),
    ("OVERWEIGHT",  (1,  0.6)),
    ("HOLD",        (0,  0.5)),
    ("UNDERWEIGHT", (-1, 0.6)),
    ("SELL",        (-1, 0.9)),
])
def test_map_rating_known(runner, rating, expected):
    assert runner._map_rating(rating) == expected


# Unknown rating → (0, 0.5)
def test_map_rating_unknown(runner):
    assert runner._map_rating("STRONG_BUY") == (0, 0.5)


# Case-insensitive
def test_map_rating_lowercase(runner):
    assert runner._map_rating("buy") == (1, 0.9)
    assert runner._map_rating("sell") == (-1, 0.9)
    assert runner._map_rating("hold") == (0, 0.5)


# Empty string → (0, 0.5)
def test_map_rating_empty_string(runner):
    assert runner._map_rating("") == (0, 0.5)
