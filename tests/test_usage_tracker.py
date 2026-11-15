"""R5 LLM usage/cost meter + budget circuit breaker (RE.md 需求 5).

Acceptance tests written before the feature. Until ``usage_tracker`` lands, the
imports and attributes below fail on purpose; each failure names the behaviour
the implementation must provide.

Design decisions reflected here (from the approved plan):

* Budget is *parsed and validated explicitly* — ``None`` means no cap (and is
  NOT coerced to a float), ``0.0`` is legal (the first billed call stops the
  run), negatives / NaN / inf / bool / non-numeric are rejected. Stop uses the
  ``spent >= budget`` rule checked before a new call is dispatched, so an
  in-flight request can push the running total past the cap.
* ``on_llm_start`` AND ``on_chat_model_start`` are both counted.
* Unknown ``(provider, model)`` prices are ``None`` (unknown), never invented;
  ``ollama`` / ``openai_compatible`` default to unknown too — only calls
  *confirmed* free are zero-cost and never block.
* Each run is metered independently (one tracker per run, shared by the graph
  and the CLI), events are de-duplicated by ``run_id``.
* A ``BudgetExceeded`` raised at ``on_*_start`` must abort the *real* dispatch
  before the underlying model issues a request, and must not be turned into a
  fallback request by the structured / memory- reflection exception handlers.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

# --- fake price table, clearly labelled -------------------------------------
# NOT real prices: a fixed, explicit test fixture only.
FAKE_PRICING = {
    ("fake-provider", "fake-model"): (1.0, 2.0),  # USD per 1M input / output tokens
}


# ===========================================================================
# Budget parsing / validation
# ===========================================================================

@pytest.mark.unit
def test_none_budget_means_no_cap_and_is_not_coerced_to_float():
    from tradingagents.llm_clients.usage_tracker import UsageTracker

    tracker = UsageTracker(budget_usd=None)
    assert tracker.budget_usd is None


@pytest.mark.unit
@pytest.mark.parametrize("value", [0, 0.0])
def test_zero_budget_is_legal(value):
    from tradingagents.llm_clients.usage_tracker import UsageTracker

    assert UsageTracker(budget_usd=value).budget_usd == 0.0


@pytest.mark.unit
@pytest.mark.parametrize("bad", [-1, -0.01, float("nan"), float("inf"), float("-inf"),
                                 "abc", True, False])
def test_bad_budgets_are_rejected_loudly(bad):
    from tradingagents.llm_clients.usage_tracker import UsageTracker

    with pytest.raises(ValueError):
        UsageTracker(budget_usd=bad)


@pytest.mark.unit
def test_numeric_string_budget_is_accepted_and_parsed():
    from tradingagents.llm_clients.usage_tracker import UsageTracker

    tracker = UsageTracker(budget_usd="0.5")  # env vars arrive as strings
    assert tracker.budget_usd == 0.5 and isinstance(tracker.budget_usd, float)


# ===========================================================================
# Counting / estimation / de-duplication
# ===========================================================================

def _chat_result(content="ok"):
    return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])


def _end_event(in_tok, out_tok):
    """A minimal LLMResult the tracker reads usage_metadata from."""
    from langchain_core.messages import AIMessage as AI
    from langchain_core.outputs import LLMResult

    message = AI(
        content="ok",
        usage_metadata={"input_tokens": in_tok, "output_tokens": out_tok,
                        "total_tokens": in_tok + out_tok},
    )
    return LLMResult(generations=[[ChatGeneration(message=message)]])


def _start_kwargs(run_id, provider="fake-provider", model="fake-model"):
    return {
        "run_id": run_id,
        "metadata": {"ta_provider": provider, "ta_model": model},
    }


@pytest.mark.unit
def test_on_chat_model_start_is_counted(monkeypatch):
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    tracker = ut.UsageTracker()
    tracker.on_chat_model_start({}, [[HumanMessage("q")]],
                                **{**_start_kwargs("r1"), "run_id": "r1"})
    tracker.on_llm_end(_end_event(1000, 500), run_id="r1")
    stats = tracker.to_dict()
    assert stats["calls"] == 1
    assert stats["tokens_in"] == 1000 and stats["tokens_out"] == 500
    # (1000/1e6)*1.0 + (500/1e6)*2.0 = 0.001 + 0.001 = 0.002
    assert stats["total_usd"] == pytest.approx(0.002)


@pytest.mark.unit
def test_on_llm_start_is_counted_too(monkeypatch):
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    tracker = ut.UsageTracker()
    tracker.on_llm_start({}, ["q"], **_start_kwargs("r1"))
    tracker.on_llm_end(_end_event(1_000_000, 0), run_id="r1")
    assert tracker.to_dict()["total_usd"] == pytest.approx(1.0)


@pytest.mark.unit
def test_duplicate_start_events_for_one_run_id_count_once(monkeypatch):
    """A retry/stream can fire start twice for the same run_id; count once."""
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    tracker = ut.UsageTracker()
    tracker.on_chat_model_start({}, [[HumanMessage("q")]], **_start_kwargs("dup"))
    tracker.on_chat_model_start({}, [[HumanMessage("q")]], **_start_kwargs("dup"))
    tracker.on_llm_end(_end_event(1000, 0), run_id="dup")
    assert tracker.to_dict()["calls"] == 1
    assert tracker.to_dict()["tokens_in"] == 1000


@pytest.mark.unit
def test_duplicate_end_events_for_one_run_id_count_once(monkeypatch):
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    tracker = ut.UsageTracker()
    tracker.on_chat_model_start({}, [[HumanMessage("q")]], **_start_kwargs("e1"))
    tracker.on_llm_end(_end_event(1000, 0), run_id="e1")
    tracker.on_llm_end(_end_event(1000, 0), run_id="e1")
    assert tracker.to_dict()["tokens_in"] == 1000


def _no_usage_end():
    """An LLMResult whose generation carries no usage_metadata."""
    from langchain_core.outputs import LLMResult

    return LLMResult(generations=[[ChatGeneration(message=AIMessage(content="ok"))]])


@pytest.mark.unit
def test_missing_usage_is_recorded_not_counted_as_known_zero(monkeypatch):
    """A call that reports no usage is tallied in missing_usage_calls and marks
    the summary incomplete — never shown as a known $0.00."""
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    tracker = ut.UsageTracker()
    tracker.on_chat_model_start({}, [[HumanMessage("q")]], **_start_kwargs("m1"))
    tracker.on_llm_end(_no_usage_end(), run_id="m1")

    stats = tracker.to_dict()
    assert stats["calls"] == 1
    assert stats["missing_usage_calls"] == 1
    assert stats["usage_complete"] is False
    assert stats["tokens_in"] == 0

    # A second, fully-reported call keeps usage_complete False (one gap remains)
    # but still counts normally.
    tracker.on_chat_model_start({}, [[HumanMessage("q")]], **_start_kwargs("m2"))
    tracker.on_llm_end(_end_event(1000, 0), run_id="m2")
    stats2 = tracker.to_dict()
    assert stats2["calls"] == 2
    assert stats2["missing_usage_calls"] == 1
    assert stats2["tokens_in"] == 1000
    assert stats2["usage_complete"] is False


@pytest.mark.unit
def test_unknown_model_pricing_is_none_and_not_added(monkeypatch):
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    tracker = ut.UsageTracker()
    tracker.on_chat_model_start({}, [[HumanMessage("q")]],
                                **_start_kwargs("u1", provider="acme", model="mystery"))
    tracker.on_llm_end(_end_event(1_000_000, 1_000_000), run_id="u1")
    stats = tracker.to_dict()
    assert stats["total_usd"] == pytest.approx(0.0)
    assert ("acme", "mystery") in stats["unknown_models"]


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["ollama", "openai_compatible"])
def test_local_providers_are_unknown_unless_confirmed_free(monkeypatch, provider):
    """Local endpoints are *not* blanket zero: only confirmed-free calls are 0.0.

    With no price row, the provider is reported as unknown (like any other),
    which never blocks a run either way.
    """
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: None)
    tracker = ut.UsageTracker()
    tracker.on_chat_model_start({}, [[HumanMessage("q")]],
                                **_start_kwargs("l1", provider=provider, model="local"))
    tracker.on_llm_end(_end_event(1_000_000, 1_000_000), run_id="l1")
    stats = tracker.to_dict()
    assert stats["total_usd"] == pytest.approx(0.0)
    assert (provider, "local") in stats["unknown_models"]


@pytest.mark.unit
def test_confirmed_free_call_is_zero_and_does_not_block_a_zero_budget(monkeypatch):
    """A confirmed-free call costs 0.0 and never trips even a 0-budget cap."""
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: (0.0, 0.0))
    tracker = ut.UsageTracker(budget_usd=0.0)
    tracker.on_chat_model_start({}, [[HumanMessage("q")]],
                                **_start_kwargs("free1", provider="local", model="free"))
    tracker.on_llm_end(_end_event(1_000_000, 1_000_000), run_id="free1")
    # A second free call is still allowed: nothing billed.
    tracker.on_chat_model_start({}, [[HumanMessage("q")]],
                                **_start_kwargs("free2", provider="local", model="free"))
    stats = tracker.to_dict()
    assert stats["stopped"] is False
    assert stats["total_usd"] == pytest.approx(0.0)


@pytest.mark.unit
def test_price_table_accepts_an_overriding_provider_model_mapping(monkeypatch):
    """The estimator must not invent prices; an injected table is honoured."""
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    assert ut.estimate_cost("fake-provider", "fake-model", 1_000_000, 0) == pytest.approx(1.0)
    assert ut.estimate_cost("someone", "new", 1_000_000, 0) is None


# ===========================================================================
# Shipping price table snapshot (offline; no network in CI)
#
# Verified against the official OpenAI pricing page on 2026-11-14:
#   https://platform.openai.com/docs/pricing
# gpt-6-sol, Standard tier, Short context (<=272K input tokens), per 1M tokens:
#   input $2.00, output $10.00. (Long context, Batch and Fast tiers differ; the
#   meter bills the Standard short-context list price as an estimate.)
# These asserts pin the snapshot so an edit to MODEL_PRICING is deliberate.
# ===========================================================================

_VERIFIED_SOURCE = "https://platform.openai.com/docs/pricing"
_VERIFIED_DATE = "2026-11-14"


@pytest.mark.unit
def test_gpt_6_sol_price_is_the_verified_standard_short_context_rate():
    from tradingagents.llm_clients import model_catalog as mc

    assert mc.get_price("openai", "gpt-6-sol") == (2.00, 10.00)
    # Case-insensitive provider lookup.
    assert mc.get_price("OpenAI", "gpt-6-sol") == (2.00, 10.00)


@pytest.mark.unit
def test_verified_entry_records_its_source_and_checked_date():
    """Every shipped price must carry a direct source URL and a checked date."""
    from tradingagents.llm_clients import model_catalog as mc

    source = mc.get_price_source("openai", "gpt-6-sol")
    assert source and _VERIFIED_SOURCE in source
    assert _VERIFIED_DATE in source


@pytest.mark.unit
def test_every_shipped_price_has_a_source_entry():
    """No shipping price may claim to be known without a source + date."""
    from tradingagents.llm_clients import model_catalog as mc

    for provider, model in mc.MODEL_PRICING:
        source = mc.get_price_source(provider, model)
        assert source, f"{provider}/{model} has a price but no recorded source"
        assert _VERIFIED_DATE in source, f"{provider}/{model} source has no checked date"


# ===========================================================================
# Budget circuit breaker: real dispatch, fake underlying model
# ===========================================================================

class CountingChatModel(BaseChatModel):
    """A chat model that counts requests and reports real token usage.

    Each call returns a fixed ``usage_metadata`` (1000 input, 0 output -> the
    fake price table bills 0.001/call) so a completed call *actually* incurs the
    cost the assertions expect. The implementation must derive the cost from
    this reported usage — never hard-code it.
    """

    requests: list = Field(default_factory=list)
    in_tokens: int = 1000
    out_tokens: int = 0

    @property
    def _llm_type(self) -> str:
        return "counting"

    def bind_tools(self, tools, **kwargs):
        # `requests` is shared across bound copies; a bound copy keeps routing
        # through this class's invoke, so callbacks still dispatch for real.
        return self.model_copy()

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.requests.append(messages)
        message = AIMessage(
            content="ok",
            usage_metadata={"input_tokens": self.in_tokens,
                            "output_tokens": self.out_tokens,
                            "total_tokens": self.in_tokens + self.out_tokens},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


@pytest.mark.unit
def test_budget_stop_happens_before_the_next_real_request(monkeypatch):
    """The 2nd model call is blocked in on_chat_model_start; the model never runs it.

    Uses real langchain callback dispatch (callbacks=) so this proves the
    handler vetoes the request, not merely that a method raises when called
    by hand.
    """
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    model = CountingChatModel(metadata={"ta_provider": "fake-provider",
                                        "ta_model": "fake-model"})
    tracker = ut.UsageTracker(budget_usd=0.0)
    config = {"callbacks": [tracker]}

    with pytest.raises(ut.BudgetExceeded):
        model.invoke([HumanMessage("first")], config=config)

    assert len(model.requests) == 0, "a zero budget must not spend on the first request"
    assert tracker.stopped is True
    assert tracker.stop_reason == "BUDGET_STOPPED"


@pytest.mark.unit
def test_budget_stop_after_a_billed_call_blocks_the_following_one(monkeypatch):
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    model = CountingChatModel(metadata={"ta_provider": "fake-provider",
                                        "ta_model": "fake-model"})
    # Each call bills 0.001 (1000 in-tokens × 1.0/M); budget 0.001 lets one through.
    tracker = ut.UsageTracker(budget_usd=0.001)
    config = {"callbacks": [tracker]}
    model.invoke([HumanMessage("first")], config=config)
    assert len(model.requests) == 1
    assert tracker.to_dict()["total_usd"] == pytest.approx(0.001)

    with pytest.raises(ut.BudgetExceeded):
        model.invoke([HumanMessage("second")], config=config)
    assert len(model.requests) == 1, "the stopped call must not reach the model"


@pytest.mark.unit
def test_threshold_equality_stops(monkeypatch):
    """spent == budget is over the line (>=), not allowed through."""
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    model = CountingChatModel(metadata={"ta_provider": "fake-provider",
                                        "ta_model": "fake-model"})
    tracker = ut.UsageTracker(budget_usd=0.001)
    config = {"callbacks": [tracker]}
    model.invoke([HumanMessage("first")], config=config)
    # running total is exactly 0.001 == budget
    assert tracker.to_dict()["total_usd"] == pytest.approx(0.001)
    with pytest.raises(ut.BudgetExceeded):
        model.invoke([HumanMessage("second")], config=config)
    assert len(model.requests) == 1


@pytest.mark.unit
def test_in_flight_request_completing_after_stop_is_still_counted(monkeypatch):
    """A/B start concurrently; A completes (hits cap); C is refused; then B lands.

    B was already in flight when the cap was reached, so its completion must
    still be recorded — the total may end up over the cap, by design.
    """
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    tracker = ut.UsageTracker(budget_usd=0.001)
    model = CountingChatModel(metadata={"ta_provider": "fake-provider",
                                        "ta_model": "fake-model"})
    config = {"callbacks": [tracker]}

    # A and B both start (each 0.001 when it completes; start does not bill).
    tracker.on_chat_model_start({}, [[HumanMessage("q")]], **_start_kwargs("A"))
    tracker.on_chat_model_start({}, [[HumanMessage("q")]], **_start_kwargs("B"))
    assert len(model.requests) == 0
    # A completes first -> total 0.001, exactly the cap.
    tracker.on_llm_end(_end_event(1000, 0), run_id="A")
    assert tracker.to_dict()["total_usd"] == pytest.approx(0.001)
    # C is attempted through real dispatch: refused before any request, stop marked.
    with pytest.raises(ut.BudgetExceeded):
        model.invoke([HumanMessage("C")], config=config)
    assert len(model.requests) == 0
    assert tracker.stopped is True and tracker.stop_reason == "BUDGET_STOPPED"
    # B, already in flight, now completes: its usage is still recorded.
    tracker.on_llm_end(_end_event(1000, 0), run_id="B")
    stats = tracker.to_dict()
    assert stats["tokens_in"] == 2000
    assert stats["total_usd"] == pytest.approx(0.002)  # over the cap, by design


# ===========================================================================
# BudgetExceeded must survive the structure/memory fallbacks
# ===========================================================================

@pytest.mark.unit
def test_structured_invoke_does_not_fall_back_on_budget_stop():
    from tradingagents.agents import structured
    from tradingagents.llm_clients.usage_tracker import BudgetExceeded

    class _Boom:
        def invoke(self, prompt):
            raise BudgetExceeded("stop")

    plain_calls = []

    class _Plain:
        def invoke(self, prompt):
            plain_calls.append(prompt)
            raise AssertionError("fallback free-text request must not fire")

    with pytest.raises(BudgetExceeded):
        structured.invoke_structured_or_freetext(
            _Boom(), _Plain(), "prompt", render=lambda x: str(x), agent_name="X")
    assert plain_calls == []


@pytest.mark.unit
def test_settlement_reflection_budget_stop_is_not_swallowed():
    from tradingagents.llm_clients.usage_tracker import BudgetExceeded
    from tradingagents.memory import settlement

    class _Log:
        def settling(self, wait=True):
            import contextlib
            @contextlib.contextmanager
            def cm():
                yield True
            return cm()

        def get_pending_entries(self):
            return [{"ticker": "NVDA", "date": "2026-01-02", "decision": "d"}]

    class _Reflector:
        def reflect_on_final_decision(self, **kw):
            raise BudgetExceeded("stop")

    import tradingagents.memory.settlement as s
    # Make the price fetch succeed so we reach the reflection call.
    orig = s.fetch_returns
    try:
        s.fetch_returns = lambda *a, **k: (0.01, 0.005, 5, "2026-01-09")
        with pytest.raises(BudgetExceeded):
            settlement.settle_pending("NVDA", _Log(), _Reflector(), {"benchmark_ticker": "SPY"})
    finally:
        s.fetch_returns = orig


@pytest.mark.unit
def test_memory_step_does_not_swallow_budget_stop():
    """_memory_step's broad except must let BudgetExceeded abort the run."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.llm_clients.usage_tracker import BudgetExceeded

    graph = object.__new__(TradingAgentsGraph)
    graph.settle_all_pending = lambda wait=False: (_ for _ in ()).throw(BudgetExceeded("stop"))
    graph.memory_log = SimpleNamespace(get_past_context=lambda *a, **k: "lessons")
    graph._memory_as_of = lambda d: None

    with pytest.raises(BudgetExceeded):
        graph._memory_step({"company_of_interest": "NVDA", "trade_date": "2026-01-02"})


