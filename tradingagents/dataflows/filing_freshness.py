"""SEC filing freshness gate (P0.1).

A fundamentals report is only as current as the latest authoritative filing
known at the analysis date — not the latest record a vendor happens to
serve. The BRK-B report of 2026-11-08 leaned on Q2 (period ended
2026-06-30) while the Q3 filing (period ended 2026-09-30) had already been
published on 2026-11-07: an older quarter presented as the current one.

The gate answers one question deterministically, for any ticker and any
fiscal calendar: given the filings known at ``analysis_as_of`` and the
period the analyst actually used, is the used period the freshest
authoritative one?

- ``CURRENT`` — the used period matches the latest known filing.
- ``STALE_FUNDAMENTALS`` — the used period is older than the latest known
  filing: the report's "current" fundamentals are not current.
- ``FUNDAMENTALS_UNAVAILABLE`` — no dated filing is known at the analysis
  date (or the used period is unknown): nothing authoritative to compare
  against, so a decision relying on fundamentals cannot be called verified.

No look-ahead: a filing dated after ``as_of_date`` was not known then and
never counts — that is what keeps backtests honest. A company release and
a SEC filing are different sources with different dates; either being
known makes the period known, and the verdict reports which.

Every record carries the fields the audit needs: ``filing_date``,
``accepted_at``, ``period_end``, ``form_type``, ``accession_number``,
source and retrieval timestamp. Publication date and accounting period
are distinct and never conflated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

# Verdict statuses, stable for the audit trail and the Execution Gate.
CURRENT = "CURRENT"
STALE_FUNDAMENTALS = "STALE_FUNDAMENTALS"
FUNDAMENTALS_UNAVAILABLE = "FUNDAMENTALS_UNAVAILABLE"

# Reason codes the Execution Gate and the audit carry verbatim.
FUNDAMENTALS_CURRENT = "FUNDAMENTALS_CURRENT"
FUNDAMENTALS_STALE = "FUNDAMENTALS_STALE"
FUNDAMENTALS_UNAVAILABLE = "FUNDAMENTALS_UNAVAILABLE"


def _parse(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


@dataclass(frozen=True)
class FilingRecord:
    """One authoritative publication of a fiscal period's figures.

    ``published_date`` is the company-release date; ``filing_date`` the SEC
    filing date; ``accepted_at`` the EDGAR acceptance timestamp when known.
    They are different sources with different dates and either being known
    makes the period known. A record with neither date is not evidence of
    anything and never counts as known. ``accession_number`` ties the
    record to the exact filing; ``retrieved_at`` records when this system
    fetched it (a retrieval stamp, not a publication claim).
    """

    period: str                       # "2026-Q3", "2025-FY"…
    period_end: str                   # YYYY-MM-DD: the accounting period end
    published_date: str | None = None  # company release, YYYY-MM-DD
    filing_date: str | None = None     # SEC filing, YYYY-MM-DD
    accepted_at: str | None = None     # EDGAR acceptance, ISO-8601 when known
    form_type: str | None = None       # "10-Q", "10-K", "8-K"…
    accession_number: str | None = None
    source_type: str = "company_release"
    source_url: str | None = None
    retrieved_at: str | None = None
    extra: dict = field(default_factory=dict)

    def known_at(self, as_of_date: str) -> bool:
        """Whether this record was public by ``as_of_date`` (no look-ahead)."""
        as_of = _parse(as_of_date)
        if as_of is None:
            return False
        for candidate in (self.filing_date, self.published_date):
            parsed = _parse(candidate)
            if parsed is not None and parsed <= as_of:
                return True
        return False

    def summary(self) -> dict:
        """Machine-readable provenance for the audit trail."""
        return {
            "period": self.period,
            "period_end": self.period_end,
            "published_date": self.published_date,
            "filing_date": self.filing_date,
            "accepted_at": self.accepted_at,
            "form_type": self.form_type,
            "accession_number": self.accession_number,
            "source_type": self.source_type,
            "source_url": self.source_url,
        }


def latest_known_filing(
    filings: list[FilingRecord], as_of_date: str
) -> FilingRecord | None:
    """The most recent filing known at ``as_of_date``, or None.

    "Most recent" is by period end, then by the date that made it known.
    Filings dated after the analysis date are invisible here — that is the
    whole point: a backtest must not see a filing the market had not seen.
    """
    known = [f for f in filings if f.known_at(as_of_date)]
    if not known:
        return None
    return max(
        known,
        key=lambda f: (f.period_end, f.filing_date or f.published_date or ""),
    )


@dataclass(frozen=True)
class FreshnessVerdict:
    """Whether the fundamentals the analyst used are the freshest known."""

    status: str
    reason_code: str
    latest_known_period: str | None
    latest_known_period_end: str | None
    used_period: str | None
    used_period_end: str | None
    reason: str
    latest_filing: FilingRecord | None = None

    @property
    def blocks_decision(self) -> bool:
        """Stale or unavailable fundamentals must not feed an approval."""
        return self.status in (STALE_FUNDAMENTALS, FUNDAMENTALS_UNAVAILABLE)

    def summary(self) -> dict:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "latest_known_period": self.latest_known_period,
            "latest_known_period_end": self.latest_known_period_end,
            "used_period": self.used_period,
            "used_period_end": self.used_period_end,
            "reason": self.reason,
            "latest_filing": (
                self.latest_filing.summary() if self.latest_filing else None
            ),
        }


def check_filing_freshness(
    used_period_end: str | None,
    filings: list[FilingRecord],
    as_of_date: str,
    *,
    used_period: str | None = None,
) -> FreshnessVerdict:
    """Compare the period the analyst used against the latest known filing.

    ``used_period_end`` is the period end the fundamentals report actually
    leaned on (YYYY-MM-DD), ``filings`` the authoritative records known to
    the run, ``as_of_date`` the analysis date. Pure function: no network,
    no LLM, no per-ticker rules.
    """
    latest = latest_known_filing(filings, as_of_date)
    used_end = _parse(used_period_end)

    if latest is None:
        return FreshnessVerdict(
            status=FUNDAMENTALS_UNAVAILABLE,
            reason_code=FUNDAMENTALS_UNAVAILABLE,
            latest_known_period=None,
            latest_known_period_end=None,
            used_period=used_period,
            used_period_end=used_period_end,
            reason=(
                f"no authoritative filing is known as of {as_of_date}: "
                "fundamentals cannot be called current or verified"
            ),
        )

    if used_end is None:
        return FreshnessVerdict(
            status=FUNDAMENTALS_UNAVAILABLE,
            reason_code=FUNDAMENTALS_UNAVAILABLE,
            latest_known_period=latest.period,
            latest_known_period_end=latest.period_end,
            used_period=used_period,
            used_period_end=used_period_end,
            reason=(
                "the period the fundamentals report used is unknown or "
                "undated, so its freshness cannot be checked"
            ),
        )

    latest_end = _parse(latest.period_end)
    if latest_end is not None and used_end >= latest_end:
        return FreshnessVerdict(
            status=CURRENT,
            reason_code=FUNDAMENTALS_CURRENT,
            latest_known_period=latest.period,
            latest_known_period_end=latest.period_end,
            used_period=used_period,
            used_period_end=f"{used_end:%Y-%m-%d}",
            reason=(
                f"the used period ({used_end:%Y-%m-%d}) matches the latest "
                f"filing known at {as_of_date} ({latest.period}, ended "
                f"{latest.period_end})"
            ),
            latest_filing=latest,
        )

    return FreshnessVerdict(
        status=STALE_FUNDAMENTALS,
        reason_code=FUNDAMENTALS_STALE,
        latest_known_period=latest.period,
        latest_known_period_end=latest.period_end,
        used_period=used_period,
        used_period_end=f"{used_end:%Y-%m-%d}",
        reason=(
            f"the report uses the period ended {used_end:%Y-%m-%d} but a "
            f"later period ({latest.period}, ended {latest.period_end}) was "
            f"already known at {as_of_date}: an older quarter must not be "
            "presented as the current one"
        ),
        latest_filing=latest,
    )


# A period end appears in vendor output as an ISO date (2026-06-30) or as
# a quarter label (2026-Q2, Q2 2026). The regexes are structural: any
# ticker's report, no per-ticker rules.
_ISO_PERIOD_END = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_QUARTER_LABEL = re.compile(r"\b(\d{4})-Q([1-4])\b|\bQ([1-4])\s+(\d{4})\b")


def _quarter_end(year: int, quarter: int) -> str:
    """The calendar quarter end for a (year, quarter) pair."""
    end_month = {1: 3, 2: 6, 3: 9, 4: 12}[quarter]
    end_day = {3: 31, 6: 30, 9: 30, 12: 31}[end_month]
    return f"{year:04d}-{end_month:02d}-{end_day:02d}"


def used_period_end_from_report(report: str | None) -> str | None:
    """The period end a fundamentals report actually leaned on, or None.

    Reads the report text the run itself produced: the latest ISO date or
    quarter label it names as a period. Deterministic and conservative —
    an undatable report returns None, which the freshness gate treats as
    FUNDAMENTALS_UNAVAILABLE rather than guessing a period.
    """
    if not report:
        return None
    candidates: list[str] = []
    for match in _ISO_PERIOD_END.finditer(report):
        candidates.append(match.group(1))
    for match in _QUARTER_LABEL.finditer(report):
        if match.group(2):
            candidates.append(_quarter_end(int(match.group(1)), int(match.group(2))))
        else:
            candidates.append(_quarter_end(int(match.group(4)), int(match.group(3))))
    if not candidates:
        return None
    # The freshest period named is the one the report presents as current.
    return max(candidates)


def filings_from_sec_edgar(ticker: str, as_of_date: str) -> list[FilingRecord]:
    """Filing records from SEC EDGAR, as known at ``as_of_date`` (no look-ahead).

    Reads the filer's cached companyfacts and keeps, per fiscal period end,
    the earliest filing that reported it, with its form type and accession
    number. A period whose every filing is dated after ``as_of_date`` was
    not known then and is excluded. A ticker that is not a US filer, or an
    unreachable SEC, yields an empty list: the caller reports
    FUNDAMENTALS_UNAVAILABLE rather than inventing a filing.
    """
    from tradingagents.dataflows.vendors import sec_edgar

    try:
        cik = sec_edgar.cik_for(ticker)
        if cik is None:
            return []
        facts = sec_edgar._cached_json(
            sec_edgar._FACTS_URL.format(cik=cik), f"CIK{cik}.json"
        )
    except Exception:  # noqa: BLE001 — an unreachable SEC is UNAVAILABLE, not a crash
        return []

    us_gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    earliest: dict[str, dict] = {}   # period end -> earliest filing metadata
    for tag_data in us_gaap.values():
        for unit_values in (tag_data.get("units") or {}).values():
            for fact in unit_values:
                end, filed = fact.get("end"), fact.get("filed")
                if not end or not filed or str(filed) > as_of_date:
                    continue
                seen = earliest.get(end)
                if seen is None or str(filed) < seen["filed"]:
                    earliest[end] = {
                        "filed": str(filed),
                        "form": fact.get("form"),
                        "accn": fact.get("accn"),
                    }
    return [
        FilingRecord(
            period=end,
            period_end=end,
            published_date=None,
            filing_date=meta["filed"],
            form_type=meta["form"],
            accession_number=meta["accn"],
            source_type="sec_filing",
        )
        for end, meta in sorted(earliest.items())
    ]
