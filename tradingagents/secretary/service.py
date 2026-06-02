"""Secretary service.

F1 ships ``compose_deep_dive`` end-to-end. F4 ships ``compose_event_alert``.
Morning digest is stubbed — lands in F5.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
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


def _build_channel(name, conn, config):
    if name == "cli":
        from tradingagents.delivery.cli import CLIOutbound
        return CLIOutbound(conn=conn, config=config)
    if name == "email":
        from tradingagents.delivery.email import EmailOutbound
        return EmailOutbound(conn=conn, config=config)
    if name == "telegram":
        from tradingagents.delivery.telegram import TelegramOutbound
        return TelegramOutbound(conn=conn, config=config)
    return None


class RefinementDepthExceeded(Exception):
    """Raised when refinement chain would exceed configured max_depth."""


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

    def compose_event_alert_light(
        self,
        *,
        event_id: str,
        tickers: List[str],
        ttl_hours: int = 24,
        deliver: bool = True,
    ) -> str:
        """Light alert (IIC-FORGE-09): one quick summary + an event-scoped
        brief + one pending run_full_study action per ticker + per-ticker
        same-day suppression. NO persona study runs here — the heavy study is
        enqueued later, only on approval. Returns the light brief_id."""
        ev = store.get_event(self._conn, event_id=event_id)
        if ev is None:
            raise ValueError(f"compose_event_alert_light: event {event_id} not found")

        raw_text = ""
        if ev["raw_path"]:
            p = Path(ev["raw_path"])
            if p.exists():
                try:
                    raw_text = (json.loads(p.read_text(encoding="utf-8"))
                                .get("text", "") or "")
                except Exception:
                    raw_text = p.read_text(encoding="utf-8")[:4000]

        prompt = (
            "You are an equity-desk assistant. In 2-3 sentences, summarize why "
            "the following event might matter for the affected tickers "
            f"({', '.join(tickers)}). Be terse and factual.\n\n"
            f"EVENT:\n{raw_text[:4000]}"
        )
        resp = self._llm.invoke(prompt)
        summary = getattr(resp, "content", str(resp))

        brief_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        rel_path = f"briefs/{brief_id}.md"
        body = f"# Event alert (light)\n\n{summary}\n\nAffected: {', '.join(tickers)}\n"
        (self._data_dir / "briefs").mkdir(parents=True, exist_ok=True)
        (self._data_dir / rel_path).write_text(body, encoding="utf-8")

        store.insert_brief(
            self._conn,
            brief_id=brief_id,
            mode="event_alert_light",
            scope=json.dumps(list(tickers)),
            generated_ts=now.isoformat(),
            content_path=rel_path,
            run_ids=[],
            parent_brief_id=None,
            trigger_event_id=event_id,
        )

        # NOTE: insert_brief + the per-ticker actions/suppressions are written
        # via store.* helpers that each commit individually, so this is not one
        # atomic unit. A mid-loop crash can leave some tickers without an action
        # /suppression. Acceptable for V1 (brief_id is only returned on full
        # success; partial state is a UX nuisance, not corruption). A truly
        # atomic version would need non-committing store variants.
        expires_at = (now + timedelta(hours=ttl_hours)).isoformat()
        # Same-day dedup: suppress each ticker until the next LOCAL midnight.
        # Use the machine's local tz explicitly (astimezone() with no arg binds
        # the naive 'now' to local time) so this is unambiguous on UTC servers
        # and TZ-offset dev boxes alike.
        local_now = datetime.now().astimezone()
        next_local_midnight = (local_now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        until_ts = next_local_midnight.astimezone(timezone.utc).isoformat()
        for t in tickers:
            store.insert_brief_action(
                self._conn, brief_id=brief_id, action_type="run_full_study",
                action_params={"ticker": t}, expires_at=expires_at,
            )
            store.upsert_suppression(
                self._conn, key=f"event_alert:{t}", until_ts=until_ts,
                reason=f"light_alert_same_day event_id={event_id}",
                created_by="secretary",
            )

        if deliver:
            self._deliver_light_alert(brief_id, tickers, summary, ev)
        return brief_id

    def _deliver_light_alert(self, brief_id, tickers, summary, ev) -> None:
        """Best-effort fan-out to enabled channels. Delivery failures are
        recorded as deliveries rows by each channel; never raise here."""
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.delivery.render import render_for_channel
        config = dict(DEFAULT_CONFIG)
        brief = {
            "brief_id": brief_id, "mode": "event_alert_light",
            "summary": summary, "tickers": list(tickers),
            "event_headline": (ev["source"] or "event"),
        }
        names = list(config["delivery"]["enabled_channels"])
        if config["telegram_bot"]["enabled"] and "telegram" not in names:
            names.append("telegram")
        for name in names:
            try:
                ch = _build_channel(name, self._conn, config)
                if ch is None:
                    continue
                body = render_for_channel(
                    channel=name, mode="event_alert_light", brief=brief)
                ch.send(brief=brief, mode="event_alert_light", body=body)
            except Exception:  # noqa: BLE001
                pass

    # ----- F5: morning digest -----
    def compose_morning_digest(
        self, *, watchlist: List[str] | None, ts: str,
    ) -> str:
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.secretary.morning import run_one_ticker

        if watchlist is None:
            rows = self._conn.execute(
                "SELECT ticker FROM watchlist "
                # datetime(ttl_until) wrap: raw ISO 'T'+offset vs datetime('now')
                # space-form silently mis-filters same-day rows. Matches the
                # canonical query in persistence/store.get_active_watchlist.
                "WHERE ttl_until IS NULL OR datetime(ttl_until) > datetime('now') "
                "ORDER BY ticker"
            ).fetchall()
            watchlist = [r[0] for r in rows]

        per_ticker_sections: list[dict] = []
        all_run_ids: list[str] = []
        for tk in watchlist:
            try:
                run_ids, synthesis = run_one_ticker(
                    ticker=tk,
                    trade_date=ts[:10],
                    config=DEFAULT_CONFIG,
                    conn=self._conn,
                    data_dir=self._data_dir,
                )
                per_ticker_sections.append({
                    "ticker": tk,
                    "consensus": synthesis.get("consensus", ""),
                    "divergence": synthesis.get("divergence", ""),
                    "recommendation": synthesis.get("recommendation", ""),
                })
                all_run_ids.extend(run_ids)
            except Exception as exc:  # noqa: BLE001 — per-ticker isolation
                per_ticker_sections.append({
                    "ticker": tk,
                    "consensus": "(data error)",
                    "divergence": f"(data error: {exc})",
                    "recommendation": "(data error)",
                })

        brief_id = uuid.uuid4().hex
        brief_path = self._data_dir / "briefs" / f"{brief_id}.md"
        brief_path.parent.mkdir(parents=True, exist_ok=True)

        body_lines = [
            f"# Morning Digest — {ts[:10]}",
            f"_brief: `{brief_id}` · {len(watchlist)} ticker(s)_",
            "",
        ]
        for sec in per_ticker_sections:
            body_lines += [
                f"## {sec['ticker']}",
                "",
                "**Consensus:** " + sec["consensus"],
                "",
                "**Divergence:** " + sec["divergence"],
                "",
                "**Recommendation:** " + sec["recommendation"],
                "",
            ]
        brief_path.write_text("\n".join(body_lines))

        store.insert_brief(
            self._conn,
            brief_id=brief_id,
            mode="morning_digest",
            scope=json.dumps(list(watchlist)),
            generated_ts=ts,
            content_path=str(brief_path.relative_to(self._data_dir)),
            run_ids=all_run_ids,
        )
        return brief_id

    # ----- F5: refinement -----
    def compose_refinement(
        self, *, parent_brief_id: str, overrides: dict, reply_text: str,
    ) -> str:
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.secretary.morning import run_one_ticker

        parent = store.load_brief(self._conn, parent_brief_id)
        if parent is None:
            raise ValueError(f"parent brief not found: {parent_brief_id}")

        max_depth = DEFAULT_CONFIG["refinement"]["max_depth"]
        if parent["refine_depth"] >= max_depth:
            raise RefinementDepthExceeded(
                f"parent depth {parent['refine_depth']} >= max_depth {max_depth}"
            )

        scope = parent["scope"]
        ticker = scope if not scope.startswith("[") else json.loads(scope)[0]

        config = dict(DEFAULT_CONFIG)
        if overrides.get("personas"):
            config["_persona_filter"] = overrides["personas"]
        if overrides.get("risk_tilt"):
            config["_risk_tilt"] = overrides["risk_tilt"]
        if overrides.get("horizon"):
            config["_horizon"] = overrides["horizon"]
        if overrides.get("analysts"):
            config["_analysts_override"] = overrides["analysts"]

        ts = datetime.now(timezone.utc).isoformat()
        run_ids, synthesis = run_one_ticker(
            ticker=ticker, trade_date=ts[:10],
            config=config, conn=self._conn, data_dir=self._data_dir,
        )

        new_brief_id = uuid.uuid4().hex
        brief_path = self._data_dir / "briefs" / f"{new_brief_id}.md"
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        body = (
            f"# Refined Deep-Dive — {ticker}\n"
            f"_brief: `{new_brief_id}` · refining `{parent_brief_id}` · "
            f"depth {parent['refine_depth'] + 1}_\n\n"
            f"## User refinement\n> {reply_text}\n\n"
            f"## Consensus\n{synthesis.get('consensus','')}\n\n"
            f"## Divergence\n{synthesis.get('divergence','')}\n\n"
            f"## Recommendation\n{synthesis.get('recommendation','')}\n"
        )
        brief_path.write_text(body)

        store.insert_brief(
            self._conn,
            brief_id=new_brief_id,
            mode="deep_dive",
            scope=ticker,
            generated_ts=ts,
            content_path=str(brief_path.relative_to(self._data_dir)),
            run_ids=run_ids,
            parent_brief_id=parent_brief_id,
        )
        store.update_brief_refine_metadata(
            self._conn,
            brief_id=new_brief_id,
            refine_depth=parent["refine_depth"] + 1,
            refine_overrides=overrides,
        )
        return new_brief_id
