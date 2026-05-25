"""Trace replay + verification tool (T1.7).

This is the capstone of Phase 1. Given a trace file produced by
:class:`TraceCallback` (T1.2) and routed through the hash chain
(T1.3), the replayer answers four audit questions:

1. **Is this file the one we wrote?** — verify_chain() walks the SHA-256
   chain. T1.3 already does this; we surface it here as part of the
   replay flow.
2. **Are the prompts still the ones that produced this trace?** —
   verify_prompts() looks up every recorded prompt_key + prompt_version
   in the live registry and compares the resulting template hash to
   the one recorded in the trace. A mismatch means someone edited a
   prompt file after the run was logged. Detected without re-running
   the LLM.
3. **What actually happened in this run?** — summary() builds a
   high-level view: number of LLM calls, tool calls, nodes visited,
   total wall time, fingerprints seen.
4. **What was the call tree?** — tree() reconstructs the
   parent_record_id graph so a reviewer can see "tool X was called
   inside LLM Y inside graph node Z".

What the replayer does NOT do (yet)
-----------------------------------
**Re-execute the LLM**. Sending the recorded prompts back to a live
model and diff'ing the new response against the recorded one is a
useful audit step ("response is reproducible under temperature=0
+seed") but it costs API calls and requires the same model snapshot
to still be available. That capability ships in T3.4's drift
monitoring loop, where it belongs — it's an ongoing-monitoring task,
not a one-shot replay artefact.

CLI usage
---------
::

    python -m tradingagents.audit.replay verify <path>
    python -m tradingagents.audit.replay summary <path>
    python -m tradingagents.audit.replay prompts <path>
    python -m tradingagents.audit.replay tree <path>

All commands accept ``--json`` for machine-readable output and
``--registry-dir <path>`` to override the prompt template lookup
(useful for replaying against an older repo checkout).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tradingagents.audit.ledger import VerifyResult, verify_ledger
from tradingagents.audit.prompt_registry import (
    PromptNotFoundError,
    PromptRegistry,
    default_registry,
)


# -------------------------------------------------------------------- #
# Result types
# -------------------------------------------------------------------- #


@dataclass
class PromptVerification:
    """One LLM call's prompt-provenance check.

    A row says: "the LLM_START record at ``record_id`` claimed to use
    template ``prompt_key`` version ``prompt_version`` with hash
    ``recorded_hash``. Looking up that template in the current registry
    yields ``current_hash``. If they match, the on-disk template is
    still the one that produced this trace."
    """
    record_id: str
    node: Optional[str]
    prompt_key: str
    prompt_version: str
    recorded_hash: str
    current_hash: Optional[str]
    matches: bool
    template_missing: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReplaySummary:
    """High-level statistics computed from one trace file."""
    session_id: Optional[str]
    total_records: int
    llm_calls: int  # paired LLM_START events
    tool_calls: int  # paired TOOL_START events
    nodes_visited: List[str]
    fingerprints_seen: List[str]
    models_seen: List[str]
    first_ts: Optional[str]
    last_ts: Optional[str]
    wall_seconds: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# -------------------------------------------------------------------- #
# Replayer
# -------------------------------------------------------------------- #


class Replayer:
    """Load a trace file and answer audit questions about it.

    ``prompt_registry`` may be supplied to point at a different prompts
    directory than the package default — useful for replaying a trace
    against an older repo checkout where the templates differ.
    """

    def __init__(
        self,
        path: Path,
        *,
        prompt_registry: Optional[PromptRegistry] = None,
    ) -> None:
        self.path = Path(path).expanduser()
        self.registry = prompt_registry or default_registry()
        self._records: Optional[List[Dict[str, Any]]] = None  # lazy

    # ------------------------------------------------------------------ #
    # Lazy load
    # ------------------------------------------------------------------ #

    def records(self) -> List[Dict[str, Any]]:
        """Read all records from disk. Parsed lazily; cached after first call."""
        if self._records is not None:
            return self._records
        if not self.path.is_file():
            raise FileNotFoundError(f"trace file not found: {self.path}")
        out: List[Dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                # We intentionally don't raise here — a single bad line
                # shouldn't block reading the rest of the trace, and
                # verify_chain() will flag the corruption separately.
                continue
        self._records = out
        return out

    # ------------------------------------------------------------------ #
    # Verification
    # ------------------------------------------------------------------ #

    def verify_chain(self) -> VerifyResult:
        """Delegate to T1.3's chain walker."""
        return verify_ledger(self.path)

    def verify_prompts(self) -> List[PromptVerification]:
        """For each LLM_START with prompt metadata, compare recorded hash
        to the current registry's hash.

        Returns an empty list when there are no LLM_START records that
        carry prompt provenance — that's a T1.4-disabled session, not
        an audit failure.

        Mismatch is what we're looking for: a recorded ``prompt_hash``
        that no longer equals the on-disk template's hash means
        someone edited the template after this run was logged. In a
        compliant pipeline this should never happen — prompt
        versioning (T1.4) requires shipping a ``vN+1`` file rather
        than mutating ``vN``.

        Handles two metadata shapes:

        - **Single-template** (most agents): ``prompt_key``,
          ``prompt_version``, ``prompt_hash`` all together. One row.
        - **Trader** (two-template): ``prompt_key="trader/messages"``
          but ``prompt_hash_system`` and ``prompt_hash_user`` carried
          separately. Emits one row per side so a mismatch localises
          to the offending file.
        """
        out: List[PromptVerification] = []
        for rec in self.records():
            if rec.get("type") != "llm_start":
                continue
            md = (rec.get("payload") or {}).get("metadata") or {}
            key = md.get("prompt_key")
            if not key:
                # T1.4 provenance not recorded — pre-T1.4 trace or an
                # un-migrated agent (the 4 analysts). Not a failure;
                # just nothing to verify.
                continue

            # Single-template path: a top-level prompt_hash is present.
            recorded_hash = md.get("prompt_hash")
            version = md.get("prompt_version", "v1")
            if recorded_hash:
                out.append(self._check_one(
                    rec, key=key, version=version, recorded_hash=recorded_hash,
                ))

            # Trader two-template path: emit one verification per side,
            # keyed by trader/trader_{system,user}. The recorded
            # ``prompt_version`` looks like ``"system=v1,user=v1"`` so
            # we parse it to recover each side's version.
            for side in ("system", "user"):
                side_hash = md.get(f"prompt_hash_{side}")
                if not side_hash:
                    continue
                side_version = _parse_trader_version(version, side)
                out.append(self._check_one(
                    rec,
                    key=f"trader/trader_{side}",
                    version=side_version,
                    recorded_hash=side_hash,
                ))
        return out

    def _check_one(
        self,
        rec: Dict[str, Any],
        *,
        key: str,
        version: str,
        recorded_hash: str,
    ) -> PromptVerification:
        """Look up one (key, version) in the registry and build a row."""
        try:
            _, current_hash = self.registry.load(key, version)
            missing = False
        except PromptNotFoundError:
            current_hash = None
            missing = True
        return PromptVerification(
            record_id=rec.get("record_id", ""),
            node=rec.get("node"),
            prompt_key=key,
            prompt_version=version,
            recorded_hash=recorded_hash,
            current_hash=current_hash,
            matches=(not missing) and current_hash == recorded_hash,
            template_missing=missing,
        )

    # ------------------------------------------------------------------ #
    # Summary
    # ------------------------------------------------------------------ #

    def summary(self) -> ReplaySummary:
        recs = self.records()
        session_ids = {r.get("session_id") for r in recs if r.get("session_id")}
        # All records in one file share a session_id; if multiple appear,
        # the file was concatenated from multiple sessions. We report
        # the first one we see and let the caller decide whether that's
        # a problem.
        session_id = next(iter(session_ids), None)

        llm_calls = sum(1 for r in recs if r.get("type") == "llm_start")
        tool_calls = sum(1 for r in recs if r.get("type") == "tool_start")

        nodes_seen: List[str] = []
        for r in recs:
            node = r.get("node")
            if node and node not in nodes_seen:
                nodes_seen.append(node)

        fingerprints: List[str] = []
        models: List[str] = []
        for r in recs:
            if r.get("type") != "llm_end":
                continue
            payload = r.get("payload") or {}
            llm_output = (payload.get("response") or {}).get("llm_output") or {}
            fp = llm_output.get("system_fingerprint")
            model = llm_output.get("model_name") or llm_output.get("model")
            if fp and fp not in fingerprints:
                fingerprints.append(fp)
            if model and model not in models:
                models.append(model)

        timestamps = sorted(r.get("ts", "") for r in recs if r.get("ts"))
        first_ts = timestamps[0] if timestamps else None
        last_ts = timestamps[-1] if timestamps else None
        wall_seconds = None
        if first_ts and last_ts:
            try:
                start = _parse_iso(first_ts)
                end = _parse_iso(last_ts)
                wall_seconds = (end - start).total_seconds()
            except ValueError:
                pass

        return ReplaySummary(
            session_id=session_id,
            total_records=len(recs),
            llm_calls=llm_calls,
            tool_calls=tool_calls,
            nodes_visited=nodes_seen,
            fingerprints_seen=fingerprints,
            models_seen=models,
            first_ts=first_ts,
            last_ts=last_ts,
            wall_seconds=wall_seconds,
        )

    # ------------------------------------------------------------------ #
    # Call tree
    # ------------------------------------------------------------------ #

    def tree(self) -> List[Dict[str, Any]]:
        """Reconstruct the call hierarchy from ``parent_record_id`` links.

        Returns a list of root nodes; each node is a dict with
        ``record_id``, ``type``, ``node``, ``ts``, and ``children`` (a
        list of nested dicts in the same shape).
        """
        recs = self.records()
        by_id: Dict[str, Dict[str, Any]] = {}
        for r in recs:
            rid = r.get("record_id")
            if not rid:
                continue
            by_id[rid] = {
                "record_id": rid,
                "type": r.get("type"),
                "node": r.get("node"),
                "ts": r.get("ts"),
                "children": [],
            }

        roots: List[Dict[str, Any]] = []
        for r in recs:
            rid = r.get("record_id")
            if not rid or rid not in by_id:
                continue
            parent_id = r.get("parent_record_id")
            if parent_id and parent_id in by_id:
                by_id[parent_id]["children"].append(by_id[rid])
            else:
                roots.append(by_id[rid])
        return roots


