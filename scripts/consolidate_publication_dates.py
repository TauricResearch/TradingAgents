#!/usr/bin/env python3
"""Fold one published analysis date into another and prune unusable runs.

For the two dates, every (ticker, model) pair keeps only its newest run that
has a numeric Portfolio Manager price target; older runs and runs without a
target are removed from the published site. The source date's homepage
section is folded into the target date, ticker hubs relabel kept source-date
runs, and the sitemap drops removed pages. publication-date-merges.json
records the merge, as for earlier merges.

With --prune-local, matching run folders under docs/ move to
.tradingagents/pruned-reports/ so a later publish_site.sh run cannot re-add
them. Nothing is deleted locally.

Usage:
  python scripts/consolidate_publication_dates.py --source-date 2026-10-01 \
      --target-date 2026-10-03 [--prune-local] [--push]

Without --push the result is only written to _site for review. --push fetches
origin/gh-pages first, then publishes one commit whose only deletions are the
pruned run folders.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bs4 import BeautifulSoup, Tag  # noqa: E402

from cli.report_fields import extract_price_target  # noqa: E402
from scripts import (  # noqa: E402
    build_publish_site as publish,
    build_reports_site as site,
    published_history as history,
)
from scripts.report_workflow import WorkflowError  # noqa: E402

DOCS = ROOT / "docs"
PRUNED = ROOT / ".tradingagents" / "pruned-reports"
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def slug(date: str) -> str:
    return site.normalize_analysis_date(date).replace("-", "")


def run_key(folder: str) -> tuple[str, str, str] | None:
    """(date slug, model, run stamp) for a timestamped run folder."""
    m = site.RUN_DIR_RE.match(folder)
    if not m or not m["run_date"]:
        return None
    return m["date"], m["model"], m["run_date"] + m["run_time"]


def published_target(report: Path) -> float | None:
    """Numeric target from the Portfolio Manager section of a compiled report."""
    article = BeautifulSoup(report.read_text(encoding="utf-8"), "html.parser").select_one("article")
    if article is None:
        return None
    heading = next(
        (h for h in article.find_all("h2") if "Portfolio Manager Decision" in h.get_text()), None
    )
    if heading is None:
        return None
    lines = [
        el.get_text(" ", strip=True)
        for el in heading.find_all_next(["p", "li", "td", "th", "h3", "h4"])
    ]
    return extract_price_target("\n".join(lines))


def local_target(run_dir: Path) -> float | None:
    try:
        return extract_price_target((run_dir / "5_portfolio" / "decision.md").read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return None


def choose(runs: dict[str, dict]) -> set[str]:
    """Run ids (ticker/folder) to keep: newest run with a target per pair."""
    best: dict[tuple[str, str], tuple[str, str]] = {}
    for run_id, info in runs.items():
        if info["target"] is None:
            continue
        pair = (info["ticker"], info["model"])
        if pair not in best or info["stamp"] > best[pair][0]:
            best[pair] = (info["stamp"], run_id)
    return {run_id for _, run_id in best.values()}


def collect(base: Path, dates: set[str], target_fn) -> dict[str, dict]:
    runs = {}
    for ticker_dir in sorted(base.iterdir()):
        if not ticker_dir.is_dir() or not site.TICKER_DIR_RE.match(ticker_dir.name):
            continue
        for run_dir in sorted(ticker_dir.iterdir()):
            key = run_key(run_dir.name)
            if not run_dir.is_dir() or key is None or key[0] not in dates:
                continue
            runs[f"{ticker_dir.name}/{run_dir.name}"] = {
                "ticker": ticker_dir.name, "model": key[1], "stamp": key[2],
                "target": target_fn(run_dir),
            }
    return runs


def href_run(href: str, base: str = "") -> str:
    path = unquote(urlsplit(href).path).lstrip("./")
    if base:
        path = f"{base}/{path}"
    return path.split("/complete_report", 1)[0]


def rewrite_home(path: Path, source: str, target: str, removed: set[str], paths: set[str]) -> None:
    page = history.read_page(path)
    sections = history.daily_sections(page)
    if target not in sections:
        raise WorkflowError(f"No published {target} summary to merge into")
    rows: dict[str, Tag] = {}
    for date in (target, source):
        for tag in sections.get(date, []):
            if tag.name != "table":
                continue
            for row in history.required(tag, "tbody").find_all("tr"):
                run_id = href_run(str(history.required(row, "a[href]")["href"]))
                if run_id not in removed:
                    rows.setdefault(run_id, row)

    container = history.required(page, ".daily-summary-tables")
    current = None
    for tag in list(container.find_all(recursive=False)):
        match = history.DATE_HEADING.fullmatch(str(tag.get("id", "")))
        if tag.name == "h2" and match:
            current = match[1]
        if current == source:
            tag.decompose()
        elif current == target and tag.name == "p" and "incomplete decision" in tag.get_text():
            tag.decompose()  # every incomplete decision for this date is pruned
    table = next(t for t in container.find_all("table", recursive=False)
                 if t.find_previous("h2").get("id") == f"{target}-decision-summary")
    body = history.required(table, "tbody")
    body.clear()
    for row in sorted(rows.values(), key=history.summary_key):
        body.append(row)

    for item in list(history.required(page, ".daily-summary-rail ul").find_all("li")):
        anchor = history.required(item, "a")
        if anchor["href"] == f"#{source}-decision-summary":
            item.decompose()
        elif anchor["href"] == f"#{target}-decision-summary":
            item.find("span").string = f"{len(rows)} report{'s' if len(rows) != 1 else ''}"
    for anchor in page.select(f'nav.md-nav--secondary a[href="#{source}-decision-summary"]'):
        anchor.find_parent("li").decompose()

    counts = Counter(p.split("/", 1)[0] for p in paths)
    article = history.required(page, "article.md-content__inner")
    history.required(article, "p em").string = f"{len(paths)} runs across {len(counts)} tickers."
    ticker_list = history.required(article, "#tickers").find_next_sibling("ul")
    ticker_list.clear()
    for ticker in sorted(counts):
        item = page.new_tag("li")
        anchor = page.new_tag("a", href=f"{ticker}/")
        anchor.string = ticker
        item.append(anchor)
        item.append(f" · {counts[ticker]} runs")
        ticker_list.append(item)
    history.navigation(page, sorted(counts))
    path.write_text(str(page), encoding="utf-8")


def rewrite_hub(path: Path, source: str, target: str, removed: set[str], tickers: list[str]) -> None:
    page = history.read_page(path)
    body = history.required(page, "article table tbody")
    kept = []
    for row in body.find_all("tr"):
        run_id = href_run(str(history.required(row, "a[href]")["href"]), path.parent.name)
        if run_id in removed:
            continue
        date_cell = row.find_all("td", recursive=False)[0]
        if date_cell.get_text(strip=True) == source:
            date_cell.string = target
        kept.append(row.extract())
    body.clear()

    def order(row: Tag) -> tuple[str, str]:
        cells = row.find_all("td", recursive=False)
        return cells[0].get_text(strip=True), cells[2].get_text(strip=True)

    for row in sorted(kept, key=order, reverse=True):
        body.append(row)
    history.required(page, "article p em").string = f"{len(kept)} run(s)."
    history.navigation(page, tickers, path.parent.name)
    path.write_text(str(page), encoding="utf-8")


def rewrite_sitemap(path: Path, removed: set[str]) -> None:
    ET.register_namespace("", SITEMAP_NS)
    root = ET.parse(path).getroot()
    for entry in list(root):
        loc = entry.findtext(f"{{{SITEMAP_NS}}}loc") or ""
        if any(f"/{run_id}/" in loc for run_id in removed):
            root.remove(entry)
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    path.write_bytes(data)
    path.with_suffix(".xml.gz").write_bytes(gzip.compress(data, mtime=0))


def git(*args: str, env: dict | None = None) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True, env=env).stdout.strip()


def push(site_dir: Path, base_commit: str, removed: set[str], source: str, target: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        git("read-tree", base_commit, env=env)
        git(f"--work-tree={site_dir}", "add", "--all", "--force", "--", ".", env=env)
        tree = git("write-tree", env=env)
    deleted = git("diff", "--name-only", "--diff-filter=D", base_commit, tree).splitlines()
    unexpected = [p for p in deleted if p.rsplit("/complete_report", 1)[0] not in removed]
    if unexpected:
        raise WorkflowError(f"Refusing to delete files outside the pruned runs: {unexpected[:5]}")
    commit = git("-c", "user.useConfigOnly=true", "commit-tree", tree, "-p", base_commit,
                 "-m", f"Merge {source} reports into {target}; prune superseded and no-target runs")
    git("push", "origin", f"{commit}:refs/heads/gh-pages")
    print(f"Pushed {commit[:12]} to gh-pages ({len(deleted)} files removed).")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-date", required=True)
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--base-ref", default="origin/gh-pages")
    parser.add_argument("--site-dir", type=Path, default=ROOT / "_site")
    parser.add_argument("--prune-local", action="store_true")
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()
    source = site.normalize_analysis_date(args.source_date)
    target = site.normalize_analysis_date(args.target_date)
    if source == target:
        parser.error("source and target dates must differ")
    dates = {slug(source), slug(target)}

    if args.push:
        git("fetch", "origin", f"+refs/heads/gh-pages:refs/remotes/{args.base_ref}")
    site_dir = args.site_dir.resolve()
    with tempfile.TemporaryDirectory(prefix=".consolidate-", dir=site_dir.parent) as tmp:
        merged = Path(tmp) / "merged"
        base_commit = publish.snapshot_published_site(merged, args.base_ref)
        runs = collect(merged, dates, lambda d: published_target(d / "complete_report" / "index.html"))
        keep = choose(runs)
        removed = set(runs) - keep
        print(f"{source} + {target}: {len(runs)} published runs; keep {len(keep)}, remove {len(removed)}")
        for (date, model, why), n in sorted(Counter(
            (r.split("/")[1][:8], runs[r]["model"],
             "no target" if runs[r]["target"] is None else "superseded")
            for r in removed
        ).items()):
            print(f"  remove {date} {model} ({why}): {n}")

        for run_id in removed:
            shutil.rmtree(merged / run_id)
        paths = history.report_paths(merged)
        tickers = sorted({p.split("/", 1)[0] for p in paths})
        rewrite_home(merged / "index.html", source, target, removed, paths)
        for ticker in tickers:
            rewrite_hub(merged / ticker / "index.html", source, target, removed, tickers)
        rewrite_sitemap(merged / "sitemap.xml", removed)
        merges_path = merged / "publication-date-merges.json"
        merges = json.loads(merges_path.read_text()) if merges_path.is_file() else {}
        merges[source] = target
        merges_path.write_text(json.dumps(dict(sorted(merges.items())), indent=2) + "\n")

        for page in merged.rglob("*.html"):
            text = page.read_text(encoding="utf-8")
            stale = next((r for r in removed if r.split("/", 1)[1] in text), None)
            if stale:
                raise WorkflowError(f"{page.relative_to(merged)} still links to pruned run {stale}")
        history.validate_indexes(merged, paths)
        publish.install_preview(merged, site_dir)
    print(f"Site written to {site_dir}: {len(paths)} reports.")

    if args.prune_local:
        local = collect(DOCS, dates, local_target)
        # Published keepers stay authoritative; a local run survives only if it
        # is a published keeper or newer than its pair's keeper with a target.
        best = {(runs[r]["ticker"], runs[r]["model"]): runs[r]["stamp"] for r in keep}
        moved = 0
        for run_id, info in sorted(local.items()):
            pair = (info["ticker"], info["model"])
            newer = info["target"] is not None and info["stamp"] > best.get(pair, "")
            if run_id in keep or newer:
                continue
            destination = PRUNED / run_id
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise WorkflowError(f"Pruned copy already exists: {destination}")
            (DOCS / run_id).rename(destination)
            moved += 1
        print(f"Moved {moved} local run folder(s) to {PRUNED.relative_to(ROOT)}/")

    if args.push:
        push(site_dir, base_commit, removed, source, target)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except WorkflowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
