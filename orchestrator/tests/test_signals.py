"""Tests for SignalMerger in orchestrator/signals.py."""
import math
import pytest
from datetime import datetime, timezone

from orchestrator.config import OrchestratorConfig
from orchestrator.signals import Signal, SignalMerger


def _make_signal(ticker="AAPL", direction=1, confidence=0.8, source="quant"):
    return Signal(
        ticker=ticker,
        direction=direction,
        confidence=confidence,
        source=source,
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def merger():
    return SignalMerger(OrchestratorConfig())


# Branch 1: both None → ValueError
def test_merge_both_none_raises(merger):
    with pytest.raises(ValueError):
        merger.merge(None, None)


# Branch 2: quant only
def test_merge_quant_only(merger):
    cfg = OrchestratorConfig()
    q = _make_signal(direction=1, confidence=0.8, source="quant")
    result = merger.merge(q, None)
    assert result.direction == 1
    expected_conf = min(0.8 * cfg.quant_solo_penalty, cfg.quant_weight_cap)
    assert math.isclose(result.confidence, expected_conf)
    assert result.quant_signal is q
    assert result.llm_signal is None


def test_merge_quant_only_capped(merger):
    cfg = OrchestratorConfig()
    # confidence=1.0 * quant_solo_penalty=0.8 → 0.8 == quant_weight_cap=0.8, no clamp needed
    q = _make_signal(direction=-1, confidence=1.0, source="quant")
    result = merger.merge(q, None)
    expected_conf = min(1.0 * cfg.quant_solo_penalty, cfg.quant_weight_cap)
    assert math.isclose(result.confidence, expected_conf)
    assert result.direction == -1


# Branch 3: llm only
def test_merge_llm_only(merger):
    cfg = OrchestratorConfig()
    l = _make_signal(direction=-1, confidence=0.9, source="llm")
    result = merger.merge(None, l)
    assert result.direction == -1
    expected_conf = min(0.9 * cfg.llm_solo_penalty, cfg.llm_weight_cap)
    assert math.isclose(result.confidence, expected_conf)
    assert result.llm_signal is l
    assert result.quant_signal is None


def test_merge_llm_only_capped(merger):
    cfg = OrchestratorConfig()
    # Force cap: confidence=1.0, llm_solo_penalty=0.7 → 0.7 < llm_weight_cap=0.9, no cap
    l = _make_signal(direction=1, confidence=1.0, source="llm")
    result = merger.merge(None, l)
    expected_conf = min(1.0 * cfg.llm_solo_penalty, cfg.llm_weight_cap)
    assert math.isclose(result.confidence, expected_conf)


# Branch 4: both present, same direction
def test_merge_both_same_direction(merger):
    cfg = OrchestratorConfig()
    q = _make_signal(direction=1, confidence=0.6, source="quant")
    l = _make_signal(direction=1, confidence=0.8, source="llm")
    result = merger.merge(q, l)
    assert result.direction == 1
    weighted_sum = 1 * 0.6 + 1 * 0.8  # 1.4
    total_conf = 0.6 + 0.8             # 1.4
    raw_conf = abs(weighted_sum) / total_conf  # 1.0
    # actual code caps at min(raw, quant_weight_cap, llm_weight_cap)
    expected_conf = min(raw_conf, cfg.quant_weight_cap, cfg.llm_weight_cap)
    assert math.isclose(result.confidence, expected_conf)


# Branch 5: both present, opposite direction
def test_merge_both_opposite_direction_quant_wins(merger):
    cfg = OrchestratorConfig()
    # quant stronger: direction should be quant's
    q = _make_signal(direction=1, confidence=0.9, source="quant")
    l = _make_signal(direction=-1, confidence=0.3, source="llm")
    result = merger.merge(q, l)
    weighted_sum = 1 * 0.9 + (-1) * 0.3  # 0.6
    assert result.direction == 1
    total_conf = 0.9 + 0.3
    raw_conf = abs(weighted_sum) / total_conf
    expected_conf = min(raw_conf, cfg.quant_weight_cap, cfg.llm_weight_cap)
    assert math.isclose(result.confidence, expected_conf)


def test_merge_both_opposite_direction_llm_wins(merger):
    q = _make_signal(direction=1, confidence=0.2, source="quant")
    l = _make_signal(direction=-1, confidence=0.8, source="llm")
    result = merger.merge(q, l)
    assert result.direction == -1


# weighted_sum=0 → direction=HOLD
def test_merge_weighted_sum_zero(merger):
    q = _make_signal(direction=1, confidence=0.5, source="quant")
    l = _make_signal(direction=-1, confidence=0.5, source="llm")
    result = merger.merge(q, l)
    assert result.direction == 0
    assert math.isclose(result.confidence, 0.0)