# -------------------------------------------------------------------- #
# Helpers
# -------------------------------------------------------------------- #


def _parse_iso(s: str) -> datetime:
    """Parse a timestamp accepting both ``Z`` and ``+00:00`` suffixes."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _parse_trader_version(composite: str, side: str) -> str:
    """Pull ``vN`` for one side out of trader's composite version string.

    Trader records ``prompt_version`` as e.g. ``"system=v1,user=v2"``.
    Falls back to ``"v1"`` if the format is unrecognised.
    """
    for part in composite.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip() == side:
                return v.strip()
    return "v1"


def _print_summary(summary: ReplaySummary, json_out: bool) -> None:
    if json_out:
        print(json.dumps(summary.to_dict(), indent=2, default=str))
        return
    print(f"Session ID:       {summary.session_id}")
    print(f"Total records:    {summary.total_records}")
    print(f"LLM calls:        {summary.llm_calls}")
    print(f"Tool calls:       {summary.tool_calls}")
    print(f"Nodes visited:    {', '.join(summary.nodes_visited) or '(none)'}")
    print(f"Models seen:      {', '.join(summary.models_seen) or '(none)'}")
    print(f"Fingerprints:     {', '.join(summary.fingerprints_seen) or '(none)'}")
    print(f"First event:      {summary.first_ts}")
    print(f"Last event:       {summary.last_ts}")
    if summary.wall_seconds is not None:
        print(f"Wall clock:       {summary.wall_seconds:.1f}s")


def _print_verify(result: VerifyResult, json_out: bool) -> None:
    if json_out:
        print(json.dumps(asdict(result), indent=2))
        return
    status = "OK" if result.ok else "BROKEN"
    print(f"Chain status:     {status}")
    print(f"Format:           {result.format}")
    print(f"Total records:    {result.total_records}")
    if result.broken_lines:
        print(f"Broken lines:     {result.broken_lines}")


def _print_prompts(checks: List[PromptVerification], json_out: bool) -> None:
    if json_out:
        print(json.dumps([c.to_dict() for c in checks], indent=2))
        return
    if not checks:
        print("(no prompt-provenance records in this trace)")
        return
    matching = sum(1 for c in checks if c.matches)
    print(f"Prompt checks: {matching}/{len(checks)} match the current registry")
    print()
    for c in checks:
        flag = "OK" if c.matches else ("MISSING" if c.template_missing else "MISMATCH")
        print(f"  [{flag:8}] {c.prompt_key}@{c.prompt_version}  node={c.node or '-'}")
        if not c.matches:
            print(f"             recorded: {c.recorded_hash}")
            print(f"             current:  {c.current_hash}")


def _print_tree(roots: List[Dict[str, Any]], json_out: bool) -> None:
    if json_out:
        print(json.dumps(roots, indent=2, default=str))
        return

    def _walk(node: Dict[str, Any], depth: int) -> None:
        indent = "  " * depth
        label = f"[{node['type']}]"
        if node.get("node"):
            label += f" {node['node']}"
        print(f"{indent}{label}  ({node['ts']})")
        for child in node.get("children", []):
            _walk(child, depth + 1)

    for r in roots:
        _walk(r, 0)


# -------------------------------------------------------------------- #
# CLI
# -------------------------------------------------------------------- #


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tradingagents.audit.replay",
        description="Verify and inspect TradingAgents trace files.",
    )
    parser.add_argument(
        "command",
        choices=["verify", "summary", "prompts", "tree"],
        help="What to do with the trace file.",
    )
    parser.add_argument("path", help="Path to the trace JSONL file.")
    parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON instead of human-readable output.",
    )
    parser.add_argument(
        "--registry-dir", default=None,
        help="Override prompt template directory (default: packaged prompts).",
    )
    args = parser.parse_args(argv)

    if args.registry_dir:
        registry = PromptRegistry(base_dir=Path(args.registry_dir))
    else:
        registry = default_registry()

    replayer = Replayer(Path(args.path), prompt_registry=registry)

    if args.command == "verify":
        result = replayer.verify_chain()
        _print_verify(result, args.json)
        return 0 if result.ok else 1

    if args.command == "summary":
        summary = replayer.summary()
        _print_summary(summary, args.json)
        return 0

    if args.command == "prompts":
        checks = replayer.verify_prompts()
        _print_prompts(checks, args.json)
        # Exit non-zero if any prompt drifted
        if any(not c.matches for c in checks):
            return 1
        return 0

    if args.command == "tree":
        roots = replayer.tree()
        _print_tree(roots, args.json)
        return 0

    return 2  # unreachable


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
