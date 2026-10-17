"""A token budget for a whole run that stops it once spent (#515).

``max_tool_rounds`` bounds one analyst's tool loop and ``max_tokens`` one reply;
``run_token_budget`` bounds what every model call of a run spends together.
"""
from __future__ import annotations

import copy
import logging
import threading
import uuid

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

import tradingagents.default_config as default_config_module
from tests.test_graph_end_to_end import TRADE_DATE, ScriptedModel, _Client, offline  # noqa: F401
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph import trading_graph
from tradingagents.llm_clients.token_budget import (
    TokenBudgetExceeded,
    TokenBudgetHandler,
    _coerce_run_token_budget,
)

IN, OUT = 100, 50   # tokens a MeteredModel call reports
PER_CALL = IN + OUT


def _result(input_tokens=IN, output_tokens=OUT) -> LLMResult:
    message = AIMessage(content="ok", usage_metadata={
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens})
    return LLMResult(generations=[[ChatGeneration(message=message)]])


def _call(handler, result=None):
    """One model call as LangChain reports it to a callback handler."""
    run_id = uuid.uuid4()
    handler.on_chat_model_start({}, [[]], run_id=run_id)
    handler.on_llm_end(result or _result(), run_id=run_id)


# --- coercion / validation -------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("value,expected", [(1, 1), (500_000, 500_000), ("20000", 20000)])
def test_coerce_accepts_positive_ints_and_numeric_strings(value, expected):
    assert _coerce_run_token_budget(value) == expected


@pytest.mark.unit
@pytest.mark.parametrize("bad", [0, -1, "-5"])
def test_coerce_rejects_zero_and_negative(bad):
    with pytest.raises(ValueError, match="> 0"):
        _coerce_run_token_budget(bad)


@pytest.mark.unit
@pytest.mark.parametrize("bad", [True, False])
def test_coerce_rejects_booleans(bad):
    with pytest.raises(ValueError, match="boolean"):
        _coerce_run_token_budget(bad)


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["abc", "1.5", None])
def test_coerce_rejects_non_integers(bad):
    with pytest.raises(ValueError, match="integer"):
        _coerce_run_token_budget(bad)


# --- env overlay -----------------------------------------------------------


def _config_with_env(monkeypatch, **overrides):
    """The defaults as the environment given here would set them."""
    for key in list(default_config_module._ENV_OVERRIDES):
        monkeypatch.delenv(key, raising=False)
    for key, val in overrides.items():
        monkeypatch.setenv(key, val)
    return default_config_module.build_default_config()


@pytest.mark.unit
def test_default_is_no_budget(monkeypatch):
    assert _config_with_env(monkeypatch)["run_token_budget"] is None


@pytest.mark.unit
def test_env_override_sets_config(monkeypatch):
    config = _config_with_env(monkeypatch, TRADINGAGENTS_RUN_TOKEN_BUDGET="5000")
    # None-default key: the env value arrives as a string and is coerced downstream.
    assert config["run_token_budget"] == "5000"
    assert _coerce_run_token_budget(config["run_token_budget"]) == 5000


@pytest.mark.unit
def test_budget_is_separate_from_the_per_reply_cap(monkeypatch):
    config = _config_with_env(monkeypatch, TRADINGAGENTS_MAX_TOKENS="8192")
    assert config["max_tokens"] == "8192"
    assert config["run_token_budget"] is None


# --- the handler -----------------------------------------------------------


@pytest.mark.unit
def test_counts_input_and_output_across_calls():
    handler = TokenBudgetHandler(10_000)
    _call(handler)
    _call(handler, _result(1_000, 200))
    assert handler.spent == PER_CALL + 1_200
    assert handler.remaining() == 10_000 - PER_CALL - 1_200


@pytest.mark.unit
def test_calls_go_ahead_while_budget_remains():
    handler = TokenBudgetHandler(3 * PER_CALL + 1)
    for _ in range(4):        # the 4th starts with one token left
        _call(handler)
    assert handler.spent == 4 * PER_CALL


