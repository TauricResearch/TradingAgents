#!/usr/bin/env python3
"""
Hypothesis Runner — orchestrates daily experiment cycles.

For each running hypothesis in active.json:
  1. Creates a git worktree for the hypothesis branch
  2. Runs the daily discovery pipeline in that worktree
  3. Extracts picks from the discovery result, appends to picks.json
  4. Commits and pushes picks to hypothesis branch
  5. Removes worktree
  6. Updates active.json (days_elapsed, picks_log)
  7. If days_elapsed >= min_days: concludes the hypothesis

After all hypotheses: promotes highest-priority pending → running if a slot opened.

Environment variables:
  FILTER_ID — if set, only run the hypothesis with this ID
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ACTIVE_JSON = ROOT / "docs/iterations/hypotheses/active.json"
CONCLUDED_DIR = ROOT / "docs/iterations/hypotheses/concluded"
DB_PATH = ROOT / "data/recommendations/performance_database.json"
TODAY = datetime.utcnow().strftime("%Y-%m-%d")


def load_registry() -> dict:
    with open(ACTIVE_JSON) as f:
        return json.load(f)


def save_registry(registry: dict) -> None:
    with open(ACTIVE_JSON, "w") as f:
        json.dump(registry, f, indent=2)


def run(cmd: list, cwd: str = None, check: bool = True) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=cwd or str(ROOT), check=check, capture_output=False)


def extract_picks(worktree: str, scanner: str) -> list:
    """Extract picks for the given scanner from the most recent discovery result in the worktree."""
    results_dir = Path(worktree) / "results" / "discovery" / TODAY
    if not results_dir.exists():
        print(f"    No discovery results for {TODAY} in worktree", flush=True)
        return []
    picks = []
    for run_dir in sorted(results_dir.iterdir()):
        result_file = run_dir / "discovery_result.json"
        if not result_file.exists():
            continue
        try:
            with open(result_file) as f:
                data = json.load(f)
            for item in data.get("final_ranking", []):
                if item.get("strategy_match") == scanner:
                    picks.append(
                        {
                            "date": TODAY,
                            "ticker": item["ticker"],
                            "score": item.get("final_score"),
                            "confidence": item.get("confidence"),
                            "scanner": scanner,
                            "return_7d": None,
                            "win_7d": None,
                        }
                    )
        except Exception as e:
            print(f"    Warning: could not read {result_file}: {e}", flush=True)
    return picks


def load_picks_from_branch(hypothesis_id: str, branch: str) -> list:
    """Load picks.json from the hypothesis branch using git show."""
    picks_path = f"docs/iterations/hypotheses/{hypothesis_id}/picks.json"
    result = subprocess.run(
        ["git", "show", f"{branch}:{picks_path}"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout).get("picks", [])
    except Exception:
        return []


def save_picks_to_worktree(worktree: str, hypothesis_id: str, scanner: str, picks: list) -> None:
    """Write updated picks.json into the worktree and commit."""
    picks_dir = Path(worktree) / "docs" / "iterations" / "hypotheses" / hypothesis_id
    picks_dir.mkdir(parents=True, exist_ok=True)
    picks_file = picks_dir / "picks.json"
    payload = {"hypothesis_id": hypothesis_id, "scanner": scanner, "picks": picks}
    picks_file.write_text(json.dumps(payload, indent=2))
    run(["git", "add", str(picks_file)], cwd=worktree)
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=worktree)
    if result.returncode != 0:
        run(
            ["git", "commit", "-m", f"chore(hypotheses): picks {TODAY} for {hypothesis_id}"],
            cwd=worktree,
        )


def run_hypothesis(hyp: dict) -> bool:
    """Run one hypothesis experiment cycle. Returns True if the experiment concluded."""
    hid = hyp["id"]
    branch = hyp["branch"]
    scanner = hyp["scanner"]
    worktree = f"/tmp/hyp-{hid}"

    print(f"\n── Hypothesis: {hid} ──", flush=True)

    run(["git", "fetch", "origin", branch], check=False)
    run(["git", "worktree", "add", worktree, branch])

    try:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/run_daily_discovery.py",
                "--date",
                TODAY,
                "--no-update-positions",
            ],
            cwd=worktree,
            check=False,
        )
        if result.returncode != 0:
            print(f"    Discovery failed for {hid}, skipping picks update", flush=True)
        else:
            new_picks = extract_picks(worktree, scanner)
            existing_picks = load_picks_from_branch(hid, branch)
            seen = {(p["date"], p["ticker"]) for p in existing_picks}
            merged = existing_picks + [p for p in new_picks if (p["date"], p["ticker"]) not in seen]
            save_picks_to_worktree(worktree, hid, scanner, merged)
            run(["git", "push", "origin", f"HEAD:{branch}"], cwd=worktree)

            if TODAY not in hyp.get("picks_log", []):
                hyp.setdefault("picks_log", []).append(TODAY)
            hyp["days_elapsed"] = len(hyp["picks_log"])

            if hyp["days_elapsed"] >= hyp["min_days"]:
                return conclude_hypothesis(hyp)

    finally:
        run(["git", "worktree", "remove", "--force", worktree], check=False)

    return False


def conclude_hypothesis(hyp: dict) -> bool:
    """Run comparison, write conclusion doc, close/merge PR. Returns True."""
    hid = hyp["id"]
    scanner = hyp["scanner"]
    branch = hyp["branch"]

    print(f"\n  Concluding {hid}...", flush=True)

    picks = load_picks_from_branch(hid, branch)
    if not picks:
        conclusion = {
            "decision": "rejected",
            "reason": "No picks were collected during the experiment period",
            "hypothesis": {"count": 0, "evaluated": 0, "win_rate": None, "avg_return": None},
            "baseline": {"count": 0, "win_rate": None, "avg_return": None},
        }
    else:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/compare_hypothesis.py",
                "--hypothesis-id",
                hid,
                "--picks-json",
                json.dumps(picks),
                "--scanner",
                scanner,
                "--db-path",
                str(DB_PATH),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"    compare_hypothesis.py failed: {result.stderr}", flush=True)
            return False
        conclusion = json.loads(result.stdout)

    decision = conclusion["decision"]
    hyp_metrics = conclusion["hypothesis"]
    base_metrics = conclusion["baseline"]

    period_start = hyp.get("created_at", TODAY)
    concluded_doc = CONCLUDED_DIR / f"{TODAY}-{hid}.md"
    concluded_doc.write_text(
        f"# Hypothesis: {hyp['title']}\n\n"
        f"**Scanner:** {scanner}\n"
        f"**Branch:** {branch}\n"
        f"**Period:** {period_start} → {TODAY} ({hyp['days_elapsed']} days)\n"
        f"**Outcome:** {'accepted ✅' if decision == 'accepted' else 'rejected ❌'}\n\n"
        f"## Hypothesis\n{hyp.get('description', hyp['title'])}\n\n"
        f"## Results\n\n"
        f"| Metric | Baseline | Experiment | Delta |\n"
        f"|---|---|---|---|\n"
        f"| 7d win rate | {base_metrics.get('win_rate') or '—'}% | "
        f"{hyp_metrics.get('win_rate') or '—'}% | "
        f"{_delta_str(hyp_metrics.get('win_rate'), base_metrics.get('win_rate'), 'pp')} |\n"
        f"| Avg return | {base_metrics.get('avg_return') or '—'}% | "
        f"{hyp_metrics.get('avg_return') or '—'}% | "
        f"{_delta_str(hyp_metrics.get('avg_return'), base_metrics.get('avg_return'), '%')} |\n"
        f"| Picks | {base_metrics.get('count', '—')} | {hyp_metrics.get('count', '—')} | — |\n\n"
        f"## Decision\n{conclusion['reason']}\n\n"
        f"## Action\n"
        f"{'Branch merged into main.' if decision == 'accepted' else 'Branch closed without merging.'}\n"
    )

    run(["git", "add", str(concluded_doc)], check=False)

    pr = hyp.get("pr_number")
    if pr:
        if decision == "accepted":
            subprocess.run(
                ["gh", "pr", "merge", str(pr), "--squash", "--delete-branch"],
                cwd=str(ROOT),
                check=False,
            )
        else:
            subprocess.run(
                ["gh", "pr", "close", str(pr), "--delete-branch"],
                cwd=str(ROOT),
                check=False,
            )

    hyp["status"] = "concluded"
    hyp["conclusion"] = decision

    print(f"  {hid}: {decision} — {conclusion['reason']}", flush=True)
    return True


def _delta_str(hyp_val, base_val, unit: str) -> str:
    if hyp_val is None or base_val is None:
        return "—"
    delta = hyp_val - base_val
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.1f}{unit}"


def promote_pending(registry: dict) -> None:
    """Promote the highest-priority pending hypothesis to running if a slot is open."""
    running_count = sum(1 for h in registry["hypotheses"] if h["status"] == "running")
    max_active = registry.get("max_active", 5)
    if running_count >= max_active:
        return
    pending = [h for h in registry["hypotheses"] if h["status"] == "pending"]
    if not pending:
        return
    to_promote = max(pending, key=lambda h: h.get("priority", 0))
    to_promote["status"] = "running"
    print(f"\n  Promoted pending hypothesis to running: {to_promote['id']}", flush=True)


def main():
    registry = load_registry()
    filter_id = os.environ.get("FILTER_ID", "").strip()

    hypotheses = registry.get("hypotheses", [])
    running = [
        h
        for h in hypotheses
        if h["status"] == "running" and (not filter_id or h["id"] == filter_id)
    ]

    if not running:
        print("No running hypotheses to process.", flush=True)
    else:
        for hyp in running:
            run_hypothesis(hyp)

    promote_pending(registry)
    save_registry(registry)
    print("\nRegistry updated.", flush=True)


if __name__ == "__main__":
    main()
