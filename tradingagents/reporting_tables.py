"""Structured table extraction for session reports (CLI + web).

Report markdown often carries malformed or ASCII-ish tables, so pure
regex detection is unreliable. Instead each report section is sent to a
user-selected table model that returns clean ``{title, headers, rows}``
JSON; a naive pipe-table parser is the fallback when the model output
cannot be decoded.

Results land in ``<session_dir>/tables.json`` (plus a human-readable
``tables.md``), so both the CLI and the web UIs read the same artifact:

  {"<agent label>": [{"title": str, "headers": [...], "rows": [[...]]}]}
"""

from __future__ import annotations

import json
import re
from pathlib import Path

TABLES_FILE = "tables.json"
TABLES_MD_FILE = "tables.md"

# Saved-tree files (reports/<TICKER>_<ts>/) -> agent label.
_SAVED_FILES = {
    "1_analysts/market.md": "Market Analyst",
    "1_analysts/sentiment.md": "Sentiment Analyst",
    "1_analysts/news.md": "News Analyst",
    "1_analysts/fundamentals.md": "Fundamentals Analyst",
    "2_research/bull.md": "Bull Researcher",
    "2_research/bear.md": "Bear Researcher",
    "2_research/manager.md": "Research Manager",
    "3_trading/trader.md": "Trader",
    "4_risk/aggressive.md": "Aggressive Analyst",
    "4_risk/conservative.md": "Conservative Analyst",
    "4_risk/neutral.md": "Neutral Analyst",
    "5_portfolio/decision.md": "Portfolio Manager",
}

# Live-run files (<results>/<ticker>/<date>/reports/*.md) -> agent label.
_RUN_FILES = {
    "market_report.md": "Market Analyst",
    "sentiment_report.md": "Sentiment Analyst",
    "news_report.md": "News Analyst",
    "fundamentals_report.md": "Fundamentals Analyst",
    "investment_plan.md": "Research Team",
    "trader_investment_plan.md": "Trader",
    "final_trade_decision.md": "Portfolio Management",
}

EXTRACT_PROMPT = """You extract data tables from a financial analysis report section.

Agent: {agent}
Report section markdown:
---
{content}
---

Return ONLY a JSON array (no prose, no fences) with one object per data
table found:
[{{"title": "<short table title>", "headers": ["col1", "col2"], "rows": [["a", "b"], ...]}}]
Rules: every row must have exactly len(headers) cells (pad with ""); keep
numbers as written; skip tables with no data rows; return [] if none exist."""


def collect_section_files(session_dir: Path, kind: str) -> list[tuple[str, Path]]:
    """List (agent label, markdown file) present in a session dir."""
    session_dir = Path(session_dir)
    mapping = _SAVED_FILES if kind == "saved" else _RUN_FILES
    base = session_dir if kind == "saved" else (session_dir / "reports")
    found = []
    for rel, label in mapping.items():
        path = base / rel
        try:
            if path.is_file() and path.stat().st_size > 0:
                found.append((label, path))
        except OSError:
            continue
    return found


def parse_pipe_tables(md_text: str) -> list[dict]:
    """Naive pipe-table parser (fallback when the LLM output won't decode)."""
    tables = []
    lines = (md_text or "").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if (
            "|" in line
            and i + 1 < len(lines)
            and re.match(r"^\s*\|?[\s:\-|]+\|?\s*$", lines[i + 1])
            and "-" in lines[i + 1]
        ):
            headers = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and "|" in lines[i]:
                row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if len(row) < len(headers):
                    row += [""] * (len(headers) - len(row))
                rows.append(row[: len(headers)])
                i += 1
            if headers and rows:
                tables.append({"title": "", "headers": headers, "rows": rows})
            continue
        i += 1
    return tables


def _decode_tables(raw: str) -> list[dict] | None:
    """Decode model JSON output into normalized table dicts, or None."""
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except Exception:
        return None
    if isinstance(data, dict):
        data = data.get("tables", [])
    if not isinstance(data, list):
        return None
    tables = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        headers = [str(h) for h in entry.get("headers", [])]
        rows = entry.get("rows", [])
        if not headers or not isinstance(rows, list):
            continue
        clean_rows = []
        for row in rows:
            if not isinstance(row, list):
                continue
            cells = [str(c) for c in row]
            if len(cells) < len(headers):
                cells += [""] * (len(headers) - len(cells))
            clean_rows.append(cells[: len(headers)])
        if clean_rows:
            tables.append(
                {
                    "title": str(entry.get("title", "")),
                    "headers": headers,
                    "rows": clean_rows,
                }
            )
    return tables


def reformat_with_llm(llm, agent_label: str, content: str) -> list[dict]:
    """Ask the table model to normalize a section; fallback to pipe parsing."""
    prompt = EXTRACT_PROMPT.format(agent=agent_label, content=content[:12000])
    try:
        result = llm.invoke(prompt)
        text = getattr(result, "content", result)
        if isinstance(text, list):  # content-block style responses
            text = "\n".join(
                str(b.get("text", "")) if isinstance(b, dict) else str(b) for b in text
            )
        decoded = _decode_tables(str(text))
        if decoded is not None:
            return decoded
    except Exception:
        pass
    return parse_pipe_tables(content)


def generate_tables_for_session(
    session_dir,
    kind: str,
    provider: str,
    model: str,
    base_url: str | None = None,
    progress_cb=None,
) -> dict:
    """Generate ``tables.json`` (+ ``tables.md``) for a session directory.

    Returns ``{agent_label: [tables]}``. Raises on LLM/config errors so the
    caller (CLI prompt or API job) can surface the real message.
    """
    from tradingagents.llm_clients.factory import create_llm_client

    session_dir = Path(session_dir)
    files = collect_section_files(session_dir, kind)
    if not files:
        raise ValueError("No report sections found in this session.")
    client = create_llm_client(provider, model, base_url)
    llm = client.get_llm()

    all_tables: dict[str, list[dict]] = {}
    for agent_label, path in files:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        tables = reformat_with_llm(llm, agent_label, content)
        if tables:
            all_tables[agent_label] = tables
        if progress_cb is not None:
            progress_cb(agent_label, len(tables))

    (session_dir / TABLES_FILE).write_text(
        json.dumps(all_tables, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md_parts = [f"# Tables: {session_dir.name}\n"]
    for agent_label, tables in all_tables.items():
        md_parts.append(f"\n## {agent_label}\n")
        for table in tables:
            if table.get("title"):
                md_parts.append(f"\n### {table['title']}\n")
            header = "| " + " | ".join(table["headers"]) + " |"
            sep = "| " + " | ".join("---" for _ in table["headers"]) + " |"
            md_parts.append(header + "\n" + sep)
            for row in table["rows"]:
                md_parts.append("| " + " | ".join(row) + " |")
            md_parts.append("")
    (session_dir / TABLES_MD_FILE).write_text("\n".join(md_parts), encoding="utf-8")
    return all_tables


def load_tables(session_dir) -> dict:
    """Read a session's tables.json ({} when absent/unreadable)."""
    try:
        return json.loads((Path(session_dir) / TABLES_FILE).read_text(encoding="utf-8"))
    except Exception:
        return {}
