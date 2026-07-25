from __future__ import annotations

import inspect
from dataclasses import dataclass

import pytest

import tradingagents.agents.analysts.fundamentals_analyst as fundamentals_analyst
import tradingagents.agents.analysts.market_analyst as market_analyst
import tradingagents.agents.analysts.news_analyst as news_analyst
import tradingagents.agents.analysts.sentiment_analyst as sentiment_analyst
import tradingagents.agents.managers.portfolio_manager as portfolio_manager
import tradingagents.agents.researchers.bear_researcher as bear_researcher
import tradingagents.agents.researchers.bull_researcher as bull_researcher
from tradingagents.observability.context import ObservationContext, observation_scope
from tradingagents.observability.provenance import provenance_scope
from tradingagents.skills.registry import (
    ROLE_SKILL_NAMES,
    ROLE_SKILL_TRIGGER_PATTERNS,
    SkillRegistry,
    SkillValidationError,
    build_role_skill_prompt,
    build_skill_trigger_context,
    emit_methodology_artifact,
    iter_bundled_skills,
)

pytestmark = pytest.mark.unit


def _write_skill(library, name: str, frontmatter: str, body: str = "Use verified facts."):
    skill_dir = library / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\n{frontmatter}\n---\n{body}\n", encoding="utf-8"
    )


def test_all_statically_mapped_bundled_skills_validate():
    registry = SkillRegistry()
    loaded = tuple(iter_bundled_skills(registry))

    assert {skill.frontmatter.name for skill in loaded} == {
        name for names in ROLE_SKILL_NAMES.values() for name in names
    }
    assert all(skill.body for skill in loaded)


def test_frontmatter_index_does_not_load_markdown_body(monkeypatch):
    registry = SkillRegistry()

    def fail_if_body_is_loaded(_name):
        raise AssertionError("frontmatter index must not load a skill body")

    monkeypatch.setattr(registry, "load", fail_if_body_is_loaded)

    summaries = registry.summaries_for_role("fundamentals_analyst")

    assert [summary.name for summary in summaries] == [
        "financial-statement-analyzer",
        "juglar-cycle-stock-stage",
    ]


def test_prompt_keeps_role_index_but_loads_only_one_triggered_body():
    prompt = build_role_skill_prompt(
        "fundamentals_analyst",
        trigger_text="请审查 revenue, cash flow 和 debt。",
    )

    assert "financial-statement-analyzer" in prompt
    assert "juglar-cycle-stock-stage" in prompt
    assert "Reconcile revenue, operating profit" in prompt
    assert "Separate observed facts from the cycle interpretation" not in prompt
    assert "serenity-alpha" not in prompt
    assert "do not authorize new tools" in prompt


def test_trigger_selection_is_static_bounded_and_can_select_nothing():
    registry = SkillRegistry()

    selected = registry.select_for_role(
        "fundamentals_analyst",
        trigger_text="financial cycle macro 财务 周期",
        max_skills=1,
    )
    assert [skill.frontmatter.name for skill in selected] == [
        "financial-statement-analyzer"
    ]
    assert registry.select_for_role(
        "fundamentals_analyst", trigger_text="unrelated words", max_skills=3
    ) == ()
    with pytest.raises(ValueError, match="between 1 and 3"):
        registry.select_for_role(
            "fundamentals_analyst", trigger_text="financial", max_skills=4
        )


def test_trigger_rules_remain_code_owned_and_within_static_allowlist():
    assert set(ROLE_SKILL_TRIGGER_PATTERNS) == set(ROLE_SKILL_NAMES)
    assert all(
        set(patterns).issubset(ROLE_SKILL_NAMES[role])
        for role, patterns in ROLE_SKILL_TRIGGER_PATTERNS.items()
    )
    assert build_skill_trigger_context("first", ["second"], limit=9) == "first\nsec"


