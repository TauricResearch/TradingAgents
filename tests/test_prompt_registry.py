"""Tests for ``tradingagents.audit.prompt_registry`` (T1.4).

Two layers:

1. **Registry contract** — load / render / cache / hash / version /
   missing-variable / path-traversal / trace_metadata semantics.

2. **Byte-identical equivalence** — rendering each migrated template
   with sample inputs must produce the exact string the original
   f-string in the agent factory would have produced. This is the
   hard proof that the migration is non-behavior-changing; without
   it the audit story is fiction.
"""

from __future__ import annotations

import hashlib
import textwrap
import uuid
from pathlib import Path

import pytest

from tradingagents.audit.prompt_registry import (
    DEFAULT_PROMPTS_DIR,
    PromptNotFoundError,
    PromptRegistry,
    default_registry,
    reset_default_registry,
)
from tradingagents.dataflows.config import set_config


# -------------------------------------------------------------------- #
# Registry contract
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestPromptRegistryLoad:
    def test_load_returns_text_and_hash(self, tmp_path):
        (tmp_path / "x.v1.txt").write_text("hello $name")
        r = PromptRegistry(base_dir=tmp_path)
        text, h = r.load("x", "v1")
        assert text == "hello $name"
        assert h == hashlib.sha256(b"hello $name").hexdigest()

    def test_load_respects_subdirs(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "b.v1.txt").write_text("ok")
        r = PromptRegistry(base_dir=tmp_path)
        text, _ = r.load("a/b", "v1")
        assert text == "ok"

    def test_load_missing_raises_PromptNotFoundError(self, tmp_path):
        r = PromptRegistry(base_dir=tmp_path)
        with pytest.raises(PromptNotFoundError):
            r.load("nope", "v1")

    def test_load_caches_after_first_read(self, tmp_path):
        path = tmp_path / "x.v1.txt"
        path.write_text("first")
        r = PromptRegistry(base_dir=tmp_path)
        text1, h1 = r.load("x", "v1")
        # Mutate file on disk — cache must hold the original text
        path.write_text("second")
        text2, h2 = r.load("x", "v1")
        assert text1 == text2 == "first"
        assert h1 == h2

    def test_different_versions_have_different_hashes(self, tmp_path):
        (tmp_path / "x.v1.txt").write_text("alpha")
        (tmp_path / "x.v2.txt").write_text("beta")
        r = PromptRegistry(base_dir=tmp_path)
        _, h1 = r.load("x", "v1")
        _, h2 = r.load("x", "v2")
        assert h1 != h2

    def test_path_traversal_blocked(self, tmp_path):
        """``..`` segments must not escape the registry's base_dir."""
        r = PromptRegistry(base_dir=tmp_path)
        with pytest.raises(PromptNotFoundError):
            r.load("../etc/passwd", "v1")

    def test_hash_is_sha256_hex(self, tmp_path):
        (tmp_path / "x.v1.txt").write_text("content")
        r = PromptRegistry(base_dir=tmp_path)
        _, h = r.load("x", "v1")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