# ===========================================================================
# Factory: provider/model metadata survives the real client build
# ===========================================================================

@pytest.mark.unit
def test_metadata_reaches_the_model_through_create_tier_client(monkeypatch):
    """create_tier_client must tag the model so the tracker knows provider/model."""
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder")
    from tradingagents.llm_clients import create_tier_client

    cfg = {
        "llm_provider": "openai", "quick_think_llm": "gpt-6-luna",
        "deep_think_llm": "gpt-6-sol", "quick_think_provider": None,
        "deep_think_provider": None, "quick_think_backend_url": None,
        "deep_think_backend_url": None, "backend_url": None,
    }
    llm = create_tier_client(cfg, "quick").get_llm()
    meta = getattr(llm, "metadata", {}) or {}
    assert meta.get("ta_provider") == "openai"
    assert meta.get("ta_model") == "gpt-6-luna"


@pytest.mark.unit
def test_bound_model_still_delivers_metadata_to_the_tracker(monkeypatch):
    """After bind_tools/with_structured_output, provider/model still reach on_chat_model_start."""
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    seen = {}

    class Probe(ut.UsageTracker):
        def on_chat_model_start(self, serialized, messages, **kw):
            seen["provider"] = (kw.get("metadata") or {}).get("ta_provider")
            seen["model"] = (kw.get("metadata") or {}).get("ta_model")
            seen["serialized_model"] = (serialized.get("kwargs") or {}).get("model_name") \
                or (serialized.get("kwargs") or {}).get("model")
            return super().on_chat_model_start(serialized, messages, **kw)

    tracker = Probe()
    model = CountingChatModel(metadata={"ta_provider": "fake-provider",
                                        "ta_model": "fake-model"})
    # Bind tools and a structured output just as the agents do, then invoke.
    bound = model.bind_tools([])
    bound.invoke([HumanMessage("q")], config={"callbacks": [tracker]})

    assert seen["provider"] == "fake-provider"
    assert seen["model"] == "fake-model"
    # The tracker recorded usage under that provider/model (not unknown).
    stats = tracker.to_dict()
    assert ("fake-provider", "fake-model") not in stats["unknown_models"]
    assert stats["tokens_in"] == 1000


