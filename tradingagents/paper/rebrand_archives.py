"""Rebrand archived reports produced before Koral Equities' wordmark was introduced.

Changes ONLY the HTML presentation: title, brand link, report style, version
label and footer. Never edits analyst paragraphs, AI decisions or the paper
portfolio. Makes a .html.upstream-backup for each original.
"""

from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path

from tradingagents.report_html import _CSS, _WORDMARK
from tradingagents.paper.cli import DEFAULT_PATH


def rebrand_html(source: str) -> str:
    """Return archive HTML with Koral identity, or the unchanged text if not applicable."""
    if 'aria-label="Koral Equities"' in source and "Tauric Research" not in source:
        return source
    if 'aria-label="Tauric Research"' not in source:
        return source
    if source.count("<style>") != 1 or source.count("</style>") != 1:
        raise ValueError("Unknown report stylesheet; do not edit")
    if source.count('<footer class="credit">') != 1:
        raise ValueError("Unknown credit section; do not edit")
    if source.count('<a class="logo"') != 1:
        raise ValueError("Unknown logo section; do not edit")

    html, count = re.subn(
        r'<a class="logo"[^>]*>.*?</a>',
        '<div class="logo" aria-label="Koral Equities">' + _WORDMARK + "</div>",
        source,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise ValueError("Cannot match original report logo")
    html, count = re.subn(
        r"<title>(.*?)</title>",
        lambda match: "<title>Koral Equities | " +
        match.group(1).replace(": TradingAgents report", "") +
        " | Equity Research</title>",
        html, count=1, flags=re.DOTALL,
    )
    if count != 1:
        raise ValueError("Cannot match report title")
    html, count = re.subn(r"<style>.*?</style>", lambda _: "<style>" + _CSS + "</style>",
                          html, count=1, flags=re.DOTALL)
    if count != 1:
        raise ValueError("Cannot match original styles")
    html, count = re.subn(
        r'<footer class="credit">.*?</footer>',
        '<footer class="credit">KORAL EQUITIES · Independent equity research · Simulation only</footer>',
        html, count=1, flags=re.DOTALL,
    )
    if count != 1:
        raise ValueError("Cannot match original footer")
    html = re.sub(
        r"<dt>Version</dt><dd>TradingAgents ([0-9][^<]*)</dd>",
        r"<dt>Research engine</dt><dd>v\1</dd>",
        html, count=1,
    )
    # The original source's header and footer must no longer advertise upstream.
    header = html.split("</header>", 1)[0]
    footer = html.split('<footer class="credit">', 1)[1].split("</footer>", 1)[0]
    if "Tauric" in header or "Tauric" in footer or "TradingAgents report" in header:
        raise ValueError("Old branding remains in the header/footer")
    return html


def archive_reports(root: Path, apply: bool = False) -> tuple[int, int]:
    """Scan archived report pages; optionally make a backup and replace each atomically."""
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Report folder does not exist: {root}")
    matches = 0
    changed = 0
    for path in sorted(root.rglob("complete_report.html")):
        original = path.read_text(encoding="utf-8")
        updated = rebrand_html(original)
        if original == updated:
            continue
        matches += 1
        print(f"{'Updating' if apply else 'Would update'}: {path}")
        if not apply:
            continue
        backup = path.with_name(path.name + ".upstream-backup")
        if backup.exists():
            raise FileExistsError(f"Refusing to overwrite original report backup: {backup}")
        backup.write_text(original, encoding="utf-8")
        fd, tmp = tempfile.mkstemp(prefix=".koral-report-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                out.write(updated)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        changed += 1
    return matches, changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="koral-equities-rebrand-reports",
                                     description="Locally rebrand saved research HTML; never touch trades")
    parser.add_argument("--folder", type=Path, default=DEFAULT_PATH.parent / "reports")
    parser.add_argument("--apply", action="store_true", help="Write backups and update report HTML")
    args = parser.parse_args(argv)
    try:
        scanned, done = archive_reports(args.folder, args.apply)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"{scanned} archived reports matched; {done} updated. "
          + ("Originals preserved as .upstream-backup files." if done else "No originals modified."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