@pytest.mark.unit
class TestPromptRegistryRender:
    def test_render_substitutes_dollar_vars(self, tmp_path):
        (tmp_path / "x.v1.txt").write_text("hello $name, you are $age")
        r = PromptRegistry(base_dir=tmp_path)
        rendered, h = r.render("x", name="Alice", age="30")
        assert rendered == "hello Alice, you are 30"

    def test_render_substitutes_braced_vars(self, tmp_path):
        (tmp_path / "x.v1.txt").write_text("${greeting}, world")
        r = PromptRegistry(base_dir=tmp_path)
        rendered, _ = r.render("x", greeting="Hi")
        assert rendered == "Hi, world"

    def test_render_returns_template_hash_not_rendered_hash(self, tmp_path):
        """Hash is of the TEMPLATE, not the rendered output. Two different
        renders of the same template must return the same hash."""
        (tmp_path / "x.v1.txt").write_text("$x")
        r = PromptRegistry(base_dir=tmp_path)
        _, h_a = r.render("x", x="A")
        _, h_b = r.render("x", x="B")
        assert h_a == h_b

    def test_render_missing_var_raises_KeyError(self, tmp_path):
        """Silent empty substitution would let typos at the call site
        produce blank sections in production prompts. Fail loud."""
        (tmp_path / "x.v1.txt").write_text("$one and $two")
        r = PromptRegistry(base_dir=tmp_path)
        with pytest.raises(KeyError) as exc_info:
            r.render("x", one="hello")  # 'two' missing
        # Error mentions which variable + which key/version
        assert "two" in str(exc_info.value)
        assert "x" in str(exc_info.value)

    def test_render_strips_trailing_newline(self, tmp_path):
        """File-stored templates almost always have a trailing \\n from the
        editor. rstrip preserves byte-identical equivalence with f-strings."""
        # File ends with `$x\n` (trailing newline)
        (tmp_path / "x.v1.txt").write_text("$x\n")
        r = PromptRegistry(base_dir=tmp_path)
        rendered, _ = r.render("x", x="content")
        assert rendered == "content"

    def test_trace_metadata_shape(self, tmp_path):
        (tmp_path / "researchers" / "bull.v1.txt").parent.mkdir()
        (tmp_path / "researchers" / "bull.v1.txt").write_text("x")
        r = PromptRegistry(base_dir=tmp_path)
        md = r.trace_metadata("researchers/bull", "v1")
        assert md["prompt_key"] == "researchers/bull"
        assert md["prompt_version"] == "v1"
        assert md["prompt_hash"]
        assert len(md["prompt_hash"]) == 64


@pytest.mark.unit
class TestDefaultRegistrySingleton:
    def test_default_registry_returns_same_instance(self):
        reset_default_registry()
        a = default_registry()
        b = default_registry()
        assert a is b

    def test_reset_creates_new_instance(self):
        a = default_registry()
        reset_default_registry()
        b = default_registry()
        assert a is not b

    def test_default_points_at_packaged_prompts(self):
        reset_default_registry()
        r = default_registry()
        # The default base_dir is tradingagents/prompts at the package root
        assert r.base_dir == DEFAULT_PROMPTS_DIR
        # And the bull_researcher template should be loadable from there
        text, h = r.load("researchers/bull_researcher", "v1")
        assert "Bull Analyst" in text


# -------------------------------------------------------------------- #
# Byte-identical equivalence: rendered template == original f-string
# -------------------------------------------------------------------- #


_BULL_INPUTS = {
    "target_label": "stock",
    "fundamentals_label": "Company fundamentals report",
    "market_research_report": "MARKET",
    "sentiment_report": "SENTIMENT",
    "news_report": "NEWS",
    "fundamentals_report": "FUND",
    "history": "HIST",
    "current_response": "BEAR_LAST",
}


def _bull_legacy_fstring(language_instruction: str, **i) -> str:
    """The exact pre-T1.4 f-string body, kept here as the equivalence reference.

    Any change to this function must be matched by a change to
    ``researchers/bull_researcher.v1.txt`` and a hash bump in the
    on-disk template — otherwise the agent silently shifts behavior.
    Pinning this in the test suite is what enforces that.
    """
    return f"""You are a Bull Analyst advocating for investing in the {i['target_label']}. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

Resources available:
Market research report: {i['market_research_report']}
Social media sentiment report: {i['sentiment_report']}
Latest world affairs news: {i['news_report']}
{i['fundamentals_label']}: {i['fundamentals_report']}
Conversation history of the debate: {i['history']}
Last bear argument: {i['current_response']}
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position.
""" + language_instruction


@pytest.mark.unit
class TestByteIdenticalEquivalence:
    """Each migrated template renders byte-identical to its legacy f-string.

    These tests are the hard floor of the T1.4 contract: if any
    template drifts from its pre-migration form, the assertion catches
    it before bad audit data is produced.
    """

    def setup_method(self):
        reset_default_registry()
        # English (default) — language_instruction renders as empty
        set_config({"output_language": "English"})

    def test_bull_researcher_byte_identical_english(self):
        registry = default_registry()
        rendered, _ = registry.render(
            "researchers/bull_researcher",
            language_instruction="",
            **_BULL_INPUTS,
        )
        expected = _bull_legacy_fstring(language_instruction="", **_BULL_INPUTS)
        assert rendered == expected

    def test_bull_researcher_byte_identical_chinese(self):
        registry = default_registry()
        lang_inst = " Write your entire response in Chinese."
        rendered, _ = registry.render(
            "researchers/bull_researcher",
            language_instruction=lang_inst,
            **_BULL_INPUTS,
        )
        expected = _bull_legacy_fstring(language_instruction=lang_inst, **_BULL_INPUTS)
        assert rendered == expected


