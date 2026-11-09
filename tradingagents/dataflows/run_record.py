"""One immutable record per analysis, addressed by a unique run id (§2 of P4).

The audit already wrote a structured JSON per run, but named it after the
analysis date: `audit_2026-11-09.json`. Two analyses of the same instrument on
the same day therefore overwrote each other, and the lineage audit found exactly
that — the 14:05, 18:37 and 19:24 runs were gone, replaced by the 21:01 one.

Naming alone is not enough to make a run reproducible, because a name does not
say *which code* produced the file. Each record here carries the runtime
fingerprint (commit, build id, service start, interpreter and vendor versions),
the model configuration, the inputs it consumed and the verdicts it produced, so
a later reader can tell two runs apart and tell a re-run of the same code from a
run of different code.

Storage discipline
------------------
- **Never overwrite.** A run id is fixed at first write; `write_run` refuses to
  replace an existing record rather than silently losing the earlier one.
- **Retention.** Records are pruned oldest-first only when an explicit limit is
  configured, and pruning never touches the newest record for a ticker.
- **Redaction.** Anything that looks like a credential is removed before the
  file is written. Keys never belong in an audit, but a config dump is exactly
  where they would leak, so the filter is applied to the whole payload.
- **Bounded size.** Large agent reports are stored truncated with an explicit
  marker and their true length, so a runaway report cannot fill the disk while a
  reader still learns that it was truncated.
- **Owner-only permissions.** The directory and files are created `0o700` /
  `0o600`: an audit contains the caller's simulated positions and is not public.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import platform
import re
import secrets
import sys
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"

# How much of each agent report to keep. A full multi-thousand-line report per
# run, times many runs, is what fills a disk; the head is what a reader checks
# first, and the truncation is recorded rather than hidden.
DEFAULT_MAX_TEXT_CHARS = 20_000

# Field names whose values are secrets. Matched case-insensitively against the
# whole key, wherever it appears in the payload.
_SECRET_KEY = re.compile(
    r"(api[_-]?key|secret|token|password|passwd|credential|private[_-]?key"
    r"|access[_-]?key|session[_-]?id|cookie|authorization)",
    re.IGNORECASE,
)

# Value shapes that are obviously credentials even under an innocent key name.
_SECRET_VALUE = re.compile(
    r"^(sk-|pk_|ghp_|gho_|github_pat_|xox[baprs]-|AKIA|ASIA|eyJ)[A-Za-z0-9_\-\.]{8,}$"
)

REDACTED = "[REDACTED]"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def utc_stamp() -> str:
    """A filesystem-safe UTC timestamp, to the second."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def new_run_id(ticker: str) -> str:
    """A unique, sortable id for one analysis.

    Sortable by time, unique without coordination, and safe as a path
    component. The ticker is kept in the name so an operator can find a run
    without opening the file, and the random suffix is what guarantees two
    analyses in the same second cannot collide — the defect this replaces
    used the date, which made collisions the normal case.
    """
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", ticker).strip("-") or "unknown"
    return f"{utc_stamp()}-{safe}-{secrets.token_hex(4)}"


def redact(payload):
    """Strip credentials from a JSON-able structure, recursively.

    Applied to the *whole* record rather than to a known list of fields: a
    config dump is where a key would leak, and a filter that only knows today's
    field names would miss tomorrow's.
    """
    if isinstance(payload, dict):
        cleaned = {}
        for key, value in payload.items():
            if isinstance(key, str) and _SECRET_KEY.search(key):
                cleaned[key] = REDACTED
            else:
                cleaned[key] = redact(value)
        return cleaned
    if isinstance(payload, (list, tuple)):
        return [redact(item) for item in payload]
    if isinstance(payload, str):
        if _SECRET_VALUE.match(payload.strip()):
            return REDACTED
        return payload
    return payload


def _bounded(text, limit: int) -> dict:
    """A report as a bounded, self-describing value."""
    if text is None:
        return {"chars": 0, "truncated": False, "text": None}
    if not isinstance(text, str):
        text = str(text)
    if len(text) <= limit:
        return {"chars": len(text), "truncated": False, "text": text}
    return {
        "chars": len(text),
        "truncated": True,
        "kept_chars": limit,
        "text": text[:limit],
    }


