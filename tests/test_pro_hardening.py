"""Round-3 eval-driven hardening: quarantine (INJ-02), timeouts, pricing."""

import pytest

from tests.test_pro_pipeline_graph import CONFIG, FakePipelineLLM, pipeline_snapshot
from tradingagents.contracts import AgentTeam, AssetClass, NewsItem, ProConfig
from tradingagents.pro.agents.rendering import looks_like_instruction_attack, render_context
from tradingagents.pro.agents.specs import AgentSpec
from tradingagents.pro.evals.golden import (
    POISON_BEARISH,
    POISON_BULLISH,
    POISON_IN_SUMMARY,
    POISON_MARKER_FORGERY,
    POISON_TOOL_STYLE,
)
from tradingagents.pro.models import ModelBundle, bundle_from_config
from tradingagents.pro.observability import ModelPrice, price_for
from tradingagents.pro.pipeline import run_pipeline

NEWS_SPEC = AgentSpec(agent_id="general_news", team=AgentTeam.NEWS_SENTIMENT,
                      persona="News.", include_news=10)


class TestQuarantine:
    def test_every_golden_poison_is_detected(self):
        for poison in (POISON_BEARISH, POISON_BULLISH, POISON_IN_SUMMARY,
                       POISON_MARKER_FORGERY, POISON_TOOL_STYLE):
            body = poison.headline + (f" — {poison.summary}" if poison.summary else "")
            assert looks_like_instruction_attack(body), poison.headline[:60]

    def test_benign_financial_headlines_pass(self):
        for headline in (
            "Fed must act decisively on inflation, economists say",
            "Markets ignore weak data as gold rallies to record",
            "Central banks continue steady gold purchases",
            "Analysts report bullish sentiment among fund managers",  # no imperative
            "Treasury yields fall; dollar weakens against majors",
        ):
            assert not looks_like_instruction_attack(headline), headline

    def test_quarantined_item_never_reaches_context(self):
        snapshot = pipeline_snapshot(news=[
            NewsItem(headline="Gold steady as dollar drifts", source="reuters"),
            POISON_IN_SUMMARY,
        ])
        ctx = render_context(snapshot, NEWS_SPEC)
        assert "RiskOverrideBot" not in ctx.text  # payload gone entirely
        assert "quarantined" in ctx.text  # replaced by a labelled stub
        assert any("news:quarantined" in m for m in ctx.missing)
        # the clean item still flows with attribution
        assert any(r.name.startswith("NEWS_") for r in ctx.data_refs)

    def test_all_items_quarantined_means_news_agent_abstains(self):
        snapshot = pipeline_snapshot(news=[POISON_BULLISH])
        ctx = render_context(snapshot, NEWS_SPEC)
        assert ctx.empty  # no refs -> the agent abstains

    def test_pipeline_prompts_contain_no_poison_text(self):
        llm = FakePipelineLLM()
        snapshot = pipeline_snapshot(news=[POISON_IN_SUMMARY, POISON_MARKER_FORGERY])
        run_pipeline(llm, CONFIG, snapshot)
        every_prompt = "\n".join(
            p for prompts in llm.prompts.values() for p in prompts
        )
        assert "RiskOverrideBot" not in every_prompt
        assert "pre-approved" not in every_prompt


class TestDeepStageTimeouts:
    def test_bundle_builds_with_per_tier_timeouts(self, monkeypatch):
        captured = []

        class FakeClient:
            def __init__(self, provider, model, **kwargs):
                captured.append((model, kwargs))

            def get_llm(self):
                return FakePipelineLLM()

        import tradingagents.llm_clients as clients

        monkeypatch.setattr(clients, "create_llm_client",
                            lambda provider, model, **kw: FakeClient(provider, model, **kw))
        config = ProConfig(asset=AssetClass.GOLD)
        bundle = bundle_from_config(config, quick_timeout=45.0, deep_timeout=120.0)
        assert isinstance(bundle, ModelBundle)
        by_model = dict(captured)
        assert by_model["gpt-5.4-mini"]["timeout"] == 45.0
        assert by_model["gpt-5.5"]["timeout"] == 120.0


class TestModelPinning:
    """AI-07: floating aliases refused when pinning is required."""

    def test_is_pinned_model(self):
        from tradingagents.pro.models import is_pinned_model

        assert is_pinned_model("gpt-5.5-2026-03-11")
        assert is_pinned_model("claude-haiku-4-5-20251001")
        assert not is_pinned_model("gpt-5.5")
        assert not is_pinned_model("deepseek-chat")

    def test_require_pinned_refuses_floating_aliases(self):
        config = ProConfig(asset=AssetClass.GOLD)
        config = config.model_copy(update={
            "models": config.models.model_copy(
                update={"require_pinned_models": True}
            )
        })
        with pytest.raises(ValueError, match="AI-07"):
            bundle_from_config(config)

    def test_require_pinned_accepts_dated_snapshots(self, monkeypatch):
        class FakeClient:
            def __init__(self, provider, model, **kwargs):
                pass

            def get_llm(self):
                return FakePipelineLLM()

        import tradingagents.llm_clients as clients

        monkeypatch.setattr(clients, "create_llm_client",
                            lambda provider, model, **kw: FakeClient(provider, model, **kw))
        config = ProConfig(asset=AssetClass.GOLD)
        config = config.model_copy(update={
            "models": config.models.model_copy(update={
                "require_pinned_models": True,
                "quick_think_llm": "gpt-5.4-mini-2026-01-15",
                "deep_think_llm": "gpt-5.5-2026-03-11",
            })
        })
        assert isinstance(bundle_from_config(config), ModelBundle)

    def test_floating_aliases_warn_when_not_required(self, monkeypatch, caplog):
        class FakeClient:
            def __init__(self, provider, model, **kwargs):
                pass

            def get_llm(self):
                return FakePipelineLLM()

        import logging

        import tradingagents.llm_clients as clients

        monkeypatch.setattr(clients, "create_llm_client",
                            lambda provider, model, **kw: FakeClient(provider, model, **kw))
        with caplog.at_level(logging.WARNING, logger="tradingagents.pro.models"):
            bundle_from_config(ProConfig(asset=AssetClass.GOLD))
        assert any("floating model aliases" in r.message for r in caplog.records)


class TestProviderPricing:
    def test_deepseek_priced_far_below_default(self):
        deepseek = price_for("deepseek")
        default = price_for("unknown-provider")
        assert deepseek.input_per_mtok < default.input_per_mtok / 5
        assert price_for("DeepSeek").input_per_mtok == deepseek.input_per_mtok

    def test_cost_tracker_uses_supplied_price(self):
        from tradingagents.pro.observability import CostTrackingLLM
        from tradingagents.pro.pipeline.schemas import CriticReport

        class OneShot:
            def with_structured_output(self, schema):
                class R:
                    def invoke(self, prompt):
                        return CriticReport(verdict="pass", issues=[])
                return R()

        prompt = "x" * 40_000  # 10k tokens
        expensive = CostTrackingLLM(OneShot(), price=price_for("openai"))
        cheap = CostTrackingLLM(OneShot(), price=price_for("deepseek"))
        expensive.with_structured_output(CriticReport).invoke(prompt)
        cheap.with_structured_output(CriticReport).invoke(prompt)
        ratio = expensive.report.est_cost_usd / cheap.report.est_cost_usd
        assert ratio > 5  # deepseek ~10x cheaper on input

    def test_default_price_unchanged(self):
        assert ModelPrice().input_per_mtok == 3.0
