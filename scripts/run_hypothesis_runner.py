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
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

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
    # Validate id to prevent path traversal in worktree path
    if not re.fullmatch(r"[a-zA-Z0-9_\-]+", hid):
        print(f"  Skipping hypothesis with invalid id: {hid!r}", flush=True)
        return False
    branch = hyp["branch"]
    scanner = hyp["scanner"]
    worktree = f"/tmp/hyp-{hid}"

    print(f"\n── Hypothesis: {hid} ──", flush=True)

    run(["git", "fetch", "origin", branch], check=False)
    run(["git", "worktree", "add", worktree, branch])

    # Symlink .env from main repo into worktree so load_dotenv() finds it locally.
    # In CI, secrets are env vars already — the symlink is a no-op there.
    env_src = ROOT / ".env"
    env_dst = Path(worktree) / ".env"
    if env_src.exists() and not env_dst.exists():
        env_dst.symlink_to(env_src)

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


def llm_analysis(hyp: dict, conclusion: dict, scanner_domain: str) -> Optional[str]:
    """
    Ask Claude to interpret the experiment results and provide richer context.

    Returns a markdown string to embed in the PR comment, or None if the API
    call fails or ANTHROPIC_API_KEY is not set.

    The LLM does NOT override the programmatic decision — it adds nuance:
    sample-size caveats, market-condition context, follow-up hypotheses.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        import anthropic
    except ImportError:
        print("    anthropic SDK not installed, skipping LLM analysis", flush=True)
        return None

    hyp_metrics = conclusion["hypothesis"]
    base_metrics = conclusion["baseline"]
    decision = conclusion["decision"]

    prompt = f"""You are analyzing the results of a scanner hypothesis experiment for an automated trading discovery system.

## Hypothesis
**ID:** {hyp["id"]}
**Title:** {hyp.get("title", "")}
**Description:** {hyp.get("description", hyp.get("title", ""))}
**Scanner:** {hyp["scanner"]}
**Period:** {hyp.get("created_at")} → {TODAY} ({hyp.get("days_elapsed")} days)

## Statistical Results
**Decision (programmatic):** {decision}
**Reason:** {conclusion["reason"]}

| Metric | Baseline | Experiment | Delta |
|---|---|---|---|
| 7d win rate | {base_metrics.get("win_rate") or "—"}% | {hyp_metrics.get("win_rate") or "—"}% | {_delta_str(hyp_metrics.get("win_rate"), base_metrics.get("win_rate"), "pp")} |
| Avg 7d return | {base_metrics.get("avg_return") or "—"}% | {hyp_metrics.get("avg_return") or "—"}% | {_delta_str(hyp_metrics.get("avg_return"), base_metrics.get("avg_return"), "%")} |
| Picks evaluated | {base_metrics.get("evaluated", base_metrics.get("count", "—"))} | {hyp_metrics.get("evaluated", hyp_metrics.get("count", "—"))} | — |

## Scanner Domain Knowledge
{scanner_domain}

---

Provide a concise analysis (3–5 sentences) covering:
1. Whether the sample size is sufficient to trust the result, or if more data is needed
2. Any caveats about the measurement period (e.g., unusual market conditions)
3. What the numbers suggest about the underlying hypothesis — even if the decision is "rejected", is the direction meaningful?
4. One concrete follow-up hypothesis worth testing next

Be direct. Do not restate the numbers — interpret them. Do not recommend merging or closing the PR."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception as e:
        print(f"    LLM analysis failed: {e}", flush=True)
        return None


