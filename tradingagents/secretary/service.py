"""Secretary service.

F1 ships ``compose_deep_dive`` end-to-end. Morning digest and event alert
are stubbed — they land in later phases (F3+/F5).
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Environment, FileSystemLoader, select_autoescape

from tradingagents.persistence import store
from tradingagents.secretary.synthesis import synthesize_brief

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(disabled_extensions=("j2",)),
    keep_trailing_newline=True,
)


def render_deep_dive(
    *,
    ticker: str,
    trade_date: str,
    synthesis: Dict[str, str],
    persona_runs: List[Dict[str, Any]],
) -> str:
    return _env.get_template("deep_dive.j2").render(
        ticker=ticker,
        trade_date=trade_date,
        synthesis=synthesis,
        persona_runs=persona_runs,
    )


class Secretary:
    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        data_dir: str,
        llm: Any,
    ) -> None:
        self._conn = conn
        self._data_dir = Path(data_dir)
        self._llm = llm

    # ----- Deep-dive (F1 scope) -----
    def compose_deep_dive(
        self,
        *,
        ticker: str,
        run_ids: List[str],
        trade_date: str,
    ) -> str:
        # Load each run's pm_synthesis.md (or fall back to meta.json) as the
        # final_trade_decision text for that persona.
        persona_runs: List[Dict[str, Any]] = []
        for rid in run_ids:
            row = self._conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (rid,)
            ).fetchone()
            if row is None:
                continue
            artifact_dir = self._data_dir / row["artifact_dir"]
            pm_path = artifact_dir / "pm_synthesis.md"
            body = pm_path.read_text(encoding="utf-8") if pm_path.exists() else ""
            persona_runs.append({
                "persona_id": row["persona_id"] or "default",
                "decision": row["decision"] or "?",
                "final_trade_decision": body,
            })

        synthesis = synthesize_brief(
            llm=self._llm,
            ticker=ticker,
            persona_runs=persona_runs,
        )

        markdown = render_deep_dive(
            ticker=ticker,
            trade_date=trade_date,
            synthesis=synthesis,
            persona_runs=persona_runs,
        )

        brief_id = uuid.uuid4().hex
        rel_path = f"briefs/{brief_id}.md"
        (self._data_dir / "briefs").mkdir(parents=True, exist_ok=True)
        (self._data_dir / rel_path).write_text(markdown, encoding="utf-8")

        store.insert_brief(
            self._conn,
            brief_id=brief_id,
            mode="deep_dive",
            scope=ticker,
            generated_ts=datetime.now(timezone.utc).isoformat(),
            content_path=rel_path,
            run_ids=run_ids,
            parent_brief_id=None,
        )
        return brief_id

    # ----- Stubs for later phases -----
    def compose_morning_digest(self, *, watchlist: List[str], ts: str) -> str:
        raise NotImplementedError("compose_morning_digest lands in F5")

    def compose_event_alert(self, *, event_id: str) -> str:
        raise NotImplementedError("compose_event_alert lands in F4")