@pytest.mark.unit
def test_the_call_after_the_budget_is_spent_is_refused():
    handler = TokenBudgetHandler(2 * PER_CALL)
    _call(handler)
    _call(handler)
    with pytest.raises(TokenBudgetExceeded, match="300 of 300") as exc:
        handler.on_chat_model_start({}, [[]], run_id=uuid.uuid4())
    assert (exc.value.spent, exc.value.budget) == (300, 300)
    # Non-chat LLMs stop at the same point.
    with pytest.raises(TokenBudgetExceeded):
        handler.on_llm_start({}, ["prompt"], run_id=uuid.uuid4())


@pytest.mark.unit
def test_once_spent_every_later_call_is_refused():
    """A caller that swallows the error still cannot spend more."""
    handler = TokenBudgetHandler(PER_CALL)
    _call(handler)
    for _ in range(3):
        with pytest.raises(TokenBudgetExceeded):
            handler.on_chat_model_start({}, [[]], run_id=uuid.uuid4())
    assert handler.spent == PER_CALL


@pytest.mark.unit
def test_raises_through_langchain_instead_of_being_logged():
    # LangChain only logs a callback's exception unless the handler opts in.
    assert TokenBudgetHandler.raise_error is True


@pytest.mark.unit
def test_reset_starts_a_new_run_from_zero():
    handler = TokenBudgetHandler(PER_CALL)
    _call(handler)
    handler.reset()
    assert handler.spent == 0
    _call(handler)            # would be refused without the reset


@pytest.mark.unit
def test_a_call_with_no_usage_warns_once_and_is_not_refused(caplog):
    handler = TokenBudgetHandler(PER_CALL)
    no_usage = LLMResult(generations=[[ChatGeneration(message=AIMessage(content="ok"))]])
    with caplog.at_level(logging.WARNING, logger="tradingagents.llm_clients.token_budget"):
        _call(handler, no_usage)
        _call(handler, no_usage)
    assert handler.spent == 0
    assert sum("reported no token usage" in r.message for r in caplog.records) == 1