def _detect_baseline_drift(scanner: str, since: str) -> Optional[str]:
    """
    Check if the scanner's source file changed on main since the experiment started.

    Returns a warning string if drift is detected, None otherwise.

    When main's scanner code changes mid-experiment, the baseline picks in
    performance_database.json start reflecting the new code. The comparison
    becomes confounded: hypothesis vs. original-main for early picks, but
    hypothesis vs. new-main for later picks.
    """
    scanner_file = f"tradingagents/dataflows/discovery/scanners/{scanner}.py"
    result = subprocess.run(
        ["git", "log", "main", f"--since={since}", "--oneline", "--", scanner_file],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None

    commits = result.stdout.strip().splitlines()
    latest = commits[0]
    count = len(commits)
    noun = "commit" if count == 1 else "commits"
    warning = (
        f"`{scanner_file}` changed {count} {noun} on main since {since} "
        f"(latest: {latest}). Baseline picks may reflect the updated code — "
        f"interpret the delta with caution."
    )
    print(f"    ⚠️  Baseline drift: {warning}", flush=True)
    return warning


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

    # Detect if the scanner file changed on main since the experiment started.
    # If it did, the baseline picks (from main's daily runs) may no longer reflect
    # the original code — the comparison could be confounded.
    confound_warning = _detect_baseline_drift(scanner, hyp.get("created_at", TODAY))

    # Load scanner domain knowledge (may not exist yet — that's fine)
    scanner_domain_path = ROOT / "docs" / "iterations" / "scanners" / f"{scanner}.md"
    scanner_domain = scanner_domain_path.read_text() if scanner_domain_path.exists() else ""

    # Optional LLM analysis — enriches the conclusion without overriding the decision
    analysis = llm_analysis(hyp, conclusion, scanner_domain)
    analysis_section = f"\n\n## Analysis\n{analysis}" if analysis else ""

    confound_section = (
        f"\n\n> ⚠️ **Baseline drift detected:** {confound_warning}" if confound_warning else ""
    )

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
        f"## Decision\n{conclusion['reason']}\n"
        f"{confound_section}"
        f"{analysis_section}\n\n"
        f"## Action\n"
        f"{'Ready to merge — awaiting manual review.' if decision == 'accepted' else 'Experiment concluded — awaiting manual review before closing.'}\n"
    )

    run(["git", "add", str(concluded_doc)], check=False)

    pr = hyp.get("pr_number")
    if pr:
        # Mark PR ready for review (removes draft status) and post conclusion as a comment.
        # The PR is NOT merged or closed automatically — the user reviews and decides.
        outcome_emoji = "✅ accepted" if decision == "accepted" else "❌ rejected"
        analysis_block = f"\n\n**Analysis**\n{analysis}" if analysis else ""
        confound_block = (
            f"\n\n> ⚠️ **Baseline drift:** {confound_warning}" if confound_warning else ""
        )
        comment = (
            f"**Hypothesis concluded: {outcome_emoji}**\n\n"
            f"{conclusion['reason']}\n\n"
            f"| Metric | Baseline | Experiment |\n"
            f"|---|---|---|\n"
            f"| 7d win rate | {base_metrics.get('win_rate') or '—'}% | {hyp_metrics.get('win_rate') or '—'}% |\n"
            f"| Avg return | {base_metrics.get('avg_return') or '—'}% | {hyp_metrics.get('avg_return') or '—'}% |\n"
            f"{confound_block}"
            f"{analysis_block}\n\n"
            f"{'Merge this PR to apply the change.' if decision == 'accepted' else 'Close this PR to discard the experiment.'}"
        )
        subprocess.run(
            ["gh", "pr", "ready", str(pr)],
            cwd=str(ROOT),
            check=False,
        )
        subprocess.run(
            ["gh", "pr", "comment", str(pr), "--body", comment],
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
    # Skip weekends — markets are closed, picks would be noise and days_elapsed
    # would count non-trading days toward min_days.
    weekday = datetime.utcnow().weekday()  # 0=Mon … 6=Sun
    if weekday >= 5:
        day_name = "Saturday" if weekday == 5 else "Sunday"
        print(f"Skipping hypothesis runner — today is {day_name} (market closed).", flush=True)
        return

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
        run(["git", "worktree", "prune"], check=False)
        for hyp in running:
            try:
                run_hypothesis(hyp)
            except Exception as e:
                print(f"  Error processing {hyp['id']}: {e}", flush=True)

    promote_pending(registry)
    save_registry(registry)
    print("\nRegistry updated.", flush=True)


if __name__ == "__main__":
    main()
