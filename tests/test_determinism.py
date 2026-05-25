"""Tests for Phase 0 — Determinism + Fingerprint capture.

T0.1: every LLM client must inject ``temperature`` and ``seed`` (where the
provider+model accept them) so that two runs against the same input
produce reproducible output. Reasoning-mode models that 400 on temperature
overrides (GPT-5 + reasoning_effort, Claude opus/sonnet 4+ with effort,
Gemini with thinking_level on certain models) must be auto-detected and
have the temperature pin skipped.

T0.2: the stats callback must extract ``system_fingerprint`` and the
effective model identifier from every LLM response so drift detection
(T3.4) has the per-call evidence it needs.
"""

import pytest
from unittest.mock import MagicMock

from tradingagents.llm_clients import (
    anthropic_client as anthropic_mod,
    google_client as google_mod,
    openai_client as openai_mod,
)
from tradingagents.llm_clients.base_client import (
    apply_determinism_kwargs,
    supports_temperature_pin,
)


# -------------------------------------------------------------------- #
# Helpers
# -------------------------------------------------------------------- #


def _capture_openai_kwargs(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        openai_mod, "NormalizedChatOpenAI",
        lambda **kwargs: captured.setdefault("kwargs", kwargs),
    )
    return captured


def _capture_anthropic_kwargs(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        anthropic_mod, "NormalizedChatAnthropic",
        lambda **kwargs: captured.setdefault("kwargs", kwargs),
    )
    return captured


def _capture_google_kwargs(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        google_mod, "NormalizedChatGoogleGenerativeAI",
        lambda **kwargs: captured.setdefault("kwargs", kwargs),
    )
    return captured


# -------------------------------------------------------------------- #
# T0.1 — supports_temperature_pin
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestSupportsTemperaturePin:
    """The capability check that gates whether we pin temperature."""

    def test_plain_chat_model_supports_pin(self):
        assert supports_temperature_pin("gpt-4.1", {}) is True
        assert supports_temperature_pin("claude-haiku-4-5", {}) is True
        assert supports_temperature_pin("gemini-2.5-flash", {}) is True

    def test_openai_reasoning_effort_blocks_pin(self):
        """GPT-5 + reasoning_effort rejects temperature overrides with 400."""
        assert supports_temperature_pin(
            "gpt-5.4", {"reasoning_effort": "high"}
        ) is False

    def test_anthropic_effort_blocks_pin(self):
        """Claude extended thinking does not accept custom temperature."""
        assert supports_temperature_pin(
            "claude-opus-4-7", {"effort": "high"}
        ) is False

    def test_google_thinking_level_blocks_pin(self):
        assert supports_temperature_pin(
            "gemini-3.0-pro", {"thinking_level": "high"}
        ) is False

    def test_empty_reasoning_value_does_not_block(self):
        """Empty string / None for reasoning kwargs should be ignored."""
        assert supports_temperature_pin(
            "gpt-5.4", {"reasoning_effort": None}
        ) is True
        assert supports_temperature_pin(
            "gpt-5.4", {"reasoning_effort": ""}
        ) is True


# -------------------------------------------------------------------- #
# T0.1 — apply_determinism_kwargs (the shared helper)
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestApplyDeterminismKwargs:
    def test_openai_gets_temperature_and_seed(self):
        kw: dict = {}
        apply_determinism_kwargs(
            kw, model="gpt-4.1", temperature=0.0, seed=42, provider="openai",
        )
        assert kw["temperature"] == 0.0
        assert kw["seed"] == 42

    def test_anthropic_gets_temperature_only(self):
        """Anthropic does not currently expose a public seed param."""
        kw: dict = {}
        apply_determinism_kwargs(
            kw, model="claude-haiku-4-5", temperature=0.0, seed=42,
            provider="anthropic",
        )
        assert kw["temperature"] == 0.0
        assert "seed" not in kw

    def test_google_gets_temperature_top_p_top_k(self):
        kw: dict = {}
        apply_determinism_kwargs(
            kw, model="gemini-2.5-flash", temperature=0.0, seed=42,
            provider="google",
        )
        assert kw["temperature"] == 0.0
        assert kw["top_p"] == 1.0
        assert kw["top_k"] == 1
        assert "seed" not in kw  # google client does not forward seed today

    def test_user_override_wins(self):
        """If the user already set temperature, we don't clobber it."""
        kw = {"temperature": 0.7}
        apply_determinism_kwargs(
            kw, model="gpt-4.1", temperature=0.0, seed=42, provider="openai",
        )
        assert kw["temperature"] == 0.7  # user's value preserved
        assert kw["seed"] == 42

    def test_none_temperature_means_skip(self):
        """temperature=None means 'caller did not request a pin' — pass through."""
        kw: dict = {}
        apply_determinism_kwargs(
            kw, model="gpt-4.1", temperature=None, seed=42, provider="openai",
        )
        assert "temperature" not in kw
        assert kw["seed"] == 42

    def test_reasoning_model_skips_temperature(self):
        """GPT-5 with reasoning_effort should not get temperature pinned."""
        kw = {"reasoning_effort": "high"}
        apply_determinism_kwargs(
            kw, model="gpt-5.4", temperature=0.0, seed=42, provider="openai",
        )
        assert "temperature" not in kw
        assert kw["seed"] == 42  # but seed still applies