@pytest.mark.unit
def test_concurrent_calls_are_all_counted():
    handler = TokenBudgetHandler(10**9)
    threads = [threading.Thread(target=lambda: [_call(handler) for _ in range(50)]) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert handler.spent == 8 * 50 * PER_CALL


@pytest.mark.unit
def test_a_retried_call_counts_only_the_attempt_that_finished():
    attempts = []

    class FlakyModel(ScriptedModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("429")
            return _metered(super()._generate(messages, stop, run_manager, **kwargs))

    handler = TokenBudgetHandler(10_000)
    model = FlakyModel(callbacks=[handler]).with_retry(stop_after_attempt=2, wait_exponential_jitter=False)
    model.invoke("hello")
    assert len(attempts) == 2
    assert handler.spent == PER_CALL


# --- the graph -------------------------------------------------------------


def _metered(result):
    result.generations[0].message.usage_metadata = {
        "input_tokens": IN, "output_tokens": OUT, "total_tokens": PER_CALL}
    return result


class MeteredModel(ScriptedModel):
    """ScriptedModel whose every call reports IN + OUT tokens of usage."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return _metered(super()._generate(messages, stop, run_manager, **kwargs))


def _graph(tmp_path, monkeypatch, model, callbacks=None, **config):
    """A graph whose models receive the callbacks the graph hands its tier clients."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.update(results_dir=str(tmp_path / "results"), data_cache_dir=str(tmp_path / "cache"),
               memory_log_path=str(tmp_path / "log.md"), **config)
    tiers = {}

    def client(config, tier, **kwargs):
        tiers[tier] = kwargs.get("callbacks")
        return _Client(model.model_copy(update={"callbacks": kwargs.get("callbacks")}))

    monkeypatch.setattr(trading_graph, "create_tier_client", client)
    graph = trading_graph.TradingAgentsGraph(config=cfg, callbacks=callbacks)
    graph.tier_callbacks = tiers
    return graph


def _full_run_calls(tmp_path, monkeypatch) -> int:
    model = MeteredModel()
    _graph(tmp_path / "full", monkeypatch, model).propagate("NVDA", TRADE_DATE)
    return len(model.calls)


@pytest.mark.unit
def test_no_budget_attaches_no_handler(tmp_path, monkeypatch):
    graph = _graph(tmp_path, monkeypatch, MeteredModel())
    assert graph.token_budget is None
    assert graph.tier_callbacks == {"deep": None, "quick": None}


@pytest.mark.unit
def test_a_budget_reaches_both_tiers_beside_the_callers_handlers(tmp_path, monkeypatch):
    mine = TokenBudgetHandler(1)    # any handler of the caller's
    callers = [mine]
    graph = _graph(tmp_path, monkeypatch, MeteredModel(), callbacks=callers, run_token_budget="5000")
    assert graph.token_budget.budget == 5000
    for tier in ("deep", "quick"):
        assert graph.tier_callbacks[tier] == [mine, graph.token_budget]
    assert callers == [mine]        # the caller's list is left alone


@pytest.mark.unit
def test_an_invalid_budget_fails_at_construction(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="run_token_budget"):
        _graph(tmp_path, monkeypatch, MeteredModel(), run_token_budget="lots")


@pytest.mark.unit
def test_the_budget_is_recorded_but_not_part_of_the_checkpoint_signature(tmp_path, monkeypatch):
    graph = _graph(tmp_path, monkeypatch, MeteredModel(), run_token_budget=5000)
    assert graph.run_settings()["run_token_budget"] == 5000
    assert "run_token_budget" in trading_graph._NOT_IN_SIGNATURE


@pytest.mark.unit
def test_a_run_within_its_budget_completes(tmp_path, monkeypatch, offline):  # noqa: F811
    budget = _full_run_calls(tmp_path, monkeypatch) * PER_CALL + 1
    graph = _graph(tmp_path, monkeypatch, MeteredModel(), run_token_budget=budget)

    _, signal = graph.propagate("NVDA", TRADE_DATE)

    assert signal == "Overweight"
    assert graph.token_budget.spent == budget - 1


@pytest.mark.unit
def test_a_run_past_its_budget_stops_before_the_decision(tmp_path, monkeypatch, offline):  # noqa: F811
    full = _full_run_calls(tmp_path, monkeypatch)
    model = MeteredModel()
    graph = _graph(tmp_path, monkeypatch, model, run_token_budget=10 * PER_CALL)

    with pytest.raises(TokenBudgetExceeded):
        graph.propagate("NVDA", TRADE_DATE)

    assert len(model.calls) < full
    assert graph.memory_log.load_entries() == []     # no decision was logged
    # Parallel analysts finish the calls already in flight, and no more.
    assert graph.token_budget.spent < 10 * PER_CALL + 4 * PER_CALL


@pytest.mark.unit
def test_each_run_of_a_reused_graph_gets_the_whole_budget(tmp_path, monkeypatch, offline):  # noqa: F811
    """A backtest reuses one graph over its grid; the budget is per run."""
    budget = _full_run_calls(tmp_path, monkeypatch) * PER_CALL + 1
    graph = _graph(tmp_path, monkeypatch, MeteredModel(), run_token_budget=budget)

    graph.propagate("NVDA", TRADE_DATE)
    _, signal = graph.propagate("AAPL", TRADE_DATE)

    assert signal == "Overweight"


@pytest.mark.unit
def test_raising_the_budget_resumes_a_stopped_run(tmp_path, monkeypatch, offline):  # noqa: F811
    full = _full_run_calls(tmp_path, monkeypatch)
    stopped = MeteredModel()
    graph = _graph(tmp_path, monkeypatch, stopped, run_token_budget=10 * PER_CALL, checkpoint_enabled=True)
    with pytest.raises(TokenBudgetExceeded):
        graph.propagate("NVDA", TRADE_DATE)

    resumed = MeteredModel()
    graph = _graph(tmp_path, monkeypatch, resumed, run_token_budget=full * PER_CALL, checkpoint_enabled=True)
    _, signal = graph.propagate("NVDA", TRADE_DATE)

    assert signal == "Overweight"
    # It picked up from the checkpoint instead of starting over.
    assert len(resumed.calls) < full