@dataclass
class RunRecord:
    """Everything one analysis produced, in a single addressable document."""

    run_id: str
    ticker: str
    analysis_date: str
    created_at: str = field(default_factory=_utc_now)

    # Identity of the code and the process that produced the record.
    fingerprint: dict = field(default_factory=dict)
    # Model selection: which provider and models answered.
    model_config: dict = field(default_factory=dict)
    # What the run consumed: prices, portfolio, filings.
    inputs: dict = field(default_factory=dict)
    # SEC filings known at the analysis date (point-in-time).
    filings: list = field(default_factory=list)
    # The certified-metric registry, as it was serialized for the audit.
    metric_registry: dict = field(default_factory=dict)
    # What each agent said, bounded and marked when truncated.
    agents: dict = field(default_factory=dict)
    # The decision, the risk assessment and the gate's verdict.
    decision: dict = field(default_factory=dict)
    risk: dict = field(default_factory=dict)
    execution_gate: dict = field(default_factory=dict)
    # The full structured audit (the existing SCHEMA_VERSION document).
    audit: dict = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "ticker": self.ticker,
            "analysis_date": self.analysis_date,
            "created_at": self.created_at,
            "fingerprint": self.fingerprint,
            "model_config": self.model_config,
            "inputs": self.inputs,
            "filings": self.filings,
            "metric_registry": self.metric_registry,
            "agents": self.agents,
            "decision": self.decision,
            "risk": self.risk,
            "execution_gate": self.execution_gate,
            "audit": self.audit,
        }


def run_directory(results_dir: str | Path, ticker: str) -> Path:
    """Where a ticker's runs live, created owner-only."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", ticker).strip("-") or "unknown"
    directory = Path(results_dir) / safe / "runs"
    directory.mkdir(parents=True, exist_ok=True)
    # A filesystem without POSIX modes must not fail the run.
    with suppress(OSError):
        os.chmod(directory, 0o700)
    return directory


def write_run(results_dir: str | Path, record: RunRecord, *,
              max_text_chars: int = DEFAULT_MAX_TEXT_CHARS) -> Path:
    """Persist one run, never replacing an existing record.

    Returns the path written. Raises ``FileExistsError`` rather than
    overwriting: a duplicate id is a bug in id generation, and losing the
    earlier analysis silently is the failure this module exists to prevent.
    """
    directory = run_directory(results_dir, record.ticker)
    path = directory / f"{record.run_id}.json"

    payload = redact(record.to_dict())

    # The agents' texts are the only unbounded part; bound them here so the
    # writer does not depend on every caller remembering to.
    agents = payload.get("agents")
    if isinstance(agents, dict):
        payload["agents"] = {
            name: (_bounded(value, max_text_chars)
                   if isinstance(value, str) or value is None
                   else {"chars": None, "truncated": False, "text": value})
            for name, value in agents.items()
        }

    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL   # O_EXCL: never overwrite
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        logger.error("Refusing to overwrite run record %s", path)
        raise
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def read_run(path: str | Path) -> dict:
    """Read one run record."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def list_runs(results_dir: str | Path, ticker: str) -> list[Path]:
    """Every run record for a ticker, oldest first (the ids sort by time)."""
    directory = Path(results_dir) / re.sub(
        r"[^A-Za-z0-9._-]+", "-", ticker).strip("-") / "runs"
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"))


@dataclass(frozen=True)
class RetentionReport:
    """What a retention pass did, so pruning is auditable itself."""

    kept: int
    deleted: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {"kept": self.kept, "deleted": self.deleted}


