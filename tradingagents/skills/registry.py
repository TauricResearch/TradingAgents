"""Validate and progressively load the bundled research-methodology skills.

This module intentionally is *not* a plugin or tool registry.  A skill is a
reviewable local Markdown document and may only influence the system prompt of
the role explicitly mapped below.  It cannot add tools, code, network access,
or change graph topology.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from tradingagents.observability.context import current_observation_context
from tradingagents.observability.provenance import current_provenance_observer
from tradingagents.skills.artifacts import (
    PublicArtifact,
    artifact_schema_for_role,
)

logger = logging.getLogger(__name__)

_SKILL_NAME = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_MAX_SKILL_BYTES = 32 * 1024
_MAX_FRONTMATTER_BYTES = 8 * 1024
_ALLOWED_FRONTMATTER_KEYS = frozenset(
    {"name", "description", "roles", "triggers", "output_schema"}
)
_KNOWN_ROLES = frozenset(
    {
        "fundamentals_analyst",
        "news_analyst",
        "market_analyst",
        "sentiment_analyst",
        "bull_researcher",
        "bear_researcher",
        "portfolio_manager",
    }
)

# This is deliberately code-owned.  YAML analyst presets may choose and order
# analyst *roles*, but they must not activate arbitrary skill text.
ROLE_SKILL_NAMES: Mapping[str, tuple[str, ...]] = {
    "fundamentals_analyst": (
        "financial-statement-analyzer",
        "juglar-cycle-stock-stage",
    ),
    "news_analyst": (
        "serenity-alpha",
        "event-driven-detector",
        "sector-rotation-detector",
    ),
    "market_analyst": ("market-regime-and-health",),
    "sentiment_analyst": ("sentiment-reality-gap",),
    "bull_researcher": (
        "bayesian-intrinsic-growth-valuation",
        "tam-adj-peg",
    ),
    "bear_researcher": (
        "bayesian-intrinsic-growth-valuation",
        "tam-adj-peg",
    ),
    "portfolio_manager": ("buy-side-equity-research-memo",),
}

# These rules are deliberately code-owned just like ``ROLE_SKILL_NAMES``.
# A document's human-readable frontmatter explains *why* it is useful, but it
# must not become executable selection logic merely because somebody edits
# Markdown.  The input is an already-present request/report string; matching
# it can select only an allow-listed body and cannot create a tool, prompt, or
# skill name.
ROLE_SKILL_TRIGGER_PATTERNS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "fundamentals_analyst": {
        "financial-statement-analyzer": (
            "financial", "statement", "revenue", "earnings", "profit", "cash flow",
            "cashflow", "debt", "balance sheet", "governance", "财务", "利润", "现金流",
            "资产负债", "债务", "治理",
        ),
        "juglar-cycle-stock-stage": (
            "cycle", "macro", "industry", "sector", "china", "policy", "inventory",
            "capacity", "周期", "宏观", "行业", "政策", "库存", "产能",
        ),
    },
    "news_analyst": {
        "serenity-alpha": (
            "news", "catalyst", "guidance", "demand", "cost", "thesis", "headline",
            "新闻", "催化", "指引", "需求", "成本", "标题",
        ),
        "event-driven-detector": (
            "event", "buyback", "filing", "regulatory", "shareholder", "acquisition",
            "merger", "contract", "restructuring", "lock-up", "事件", "回购", "公告",
            "监管", "股东", "并购", "合同", "重组", "解禁",
        ),
        "sector-rotation-detector": (
            "macro", "sector", "industry", "rotation", "policy", "commodity", "leadership",
            "宏观", "板块", "行业", "轮动", "政策", "商品",
        ),
    },
    "market_analyst": {
        "market-regime-and-health": (
            "price", "volume", "technical", "trend", "volatility", "indicator", "ohlcv",
            "价格", "成交量", "技术", "趋势", "波动", "指标",
        ),
    },
    "sentiment_analyst": {
        "sentiment-reality-gap": (
            "sentiment", "narrative", "social", "retail", "news", "情绪", "叙事", "社交",
            "散户", "新闻",
        ),
    },
    "bull_researcher": {
        "bayesian-intrinsic-growth-valuation": (
            "growth", "valuation", "earnings", "margin", "prior", "增长", "估值", "盈利", "利润率",
        ),
        "tam-adj-peg": (
            "tam", "market size", "runway", "peg", "execution", "市场规模", "空间", "执行",
        ),
    },
    "bear_researcher": {
        "bayesian-intrinsic-growth-valuation": (
            "growth", "valuation", "earnings", "margin", "prior", "增长", "估值", "盈利", "利润率",
        ),
        "tam-adj-peg": (
            "tam", "market size", "runway", "peg", "execution", "市场规模", "空间", "执行",
        ),
    },
    "portfolio_manager": {
        "buy-side-equity-research-memo": (
            "decision", "portfolio", "risk", "scenario", "catalyst", "monitor", "投资组合", "风险",
            "情景", "催化", "跟踪", "决策",
        ),
    },
}

_MAX_SELECTED_SKILLS = 3


class SkillValidationError(ValueError):
    """Raised when a bundled skill is malformed or escapes its library."""


@dataclass(frozen=True)
class SkillFrontmatter:
    name: str
    description: str
    roles: tuple[str, ...]
    triggers: tuple[str, ...]
    output_schema: tuple[str, ...]


@dataclass(frozen=True)
class LoadedSkill:
    frontmatter: SkillFrontmatter
    body: str
    source: Path


@dataclass(frozen=True)
class MethodologyArtifact:
    """Static, non-private record of the methodology contract for one role.

    This is deliberately metadata rather than model reasoning.  Consumers may
    persist or display it without treating it as an explanation of how a model
    arrived at an individual conclusion.
    """

    role: str
    skill_names: tuple[str, ...]
    required_output_fields: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "skill_names": list(self.skill_names),
            "required_output_fields": list(self.required_output_fields),
        }


class SkillRegistry:
    """Read only validated skills below one trusted ``library`` directory."""

    def __init__(self, library_dir: str | Path | None = None) -> None:
        self.library_dir = (
            Path(library_dir).resolve()
            if library_dir is not None
            else Path(__file__).with_name("library").resolve()
        )

    def summaries_for_role(self, role: str) -> tuple[SkillFrontmatter, ...]:
        """Return compact frontmatter for the statically approved role skills."""
        return tuple(self.load_frontmatter(name) for name in self.names_for_role(role))

    def load_for_role(self, role: str) -> tuple[LoadedSkill, ...]:
        """Load full methodology text only for the statically approved role."""
        return tuple(self.load(name) for name in self.names_for_role(role))

    def methodology_artifact(
        self,
        role: str,
        *,
        trigger_text: str | None = None,
        max_skills: int = 1,
    ) -> MethodologyArtifact:
        """Return selected public output expectations without model rationale.

        The artifact records only the methodology bodies that the deterministic
        selection gate admitted for this turn.  It intentionally excludes the
        request text, full prompts, drafts, and model reasoning.
        """
        skills = self.select_for_role(
            role, trigger_text=trigger_text, max_skills=max_skills
        )
        fields = tuple(
            field
            for skill in skills
            for field in skill.frontmatter.output_schema
        )
        return MethodologyArtifact(
            role=role,
            skill_names=tuple(skill.frontmatter.name for skill in skills),
            required_output_fields=fields,
        )

    def report_artifact_schema(self, role: str) -> type[PublicArtifact]:
        """Return the code-owned Pydantic schema for a role's public scorecard.

        A skill's frontmatter remains documentation-level metadata.  The
        executable validation boundary is this explicit role mapping, which
        prevents a Markdown edit or user preset from redefining persisted
        report fields.
        """
        self.names_for_role(role)  # preserve the same role authorization gate
        return artifact_schema_for_role(role)

    def names_for_role(self, role: str) -> tuple[str, ...]:
        try:
            return ROLE_SKILL_NAMES[role]
        except KeyError as exc:
            raise SkillValidationError(f"unknown skill role: {role}") from exc

    def select_for_role(
        self,
        role: str,
        *,
        trigger_text: str | None,
        max_skills: int = 1,
    ) -> tuple[LoadedSkill, ...]:
        """Select at most three approved bodies using deterministic terms.

        All role-approved frontmatter remains visible as an index.  Full
        Markdown is loaded into a system prompt only after a code-owned rule
        matches the already available, public task context.  No user text can
        name an arbitrary file or bypass ``ROLE_SKILL_NAMES``.
        """
        if not isinstance(max_skills, int) or not 1 <= max_skills <= _MAX_SELECTED_SKILLS:
            raise ValueError(f"max_skills must be between 1 and {_MAX_SELECTED_SKILLS}")
        allowed_names = self.names_for_role(role)
        patterns = ROLE_SKILL_TRIGGER_PATTERNS.get(role, {})
        normalized = _normalize_trigger_text(trigger_text)
        selected_names = tuple(
            name
            for name in allowed_names
            if any(term in normalized for term in patterns.get(name, ()))
        )[:max_skills]
        return tuple(self.load(name) for name in selected_names)

    def load(self, name: str) -> LoadedSkill:
        source = self._checked_source(name)
        try:
            text = source.read_text(encoding="utf-8")
        except OSError as exc:
            raise SkillValidationError(f"cannot read skill {name}: {exc.strerror}") from exc
        frontmatter, body = _split_frontmatter(text, source)
        validated = _validate_frontmatter(frontmatter, source)
        if validated.name != name:
            raise SkillValidationError(
                f"skill {source} frontmatter name must match directory name {name}"
            )
        return LoadedSkill(validated, body, source)

    def load_frontmatter(self, name: str) -> SkillFrontmatter:
        """Read the bounded YAML index without loading a Markdown body."""
        source = self._checked_source(name)
        raw = _read_frontmatter_only(source)
        validated = _validate_frontmatter(raw, source)
        if validated.name != name:
            raise SkillValidationError(
                f"skill {source} frontmatter name must match directory name {name}"
            )
        return validated

    def _checked_source(self, name: str) -> Path:
        if not isinstance(name, str) or not _SKILL_NAME.fullmatch(name):
            raise SkillValidationError("skill name is invalid")
        source = self._source_for_name(name)
        try:
            if source.is_symlink():
                raise SkillValidationError(f"skill {name} must not be a symlink")
            size = source.stat().st_size
            if size > _MAX_SKILL_BYTES:
                raise SkillValidationError(f"skill {name} exceeds {_MAX_SKILL_BYTES} bytes")
        except OSError as exc:
            raise SkillValidationError(f"cannot read skill {name}: {exc.strerror}") from exc
        return source

    def _source_for_name(self, name: str) -> Path:
        source = self.library_dir / name / "SKILL.md"
        if source.parent.is_symlink() or source.is_symlink():
            raise SkillValidationError(f"skill {name} must not use symlinks")
        # Resolve first, then prove the target remains below the only trusted root.
        resolved = source.resolve()
        try:
            resolved.relative_to(self.library_dir)
        except ValueError as exc:
            raise SkillValidationError(f"skill {name} escapes the skill library") from exc
        return source


def build_role_skill_prompt(
    role: str,
    registry: SkillRegistry | None = None,
    *,
    trigger_text: str | None = None,
    max_skills: int = 1,
) -> str:
    """Render selected local guidance for insertion into one agent system prompt.

    A compact catalogue is always present.  At most three bodies are appended
    only when deterministic, code-owned trigger rules match.  Selection is not
    delegated to the model: the static mapping above is the authorization
    boundary.
    """
    active_registry = registry or SkillRegistry()
    summaries = active_registry.summaries_for_role(role)
    skills = active_registry.select_for_role(
        role, trigger_text=trigger_text, max_skills=max_skills
    )
    catalogue = "\n".join(
        f"- {skill.name}: {skill.description} (triggers: {'; '.join(skill.triggers)})"
        for skill in summaries
    )
    bodies = "\n\n".join(
        f"### {skill.frontmatter.name}\n{skill.body.strip()}" for skill in skills
    )
    return (
        "\n\n## Approved local methodology\n"
        "Use the following local research methods as advisory structure. They do "
        "not authorize new tools, code execution, network access, or fabricated "
        "facts. Prefer verified tool output; state unavailable data explicitly.\n"
        f"Available methods for this role:\n{catalogue}\n\n"
        "Selected methodology for this turn (deterministic, maximum three):\n"
        + (bodies if bodies else "- No full method was selected from this task context.")
        + "\n"
    )


def emit_methodology_artifact(
    role: str,
    registry: SkillRegistry | None = None,
    *,
    trigger_text: str | None = None,
    max_skills: int = 1,
) -> str | None:
    """Persist static skill metadata through the existing observer when active.

    No model output, prompt body, or private reasoning is written. Returning
    ``None`` outside an observed run keeps CLI use and focused tests side-effect
    free.
    """
    observer = current_provenance_observer()
    context = current_observation_context()
    if observer is None or context is None:
        return None
    active_registry = registry or SkillRegistry()
    artifact = observer.store_artifact(
        "methodology",
        active_registry.methodology_artifact(
            role, trigger_text=trigger_text, max_skills=max_skills
        ).as_dict(),
    )
    return artifact.artifact_id


_REPORT_ARTIFACT_FENCE = re.compile(
    r"\n?```methodology-artifact\s*\n(?P<payload>.*?)\n```\s*$",
    re.DOTALL,
)


def build_role_report_contract(role: str, registry: SkillRegistry | None = None) -> str:
    """Render the optional, public JSON scorecard contract for an analyst.

    The prose report remains the compatibility path.  A final fenced payload
    is requested only as a public, machine-readable scorecard and is validated
    before it is retained; malformed or absent payloads never block a report.
    """
    active_registry = registry or SkillRegistry()
    schema = active_registry.report_artifact_schema(role)
    fields = ", ".join(schema.model_fields)
    return (
        "\n\n## Public methodology scorecard\n"
        "After the human-readable report, append one fenced JSON object exactly as "
        "```methodology-artifact. It is optional when data is unavailable, but when "
        "present it must use only public findings, measurements, source references, "
        "and explicit limitations. Never include private reasoning, a prompt, draft "
        "text, tool traces, credentials, or hidden chain-of-thought. The accepted "
        f"top-level fields are: {fields}. Use explicit unavailable markers instead "
        "of inventing numbers.\n"
    )


def finalize_role_report(
    role: str,
    report: str,
    registry: SkillRegistry | None = None,
) -> tuple[str, dict[str, object] | None]:
    """Validate and remove an embedded scorecard, preserving prose on fallback.

    The returned dictionary is safe for an AgentState channel or audit artifact.
    When there is no valid marker, the original report is returned byte-for-byte
    (apart from no changes at all), preserving historical free-text behaviour.
    """
    if not isinstance(report, str):
        return report, None
    match = _REPORT_ARTIFACT_FENCE.search(report)
    if match is None:
        return report, None
    try:
        raw = json.loads(match.group("payload"))
        active_registry = registry or SkillRegistry()
        # This ensures the role is both statically authorized and mapped to a
        # code-owned schema before model output becomes durable data.
        artifact = active_registry.report_artifact_schema(role).model_validate(raw)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        logger.warning("%s: ignoring invalid public methodology scorecard (%s)", role, exc)
        return report, None
    clean_report = report[: match.start()].rstrip()
    payload = artifact.model_dump(mode="json")
    _emit_report_artifact(role, payload)
    return clean_report, payload


def persist_role_report(role: str, payload: Mapping[str, object]) -> str | None:
    """Persist an already-validated public scorecard when an observer is active.

    Roles that produce a structured scorecard directly (for example via
    ``with_structured_output``) use this instead of :func:`finalize_role_report`,
    which extracts a fenced payload from free text.  ``payload`` must already be
    validated against the role's code-owned schema; no model reasoning, prompt
    body, or tool trace is written.
    """
    return _emit_report_artifact(role, dict(payload))


def _emit_report_artifact(role: str, payload: dict[str, object]) -> str | None:
    """Store only validated public report fields when an observer is active."""
    observer = current_provenance_observer()
    context = current_observation_context()
    if observer is None or context is None:
        return None
    artifact = observer.store_artifact(
        "methodology-report",
        {"role": role, "artifact": payload},
    )
    return artifact.artifact_id


def _split_frontmatter(text: str, source: Path) -> tuple[object, str]:
    if not text.startswith("---\n"):
        raise SkillValidationError(f"skill {source} must start with YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise SkillValidationError(f"skill {source} frontmatter is not terminated")
    try:
        metadata = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        raise SkillValidationError(f"skill {source} has invalid YAML: {exc}") from exc
    body = text[end + len("\n---\n") :].strip()
    if not body:
        raise SkillValidationError(f"skill {source} needs a non-empty Markdown body")
    return metadata, body


def _read_frontmatter_only(source: Path) -> object:
    """Parse only the bounded YAML header from a trusted skill file."""
    try:
        with source.open(encoding="utf-8") as handle:
            if handle.readline() != "---\n":
                raise SkillValidationError(f"skill {source} must start with YAML frontmatter")
            lines: list[str] = []
            total = 0
            for line in handle:
                total += len(line.encode("utf-8"))
                if total > _MAX_FRONTMATTER_BYTES:
                    raise SkillValidationError(
                        f"skill {source} frontmatter exceeds {_MAX_FRONTMATTER_BYTES} bytes"
                    )
                if line == "---\n":
                    break
                lines.append(line)
            else:
                raise SkillValidationError(f"skill {source} frontmatter is not terminated")
    except OSError as exc:
        raise SkillValidationError(f"cannot read skill frontmatter {source}: {exc.strerror}") from exc
    try:
        return yaml.safe_load("".join(lines))
    except yaml.YAMLError as exc:
        raise SkillValidationError(f"skill {source} has invalid YAML: {exc}") from exc


def _validate_frontmatter(raw: object, source: Path) -> SkillFrontmatter:
    if not isinstance(raw, dict):
        raise SkillValidationError(f"skill {source} frontmatter must be a mapping")
    unknown = sorted(set(raw) - _ALLOWED_FRONTMATTER_KEYS)
    if unknown:
        raise SkillValidationError(
            f"skill {source} has unsupported frontmatter keys: {', '.join(unknown)}"
        )
    name = raw.get("name")
    description = raw.get("description")
    roles = _string_list(raw.get("roles"), "roles", source)
    triggers = _string_list(raw.get("triggers"), "triggers", source)
    output_schema = _string_list(raw.get("output_schema"), "output_schema", source)
    if not isinstance(name, str) or not _SKILL_NAME.fullmatch(name):
        raise SkillValidationError(f"skill {source} has an invalid name")
    if not isinstance(description, str) or not description.strip() or len(description) > 280:
        raise SkillValidationError(f"skill {source} needs a concise description")
    unknown_roles = sorted(set(roles) - _KNOWN_ROLES)
    if unknown_roles:
        raise SkillValidationError(
            f"skill {source} has unknown roles: {', '.join(unknown_roles)}"
        )
    return SkillFrontmatter(
        name=name,
        description=description.strip(),
        roles=roles,
        triggers=triggers,
        output_schema=output_schema,
    )


def _string_list(value: object, field: str, source: Path) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise SkillValidationError(f"skill {source} needs a non-empty {field} list")
    result = tuple(item.strip() for item in value)
    if len(set(result)) != len(result):
        raise SkillValidationError(f"skill {source} has duplicate {field} entries")
    return result


def build_skill_trigger_context(*values: object, limit: int = 12000) -> str:
    """Extract bounded public text for deterministic selection only.

    This function does not persist its input and deliberately keeps no prompt
    or chain-of-thought record.  It accepts the already visible user request,
    reports, or debate summaries in a state object and turns them into a
    bounded lexical selection input.
    """
    if not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    parts: list[str] = []
    for value in values:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                content = getattr(item, "content", item)
                if isinstance(content, str):
                    parts.append(content)
    return "\n".join(parts)[:limit]


def _normalize_trigger_text(value: str | None) -> str:
    return value.casefold() if isinstance(value, str) else ""


def iter_bundled_skills(registry: SkillRegistry | None = None) -> Iterable[LoadedSkill]:
    """Yield all statically referenced skills once, for validation and tests."""
    active_registry = registry or SkillRegistry()
    seen: set[str] = set()
    for names in ROLE_SKILL_NAMES.values():
        for name in names:
            if name not in seen:
                seen.add(name)
                yield active_registry.load(name)
