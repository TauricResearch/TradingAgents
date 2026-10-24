"""Verify a completed Koral Equities source-only AI dry-run audit folder.

This tool is intentionally a READ-ONLY consistency audit. It never opens a
paper portfolio, connects to a broker or calls any model/vendor. It validates
archived file integrity and that a diagnostic TradeIntent was never approved.

SHA-256 hashes in a locally generated manifest are NOT digital signatures or
proof of an exchange-certified price, an issuer-confirmed earnings date or AI
correctness. A malicious actor who rewrites both a file and manifest can fake
an internally consistent folder; these checks catch accidental/local changes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

SCHEMA = "koral-real-market-dry-run-v1"
CLASSIFICATIONS = frozenset({
    "RETROSPECTIVE_SOURCE_AUDIT_NOT_FORWARD_RESEARCH",
    "SAME_SESSION_REAL_AI_DRY_RUN_NOT_FORWARD_TRADE",
    "SAME_SESSION_NO_ELIGIBLE_AI_BLOCKED_NO_TRADE",
    "SAME_SESSION_MARKET_SOURCE_AUDIT_ONLY",
})
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(source: str, root: Path) -> Path:
    """No absolute paths, parent hops, Windows drives or symlink escapes."""
    if not isinstance(source, str) or "\\" in source or ":" in source:
        raise ValueError("Audit file path is not canonical POSIX relative")
    pure = PurePosixPath(source)
    if (not source or pure.is_absolute() or ".." in pure.parts or
            pure.as_posix() != source or source.startswith(".")):
        raise ValueError("Audit file path is unsafe")
    path = root.joinpath(*pure.parts)
    if not path.resolve().is_relative_to(root) or path.is_symlink():
        raise ValueError("Audit source escapes its folder or is a symlink")
    return path


def audit(folder: Path) -> dict:
    root = folder.expanduser().resolve()
    portfolio = (Path.home() / ".tradingagents" / "paper").resolve()
    if root == portfolio or portfolio in root.parents:
        raise ValueError("Dry-run audit must not inspect paper account files")
    manifest_path = root / "DRY_RUN_MANIFEST.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("Dry-run manifest missing or unsafe")
    raw = manifest_path.read_bytes()
    if len(raw) > 3_000_000:
        raise ValueError("Unexpectedly large manifest")
    man = json.loads(raw)
    if not isinstance(man, dict) or man.get("schema") != SCHEMA:
        raise ValueError("Unknown dry-run manifest schema")
    if man.get("mode") != "NO_ORDERS" or man.get("classification") not in CLASSIFICATIONS:
        raise ValueError("Manifest is not a recognised read-only research run")
    if (man.get("account_reads") != 0 or man.get("account_writes") != 0 or
            man.get("paper_orders_created") != 0 or
            man.get("broker_connected") is not False):
        raise ValueError("Dry-run claims account access, order creation or broker connection")
    if man.get("source_vendor") != "YAHOO_SECONDARY_NOT_EXCHANGE_CERTIFIED":
        raise ValueError("Missing secondary-source provenance")
    listed = man.get("audit_files_sha256")
    origins = man.get("source_hashes")
    if not isinstance(listed, dict) or not isinstance(origins, dict):
        raise ValueError("Missing audit inventory or original source hashes")
    if not listed or len(listed) > 500:
        raise ValueError("Invalid audit inventory size")
    if not origins.get("original_sources/market.json"):
        raise ValueError("No independently copied market observation")
    if not set(origins).issubset(listed):
        raise ValueError("Original sources absent from complete audit inventory")
    if any(name not in {"original_sources/market.json", "original_sources/preclose.json"}
           for name in origins):
        raise ValueError("Unrecognised original-source inventory")

    actual_files: set[str] = set()
    for entry in root.rglob("*"):
        if entry.is_symlink():
            raise ValueError("Symlink found in archived dry run")
        if entry.is_file() and entry != manifest_path:
            actual_files.add(entry.relative_to(root).as_posix())
    if actual_files != set(listed):
        raise ValueError("Audit inventory missing or contains unexpected files")
    for name, expected in listed.items():
        if not isinstance(expected, str) or not _SHA256.fullmatch(expected):
            raise ValueError("Invalid SHA-256 digest in audit manifest")
        source = _relative(name, root)
        if not source.is_file() or _digest(source) != expected:
            raise ValueError(f"Archived evidence hash mismatch: {name}")
    for name, expected in origins.items():
        if not isinstance(expected, str) or listed.get(name) != expected:
            raise ValueError(f"Original source does not match archive: {name}")

    research = man.get("research")
    if not isinstance(research, dict):
        raise ValueError("No research results in dry-run manifest")
    receipts = 0
    diagnostics = 0
    for ticker, row in research.items():
        if not isinstance(ticker, str) or not isinstance(row, dict):
            raise ValueError("Invalid ticker/research record")
        receipt = row.get("ai_receipt")
        plan = row.get("conditional_plan")
        if plan is not None and receipt is None:
            raise ValueError("Conditional plan has no research receipt")
        if receipt is not None:
            if not isinstance(receipt, dict):
                raise ValueError("Malformed model receipt")
            saved = receipt.get("source_file")
            digest = receipt.get("source_sha256")
            if not isinstance(saved, str) or not isinstance(digest, str):
                raise ValueError("Model source receipt missing hash or file")
            source = _relative(saved.replace("\\", "/"), root)
            if (saved.replace("\\", "/") not in listed or
                    not _SHA256.fullmatch(digest) or not source.is_file() or
                    _digest(source) != digest):
                raise ValueError(f"Model source receipt hash mismatch: {ticker}")
            receipts += 1
        if plan is not None:
            if not isinstance(plan, dict) or plan.get("approved") is not False or plan.get("submitted") is not False:
                raise ValueError("Diagnostic plan incorrectly reports approval/submission")
            if plan.get("report_sha256") != receipt.get("source_sha256"):
                raise ValueError("Trade plan does not match original research")
            if row.get("reason") != "CONDITIONAL_PLAN_DIAGNOSTIC_ONLY":
                raise ValueError("Plan is not classified as diagnostic-only")
            diagnostics += 1
    return {
        "status": "SOURCE_INTEGRITY_AUDIT_PASSED",
        "session": man.get("session"),
        "classification": man["classification"],
        "files_verified": len(listed),
        "original_sources_verified": len(origins),
        "model_receipts_verified": receipts,
        "diagnostic_plans_verified": diagnostics,
        "paper_orders": 0,
        "warning": "Local hashes are not independent signatures, vendor certification, or proof of investment edge",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="koral-equities-dry-run-audit",
        description="Read-only verification of a saved market/AI research folder; no broker or orders",
    )
    parser.add_argument("--folder", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.folder)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"SOURCE AUDIT BLOCKED: {type(exc).__name__}: {exc}")
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