def prune_runs(results_dir: str | Path, ticker: str, keep: int) -> RetentionReport:
    """Delete all but the newest ``keep`` records for a ticker.

    Only ever called with an explicit limit; nothing is pruned by default,
    because an audit trail that ages out without being asked is not a trail.
    The newest record is always kept even when ``keep`` is 0 or negative: a
    retention policy that can delete the only evidence of the latest analysis
    is not a policy an operator meant to set.
    """
    runs = list_runs(results_dir, ticker)
    keep = max(1, int(keep))
    if len(runs) <= keep:
        return RetentionReport(kept=len(runs))

    doomed = runs[:-keep]
    deleted = []
    for path in doomed:
        try:
            path.unlink()
            deleted.append(path.name)
        except OSError:
            logger.warning("Could not prune run record %s", path, exc_info=True)
    return RetentionReport(kept=len(runs) - len(deleted), deleted=deleted)


# ---------------------------------------------------------------------------
# Runtime fingerprint (§3)
# ---------------------------------------------------------------------------


def runtime_fingerprint() -> dict:
    """What code and process this run executed under.

    Deliberately free of filesystem paths, environment values and versions of
    packages that would reveal a deployment's internals: a commit, a build id
    and an interpreter version identify a build without describing a host.
    """
    from tradingagents.build_info import LOADED_AT, commit_sha

    return {
        "commit": commit_sha(),
        "build_id": build_id(),
        "service_started_at": LOADED_AT,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}."
                  f"{sys.version_info.micro}",
        "implementation": platform.python_implementation(),
        "validators": validator_status(),
    }


def build_id() -> str:
    """A build identifier: the short commit plus the code-load timestamp.

    The commit alone cannot distinguish "restarted after the merge" from
    "still running the pre-merge process", which is precisely the question the
    lineage audit could not answer. Pairing it with the moment this process
    imported its code can.
    """
    from tradingagents.build_info import LOADED_AT, commit_sha

    return f"{commit_sha()}@{LOADED_AT}"


def validator_status() -> dict:
    """Whether the deterministic components are actually loaded and callable.

    This is the check the audit asked for by name: modules that import cleanly
    but are never called look identical to modules that work. Reporting the
    import *and* the presence of the expected callables makes a broken wiring
    visible from the service itself.

    Each entry names a module and the callables a working build must expose.
    The check imports the module directly rather than reading attributes off a
    package namespace: ``math`` re-exports a curated subset, so probing the
    package for a submodule reports a false negative for modules that are
    present and working.
    """
    checks = {
        "math_precision": ("tradingagents.dataflows.math.precision",
                           ("as_decimal", "quantize", "pct_change")),
        "math_valuation": ("tradingagents.dataflows.math.valuation",
                           ("earnings_per_share", "price_to_book")),
        "math_technical": ("tradingagents.dataflows.math.technical",
                           ("relative_strength_index", "average_true_range",
                            "bollinger_bands")),
        "metric_registry": ("tradingagents.dataflows.math.registry",
                            ("MetricRegistry",)),
        "math_extraction": ("tradingagents.dataflows.math.extraction",
                            ("extract_run_inputs",)),
        "risk_engine": ("tradingagents.dataflows.risk_engine",
                        ("size_position", "size_with_exposure_cap",
                         "validate_stop")),
        "execution_gate": ("tradingagents.dataflows.execution_gate",
                           ("evaluate_plan", "ExecutionGate")),
        "gate_integration": ("tradingagents.dataflows.gate_integration",
                             ("evaluate_decision",)),
        "arithmetic_guard": ("tradingagents.dataflows.arithmetic",
                             ("check_stated_percentage",
                              "check_price_timestamp_alignment")),
    }
    status = {}
    for name, (module_name, attributes) in checks.items():
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 — an import failure is the finding
            status[name] = {"loaded": False, "error": type(exc).__name__}
            continue
        missing = [attr for attr in attributes if not hasattr(module, attr)]
        status[name] = {"loaded": not missing, "missing": missing}
    return status


def model_config(config: dict) -> dict:
    """The model selection of a run, with anything secret removed.

    Kept separate from the fingerprint: which models answered is part of what
    makes a run reproducible, but it is not a property of the build.
    """
    keys = ("llm_provider", "deep_think_llm", "quick_think_llm",
            "backend_url", "llm_temperature", "google_thinking_level",
            "openai_reasoning_effort", "anthropic_effort", "agent_max_retries")
    return redact({key: config.get(key) for key in keys})