def test_methodology_artifact_contains_only_selected_contract_metadata():
    artifact = SkillRegistry().methodology_artifact(
        "portfolio_manager", trigger_text="final portfolio decision risk scenario"
    )

    assert artifact.as_dict() == {
        "role": "portfolio_manager",
        "skill_names": ["buy-side-equity-research-memo"],
        "required_output_fields": [
            "thesis",
            "scenarios",
            "reverse_case",
            "catalysts",
            "monitoring",
        ],
    }


@dataclass(frozen=True)
class _StoredArtifact:
    artifact_id: str


class _ArtifactObserver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, str]] = []

    def store_artifact(self, kind, value, *, media_type="application/json"):
        self.calls.append((kind, value, media_type))
        return _StoredArtifact("artifact_methodology")


def test_methodology_artifact_uses_existing_observer_only_when_context_is_active():
    observer = _ArtifactObserver()
    context = ObservationContext(
        run_id="run_1",
        actor_id="manager.portfolio",
        node_id="Portfolio Manager",
        role_instance_id="run_1:manager.portfolio",
        turn_id="turn_1",
        graph_task_id="task_1",
        graph_step=1,
    )

    assert emit_methodology_artifact(
        "portfolio_manager", trigger_text="portfolio decision"
    ) is None
    with observation_scope(context), provenance_scope(observer):
        assert (
            emit_methodology_artifact(
                "portfolio_manager", trigger_text="portfolio decision"
            )
            == "artifact_methodology"
        )

    assert observer.calls == [
        (
            "methodology",
            {
                "role": "portfolio_manager",
                "skill_names": ["buy-side-equity-research-memo"],
                "required_output_fields": [
                    "thesis",
                    "scenarios",
                    "reverse_case",
                    "catalysts",
                    "monitoring",
                ],
            },
            "application/json",
        )
    ]


@pytest.mark.parametrize(
    "module, role",
    [
        (fundamentals_analyst, "fundamentals_analyst"),
        (news_analyst, "news_analyst"),
        (market_analyst, "market_analyst"),
        (sentiment_analyst, "sentiment_analyst"),
        (bull_researcher, "bull_researcher"),
        (bear_researcher, "bear_researcher"),
        (portfolio_manager, "portfolio_manager"),
    ],
)
def test_analyst_prompts_use_only_their_static_skill_mapping(module, role):
    source = inspect.getsource(module)
    assert "build_role_skill_prompt" in source
    assert f'"{role}"' in source


def test_unknown_role_is_rejected_without_loading_arbitrary_skill():
    with pytest.raises(SkillValidationError, match="unknown skill role"):
        SkillRegistry().load_for_role("../../anything")


@pytest.mark.parametrize(
    "frontmatter, message",
    [
        (
            "name: test-skill\ndescription: x\nroles: [market_analyst]\n"
            "triggers: [a]\noutput_schema: [b]\nextra: value",
            "unsupported frontmatter keys",
        ),
        (
            "name: another-name\ndescription: x\nroles: [market_analyst]\n"
            "triggers: [a]\noutput_schema: [b]",
            "must match directory name",
        ),
        (
            "name: test-skill\ndescription: x\nroles: [unknown_role]\n"
            "triggers: [a]\noutput_schema: [b]",
            "unknown roles",
        ),
    ],
)
def test_registry_rejects_unsafe_or_incomplete_frontmatter(tmp_path, frontmatter, message):
    library = tmp_path / "library"
    _write_skill(library, "test-skill", frontmatter)

    with pytest.raises(SkillValidationError, match=message):
        SkillRegistry(library).load("test-skill")


def test_registry_rejects_symlinked_skill(tmp_path):
    library = tmp_path / "library"
    source = tmp_path / "outside"
    _write_skill(
        source,
        "test-skill",
        "name: test-skill\ndescription: x\nroles: [market_analyst]\n"
        "triggers: [a]\noutput_schema: [b]",
    )
    library.mkdir()
    (library / "test-skill").symlink_to(source / "test-skill", target_is_directory=True)

    with pytest.raises(SkillValidationError, match="symlinks"):
        SkillRegistry(library).load("test-skill")
