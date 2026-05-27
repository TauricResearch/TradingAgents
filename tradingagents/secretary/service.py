"""Secretary service.

F1 ships ``compose_deep_dive`` end-to-end. F4 ships ``compose_event_alert``.
Morning digest is stubbed — lands in F5.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Environment, FileSystemLoader, select_autoescape

from tradingagents.personas.loader import load_all_personas
from tradingagents.persistence import store
from tradingagents.secretary.persona_runner import run_personas_parallel
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


def render_event_alert(
    *,
    ticker: str,
    event: Dict[str, Any],
    synthesis: Dict[str, str],
    persona_runs: List[Dict[str, Any]],
) -> str:
    return _env.get_template("event_alert.j2").render(
        ticker=ticker,
        event=event,
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

    # ----- Event alert (F4 scope) -----
    def compose_event_alert(
        self,
        *,
        event_id: str,
        ticker: str,
        job_id: int,
    ) -> str:
        """Produce an event-alert brief for a single triaged event.

        ``ticker`` is the watchlist ticker that fired the trigger rule (passed
        in from the promoter's job payload — events can have multiple
        event_ticker rows; the promoter resolves which one at enqueue time).
        """
        ev = store.get_event(self._conn, event_id=event_id)
        if ev is None:
            raise ValueError(f"compose_event_alert: event {event_id} not found")

        # Read the raw payload off disk — F3 wrote it to events/<event_id>.json.
        raw_text = ""
        if ev["raw_path"]:
            raw_path = Path(ev["raw_path"])
            if raw_path.exists():
                try:
                    raw = json.loads(raw_path.read_text(encoding="utf-8"))
                    raw_text = raw.get("text", "") or ""
                except Exception:
                    raw_text = raw_path.read_text(encoding="utf-8")[:4000]

        trade_date = datetime.fromisoformat(
            ev["ingested_ts"].replace("Z", "+00:00")
        ).date().isoformat()

        # Load personas + run them in parallel with event_context threaded in.
        personas_dir = (
            Path(__file__).resolve().parent.parent / "personas"
        )
        personas = load_all_personas(str(personas_dir))
        if not personas:
            raise RuntimeError("compose_event_alert: no personas configured")

        from tradingagents.default_config import DEFAULT_CONFIG
        config = dict(DEFAULT_CONFIG)

        run_ids = run_personas_parallel(
            personas=personas,
            ticker=ticker,
            trade_date=trade_date,
            config=config,
            parallel=True,
            event_context=raw_text,
            queue_job_id=job_id,
        )

        # Build persona_runs view for synthesis + rendering.
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
                "run_id": rid,
            })

        synthesis = synthesize_brief(
            llm=self._llm,
            ticker=ticker,
            persona_runs=persona_runs,
            event_context=raw_text,
        )

        markdown = render_event_alert(
            ticker=ticker,
            event={
                "event_id": event_id,
                "source": ev["source"],
                "ingested_ts": ev["ingested_ts"],
                "raw_text": raw_text,
            },
            synthesis=synthesis,
            persona_runs=persona_runs,
        )

        brief_id = uuid.uuid4().hex
        rel_path = f"briefs/{brief_id}.md"
        (self._data_dir / "briefs").mkdir(parents=True, exist_ok=True)
        (self._data_dir / rel_path).write_text(markdown, encoding="utf-8")

        store.insert_brief(
            self._conn,
            brief_id=brief_id, mode="event_alert", scope=ticker,
            generated_ts=datetime.now(timezone.utc).isoformat(),
            content_path=rel_path,
            run_ids=[r["run_id"] for r in persona_runs],
            parent_brief_id=None,
            trigger_event_id=event_id,
        )
        return brief_id

    # ----- Stubs for later phases -----
    def compose_morning_digest(self, *, watchlist: List[str], ts: str) -> str:
        raise NotImplementedError("compose_morning_digest lands in F5")