# ===========================================================================
# End-to-end harness: a real graph / CLI run with a scripted offline model.
# These exercise the real entry points (propagate / run_analysis), not
# write_costs directly, so cost persistence is proven to happen where a run
# actually begins and ends.
# ===========================================================================

TRADE_DATE = "2026-01-09"
_E2E_TEXT = "Report.\n\n**Rating**: Overweight\n\nFINAL TRANSACTION PROPOSAL: **BUY**"


class _E2EModel(BaseChatModel):
    """Offline chat model: reports usage per call, answers with a fixed rating.

    ``fail_after`` raises a provider error on the (n+1)-th call to exercise the
    exception-persistence path through the real graph.
    """

    in_tokens: int = 1000
    out_tokens: int = 0
    calls: list = Field(default_factory=list)
    fail_after: int | None = None

    @property
    def _llm_type(self) -> str:
        return "e2e"

    def bind_tools(self, tools, **kwargs):
        return self  # structured/free-text both fall back to plain generation

    def with_structured_output(self, schema, **kwargs):
        # Behave like a provider without structured output: every structured
        # call falls back to free text (the debate turn via its JSON schema),
        # so each call still goes through _generate and reports its usage.
        raise NotImplementedError

    def _content_for(self, messages):
        from tradingagents.agents import schemas

        last = str(messages[-1].content)
        if "Return only a JSON object matching this schema." in last:
            return schemas.DebateTurn(
                key_claims=[schemas.DebateClaim(
                    evidence="Test market report.",
                    reasoning="The report supports the test thesis.",
                    response="Address the opponent or present an opening thesis.")],
                evidence_refs=["market report"], refuted_points=[], stance_score=0.5,
                reverse_check="The test evidence may be incomplete.").model_dump_json()
        return _E2E_TEXT

    def _message(self, messages=None):
        content = self._content_for(messages) if messages else _E2E_TEXT
        return AIMessage(
            content=content,
            usage_metadata={"input_tokens": self.in_tokens,
                            "output_tokens": self.out_tokens,
                            "total_tokens": self.in_tokens + self.out_tokens},
        )

    def _record(self):
        self.calls.append(1)
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise RuntimeError("provider unavailable")

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._record()
        return ChatResult(generations=[ChatGeneration(message=self._message(messages))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        # Debug mode streams the run; emit one chunk then end.
        from langchain_core.outputs import ChatGenerationChunk

        self._record()
        yield ChatGenerationChunk(message=self._message(messages))


class _E2EClient:
    """Stands in for a tier client: tags the model with its provider/model and
    forwards the callbacks the graph supplies, so usage is metered for real."""

    def __init__(self, model, provider, model_name, callbacks=None):
        self._model = model
        self._provider = provider
        self._model_name = model_name
        self._callbacks = callbacks or []

    def get_llm(self):
        return self._model.model_copy(update={
            "metadata": {"ta_provider": self._provider, "ta_model": self._model_name},
            "callbacks": self._callbacks,
        })


@pytest.fixture
def e2e_offline(monkeypatch):
    """Every data vendor answers offline so a full graph run needs no network."""
    import pandas as pd

    from tradingagents.agents import context as agent_context
    from tradingagents.agents.analysts import sentiment_analyst
    from tradingagents.dataflows import router
    from tradingagents.dataflows.vendors.yahoo import market as yahoo_market, snapshot

    for method, vendors in router.VENDOR_METHODS.items():
        for vendor in vendors:
            monkeypatch.setitem(vendors, vendor, lambda *a, _m=method, **k: f"{_m} data")
    prices = pd.DataFrame({
        "Date": pd.bdate_range(end=TRADE_DATE, periods=60),
        "Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1_000_000,
    })
    monkeypatch.setattr(snapshot, "load_ohlcv", lambda *a, **k: prices.copy())
    monkeypatch.setattr(sentiment_analyst, "fetch_stocktwits_messages", lambda *a, **k: "no posts")
    monkeypatch.setattr(sentiment_analyst, "fetch_reddit_posts", lambda *a, **k: "no posts")
    monkeypatch.setattr(yahoo_market.yf, "Ticker",
                        lambda s: type("T", (), {"info": {"longName": "NVIDIA"}})())
    agent_context._identity.cache_clear()


def _e2e_graph(tmp_path, monkeypatch, model, debug=False,
               selected_analysts=("market",), **config):
    """A real TradingAgentsGraph whose tier clients return the scripted model.

    The stub factory keeps the callbacks the graph passes and tags each tier's
    model with its provider/model, so the tracker meters usage for real and the
    fake price table matches the (fake-provider, fake-model) pair.
    """
    import copy as _copy

    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph import trading_graph

    def _factory(cfg, tier, **kwargs):
        provider = (cfg.get(f"{tier}_think_provider") or cfg["llm_provider"])
        return _E2EClient(model, provider, cfg[f"{tier}_think_llm"],
                          callbacks=kwargs.get("callbacks"))

    monkeypatch.setattr(trading_graph, "create_tier_client", _factory)
    cfg = _copy.deepcopy(DEFAULT_CONFIG)
    cfg.update(llm_provider="fake-provider",
               quick_think_llm="fake-model", deep_think_llm="fake-model",
               results_dir=str(tmp_path / "results"),
               data_cache_dir=str(tmp_path / "cache"),
               memory_log_path=str(tmp_path / "log.md"), **config)
    return trading_graph.TradingAgentsGraph(
        selected_analysts=selected_analysts, config=cfg, debug=debug)


def _read_cost(tmp_path, ticker="NVDA", date=TRADE_DATE):
    import json

    path = tmp_path / "results" / "costs" / f"{ticker}_{date}.json"
    assert path.exists(), f"cost JSON missing at {path}"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.unit
@pytest.mark.parametrize("debug", [False, True], ids=["normal", "debug"])
def test_api_run_writes_cost_json_via_propagate(tmp_path, monkeypatch, e2e_offline, debug,
                                                capsys):
    """propagate() (normal and debug) persists the cost JSON for the run."""
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    model = _E2EModel()
    graph = _e2e_graph(tmp_path, monkeypatch, model, debug=debug,
                       selected_analysts=("market",), max_debate_rounds=1,
                       max_risk_discuss_rounds=1)

    graph.propagate("NVDA", TRADE_DATE)

    data = _read_cost(tmp_path)
    # Cost is derived from the model's reported usage, not hard-coded.
    assert data["tokens_in"] == model.in_tokens * len(model.calls)
    assert data["total_usd"] == pytest.approx(0.001 * len(model.calls))
    assert data["stopped"] is False


@pytest.mark.unit
def test_api_run_writes_cost_json_when_the_run_raises(tmp_path, monkeypatch, e2e_offline):
    """An aborted run still writes what it spent, then re-raises."""
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    model = _E2EModel(fail_after=2)
    graph = _e2e_graph(tmp_path, monkeypatch, model, selected_analysts=("market",),
                       max_debate_rounds=1, max_risk_discuss_rounds=1)

    with pytest.raises(RuntimeError, match="provider unavailable"):
        graph.propagate("NVDA", TRADE_DATE)

    data = _read_cost(tmp_path)
    assert data["tokens_in"] == model.in_tokens * 2  # the two completed calls
    assert data["total_usd"] > 0


@pytest.mark.unit
def test_api_run_writes_cost_json_when_budget_stops(tmp_path, monkeypatch, e2e_offline):
    """A budget stop aborts propagate() and still persists the cost JSON."""
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    model = _E2EModel()
    graph = _e2e_graph(tmp_path, monkeypatch, model, selected_analysts=("market",),
                       max_debate_rounds=1, max_risk_discuss_rounds=1,
                       max_run_budget_usd=0.0)

    with pytest.raises(ut.BudgetExceeded):
        graph.propagate("NVDA", TRADE_DATE)

    data = _read_cost(tmp_path)
    assert data["stopped"] is True and data["stop_reason"] == "BUDGET_STOPPED"


def _cli_selections(**overrides):
    selections = {
        "ticker": "NVDA", "analysis_date": TRADE_DATE, "asset_type": "stock",
        "analysts": [SimpleNamespace(value="market")],
        "research_depth": 1, "quick_think_llm": "fake-model",
        "deep_think_llm": "fake-model", "backend_url": None,
        "llm_provider": "fake-provider", "output_language": "English",
    }
    selections.update(overrides)
    return selections


def _wire_cli(tmp_path, monkeypatch, model, config_extra=None, selections=None):
    """Make a real run_analysis run offline: no live UI, scripted tier model."""
    import rich.live

    from cli import run as cli_run
    from tradingagents.graph import trading_graph as tg_module

    monkeypatch.setattr(cli_run, "get_user_selections",
                        lambda flags: _cli_selections(**(selections or {})))
    monkeypatch.setattr(cli_run, "create_layout", lambda: SimpleNamespace())
    for name in ("update_display", "update_analyst_statuses", "update_research_team_status"):
        monkeypatch.setattr(cli_run, name, lambda *a, **k: None)
    monkeypatch.setattr(cli_run, "display_complete_report", lambda state: None)
    monkeypatch.setattr(rich.live, "Live", lambda *a, **k: contextlib.nullcontext())
    # message_buffer is a module-global singleton; start each run from a clean
    # slate so assertions inspect only this run's messages and agent states.
    cli_run.message_buffer.messages.clear()
    cli_run.message_buffer.agent_status = {}

    def _factory(cfg, tier, **kwargs):
        provider = (cfg.get(f"{tier}_think_provider") or cfg["llm_provider"])
        return _E2EClient(model, provider, cfg[f"{tier}_think_llm"],
                          callbacks=kwargs.get("callbacks"))

    monkeypatch.setattr(tg_module, "create_tier_client", _factory)
    monkeypatch.setattr(cli_run, "DEFAULT_CONFIG",
                        {**cli_run.DEFAULT_CONFIG,
                         "results_dir": str(tmp_path / "results"),
                         "data_cache_dir": str(tmp_path / "cache"),
                         "memory_log_path": str(tmp_path / "log.md"),
                         **(config_extra or {})})
    return cli_run


_CLI_FLAGS = {"ticker": "NVDA", "date": TRADE_DATE, "analysts": "market",
              "save": False, "show": False}


@pytest.mark.unit
def test_cli_run_writes_cost_json_via_run_analysis(tmp_path, monkeypatch, e2e_offline):
    """The CLI entry point (run_analysis) persists the cost JSON for its run."""
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    model = _E2EModel()
    cli_run = _wire_cli(tmp_path, monkeypatch, model)

    cli_run.run_analysis(flags=dict(_CLI_FLAGS))

    data = _read_cost(tmp_path)
    assert data["tokens_in"] == model.in_tokens * len(model.calls)
    assert data["total_usd"] == pytest.approx(0.001 * len(model.calls))


@pytest.mark.unit
def test_cli_run_writes_cost_json_when_the_run_raises(tmp_path, monkeypatch, e2e_offline):
    """A normal provider error propagates from the CLI but the cost is still written."""
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    model = _E2EModel(fail_after=3)
    cli_run = _wire_cli(tmp_path, monkeypatch, model)

    with pytest.raises(RuntimeError, match="provider unavailable"):
        cli_run.run_analysis(flags=dict(_CLI_FLAGS))

    data = _read_cost(tmp_path)
    assert data["tokens_in"] == model.in_tokens * 3   # the three completed calls
    assert data["stopped"] is False


@pytest.mark.unit
def test_cli_reports_budget_stop_clearly_and_releases_the_checkpoint(
        tmp_path, monkeypatch, e2e_offline, capsys):
    """A budget stop must show BUDGET_STOPPED, the cost and the file, and must
    not claim the analysis succeeded; the checkpointer must be torn down."""
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    model = _E2EModel()
    ended = []
    cli_run = _wire_cli(tmp_path, monkeypatch, model,
                        config_extra={"max_run_budget_usd": 0.0,
                                      "checkpoint_enabled": True})

    # Track end_checkpoint so we can prove the resource is released.
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    orig_end = TradingAgentsGraph.end_checkpoint

    def _tracking_end(self):
        ended.append(True)
        return orig_end(self)

    monkeypatch.setattr(TradingAgentsGraph, "end_checkpoint", _tracking_end)

    # The budget is hit on the very first request, so the run aborts.
    cli_run.run_analysis(flags=dict(_CLI_FLAGS))

    out = capsys.readouterr().out
    assert ended, "the checkpoint must be released on a budget stop"
    assert "BUDGET_STOPPED" in out
    assert "costs" in out  # shows where the cost file is
    assert "Analysis Complete" not in out
    assert "Completed analysis" not in out

    data = _read_cost(tmp_path)
    assert data["stopped"] is True and data["stop_reason"] == "BUDGET_STOPPED"


@pytest.mark.unit
def test_budget_stop_does_not_mark_agents_completed_in_the_buffer(
        tmp_path, monkeypatch, e2e_offline):
    """On a budget stop the buffer must not record a success completion.

    Inspects the shared message_buffer directly (messages and agent_status), not
    just the terminal output: the all-agents-completed sweep and the "Completed
    analysis" line must run only on a normal finish, and a stop reason must be
    recorded instead.
    """
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    model = _E2EModel()
    cli_run = _wire_cli(tmp_path, monkeypatch, model,
                        config_extra={"max_run_budget_usd": 0.0})

    cli_run.run_analysis(flags=dict(_CLI_FLAGS))

    buf = cli_run.message_buffer
    contents = [content for _ts, _type, content in buf.messages]
    assert not any("Completed analysis" in c for c in contents), \
        "a stopped run must not record a success completion message"
    assert any("BUDGET_STOPPED" in c for c in contents), \
        "the stop reason must be recorded in the run's messages"
    # No agent may be reported completed on a stopped run: the pipeline never
    # reached the later teams, so their true status is not 'completed'.
    assert all(status != "completed" for status in buf.agent_status.values()), \
        f"no agent should be completed on a stop, got {buf.agent_status}"


@pytest.mark.unit
def test_normal_finish_marks_agents_completed_in_the_buffer(
        tmp_path, monkeypatch, e2e_offline):
    """The success sweep still runs on a normal finish (guards the fix)."""
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    model = _E2EModel()
    cli_run = _wire_cli(tmp_path, monkeypatch, model)

    cli_run.run_analysis(flags=dict(_CLI_FLAGS))

    buf = cli_run.message_buffer
    contents = [content for _ts, _type, content in buf.messages]
    assert any("Completed analysis" in c for c in contents)
    assert buf.agent_status and all(s == "completed" for s in buf.agent_status.values())


# ===========================================================================
# Report header summary compares the same numbers as the JSON
# ===========================================================================

@pytest.mark.unit
def test_report_header_matches_the_cost_json_amount(tmp_path, monkeypatch, e2e_offline):
    """The complete report's cost line shows the same tokens/amount/state as JSON."""
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    model = _E2EModel()
    graph = _e2e_graph(tmp_path, monkeypatch, model, selected_analysts=("market",),
                       max_debate_rounds=1, max_risk_discuss_rounds=1)

    final_state, _signal = graph.propagate("NVDA", TRADE_DATE)
    report_dir = tmp_path / "report"
    graph.save_reports(final_state, "NVDA", save_path=report_dir, html=False)

    data = _read_cost(tmp_path)
    report = (report_dir / "complete_report.md").read_text(encoding="utf-8")
    # Same token count, same USD amount, and the run's status appear in the report.
    assert str(data["tokens_in"]) in report
    assert f"{data['total_usd']:.4f}" in report or f"{data['total_usd']:.2f}" in report
    assert ("BUDGET_STOPPED" not in report) if not data["stopped"] else True


@pytest.mark.unit
def test_missing_usage_is_flagged_in_the_cost_json_and_report(tmp_path):
    """The cost JSON and report mark an incomplete tally; not a known $0.00."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.llm_clients import usage_tracker as ut

    # Drive the tracker directly: one call reports no usage.
    tracker = ut.UsageTracker()
    tracker.on_chat_model_start({}, [[HumanMessage("q")]], **_start_kwargs("z1"))
    tracker.on_llm_end(_no_usage_end(), run_id="z1")

    graph = object.__new__(TradingAgentsGraph)
    graph.config = {"results_dir": str(tmp_path / "results")}
    graph.selected_analysts = ("market",)
    graph.usage_tracker = tracker
    graph.run_settings = lambda: {}
    graph.write_costs("NVDA", TRADE_DATE)

    import json
    data = json.loads((tmp_path / "results" / "costs" / f"NVDA_{TRADE_DATE}.json")
                      .read_text(encoding="utf-8"))
    assert data["missing_usage_calls"] == 1
    assert data["usage_complete"] is False

    # The report header reflects the incomplete tally.
    from tradingagents.reporting import write_report_tree

    final_state = {"trade_date": TRADE_DATE, "market_report": "M", "llm_cost": data}
    out = write_report_tree(final_state, "NVDA", tmp_path / "report", settings={}, html=False)
    report = out.read_text(encoding="utf-8")
    assert "incomplete" in report.lower()


# ===========================================================================
# Config: budget key + env override
# ===========================================================================

@pytest.mark.unit
def test_default_config_has_budget_none_and_env_override(monkeypatch):
    import importlib

    import tradingagents.default_config as dc

    importlib.reload(dc)
    assert dc.DEFAULT_CONFIG["max_run_budget_usd"] is None
    assert "TRADINGAGENTS_RUN_BUDGET_USD" in dc._ENV_OVERRIDES

    monkeypatch.setenv("TRADINGAGENTS_RUN_BUDGET_USD", "0.5")
    reloaded = dc.build_default_config()
    assert reloaded["max_run_budget_usd"] == 0.5
    assert isinstance(reloaded["max_run_budget_usd"], float)


@pytest.mark.unit
def test_env_budget_rejects_garbage(monkeypatch):
    import tradingagents.default_config as dc

    monkeypatch.setenv("TRADINGAGENTS_RUN_BUDGET_USD", "not-a-number")
    with pytest.raises(ValueError):
        dc.build_default_config()


# ===========================================================================
# Per-run isolation: one graph run twice must not carry cost/stop over
# ===========================================================================

@pytest.mark.unit
def test_a_reused_graph_starts_each_run_with_a_fresh_meter(tmp_path, monkeypatch, e2e_offline):
    """A second run on the same graph neither inherits the first's cost nor its stop."""
    from tradingagents.llm_clients import usage_tracker as ut

    monkeypatch.setattr(ut, "get_price", lambda p, m: FAKE_PRICING.get((p, m)))
    model = _E2EModel()
    graph = _e2e_graph(tmp_path, monkeypatch, model, selected_analysts=("market",),
                       max_debate_rounds=1, max_risk_discuss_rounds=1)

    graph.propagate("NVDA", "2026-01-08")
    first = _read_cost(tmp_path, date="2026-01-08")
    calls_first = len(model.calls)

    graph.propagate("NVDA", TRADE_DATE)
    second = _read_cost(tmp_path, date=TRADE_DATE)
    calls_second = len(model.calls) - calls_first

    # Each run's JSON holds only its own calls, not the cumulative total.
    assert first["tokens_in"] == model.in_tokens * calls_first
    assert second["tokens_in"] == model.in_tokens * calls_second
    assert second["stopped"] is False
