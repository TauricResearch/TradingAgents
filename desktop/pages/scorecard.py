"""Recommendation Accuracy Scorecard — system performance dashboard.

Shows historical accuracy metrics: win rate, average return, best/worst
calls, and per-verdict breakdowns.  All data comes from stored
recommendation outcomes (no live price lookups).

See also: PLAN-desktop.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from nicegui import ui

from desktop.state.database import (
    HistoryDB,
    RecommendationOutcomeRow,
    RecommendationRow,
)


def render_scorecard_page(*, db: HistoryDB) -> None:
    """Render the scorecard page content."""
    page = _ScorecardPage(db=db)
    page.build()


# ── Internal data structures ──────────────────────────────────────────


@dataclass(frozen=True)
class _RecommendationWithOutcome:
    """A recommendation paired with its latest outcome row."""

    rec: RecommendationRow
    outcome: RecommendationOutcomeRow | None


# ── Helpers ───────────────────────────────────────────────────────────

_SELL_VERDICTS = frozenset({"SELL", "UNDERWEIGHT"})


def _effective_return(rec: RecommendationRow, outcome: RecommendationOutcomeRow) -> float:
    """Return the effective return, inverting sign for SELL/UNDERWEIGHT."""
    if rec.verdict in _SELL_VERDICTS:
        return -outcome.return_pct
    return outcome.return_pct


def _color_for_value(value: float) -> str:
    """Return a Quasar color name for a numeric value."""
    if value > 0:
        return "green"
    if value < 0:
        return "red"
    return "orange"


def _fmt_pct(value: float) -> str:
    """Format a percentage with sign and 1 decimal place."""
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


# ── Page class ────────────────────────────────────────────────────────


class _ScorecardPage:
    def __init__(self, *, db: HistoryDB) -> None:
        self._db = db

    def build(self) -> None:
        # Gather all data up-front
        all_recs = self._load_all_recommendations()
        outcomes_30d = self._db.list_all_outcomes(min_days=30)

        # Build lookup: recommendation_id -> RecommendationRow
        rec_by_id: dict[int, RecommendationRow] = {r.id: r for r in all_recs}

        # Pair each recommendation with its latest outcome
        paired = self._pair_recs_with_latest_outcomes(all_recs)

        # Filter 30d outcomes to only those with a matching recommendation
        valid_30d = [o for o in outcomes_30d if o.recommendation_id in rec_by_id]

        with ui.column().classes("w-full q-pa-md gap-md"):
            # Header
            with ui.row().classes("items-center gap-sm"):
                ui.label("System Performance Scorecard").classes(
                    "text-h5 text-white"
                )
                with ui.icon("info").classes("text-grey-5 cursor-pointer"):
                    ui.tooltip(
                        "Metrics are computed from stored outcome checkpoints "
                        "(1d, 7d, 30d, 90d). Win rate uses the 30-day checkpoint. "
                        "For SELL verdicts, a price decrease counts as a win."
                    )

            # Empty state
            if not valid_30d:
                self._build_empty_state()
                return

            # Compute aggregate metrics from 30d outcomes
            self._build_top_stats(valid_30d, rec_by_id)
            self._build_verdict_breakdown(valid_30d, rec_by_id)
            self._build_best_worst_table(valid_30d, rec_by_id)
            self._build_all_recommendations_table(paired)

    # ── Data loading ──────────────────────────────────────────────────

    def _load_all_recommendations(self) -> list[RecommendationRow]:
        """Load all recommendations (active and inactive) from the DB."""
        return self._db.list_all_recommendations()

    def _pair_recs_with_latest_outcomes(
        self, recs: list[RecommendationRow],
    ) -> list[_RecommendationWithOutcome]:
        """Pair each recommendation with its most recent outcome."""
        paired: list[_RecommendationWithOutcome] = []
        for rec in recs:
            outcomes = self._db.get_outcomes(rec.id)
            latest = outcomes[-1] if outcomes else None
            paired.append(_RecommendationWithOutcome(rec=rec, outcome=latest))
        return paired

    # ── Empty state ───────────────────────────────────────────────────

    def _build_empty_state(self) -> None:
        with ui.column().classes("w-full items-center q-pa-xl gap-md"):
            ui.label("No outcome data yet").classes("text-h5 text-grey-5")
            ui.label(
                "Outcomes are recorded automatically at 1d, 7d, 30d, and 90d "
                "checkpoints. Run some analyses and check back later!"
            ).classes("text-body1 text-grey-6 text-center").style(
                "max-width: 500px"
            )

    # ── Top stats row ─────────────────────────────────────────────────

    def _build_top_stats(
        self,
        outcomes: list[RecommendationOutcomeRow],
        rec_by_id: dict[int, RecommendationRow],
    ) -> None:
        effective_returns = []
        stop_hits = 0
        target_hits = 0

        for o in outcomes:
            rec = rec_by_id.get(o.recommendation_id)
            if rec is None:
                continue
            effective_returns.append(_effective_return(rec, o))
            if o.stop_hit:
                stop_hits += 1
            if o.target_hit:
                target_hits += 1

        total = len(effective_returns)
        wins = sum(1 for r in effective_returns if r > 0)
        win_rate = (wins / total * 100) if total else 0.0
        avg_return = (sum(effective_returns) / total) if total else 0.0
        stop_rate = (stop_hits / total * 100) if total else 0.0
        target_rate = (target_hits / total * 100) if total else 0.0

        with ui.row().classes("w-full gap-md"):
            self._metric_card(
                label="Win Rate (30d)",
                value=f"{win_rate:.0f}%",
                subtitle=f"{wins} / {total}",
                color=_color_for_value(win_rate - 50),
            )
            self._metric_card(
                label="Avg Return (30d)",
                value=_fmt_pct(avg_return),
                subtitle=f"{total} outcomes",
                color=_color_for_value(avg_return),
            )
            self._metric_card(
                label="Stop-Loss Hit Rate",
                value=f"{stop_rate:.0f}%",
                subtitle=f"{stop_hits} / {total}",
                color=_color_for_value(-stop_rate),  # lower = better
            )
            self._metric_card(
                label="Target Hit Rate",
                value=f"{target_rate:.0f}%",
                subtitle=f"{target_hits} / {total}",
                color=_color_for_value(target_rate),
            )

    # ── Verdict breakdown ─────────────────────────────────────────────

    def _build_verdict_breakdown(
        self,
        outcomes: list[RecommendationOutcomeRow],
        rec_by_id: dict[int, RecommendationRow],
    ) -> None:
        ui.label("By Verdict").classes("text-h6 text-white q-mt-md")

        buckets: dict[str, list[float]] = {"BUY": [], "HOLD": [], "SELL": []}

        for o in outcomes:
            rec = rec_by_id.get(o.recommendation_id)
            if rec is None:
                continue
            eff = _effective_return(rec, o)
            verdict = rec.verdict
            if verdict in ("BUY", "OVERWEIGHT"):
                buckets["BUY"].append(eff)
            elif verdict in _SELL_VERDICTS:
                buckets["SELL"].append(eff)
            else:
                buckets["HOLD"].append(eff)

        with ui.row().classes("w-full gap-md"):
            for verdict, returns in buckets.items():
                count = len(returns)
                avg = (sum(returns) / count) if count else 0.0
                note = (
                    "(price drop = win)"
                    if verdict == "SELL" and count > 0
                    else ""
                )
                self._metric_card(
                    label=f"{verdict} Calls",
                    value=_fmt_pct(avg) if count else "N/A",
                    subtitle=f"{count} calls{' ' + note if note else ''}",
                    color=_color_for_value(avg) if count else "grey",
                )

    # ── Best / Worst table ────────────────────────────────────────────

    def _build_best_worst_table(
        self,
        outcomes: list[RecommendationOutcomeRow],
        rec_by_id: dict[int, RecommendationRow],
    ) -> None:
        scored: list[tuple[float, RecommendationOutcomeRow, RecommendationRow]] = []
        for o in outcomes:
            rec = rec_by_id.get(o.recommendation_id)
            if rec is None:
                continue
            scored.append((_effective_return(rec, o), o, rec))

        if not scored:
            return

        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[:3]
        worst = scored[-3:]
        worst.reverse()

        ui.label("Best & Worst Calls (30d)").classes("text-h6 text-white q-mt-md")

        columns = [
            {"name": "rank", "label": "", "field": "rank"},
            {"name": "ticker", "label": "Ticker", "field": "ticker", "sortable": True},
            {"name": "verdict", "label": "Verdict", "field": "verdict"},
            {"name": "return_pct", "label": "Return", "field": "return_pct", "sortable": True},
            {"name": "days", "label": "Days", "field": "days"},
        ]

        rows: list[dict] = []
        for eff, o, rec in best:
            rows.append({
                "rank": "Best",
                "ticker": rec.ticker,
                "verdict": rec.verdict,
                "return_pct": _fmt_pct(eff),
                "days": o.days_elapsed,
            })
        for eff, o, rec in worst:
            rows.append({
                "rank": "Worst",
                "ticker": rec.ticker,
                "verdict": rec.verdict,
                "return_pct": _fmt_pct(eff),
                "days": o.days_elapsed,
            })

        ui.table(
            columns=columns,
            rows=rows,
            row_key="ticker",
        ).classes("w-full").props("flat bordered dense")

    # ── All recommendations table ─────────────────────────────────────

    def _build_all_recommendations_table(
        self, paired: list[_RecommendationWithOutcome],
    ) -> None:
        ui.label("All Recommendations").classes("text-h6 text-white q-mt-md")

        columns = [
            {"name": "ticker", "label": "Ticker", "field": "ticker", "sortable": True},
            {"name": "verdict", "label": "Verdict", "field": "verdict", "sortable": True},
            {"name": "entry_price", "label": "Entry Price", "field": "entry_price", "sortable": True},
            {"name": "outcome", "label": "Outcome", "field": "outcome", "sortable": True},
            {"name": "days", "label": "Days", "field": "days", "sortable": True},
            {"name": "stop_hit", "label": "Stop Hit", "field": "stop_hit"},
            {"name": "target_hit", "label": "Target Hit", "field": "target_hit"},
        ]

        rows: list[dict] = []
        for item in paired:
            rec = item.rec
            o = item.outcome
            if o is not None:
                eff = _effective_return(rec, o)
                outcome_str = _fmt_pct(eff)
                days = o.days_elapsed
                stop = "Yes" if o.stop_hit else "No"
                target = "Yes" if o.target_hit else "No"
            else:
                outcome_str = "Pending"
                days = ""
                stop = "-"
                target = "-"

            rows.append({
                "ticker": rec.ticker,
                "verdict": rec.verdict,
                "entry_price": f"${rec.price_at_analysis:.2f}" if rec.price_at_analysis else "-",
                "outcome": outcome_str,
                "days": days,
                "stop_hit": stop,
                "target_hit": target,
            })

        ui.table(
            columns=columns,
            rows=rows,
            row_key="ticker",
            pagination={"rowsPerPage": 15},
        ).classes("w-full").props("flat bordered dense")

    # ── Shared metric card component ──────────────────────────────────

    @staticmethod
    def _metric_card(
        *,
        label: str,
        value: str,
        subtitle: str,
        color: str,
    ) -> None:
        """Render a single metric card with a big number and label."""
        with ui.card().classes("q-pa-md flex-1 min-w-[180px]"):
            ui.label(label).classes("text-caption text-grey-5")
            ui.label(value).classes(f"text-h4 text-{color} q-my-xs")
            ui.label(subtitle).classes("text-caption text-grey-6")