# -------------------------------------------------------------------- #
# T0.1 — End-to-end: each client wires determinism into ChatXxx kwargs
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestOpenAIClientDeterminism:
    def test_default_pins_temperature_and_seed(self, monkeypatch):
        captured = _capture_openai_kwargs(monkeypatch)
        openai_mod.OpenAIClient(
            model="gpt-4.1",
            provider="openai",
            llm_temperature=0.0,
            llm_seed=42,
        ).get_llm()
        assert captured["kwargs"]["temperature"] == 0.0
        assert captured["kwargs"]["seed"] == 42

    def test_gpt5_with_reasoning_effort_skips_temperature(self, monkeypatch):
        captured = _capture_openai_kwargs(monkeypatch)
        openai_mod.OpenAIClient(
            model="gpt-5.4",
            provider="openai",
            reasoning_effort="high",
            llm_temperature=0.0,
            llm_seed=42,
        ).get_llm()
        # No temperature (would 400), but seed still pinned for reproducibility
        assert "temperature" not in captured["kwargs"]
        assert captured["kwargs"]["seed"] == 42
        assert captured["kwargs"]["reasoning_effort"] == "high"

    def test_xai_provider_gets_seed(self, monkeypatch):
        """OpenAI-compatible providers inherit seed support."""
        captured = _capture_openai_kwargs(monkeypatch)
        openai_mod.OpenAIClient(
            model="grok-4",
            provider="xai",
            llm_temperature=0.0,
            llm_seed=42,
        ).get_llm()
        assert captured["kwargs"]["temperature"] == 0.0
        assert captured["kwargs"]["seed"] == 42


@pytest.mark.unit
class TestAnthropicClientDeterminism:
    def test_default_pins_temperature(self, monkeypatch):
        captured = _capture_anthropic_kwargs(monkeypatch)
        anthropic_mod.AnthropicClient(
            model="claude-haiku-4-5",
            llm_temperature=0.0,
            llm_seed=42,
            api_key="x",
        ).get_llm()
        assert captured["kwargs"]["temperature"] == 0.0
        assert "seed" not in captured["kwargs"]  # no public seed param

    def test_opus_with_effort_skips_temperature(self, monkeypatch):
        """Claude extended thinking rejects temperature overrides."""
        captured = _capture_anthropic_kwargs(monkeypatch)
        anthropic_mod.AnthropicClient(
            model="claude-opus-4-7",
            effort="high",
            llm_temperature=0.0,
            llm_seed=42,
            api_key="x",
        ).get_llm()
        assert "temperature" not in captured["kwargs"]
        assert captured["kwargs"]["effort"] == "high"


@pytest.mark.unit
class TestGoogleClientDeterminism:
    def test_default_pins_temperature_top_p_top_k(self, monkeypatch):
        captured = _capture_google_kwargs(monkeypatch)
        google_mod.GoogleClient(
            model="gemini-2.5-flash",
            llm_temperature=0.0,
            llm_seed=42,
            api_key="x",
        ).get_llm()
        assert captured["kwargs"]["temperature"] == 0.0
        assert captured["kwargs"]["top_p"] == 1.0
        assert captured["kwargs"]["top_k"] == 1

    def test_gemini3_thinking_skips_temperature(self, monkeypatch):
        captured = _capture_google_kwargs(monkeypatch)
        google_mod.GoogleClient(
            model="gemini-3.0-pro",
            thinking_level="high",
            llm_temperature=0.0,
            llm_seed=42,
            api_key="x",
        ).get_llm()
        assert "temperature" not in captured["kwargs"]
        assert captured["kwargs"]["thinking_level"] == "high"


# -------------------------------------------------------------------- #
# T0.1 — trading_graph plumbing
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestTradingGraphForwardsDeterminismKwargs:
    """`_get_provider_kwargs` must hand determinism config to the client factory."""

    def test_default_config_has_determinism_keys(self):
        from tradingagents.default_config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["llm_temperature"] == 0.0
        assert DEFAULT_CONFIG["llm_seed"] == 42

    def test_provider_kwargs_include_determinism(self, monkeypatch):
        """No real provider call needed — just exercise the kwargs path."""
        # Avoid expensive setup: stub create_llm_client and the rest of init.
        from tradingagents.graph import trading_graph as tg

        captured_kwargs: list = []

        def fake_create_llm_client(provider, model, **kwargs):
            captured_kwargs.append(kwargs)
            client = MagicMock()
            client.get_llm.return_value = MagicMock()
            return client

        monkeypatch.setattr(tg, "create_llm_client", fake_create_llm_client)
        # The rest of __init__ touches LangGraph internals we don't need to
        # exercise here — short-circuit by patching setup_graph.
        monkeypatch.setattr(
            tg.GraphSetup, "setup_graph", lambda self, selected_analysts: MagicMock()
        )

        tg.TradingAgentsGraph(debug=False)

        # Two clients get created (deep + quick), both should receive
        # the determinism kwargs.
        assert len(captured_kwargs) == 2
        for kw in captured_kwargs:
            assert kw["llm_temperature"] == 0.0
            assert kw["llm_seed"] == 42