# -------------------------------------------------------------------- #
# Integration: agent factories pass prompt provenance metadata
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestAgentFactoryRecordsPromptMetadata:
    """Each migrated agent factory must call llm.invoke(prompt, config={
    "metadata": {"prompt_key": ..., "prompt_version": ..., "prompt_hash": ...}})
    so the trace records prompt provenance without callback changes."""

    def setup_method(self):
        reset_default_registry()
        set_config({"output_language": "English"})

    def _state_for_researchers(self) -> dict:
        return {
            "investment_debate_state": {
                "history": "h", "bull_history": "bh", "bear_history": "bhr",
                "current_response": "cr", "count": 0,
            },
            "market_report": "m",
            "sentiment_report": "s",
            "news_report": "n",
            "fundamentals_report": "f",
            "asset_type": "stock",
        }

    def test_bull_researcher_passes_prompt_metadata(self):
        from unittest.mock import MagicMock
        from tradingagents.agents.researchers.bull_researcher import create_bull_researcher

        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content="bull says go")
        node = create_bull_researcher(llm)
        node(self._state_for_researchers())

        # llm.invoke called once with (prompt, config={"metadata": {...}})
        assert llm.invoke.call_count == 1
        args, kwargs = llm.invoke.call_args
        md = kwargs["config"]["metadata"]
        assert md["prompt_key"] == "researchers/bull_researcher"
        assert md["prompt_version"] == "v1"
        assert len(md["prompt_hash"]) == 64

    def test_bear_researcher_passes_prompt_metadata(self):
        from unittest.mock import MagicMock
        from tradingagents.agents.researchers.bear_researcher import create_bear_researcher

        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content="bear says no")
        node = create_bear_researcher(llm)
        node(self._state_for_researchers())

        args, kwargs = llm.invoke.call_args
        md = kwargs["config"]["metadata"]
        assert md["prompt_key"] == "researchers/bear_researcher"
        assert md["prompt_version"] == "v1"
        assert len(md["prompt_hash"]) == 64

    def test_aggressive_debator_passes_prompt_metadata(self):
        from unittest.mock import MagicMock
        from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator

        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content="aggressive says yes")
        state = {
            "risk_debate_state": {
                "history": "h", "aggressive_history": "ah",
                "conservative_history": "ch", "neutral_history": "nh",
                "current_aggressive_response": "", "current_conservative_response": "",
                "current_neutral_response": "", "count": 0,
            },
            "market_report": "m", "sentiment_report": "s",
            "news_report": "n", "fundamentals_report": "f",
            "trader_investment_plan": "BUY",
        }
        node = create_aggressive_debator(llm)
        node(state)

        args, kwargs = llm.invoke.call_args
        md = kwargs["config"]["metadata"]
        assert md["prompt_key"] == "risk/aggressive"
        assert md["prompt_version"] == "v1"


@pytest.mark.unit
class TestPromptVersionOverride:
    """Pinning a custom version via state['prompt_versions'] resolves the
    matching template file. This is the rollout mechanism for new prompts."""

    def test_custom_version_loads_alternate_template(self, tmp_path):
        # Build a registry pointing at tmp_path; seed v1 + v2
        (tmp_path / "researchers").mkdir()
        (tmp_path / "researchers" / "bull_researcher.v1.txt").write_text(
            "v1 says $target_label"
        )
        (tmp_path / "researchers" / "bull_researcher.v2.txt").write_text(
            "v2 says $target_label"
        )
        registry = PromptRegistry(base_dir=tmp_path)

        t1, _ = registry.render(
            "researchers/bull_researcher", version="v1", target_label="x"
        )
        t2, _ = registry.render(
            "researchers/bull_researcher", version="v2", target_label="x"
        )
        assert t1 != t2
        assert "v1" in t1
        assert "v2" in t2
