"""Live GOV-004 replay runner.

Executes the five fixed cases through the real application boundary
(``run_analysis_api``) with the configured live model, and records auditable
per-case evidence.

Design constraints (see the task and docs/verification/semantic-evaluation.md):

* Application code is not modified. The harness only *uses* public seams:
  ``run_analysis_api``, ``freeze_explicit``/``confirm`` and a LangChain callback
  that observes model input. The news challenge cases swap the vendor function
  in-process; nothing in ``tradingagents/`` or ``cli/`` changes.
* No secrets and no raw prompts are persisted. The evidence record keeps prompt
  *counts*, challenge *marker presence*, digests and lengths -- never bodies.
* Incomplete runs and exposure failures are retained, not dropped.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cases import Case
from langchain_core.callbacks import BaseCallbackHandler

from tradingagents.runapi.execution import run_analysis_api
from tradingagents.runapi.input_service import freeze_explicit

# A conservative creds scrub applied to the evidence record as a last line of
# defence: even though the runner never stores prompts, identifiers or secrets
# could still appear in an exception message. Patterns mirror the app Redactor.
_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)api[_-]?key['\"\s:=]+[A-Za-z0-9_\-]{8,}"),
)


def _scrub(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


class PromptCapture(BaseCallbackHandler):
    """Records the *shape* of each model call, never its body.

    ``on_chat_model_start``/``on_llm_start`` fire once per model invocation.
    We keep a per-call fingerprint (sha256 of the concatenated prompt), the
    total character length, the message count, and which challenge markers the
    prompt contained. This is enough to prove a challenge reached model input
    without storing the raw prompt.
    """

    def __init__(self, markers: tuple[str, ...] = ()):
        super().__init__()
        self.markers = markers
        self.calls: list[dict[str, Any]] = []
        self._marker_hits: dict[str, int] = dict.fromkeys(markers, 0)

    def _record(self, texts: list[str]) -> None:
        joined = "\n\n".join(texts)
        digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
        hits = {marker: joined.count(marker) for marker in self.markers}
        for marker, count in hits.items():
            self._marker_hits[marker] += count
        self.calls.append({
            "prompt_sha256": digest,
            "prompt_chars": len(joined),
            "messages": len(texts),
            "marker_hits": hits,
        })

    def on_chat_model_start(self, serialized, messages, **kwargs):  # noqa: D401
        texts: list[str] = []
        for batch in messages:
            for message in batch:
                content = getattr(message, "content", "")
                if isinstance(content, list):
                    text = " ".join(
                        part.get("text", "") if isinstance(part, dict) else str(part)
                        for part in content
                    )
                else:
                    text = str(content)
                texts.append(text)
        self._record(texts)

    def on_llm_start(self, serialized, prompts, **kwargs):
        self._record([str(prompt) for prompt in prompts])

    def summary(self) -> dict[str, Any]:
        return {
            "model_calls": len(self.calls),
            "prompt_chars_total": sum(call["prompt_chars"] for call in self.calls),
            # Distinct prompt digests let a reader confirm the calls differed,
            # without exposing any body.
            "distinct_prompt_digests": sorted({call["prompt_sha256"] for call in self.calls}),
            "marker_hits_total": dict(self._marker_hits),
            "marker_reached_model": {
                marker: hits > 0 for marker, hits in self._marker_hits.items()
            },
        }


@dataclass
class CaseOutcome:
    case_id: str
    description: str
    portfolio_kind: str
    run_id: str | None
    source_revision: str
    model_config: dict[str, Any]
    outcome: str
    stop_reason: str | None
    final_rating: str | None
    output_check: str | None
    findings: list[dict[str, Any]]
    report_path: str | None
    manifest_path: str | None
    run_dir: str | None
    challenge_marker: str | None
    challenge_reached_model: bool | None
    prompt_capture: dict[str, Any]
    wall_clock_s: float
    error: str | None = None
    notes: list[str] = field(default_factory=list)


def _model_config_from_env() -> dict[str, Any]:
    """The supplied live configuration, read from the environment.

    Records only *safe* identifiers (provider, model IDs, whether a backend URL
    is set) -- never the URL itself with embedded credentials, never a key.
    """
    backend = os.getenv("TRADINGAGENTS_LLM_BACKEND_URL")
    backend_host = None
    if backend:
        match = re.match(r"https?://([^/]+)", backend)
        backend_host = match.group(1) if match else "<unparsed>"
    return {
        "llm_provider": os.getenv("TRADINGAGENTS_LLM_PROVIDER"),
        "deep_think_llm": os.getenv("TRADINGAGENTS_DEEP_THINK_LLM"),
        "quick_think_llm": os.getenv("TRADINGAGENTS_QUICK_THINK_LLM"),
        "backend_host": backend_host,
        "analysts": ["market", "social", "news", "fundamentals"],
        "max_debate_rounds": int(os.getenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "1")),
        "max_risk_discuss_rounds": int(os.getenv("TRADINGAGENTS_MAX_RISK_ROUNDS", "1")),
    }


def _live_config(results_dir: str) -> dict[str, Any]:
    from tradingagents.default_config import DEFAULT_CONFIG

    config = dict(DEFAULT_CONFIG)
    config["llm_provider"] = os.getenv("TRADINGAGENTS_LLM_PROVIDER")
    config["deep_think_llm"] = os.getenv("TRADINGAGENTS_DEEP_THINK_LLM")
    config["quick_think_llm"] = os.getenv("TRADINGAGENTS_QUICK_THINK_LLM")
    backend = os.getenv("TRADINGAGENTS_LLM_BACKEND_URL")
    if backend:
        config["backend_url"] = backend
    config["max_debate_rounds"] = int(os.getenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "1"))
    config["max_risk_discuss_rounds"] = int(os.getenv("TRADINGAGENTS_MAX_RISK_ROUNDS", "1"))
    config["output_language"] = os.getenv("TRADINGAGENTS_OUTPUT_LANGUAGE", "English")
    config["checkpoint_enabled"] = False
    config["results_dir"] = results_dir
    return config


class _InjectedNewsRouter:
    """Context manager replacing the news vendor with a synthetic item.

    Installed only around the challenge cases' engine execution. ``get_news``
    and ``get_global_news`` return the injected body so the analyst reads it as
    news; every other vendor method behaves normally (real live data). The
    original routing is restored on exit, so no application module is edited.
    """

    def __init__(self, news_body: str):
        self.news_body = news_body
        self._router = None
        self._original = None

    def __enter__(self):
        from tradingagents.dataflows import router as router_module
        self._router = router_module
        self._original = router_module.route_to_vendor

        original = self._original
        body = self.news_body

        def patched(method, *args, **kwargs):
            if method in ("get_news", "get_global_news"):
                return f"## Synthetic news item\n\n{body}\n"
            return original(method, *args, **kwargs)

        # The tools import the name directly; patch both the module attribute
        # and the already-bound references in the tools namespace.
        router_module.route_to_vendor = patched
        import tradingagents.agents.tools as tools_module
        self._patched_targets = []
        for name in ("route_to_vendor",):
            if hasattr(tools_module, name):
                self._patched_targets.append((tools_module, name, getattr(tools_module, name)))
                setattr(tools_module, name, patched)
        return self

    def __exit__(self, exc_type, exc, tb):
        self._router.route_to_vendor = self._original
        for module, name, value in getattr(self, "_patched_targets", []):
            setattr(module, name, value)
        return False


def run_case(case: Case, *, results_dir: str, ticker: str, analysis_date: str) -> CaseOutcome:
    """Execute one fixed case live and return an auditable record."""
    model_config = _model_config_from_env()
    revision = _source_revision()
    capture = PromptCapture(markers=(case.challenge_marker,) if case.challenge_marker else ())
    config = _live_config(results_dir)
    analysts = list(model_config["analysts"])
    config["selected_analysts"] = analysts

    context = freeze_explicit(ticker, analysis_date, case.portfolio).confirm()
    started = time.monotonic()
    error: str | None = None
    result = None
    try:
        # The vendor override wraps only the engine run inside run_analysis_api.
        # We achieve that by patching around the call; the analysts fire inside.
        if case.injected_news:
            with _InjectedNewsRouter(case.injected_news):
                result = run_analysis_api(
                    context, config=config,
                    selected_analysts=config["selected_analysts"],
                    callbacks=[capture],
                )
        else:
            result = run_analysis_api(
                context, config=config,
                selected_analysts=config["selected_analysts"],
                callbacks=[capture],
            )
    except BaseException as exc:  # retain exposure/engine failures, never drop them
        error = _scrub(f"{type(exc).__name__}: {exc}")
    wall = time.monotonic() - started

    capture_summary = capture.summary()
    if result is None:
        return CaseOutcome(
            case_id=case.case_id, description=case.description,
            portfolio_kind=case.portfolio_kind, run_id=context.run_id,
            source_revision=revision, model_config=model_config,
            outcome="ERROR", stop_reason=None, final_rating=None, output_check=None,
            findings=[], report_path=None, manifest_path=None, run_dir=None,
            challenge_marker=case.challenge_marker,
            challenge_reached_model=(
                capture_summary["marker_reached_model"].get(case.challenge_marker)
                if case.challenge_marker else None),
            prompt_capture=capture_summary, wall_clock_s=round(wall, 1),
            error=error, notes=["Exposure failure: exception escaped the harness call."],
        )

    reached = None
    if case.challenge_marker:
        reached = bool(capture_summary["marker_reached_model"].get(case.challenge_marker))
    run_dir = str(Path(result.manifest_path).parent) if result.manifest_path else None
    notes: list[str] = []
    if case.challenge_marker and reached is False:
        notes.append("Challenge text did NOT reach model input; case cannot pass.")
    if result.run_outcome != "COMPLETED":
        notes.append("Incomplete run retained in the summary.")
    return CaseOutcome(
        case_id=case.case_id, description=case.description,
        portfolio_kind=case.portfolio_kind, run_id=result.run_id,
        source_revision=revision, model_config=model_config,
        outcome=result.run_outcome, stop_reason=result.stop_reason,
        final_rating=result.final_rating, output_check=result.output_check,
        findings=[f.as_dict() if hasattr(f, "as_dict") else dict(f) for f in result.findings],
        report_path=result.report_path, manifest_path=result.manifest_path,
        run_dir=run_dir, challenge_marker=case.challenge_marker,
        challenge_reached_model=reached, prompt_capture=capture_summary,
        wall_clock_s=round(wall, 1), error=error, notes=notes,
    )


def _source_revision() -> str:
    try:
        import subprocess
        root = Path(__file__).resolve().parents[2]
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root,
                             capture_output=True, text=True, timeout=2, check=True)
        status = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                                capture_output=True, text=True, timeout=2, check=True)
        dirty = "+dirty" if status.stdout.strip() else ""
        return f"git:{out.stdout.strip()}{dirty}"
    except Exception:
        return "unknown"


def outcome_to_dict(outcome: CaseOutcome) -> dict[str, Any]:
    return asdict(outcome)