# -------------------------------------------------------------------- #
# T0.2 — fingerprint capture in stats handler
# -------------------------------------------------------------------- #


def _make_llm_result(
    *,
    fingerprint: str = None,
    model: str = None,
    fingerprint_in: str = "llm_output",
):
    """Build a minimal LLMResult-like object carrying the requested metadata.

    ``fingerprint_in`` controls which surface holds the fingerprint, exercising
    the three places _extract_fingerprint looks.
    """
    from langchain_core.outputs import ChatGeneration, LLMResult
    from langchain_core.messages import AIMessage

    msg = AIMessage(content="hello", response_metadata={})
    gen = ChatGeneration(message=msg, generation_info={})
    llm_output = {}

    if fingerprint_in == "llm_output":
        if model is not None:
            llm_output["model_name"] = model
        if fingerprint is not None:
            llm_output["system_fingerprint"] = fingerprint
    elif fingerprint_in == "generation_info":
        if model is not None:
            gen.generation_info["model_name"] = model
        if fingerprint is not None:
            gen.generation_info["system_fingerprint"] = fingerprint
    elif fingerprint_in == "response_metadata":
        if model is not None:
            msg.response_metadata["model_name"] = model
        if fingerprint is not None:
            msg.response_metadata["system_fingerprint"] = fingerprint

    return LLMResult(generations=[[gen]], llm_output=llm_output)


@pytest.mark.unit
class TestStatsHandlerFingerprintCapture:
    def test_captures_fingerprint_from_llm_output(self):
        """OpenAI Chat Completions surfaces fingerprint here."""
        from cli.stats_handler import StatsCallbackHandler

        h = StatsCallbackHandler()
        h.on_chat_model_start({}, [[]])
        h.on_llm_end(_make_llm_result(
            fingerprint="fp_abc123",
            model="gpt-4.1-20250901",
            fingerprint_in="llm_output",
        ))
        stats = h.get_stats()
        assert len(stats["fingerprints"]) == 1
        assert stats["fingerprints"][0]["fingerprint"] == "fp_abc123"
        assert stats["fingerprints"][0]["model"] == "gpt-4.1-20250901"

    def test_captures_fingerprint_from_response_metadata(self):
        """Modern LangChain providers surface it on the AIMessage."""
        from cli.stats_handler import StatsCallbackHandler

        h = StatsCallbackHandler()
        h.on_chat_model_start({}, [[]])
        h.on_llm_end(_make_llm_result(
            fingerprint="fp_xyz789",
            model="claude-opus-4-7-20260301",
            fingerprint_in="response_metadata",
        ))
        stats = h.get_stats()
        assert stats["fingerprints"][0]["fingerprint"] == "fp_xyz789"
        assert stats["fingerprints"][0]["model"] == "claude-opus-4-7-20260301"

    def test_captures_fingerprint_from_generation_info(self):
        from cli.stats_handler import StatsCallbackHandler

        h = StatsCallbackHandler()
        h.on_chat_model_start({}, [[]])
        h.on_llm_end(_make_llm_result(
            fingerprint="fp_gen",
            model="gemini-3.0-pro",
            fingerprint_in="generation_info",
        ))
        stats = h.get_stats()
        assert stats["fingerprints"][0]["fingerprint"] == "fp_gen"
        assert stats["fingerprints"][0]["model"] == "gemini-3.0-pro"

    def test_missing_fingerprint_records_none_not_skip(self):
        """Always log an entry — distinguish 'provider returned none' from
        'we forgot to record'. Drift detection (T3.4) depends on this."""
        from cli.stats_handler import StatsCallbackHandler

        h = StatsCallbackHandler()
        h.on_chat_model_start({}, [[]])
        h.on_llm_end(_make_llm_result(fingerprint=None, model="some-model"))
        stats = h.get_stats()
        assert len(stats["fingerprints"]) == 1
        assert stats["fingerprints"][0]["fingerprint"] is None
        assert stats["fingerprints"][0]["model"] == "some-model"

    def test_multiple_calls_recorded_in_order(self):
        from cli.stats_handler import StatsCallbackHandler

        h = StatsCallbackHandler()
        for fp, model in (("fp_a", "m1"), ("fp_b", "m2"), ("fp_c", "m3")):
            h.on_chat_model_start({}, [[]])
            h.on_llm_end(_make_llm_result(fingerprint=fp, model=model))

        stats = h.get_stats()
        assert [r["fingerprint"] for r in stats["fingerprints"]] == ["fp_a", "fp_b", "fp_c"]
        assert [r["model"] for r in stats["fingerprints"]] == ["m1", "m2", "m3"]
